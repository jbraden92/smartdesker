import re
from io import BytesIO

import pandas as pd
import streamlit as st

# =========================
# Page config & styles
# =========================
st.set_page_config(page_title="SmartDesk — Desking Assistant (POC)", page_icon="📋", layout="wide")

st.markdown(
    """
    <style>
      .card {
        border-radius: 12px;
        padding: 14px 16px;
        border: 1px solid rgba(250,250,250,0.12);
        background: rgba(255,255,255,0.03);
        margin-bottom: 10px;
      }
      .metric {font-size: 22px; font-weight: 700; margin-bottom: 4px;}
      .em {opacity: 0.75}
      .ok {color:#7DD97C;font-weight:600}
      .warn {color:#F2C14E;font-weight:600}
      .bad {color:#EF6C6C;font-weight:600}
      .stMarkdown p {margin-bottom: 0.4rem;}
      .small {font-size: 0.9rem; opacity: 0.9}
    </style>
    """,
    unsafe_allow_html=True
)

# =========================
# Helpers
# =========================
def yn(v):
    if isinstance(v, str):
        return v.strip().lower() in ("y", "yes", "true", "1")
    if isinstance(v, (int, float)):
        return v == 1
    return bool(v)

def clean_num(x, default=None):
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)): return default
        s = str(x).strip().replace(",", "")
        if s == "": return default
        return float(s)
    except Exception:
        return default

def colget(df, name):
    cols = {c.lower().strip(): c for c in df.columns}
    return df[cols[name]] if name in cols else None

def pick_or_default(series, default):
    if series is None:
        return default
    return series

# =========================
# Rate sheet loader (CSV/XLSX)
# =========================
@st.cache_data(show_spinner=False)
def load_rate_sheet_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    if ext == ".csv":
        raw = pd.read_csv(BytesIO(data))
    else:
        raw = pd.read_excel(BytesIO(data))

    out = pd.DataFrame({
        "Lender": pick_or_default(colget(raw, "lender"), ""),
        "Program": pick_or_default(colget(raw, "program"), ""),
        "MinScore": pick_or_default(colget(raw, "minscore"), None),
        "MaxScore": pick_or_default(colget(raw, "maxscore"), None),
        "MaxRepos": pick_or_default(colget(raw, "maxrepos"), 99),
        "MinJobMonths": pick_or_default(colget(raw, "minjobmonths"), 0),
        "MinIncome": pick_or_default(colget(raw, "minincome"), 0),
        "MinDown": pick_or_default(colget(raw, "mindown"), 0),
        "MaxLTV": pick_or_default(colget(raw, "maxltv"), 999),
        "MaxMiles": pick_or_default(colget(raw, "maxmiles"), 999999),
        "MaxTerm": pick_or_default(colget(raw, "maxterm"), 84),
        "AllowGig": pick_or_default(colget(raw, "allowgig"), True),
        "AllowNoDL": pick_or_default(colget(raw, "allownodl"), False),
        "AllowFrame": pick_or_default(colget(raw, "allowframe"), False),
    })

    # normalize numeric + bool
    for c in ["MinScore","MaxScore","MaxRepos","MinJobMonths","MinIncome","MinDown","MaxLTV","MaxMiles","MaxTerm"]:
        out[c] = [None if c in ("MinScore","MaxScore") and (clean_num(v) is None) else clean_num(v, 0) for v in out[c]]

    out["AllowGig"] = [yn(v) for v in out["AllowGig"]]
    out["AllowNoDL"] = [yn(v) for v in out["AllowNoDL"]]
    out["AllowFrame"] = [yn(v) for v in out["AllowFrame"]]

    out = out[out["Lender"].astype(str).str.strip()!=""].reset_index(drop=True)
    return out

# =========================
# Default rules (pre-seed)
# =========================
DEFAULT_RULES = pd.DataFrame([
    {"Lender":"Gateway Financial Solutions","Program":"Standard",
     "MinScore":None,"MaxScore":750,"MaxRepos":2,"MinJobMonths":3,"MinIncome":1800,"MinDown":500,
     "MaxLTV":125,"MaxMiles":165000,"MaxTerm":75,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},

    {"Lender":"Exeter Finance","Program":"Standard",
     "MinScore":None,"MaxScore":740,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2000,"MinDown":500,
     "MaxLTV":125,"MaxMiles":165000,"MaxTerm":75,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},

    {"Lender":"CPS (AmeriCredit)","Program":"Standard",
     "MinScore":None,"MaxScore":740,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2100,"MinDown":500,
     "MaxLTV":125,"MaxMiles":165000,"MaxTerm":75,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},

    {"Lender":"Global Lending Services","Program":"Standard",
     "MinScore":580,"MaxScore":760,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2200,"MinDown":1000,
     "MaxLTV":125,"MaxMiles":160000,"MaxTerm":75,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},

    {"Lender":"Flagship Credit Acceptance","Program":"Standard",
     "MinScore":600,"MaxScore":760,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2400,"MinDown":1000,
     "MaxLTV":125,"MaxMiles":155000,"MaxTerm":75,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},

    {"Lender":"Regional Acceptance","Program":"Standard",
     "MinScore":590,"MaxScore":760,"MaxRepos":1,"MinJobMonths":12,"MinIncome":2500,"MinDown":1000,
     "MaxLTV":125,"MaxMiles":150000,"MaxTerm":72,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},

    {"Lender":"Prestige Financial","Program":"Standard",
     "MinScore":600,"MaxScore":760,"MaxRepos":0,"MinJobMonths":12,"MinIncome":2600,"MinDown":1000,
     "MaxLTV":120,"MaxMiles":150000,"MaxTerm":72,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},

    {"Lender":"Credit Acceptance","Program":"Standard",
     "MinScore":520,"MaxScore":700,"MaxRepos":99,"MinJobMonths":1,"MinIncome":1500,"MinDown":0,
     "MaxLTV":140,"MaxMiles":200000,"MaxTerm":72,"AllowGig":True,"AllowNoDL":True,"AllowFrame":False},

    {"Lender":"United Auto Credit","Program":"Standard",
     "MinScore":540,"MaxScore":720,"MaxRepos":2,"MinJobMonths":3,"MinIncome":1800,"MinDown":500,
     "MaxLTV":130,"MaxMiles":180000,"MaxTerm":75,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},

    {"Lender":"American Credit Acceptance (ACA)","Program":"Standard",
     "MinScore":560,"MaxScore":740,"MaxRepos":2,"MinJobMonths":3,"MinIncome":1900,"MinDown":500,
     "MaxLTV":130,"MaxMiles":175000,"MaxTerm":75,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},

    {"Lender":"Westlake Financial","Program":"Standard",
     "MinScore":560,"MaxScore":740,"MaxRepos":3,"MinJobMonths":3,"MinIncome":1800,"MinDown":0,
     "MaxLTV":140,"MaxMiles":200000,"MaxTerm":75,"AllowGig":True,"AllowNoDL":True,"AllowFrame":False},

    {"Lender":"Santander Consumer","Program":"Standard",
     "MinScore":580,"MaxScore":760,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2200,"MinDown":500,
     "MaxLTV":125,"MaxMiles":160000,"MaxTerm":75,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},

    {"Lender":"Kemba CU","Program":"Prime",
     "MinScore":640,"MaxScore":850,"MaxRepos":0,"MinJobMonths":12,"MinIncome":3000,"MinDown":1000,
     "MaxLTV":110,"MaxMiles":120000,"MaxTerm":72,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},

    {"Lender":"Ally","Program":"Prime",
     "MinScore":660,"MaxScore":850,"MaxRepos":0,"MinJobMonths":12,"MinIncome":3200,"MinDown":1000,
     "MaxLTV":110,"MaxMiles":100000,"MaxTerm":72,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},

    {"Lender":"Capital One Auto","Program":"Prime",
     "MinScore":660,"MaxScore":850,"MaxRepos":0,"MinJobMonths":12,"MinIncome":3200,"MinDown":0,
     "MaxLTV":115,"MaxMiles":120000,"MaxTerm":72,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},
])

if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_RULES.copy()

# =========================
# Hard-coded inventory (demo)
# Filters: TotalCost >= 4000; exclude Stock starting with W or T
# =========================
HARD_INVENTORY = pd.DataFrame([
    {"Stock":"A001","Year":2016,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93580,"TotalCost":9990,"BookValue":11800},
    {"Stock":"A002","Year":2017,"Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"TotalCost":10450,"BookValue":12200},
    {"Stock":"A003","Year":2014,"Make":"Toyota","Model":"Camry","Trim":"SE","Miles":128590,"TotalCost":8495,"BookValue":10250},
    {"Stock":"W100","Year":2016,"Make":"VW","Model":"Jetta","Trim":"S","Miles":98000,"TotalCost":3990,"BookValue":9100},   # filtered
    {"Stock":"T200","Year":2016,"Make":"Toyota","Model":"RAV4","Trim":"LE","Miles":99000,"TotalCost":13990,"BookValue":15800}, # filtered
    {"Stock":"A004","Year":2015,"Make":"Nissan","Model":"Altima","Trim":"2.5 S","Miles":119400,"TotalCost":7795,"BookValue":9300},
    {"Stock":"A005","Year":2014,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111200,"TotalCost":8995,"BookValue":10600},
    {"Stock":"B006","Year":2011,"Make":"Kia","Model":"Soul","Trim":"Base","Miles":171500,"TotalCost":3390,"BookValue":4200},   # filtered
    {"Stock":"A007","Year":2018,"Make":"Hyundai","Model":"Elantra","Trim":"SE","Miles":88500,"TotalCost":10990,"BookValue":12500},
    {"Stock":"A008","Year":2013,"Make":"Honda","Model":"CR-V","Trim":"EX","Miles":142000,"TotalCost":9990,"BookValue":11750},
])

def normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    mapping_candidates = {
        "Stock": ["stock","stk","stocknumber","stock_no","stock#"],
        "Year": ["year","yr"],
        "Make": ["make"],
        "Model": ["model"],
        "Trim": ["trim"],
        "Miles": ["miles","odometer","odo"],
        "TotalCost": ["totalcost","price","saleprice","cost","outthedoor","otd"],
        "BookValue": ["bookvalue","nada","kbb","bb","wholesale","retailbook"],
    }
    out = pd.DataFrame()
    lower_cols = {c.lower().strip(): c for c in df.columns}
    for key, aliases in mapping_candidates.items():
        found = None
        for a in [key.lower()] + aliases:
            if a in lower_cols: found = lower_cols[a]; break
        if found is None:
            if key in ("Trim",): out[key] = ""
            else: out[key] = None
        else:
            out[key] = df[found]

    for c in ["Year","Miles","TotalCost","BookValue"]:
        out[c] = [clean_num(v, 0) for v in out[c]]

    out["Stock"] = out["Stock"].astype(str)

    mask_price = out["TotalCost"] >= 4000
    mask_stock = ~out["Stock"].str.upper().str.startswith(tuple(["W","T"]))
    out = out[mask_price & mask_stock].reset_index(drop=True)

    out = out[out["Make"].astype(str).str.strip()!=""].reset_index(drop=True)
    out["BookSpread"] = out["BookValue"] - out["TotalCost"]
    return out

# =========================
# Lender gating & scoring
# =========================
def gates_ok(row, features, unit):
    cred = features["credit"]
    income = features["income"]
    job = features["job_months"]
    repos = features["repos"]
    down = features["down"]
    has_dl = features["has_dl"]
    gig = features["gig"]
    gig_income = features["gig_income"]
    term = features["desired_term"]

    # NOTE: use pd.notna for score bounds so NaN acts as "no bound"
    if pd.notna(row["MinScore"]) and cred < float(row["MinScore"]): return (False, "Below min score")
    if pd.notna(row["MaxScore"]) and cred > float(row["MaxScore"]): return (False, "Above max score")

    if repos > float(row["MaxRepos"]): return (False, "Too many repos")
    if job < float(row["MinJobMonths"]): return (False, "Not enough job time")
    if income + (gig_income if gig else 0) < float(row["MinIncome"]): return (False, "Not enough income")
    if down < float(row["MinDown"]): return (False, "Needs more down")
    if not bool(row["AllowNoDL"]) and has_dl == "No": return (False, "DL required")
    if not bool(row["AllowGig"]) and gig and gig_income > 0: return (False, "Gig income not allowed")

    if unit is not None:
        if unit["Miles"] > float(row["MaxMiles"]): return (False, "Miles over program limit")
        if term > float(row["MaxTerm"]): return (False, "Term over program max")

        bv = max(unit["BookValue"], 1.0)
        advance = max(0.0, (unit["TotalCost"] - down - features["trade_eq"]) / bv * 100.0)
        if advance > float(row["MaxLTV"]): return (False, f"Advance {advance:.0f}% > max {row['MaxLTV']:.0f}%")

    return (True, "Meets program")

def lender_fit_score(row, features):
    cred = features["credit"]
    income = features["income"] + (features["gig_income"] if features["gig"] else 0)
    down = features["down"]
    job = features["job_months"]

    score = 0.0
    if pd.isna(row["MinScore"]) and pd.isna(row["MaxScore"]):
        score += 50
    else:
        lo = 0 if pd.isna(row["MinScore"]) else float(row["MinScore"])
        hi = 850 if pd.isna(row["MaxScore"]) else float(row["MaxScore"])
        mid = (lo + hi) / 2.0
        score += max(0.0, 100.0 - abs(cred - mid) * 0.4)

    score += min(1000.0, down) / 25.0
    score += min(5000.0, income) / 50.0
    score += min(120.0, job) / 4.0
    score += 12.0 if (features["has_dl"] == "Yes") else 0.0
    score += 8.0 if (features["gig"] and bool(row["AllowGig"])) else 0.0
    return round(score, 1)

def unit_fit_score(row, unit, features):
    bv = max(unit["BookValue"], 1.0)
    advance = max(0.0, (unit["TotalCost"] - features["down"] - features["trade_eq"]) / bv * 100.0)
    over = max(0.0, advance - float(row["MaxLTV"]))
    adv_score = max(0.0, 80.0 - over * 2.0)

    mile_over = max(0.0, unit["Miles"] - float(row["MaxMiles"]))
    miles_score = max(0.0, 50.0 - mile_over / 3000.0)

    spread_score = max(0.0, min(40.0, (unit["BookValue"] - unit["TotalCost"]) / 200.0))

    price = unit["TotalCost"]
    price_score = max(0.0, 30.0 - abs(price - 11000.0) / 700.0)

    score = adv_score + miles_score + spread_score + price_score
    return round(score, 1), advance

def top_lenders(rules_df, features, topn=5):
    rows = []
    for _, r in rules_df.iterrows():
        ok, why = gates_ok(r, features, None)
        if ok:
            s = lender_fit_score(r, features)
            rows.append({"Lender": r["Lender"], "Program": r["Program"], "Reason": why, "Score": s})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("Score", ascending=False).head(topn).reset_index(drop=True)

def best_units(inventory_df, rules_df, features, topn=5):
    results = []
    for _, unit in inventory_df.iterrows():
        best = None
        best_row = None
        best_adv = None
        for _, r in rules_df.iterrows():
            ok, _ = gates_ok(r, features, unit)
            if not ok:
                continue
            s, adv = unit_fit_score(r, unit, features)
            if (best is None) or (s > best):
                best = s
                best_row = r
                best_adv = adv
        if best is not None:
            results.append({
                "Stock": unit["Stock"],
                "Vehicle": f"{int(unit['Year'])} {unit['Make']} {unit['Model']} {str(unit['Trim']) if unit['Trim'] else ''}".strip(),
                "Miles": int(unit["Miles"]),
                "TotalCost": int(unit["TotalCost"]),
                "BookValue": int(unit["BookValue"]),
                "Advance%": round(best_adv, 1),
                "Lender": best_row["Lender"],
                "Program": best_row["Program"],
                "UnitScore": round(best,1),
                "BookSpread": int(unit["BookValue"] - unit["TotalCost"]),
            })
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    return df.sort_values(["UnitScore","BookSpread"], ascending=[False, False]).head(topn).reset_index(drop=True)

# =========================
# UI — Header
# =========================
st.title("SmartDesk — Desking Assistant (POC)")
st.caption("Upload a rate sheet + (optional) inventory. Enter basics. Get lender + Top 5 units.")

with st.expander("What files look like"):
    st.markdown(
        """
        **Rate sheet columns (case-insensitive):**  
        `Lender, Program, MinScore, MaxScore, MaxRepos, MinJobMonths, MinIncome, MinDown, MaxLTV, MaxMiles, MaxTerm, AllowGig, AllowNoDL, AllowFrame`

        **Inventory columns (case-insensitive):**  
        `Stock, Year, Make, Model, Trim, Miles, TotalCost, BookValue`

        **Built-in filters (always applied):**  
        - Exclude units with **TotalCost < $4,000**  
        - Exclude units with **Stock beginning with W or T**  
        """
    )

# =========================
# Inputs
# =========================
col_left, col_right = st.columns([1.2, 1])

with col_left:
    st.subheader("Deal Input")

    with st.form("deal_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            credit = st.number_input("Credit Score", 300, 850, 620, 1)
            income = st.number_input("Monthly Income ($/mo)", 0, 30000, 3000, 50)
            gig_flag = st.checkbox("Gig / DoorDash income?")
            gig_income = st.number_input("Gig Income ($/mo)", 0, 15000, 0, 50)

        with c2:
            repos = st.number_input("of Repos (reported)", 0, 10, 0, 1)
            has_dl = st.selectbox("Driver's License?", ["Yes","No"])
            down = st.number_input("Down Payment ($)", 0, 30000, 1000, 50)

        with c3:
            trade_eq = st.number_input("Trade Equity ($)", -20000, 20000, 0, 100)
            job_years = st.number_input("Job Time (years)", 0, 50, 0, 1)
            job_months_extra = st.number_input("Job Time (months)", 0, 11, 6, 1)

        # Removed Desired Term input; we use a sensible default below

        include_co = st.checkbox("Include Co-Applicant?")
        if include_co:
            co_cols = st.columns(2)
            with co_cols[0]:
                co_score = st.number_input("Co-Applicant Score", 300, 850, 600, 1)
            with co_cols[1]:
                co_income = st.number_input("Co-Applicant Income ($/mo)", 0, 30000, 0, 50)
        else:
            co_score = None
            co_income = 0

        submitted = st.form_submit_button("Evaluate Deal", type="primary")

with col_right:
    st.subheader("Uploads")

    # Rate sheet upload
    rs_file = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"], key="rsup")
    if rs_file is not None:
        try:
            ext = ".csv" if rs_file.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["rate_rules"] = load_rate_sheet_from_bytes(rs_file.read(), ext)
            st.success(f"Loaded {len(st.session_state['rate_rules'])} rows from **{rs_file.name}**.")
        except Exception as e:
            st.error(f"Rate sheet load error: {e}")

    # Inventory upload
    inv_file = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"], key="invup")
    if inv_file is not None:
        try:
            ext = ".csv" if inv_file.name.lower().endswith(".csv") else ".xlsx"
            raw = pd.read_csv(inv_file) if ext==".csv" else pd.read_excel(inv_file)
            INV = normalize_inventory(raw)
            st.success(f"Loaded inventory: {len(INV)} units after filters.")
        except Exception as e:
            st.error(f"Inventory load error: {e}")
            INV = normalize_inventory(HARD_INVENTORY.copy())
    else:
        # use built-in
        INV = normalize_inventory(HARD_INVENTORY.copy())

    with st.expander("Current Rate Rules (top 20)"):
        st.dataframe(st.session_state["rate_rules"].head(20), use_container_width=True)

# =========================
# Ask a lender rule (simple search)
# =========================
st.subheader("Ask about a lender rule")
q = st.text_input("Example: Does Exeter allow frame damage? or Gateway gig income?")
if q.strip():
    qlow = q.strip().lower()
    mask = st.session_state["rate_rules"].apply(
        lambda r: any(qlow in str(v).lower() for v in r.values), axis=1
    )
    hits = st.session_state["rate_rules"][mask].copy()
    if hits.empty:
        st.info("No direct matches in current rule table.")
    else:
        st.dataframe(hits, use_container_width=True)

# =========================
# Evaluate
# =========================
if submitted:
    # Default desired term to 60 months (no input)
    DEFAULT_TERM = 60

    features = {
        "credit": int(credit),
        "income": float(income) + (float(co_income) if include_co else 0.0),
        "job_months": int(job_years)*12 + int(job_months_extra),
        "repos": int(repos),
        "down": float(down),
        "trade_eq": float(trade_eq),
        "gig": bool(gig_flag),
        "gig_income": float(gig_income),
        "has_dl": has_dl,
        "desired_term": DEFAULT_TERM,
        "co_score": None if co_score is None else int(co_score),
        "co_income": float(co_income),
    }

    rules = st.session_state["rate_rules"].copy()

    top_l = top_lenders(rules, features, topn=5)
    best_u = best_units(INV, rules, features, topn=5)

    cols = st.columns(2)

    with cols[0]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="metric">Top Lender Matches</div>', unsafe_allow_html=True)
        if top_l.empty:
            st.warning("No lender fits with the current customer inputs.")
        else:
            st.dataframe(top_l, use_container_width=True, height=220)
        st.markdown('</div>', unsafe_allow_html=True)

    with cols[1]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="metric">Top 5 Units (best lender–unit pairs)</div>', unsafe_allow_html=True)
        if best_u.empty:
            st.warning("No units fit with any lender using these rules & filters.")
        else:
            show_cols = ["Stock","Vehicle","Miles","TotalCost","BookValue","BookSpread","Advance%","Lender","Program","UnitScore"]
            st.dataframe(best_u[show_cols], use_container_width=True, height=260)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("### Deal Snapshot")
    snapshot = {
        "Primary Applicant": {
            "Credit Score": features["credit"],
            "Monthly Income": income,
            "Job Months": features["job_months"],
            "Repos": features["repos"],
            "Driver's License": features["has_dl"],
        },
        "Structure": {
            "Down Payment": features["down"],
            "Trade Equity": features["trade_eq"],
            "Gig Income": features["gig_income"] if features["gig"] else 0,
            "Desired Term": DEFAULT_TERM
        },
        "Co-Applicant": {
            "Included": include_co,
            "Co Score": features["co_score"],
            "Co Income": features["co_income"],
        },
        "Notes": "Inventory filtered: TotalCost >= $4,000 and Stock NOT starting with W or T. LTV/Advance, MaxTerm, MaxMiles enforced per lender."
    }
    st.json(snapshot, expanded=False)

else:
    st.info("Fill out the form and click **Evaluate Deal**. (Inventory defaults to a built-in sample list if you don’t upload one.)")
