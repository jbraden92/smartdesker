import streamlit as st
import pandas as pd
from io import BytesIO
import math
import re

# --------------------------
# Page setup & light styling
# --------------------------
st.set_page_config(page_title="SmartDesk — Desking Assistant (POC)", page_icon="📋", layout="wide")
st.markdown(
    """
    <style>
    .card {border-radius:12px; padding:14px 16px; border:1px solid rgba(250,250,250,0.1); background:rgba(250,250,250,0.03);}
    .metric {font-size:20px; font-weight:700; margin-bottom:6px}
    .muted {opacity:.72}
    .good {color:#7AD17A; font-weight:600}
    .warn {color:#E3C252; font-weight:600}
    .bad  {color:#EC6A6A; font-weight:600}
    </style>
    """,
    unsafe_allow_html=True
)

st.title("SmartDesk — Desking Assistant (POC)")
st.caption("Upload rate sheets (optional), enter basics, and I’ll rank lenders + show the best 5 unit matches. "
           "For this POC we prioritize **Gateway** and price units at each lender’s **max allowed advance**.")

# --------------------------
# Helpers
# --------------------------
def yn(val) -> bool:
    if isinstance(val, str):
        return val.strip().lower() in ("y", "yes", "true", "1")
    if isinstance(val, (int, float)):
        return val == 1
    return bool(val)

def clean_float(x, default=0.0):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)) or x == "":
            return float(default)
        return float(x)
    except Exception:
        return float(default)

def pct(x):
    try:
        return float(x)
    except:
        return 0.0

# --------------------------
# Default Lender Rules
# --------------------------
DEFAULT_RULES = pd.DataFrame([
    # Gateway POC — favor when ties
    {"Lender":"Gateway Financial Solutions","Program":"Near/Sub",
     "MinScore":None,"MaxScore":850,"MaxRepos":2,
     "MinJobMonths":3,"MinIncome":1800,"MinDown":500,
     "AllowGig":True,"AllowNoDL":False,"AllowFrame":False,
     "MaxMiles":150000,"MaxTerm":72,"AdvanceCap":1.24},

    {"Lender":"Exeter","Program":"Near/Sub",
     "MinScore":550,"MaxScore":700,"MaxRepos":2,
     "MinJobMonths":6,"MinIncome":2000,"MinDown":500,
     "AllowGig":True,"AllowNoDL":False,"AllowFrame":False,
     "MaxMiles":160000,"MaxTerm":72,"AdvanceCap":1.15},

    {"Lender":"CPS","Program":"Near/Sub",
     "MinScore":560,"MaxScore":720,"MaxRepos":2,
     "MinJobMonths":6,"MinIncome":2200,"MinDown":500,
     "AllowGig":True,"AllowNoDL":False,"AllowFrame":False,
     "MaxMiles":160000,"MaxTerm":72,"AdvanceCap":1.24},

    {"Lender":"Prestige","Program":"Near/Sub",
     "MinScore":600,"MaxScore":750,"MaxRepos":0,
     "MinJobMonths":12,"MinIncome":2600,"MinDown":1000,
     "AllowGig":False,"AllowNoDL":False,"AllowFrame":False,
     "MaxMiles":140000,"MaxTerm":75,"AdvanceCap":1.15},

    {"Lender":"Regional Acceptance","Program":"Near/Sub",
     "MinScore":590,"MaxScore":720,"MaxRepos":1,
     "MinJobMonths":12,"MinIncome":2500,"MinDown":1000,
     "AllowGig":False,"AllowNoDL":False,"AllowFrame":False,
     "MaxMiles":140000,"MaxTerm":72,"AdvanceCap":1.15},

    {"Lender":"Flagship Credit","Program":"Near/Sub",
     "MinScore":600,"MaxScore":750,"MaxRepos":2,
     "MinJobMonths":6,"MinIncome":2400,"MinDown":1000,
     "AllowGig":True,"AllowNoDL":False,"AllowFrame":True,
     "MaxMiles":160000,"MaxTerm":75,"AdvanceCap":1.24},

    {"Lender":"Kemba CU","Program":"Prime/CU",
     "MinScore":640,"MaxScore":850,"MaxRepos":0,
     "MinJobMonths":12,"MinIncome":3000,"MinDown":1000,
     "AllowGig":False,"AllowNoDL":False,"AllowFrame":False,
     "MaxMiles":120000,"MaxTerm":84,"AdvanceCap":1.15},
])

# --------------------------
# Load rate sheet (CSV/XLSX)
# --------------------------
@st.cache_data(show_spinner=False)
def load_rate_sheet(data: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(data)) if ext == ".csv" else pd.read_excel(BytesIO(data))
    # Normalize headers
    lower = {c.lower().strip(): c for c in df.columns}

    def col(name, default=None):
        if name in lower: return df[lower[name]]
        return [default]*len(df)

    out = pd.DataFrame({
        "Lender": col("lender",""),
        "Program": col("program","Near/Sub"),
        "MinScore": [None if str(x).strip().lower() in ("", "none", "nan") else clean_float(x, None) for x in col("minscore", None)],
        "MaxScore": [None if str(x).strip().lower() in ("", "none", "nan") else clean_float(x, None) for x in col("maxscore", None)],
        "MaxRepos": [int(clean_float(x, 99)) for x in col("maxrepos", 99)],
        "MinJobMonths": [int(clean_float(x, 0)) for x in col("minjobmonths", 0)],
        "MinIncome": [clean_float(x, 0) for x in col("minincome", 0)],
        "MinDown": [clean_float(x, 0) for x in col("mindown", 0)],
        "AllowGig": [yn(x) for x in col("allowgig", True)],
        "AllowNoDL": [yn(x) for x in col("allownodl", False)],
        "AllowFrame": [yn(x) for x in col("allowframe", False)],
        "MaxMiles": [int(clean_float(x, 999999)) for x in col("maxmiles", 999999)],
        "MaxTerm": [int(clean_float(x, 84)) for x in col("maxterm", 84)],
        "AdvanceCap": [pct(x) for x in col("advancecap", 1.24)],
    })
    out = out[out["Lender"].astype(str).str.strip()!=""].reset_index(drop=True)
    return out

# Active rules in session
if "RULES" not in st.session_state:
    st.session_state["RULES"] = DEFAULT_RULES.copy()

# --------------------------
# Hard inventory (you can extend)
# total cost is Price (cost) for this POC; add other costs if needed.
# Filters: remove TotalCost < 4000, and Stock starting with W or T
# --------------------------
HARD_INVENTORY = pd.DataFrame([
    {"Stock":"A001","Year":2016,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93500,"TotalCost":9990,"BookValue":11800},
    {"Stock":"A002","Year":2017,"Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"TotalCost":10450,"BookValue":12200},
    {"Stock":"A007","Year":2018,"Make":"Hyundai","Model":"Elantra","Trim":"SEL","Miles":84500,"TotalCost":9890,"BookValue":10990},
    {"Stock":"A008","Year":2019,"Make":"Nissan","Model":"Versa","Trim":"SV","Miles":61200,"TotalCost":9490,"BookValue":9995},
    {"Stock":"X005","Year":2010,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111200,"TotalCost":8995,"BookValue":10600}, # excluded (X ok)
    {"Stock":"T200","Year":2016,"Make":"Toyota","Model":"RAV4","Trim":"LE","Miles":99000,"TotalCost":13990,"BookValue":15800},      # excluded (T*)
    {"Stock":"W100","Year":2014,"Make":"VW","Model":"Jetta","Trim":"S","Miles":98000,"TotalCost":7990,"BookValue":9100},           # excluded (W*)
    {"Stock":"B006","Year":2011,"Make":"Kia","Model":"Soul","Trim":"Base","Miles":171500,"TotalCost":3390,"BookValue":4200},      # excluded < 4k
])

def normalized_inventory(inv: pd.DataFrame) -> pd.DataFrame:
    df = inv.copy()
    # Basic cleanup
    for col in ["Miles","TotalCost","BookValue","Year"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Stock"] = df["Stock"].astype(str)

    # Apply filters
    df = df[df["TotalCost"] >= 4000]
    df = df[~df["Stock"].str.upper().str.startswith("W")]
    df = df[~df["Stock"].str.upper().str.startswith("T")]
    df = df.reset_index(drop=True)
    return df

# --------------------------
# Inputs
# --------------------------
left, right = st.columns([1.4, 1])
with left:
    with st.form("deal"):
        c1, c2, c3 = st.columns(3)
        with c1:
            credit = st.number_input("Credit Score", 300, 850, 620, 1)
            job_years = st.number_input("Job Time (years)", 0, 50, 1, 1)
        with c2:
            repos = st.number_input("# of Repos (reported)", 0, 10, 0, 1)
            has_dl = st.selectbox("Driver's License?", ["Yes", "No"])
        with c3:
            trade_eq = st.number_input("Trade Equity ($)", -20000, 20000, 0, 100)
            down = st.number_input("Down Payment ($)", 0, 30000, 1000, 50)

        c4, c5 = st.columns(2)
        with c4:
            income = st.number_input("Monthly Income ($/mo)", 0, 50000, 3000, 50)
        with c5:
            gig_flag = st.checkbox("Gig / DoorDash income?")
            gig_income = st.number_input("Gig Income ($/mo)", 0, 20000, 0, 50)

        include_co = st.checkbox("Include Co-Applicant?")
        if include_co:
            co1, co2 = st.columns(2)
            with co1:
                co_score = st.number_input("Co-Applicant Score", 300, 850, 600, 1)
            with co2:
                co_income = st.number_input("Co-Applicant Income ($/mo)", 0, 20000, 0, 50)
        else:
            co_score, co_income = None, 0

        submitted = st.form_submit_button("Evaluate Deal", type="primary")

with right:
    st.subheader("Uploads")
    rs = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"])
    if rs is not None:
        try:
            ext = ".csv" if rs.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["RULES"] = load_rate_sheet(rs.read(), ext)
            st.success(f"Loaded {len(st.session_state['RULES'])} lenders from **{rs.name}**.")
        except Exception as e:
            st.error(f"Could not read rate sheet: {e}")

    inv_file = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"])
    if inv_file is not None:
        try:
            inv_ext = ".csv" if inv_file.name.lower().endswith(".csv") else ".xlsx"
            inv_df = pd.read_csv(inv_file) if inv_ext == ".csv" else pd.read_excel(inv_file)
            st.session_state["INV"] = normalized_inventory(inv_df)
            st.success(f"Loaded {len(st.session_state['INV'])} inventory rows from **{inv_file.name}**.")
        except Exception as e:
            st.error(f"Could not read inventory: {e}")

    with st.expander("Current Rate Rules (top 20)"):
        st.dataframe(st.session_state["RULES"].head(20), use_container_width=True, height=300)

# Fallbacks
if "INV" not in st.session_state:
    st.session_state["INV"] = normalized_inventory(HARD_INVENTORY)

# --------------------------
# Lender gates & scoring
# --------------------------
def gates_ok(rule_row, f) -> (bool, str):
    """Hard approval gates."""
    # credit window
    min_s = rule_row["MinScore"]
    max_s = rule_row["MaxScore"]
    if min_s is not None and f["credit"] < min_s:     return False, "Score below lender minimum"
    if max_s is not None and f["credit"] > max_s:     return False, "Score above lender maximum"

    if f["repos"] > int(rule_row["MaxRepos"]):         return False, "Too many repos"
    if f["job_months"] < int(rule_row["MinJobMonths"]):return False, "Not enough job time"
    if f["income_total"] < float(rule_row["MinIncome"]):return False, "Income too low"
    if f["down"] < float(rule_row["MinDown"]):          return False, "Needs more down"
    if (not rule_row["AllowNoDL"]) and f["has_dl"]=="No": return False, "DL required"
    if (not rule_row["AllowGig"]) and f["gig"] and f["gig_income"]>0: return False, "Gig income not allowed"
    return True, "Meets program"

def rank_score(rule_row, f) -> float:
    """Soft score to rank eligible lenders."""
    score = 0.0
    # favor mid-window credit if a window exists
    min_s, max_s = rule_row["MinScore"], rule_row["MaxScore"]
    if min_s is not None and max_s is not None:
        mid = (min_s + max_s) / 2.0
        score += max(0, 100 - abs(f["credit"] - mid) * 0.5)
    else:
        score += 75  # no window → neutral bump (e.g., Gateway no min score)

    score += min(1200, f["down"]) / 30.0
    score += min(5000, f["income_total"]) / 50.0
    if f["gig"] and rule_row["AllowGig"]: score += 10
    if f["has_dl"]=="Yes": score += 8

    # Gateway priority nudge
    if str(rule_row["Lender"]).strip().lower().startswith("gateway"):
        score += 25
    return round(score, 2)

def price_for_lender(unit_row, rule_row) -> float:
    """Price the unit at lender's max allowed advance, capped by miles (if outside window apply a penalty)."""
    book = float(unit_row["BookValue"])
    cap  = float(rule_row["AdvanceCap"])
    price = book * cap

    # miles impact: if above max miles, knock price down slightly (still allow if other gates pass)
    if unit_row["Miles"] > int(rule_row["MaxMiles"]):
        price *= 0.98  # tiny penalty
    return round(price, 2)

# --------------------------
# Evaluate
# --------------------------
if submitted:
    features = {
        "credit": credit,
        "repos": repos,
        "job_months": job_years * 12 + 6,  # include the 6 months default from “Job Time (months)”
        "income_total": income + (gig_income if gig_flag else 0) + co_income,
        "down": down,
        "trade_eq": trade_eq,
        "gig": bool(gig_flag),
        "gig_income": gig_income if gig_flag else 0,
        "has_dl": has_dl,
        "co_score": co_score,
        "co_income": co_income
    }

    rules = st.session_state["RULES"].copy()
    inv   = st.session_state["INV"].copy()

    # Lender ranking (without unit yet)
    lender_rows = []
    for _, r in rules.iterrows():
        ok, why = gates_ok(r, features)
        s = rank_score(r, features) if ok else 0.0
        lender_rows.append({
            "Lender": r["Lender"],
            "Program": r["Program"],
            "Eligible": ok,
            "Reason": why,
            "Score": s,
            "AdvanceCap": r["AdvanceCap"],
            "MaxMiles": r["MaxMiles"]
        })
    lender_df = pd.DataFrame(lender_rows).sort_values(["Eligible","Score"], ascending=[False, False]).reset_index(drop=True)

    st.subheader("Top Lender Matches")
    if lender_df[lender_df["Eligible"]].empty:
        st.info("No lender fits with the current customer inputs.")
    else:
        st.dataframe(lender_df[["Lender","Program","Score","Reason"]], use_container_width=True, height=260)

    # Best 5 unit–lender pairs (choose lender-specific max price)
    best_pairs = []
    for _, unit in inv.iterrows():
        for _, r in rules.iterrows():
            ok, _ = gates_ok(r, features)
            if not ok:
                continue
            # unit side checks (miles only for now; frame/title could be added with columns later)
            # miles allowed? If not, let it pass with reduced FitScore
            miles_ok = unit["Miles"] <= int(r["MaxMiles"])
            target_price = price_for_lender(unit, r)
            fit = rank_score(r, features)
            if not miles_ok:
                fit *= 0.85

            best_pairs.append({
                "Stock": unit["Stock"],
                "Unit": f"{int(unit['Year'])} {unit['Make']} {unit['Model']} {unit['Trim']}",
                "Miles": int(unit["Miles"]),
                "Book": float(unit["BookValue"]),
                "Price": target_price,             # lender-max price
                "Advance%": round((target_price / max(1.0, unit["BookValue"])) * 100.0, 1),
                "Lender": r["Lender"],
                "Program": r["Program"],
                "FitScore": fit
            })

    st.subheader("Top 5 Units (best lender–unit pairs)")
    if not best_pairs:
        st.info("No units fit with any lender using these rules & filters.")
    else:
        out = pd.DataFrame(best_pairs).sort_values(["FitScore","Lender"], ascending=[False, True]).head(5).reset_index(drop=True)
        # Prefer Gateway on ties by sorting second key = Lender ascending (Gateway first alphabetically in our list)
        st.dataframe(out[["Stock","Unit","Miles","Price","Book","Advance%","Lender","Program","FitScore"]],
                     use_container_width=True, height=260)

# --------------------------
# Ask about a lender rule
# --------------------------
st.subheader("Ask about a lender rule")
q = st.text_input("Example: Does Exeter allow frame damage? or Gateway gig income?")
if q:
    pat = re.compile(re.escape(q), re.IGNORECASE)
    text_table = st.session_state["RULES"].astype(str)
    mask = text_table.apply(lambda s: s.str.contains(pat), axis=1).any(axis=1)
    hits = st.session_state["RULES"][mask]
    if hits.empty:
        st.info("No direct hits in the current rules. Try a shorter phrase (e.g., 'frame', 'gig', 'Gateway').")
    else:
        st.success(f"Found {len(hits)} matching row(s) in the rules:")
        st.dataframe(hits, use_container_width=True)

# --------------------------
# Reminder (no back-end products in math)
# --------------------------
st.markdown(
    '<div class="muted">Reminder only — products are NOT included in advance math for this POC.</div>',
    unsafe_allow_html=True
)
