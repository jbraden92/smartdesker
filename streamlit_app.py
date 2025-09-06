# streamlit_app.py
# Requirements:
#   streamlit
#   pandas
#   numpy
#   openpyxl
#   pdfplumber

import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import re

# Optional PDF parsing
try:
    import pdfplumber
except Exception:
    pdfplumber = None

# =========================
# Page config / styles
# =========================
st.set_page_config(page_title="SmartDesk — Desking Assistant", page_icon="📋", layout="wide")
st.markdown(
    """
    <style>
      .card {border-radius:10px;padding:14px 16px;border:1px solid rgba(250,250,250,.12);background:rgba(250,250,250,.03)}
      .metric {font-size:26px;font-weight:700;margin-bottom:4px}
      .em {opacity:.7}
      .ok {color:#7DD97C}
      .warn {color:#F2C14E}
      .bad {color:#EF6C6C}
      .tight p {margin:0}
    </style>
    """,
    unsafe_allow_html=True
)

# =======================================
# Small helpers
# =======================================
def _to_bool(x, default=False):
    if isinstance(x, str):
        return x.strip().lower() in ("y", "yes", "true", "1")
    if isinstance(x, (int, float, np.integer, np.floating)):
        return bool(x)
    return default

def _num(x, default=None):
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)) or (isinstance(x, str) and x.strip()==""):
            return default
        return float(x)
    except Exception:
        return default

def _safe_int(x, default=0):
    n = _num(x, None)
    return int(round(n)) if n is not None else default

# =======================================
# Default (sample/POC) lender programs
# NOTE: These are POC defaults (not official rate cards).
# =======================================
DEFAULT_RULES = pd.DataFrame([
    {"Lender":"Gateway Financial Solutions","Program":"Near/Sub","MinScore":None,"MaxScore":700,"MaxRepos":2,"MinIncome":2000,"MinDown":500,"MaxTerm":72,"MaxMiles":160000,"MaxLTV":130,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Global Lending Services","Program":"Near/Sub","MinScore":580,"MaxScore":720,"MaxRepos":2,"MinIncome":2200,"MinDown":1000,"MaxTerm":75,"MaxMiles":150000,"MaxLTV":135,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Flagship Credit","Program":"Near/Sub","MinScore":600,"MaxScore":750,"MaxRepos":2,"MinIncome":2400,"MinDown":1000,"MaxTerm":75,"MaxMiles":155000,"MaxLTV":125,"AllowGig":True,"AllowNoDL":False,"AllowFrame":True},
    {"Lender":"Regional Acceptance","Program":"Near/Sub","MinScore":590,"MaxScore":720,"MaxRepos":1,"MinIncome":2500,"MinDown":1000,"MaxTerm":72,"MaxMiles":140000,"MaxLTV":125,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Prestige","Program":"Near/Sub","MinScore":600,"MaxScore":750,"MaxRepos":0,"MinIncome":2600,"MinDown":1000,"MaxTerm":72,"MaxMiles":140000,"MaxLTV":120,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Exeter","Program":"Near/Sub","MinScore":550,"MaxScore":700,"MaxRepos":2,"MinIncome":2000,"MinDown":500,"MaxTerm":72,"MaxMiles":160000,"MaxLTV":135,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Kemba CU","Program":"Prime/CU","MinScore":640,"MaxScore":850,"MaxRepos":0,"MinIncome":3000,"MinDown":1000,"MaxTerm":84,"MaxMiles":120000,"MaxLTV":115,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},
])

# =======================================
# Hard-wired inventory (POC)
# - Filter rules: TotalCost >= $4,000
# - Exclude Stock starting with W or T
# =======================================
HARD_INVENTORY = pd.DataFrame([
    {"Stock":"A001","Year":2016,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93500,"TotalCost":9990,"BookValue":11800},
    {"Stock":"A002","Year":2017,"Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"TotalCost":10450,"BookValue":12200},
    {"Stock":"A003","Year":2014,"Make":"Toyota","Model":"Camry","Trim":"SE","Miles":128500,"TotalCost":8495,"BookValue":10250},
    {"Stock":"A004","Year":2015,"Make":"Nissan","Model":"Altima","Trim":"2.5 S","Miles":119400,"TotalCost":7795,"BookValue":9300},
    {"Stock":"X005","Year":2010,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111200,"TotalCost":8995,"BookValue":10600},  # excluded by stock prefix rule
    {"Stock":"W100","Year":2016,"Make":"Volkswagen","Model":"Jetta","Trim":"S","Miles":98800,"TotalCost":7990,"BookValue":9100},   # excluded by stock prefix rule
    {"Stock":"T200","Year":2016,"Make":"Toyota","Model":"RAV4","Trim":"LE","Miles":99000,"TotalCost":13990,"BookValue":15800},   # excluded by stock prefix rule
    {"Stock":"B006","Year":2011,"Make":"Kia","Model":"Soul","Trim":"Base","Miles":171500,"TotalCost":3390,"BookValue":4200},     # excluded by price
    {"Stock":"A007","Year":2018,"Make":"Hyundai","Model":"Elantra","Trim":"SEL","Miles":84500,"TotalCost":10990,"BookValue":12500},
    {"Stock":"A008","Year":2019,"Make":"Nissan","Model":"Versa","Trim":"SV","Miles":61200,"TotalCost":9995,"BookValue":11200},
])

# =======================================
# Parse uploaded rate sheet (CSV/XLSX) -> normalized table
# =======================================
@st.cache_data(show_spinner=False)
def load_rate_sheet_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(data)) if ext == ".csv" else pd.read_excel(BytesIO(data))
    # Lower-map
    low = {c.lower().strip(): c for c in df.columns}
    def col(name, default=None):
        c = low.get(name)
        return df[c] if c else [default]*len(df)

    out = pd.DataFrame({
        "Lender": col("lender","").astype(str).str.strip(),
        "Program": col("program","POC").astype(str).str.strip(),
        "MinScore": [ _num(x, None) for x in col("minscore", None) ],
        "MaxScore": [ _num(x, 999) for x in col("maxscore", 999) ],
        "MaxRepos": [ _num(x, 99) for x in col("maxrepos", 99) ],
        "MinIncome": [ _num(x, 0) for x in col("minincome", 0) ],
        "MinDown": [ _num(x, 0) for x in col("mindown", 0) ],
        "MaxTerm": [ _num(x, 84) for x in col("maxterm", 84) ],
        "MaxMiles": [ _num(x, 200000) for x in col("maxmiles", 200000) ],
        "MaxLTV": [ _num(x, 150) for x in col("maxltv", 150) ],
        "AllowGig": [ _to_bool(x, True) for x in col("allowgig","Yes") ],
        "AllowNoDL": [ _to_bool(x, False) for x in col("allownodl","No") ],
        "AllowFrame": [ _to_bool(x, False) for x in col("allowframe","No") ],
    })
    out = out[out["Lender"]!=""].reset_index(drop=True)
    return out

# =======================================
# PDF rate sheet parsing (heuristic)
# Extract text, try to find lines with lender name and thresholds.
# This is intentionally conservative; you can correct in the Review table.
# =======================================
def parse_pdf_rates(file_bytes: bytes) -> pd.DataFrame:
    if pdfplumber is None:
        st.warning("pdfplumber not available. Add `pdfplumber` to requirements.txt to enable PDF import.")
        return pd.DataFrame()

    rules = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw in text.splitlines():
                line = re.sub(r"\s+", " ", raw).strip()
                # Very loose match: find a lender-ish token then scan numbers/policy flags
                # You can refine for known formats later.
                if len(line) < 12:
                    continue
                # Example pattern: LENDER - Min 580 Max 720 MaxRepos 2 Income 2200 Down 1000 Term 75 Miles 150k LTV 135% Gig Y NoDL N Frame N
                m = re.search(r"(?P<lender>[A-Z][A-Za-z0-9&.\- ]+?)\s*[-:–]\s*", line)
                if not m:
                    continue
                lender = m.group("lender").strip()
                # numbers
                def grab(pattern, default=None, cast=float):
                    m2 = re.search(pattern, line, flags=re.I)
                    if not m2:
                        return default
                    try:
                        val = m2.group(1).replace(",", "")
                        if val.lower().endswith("k"):
                            val = float(val[:-1]) * 1000.0
                        return cast(val)
                    except Exception:
                        return default

                item = {
                    "Lender": lender,
                    "Program": "POC",
                    "MinScore": grab(r"Min\s*([0-9]{3})", None, float),
                    "MaxScore": grab(r"Max\s*([0-9]{3})", 999, float),
                    "MaxRepos": grab(r"repos?\s*([0-9]+)", 99, float),
                    "MinIncome": grab(r"income\s*\$?([0-9,]+k?)", 0.0, float),
                    "MinDown": grab(r"down\s*\$?([0-9,]+)", 0.0, float),
                    "MaxTerm": grab(r"term\s*([0-9]{2})", 84, float),
                    "MaxMiles": grab(r"miles?\s*([0-9,]+k?)", 200000, float),
                    "MaxLTV": grab(r"ltv\s*([0-9]{2,3})\%?", 150, float),
                    "AllowGig": bool(re.search(r"\bgig\s*(y|yes|allowed)\b", line, re.I)),
                    "AllowNoDL": bool(re.search(r"\b(no\s*dl|nodl|no dl\s*ok|no d/l)\b", line, re.I)),
                    "AllowFrame": bool(re.search(r"\b(frame|struct)\s*(ok|allow|yes)\b", line, re.I)),
                }
                if item["Lender"]:
                    rules.append(item)

    if not rules:
        return pd.DataFrame()

    df = pd.DataFrame(rules).drop_duplicates(subset=["Lender"]).reset_index(drop=True)
    return df

# =======================================
# Normalize / filter inventory
# - Keep >= $4,000
# - Exclude stock starting with W or T
# =======================================
def normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    # unify common column names
    if "Price" in work.columns and "TotalCost" not in work.columns:
        work["TotalCost"] = work["Price"]
    for must in ["Stock","Year","Make","Model","Miles","TotalCost","BookValue"]:
        if must not in work.columns:
            work[must] = np.nan

    # clean types
    work["Stock"] = work["Stock"].astype(str).str.strip()
    work["Miles"] = work["Miles"].apply(_safe_int)
    work["Year"] = work["Year"].apply(_safe_int)
    work["TotalCost"] = work["TotalCost"].apply(lambda x: max(_num(x, 0.0), 0.0))
    work["BookValue"] = work["BookValue"].apply(lambda x: max(_num(x, 0.0), 0.0))

    # filters
    work["StockUpper"] = work["Stock"].str.upper()
    work = work[work["TotalCost"] >= 4000.0]
    work = work[~work["StockUpper"].str.startswith(("W","T"))]
    work = work.drop(columns=["StockUpper"], errors="ignore").reset_index(drop=True)

    # strings
    for s in ["Make","Model","Trim"]:
        if s not in work.columns:
            work[s] = ""
        work[s] = work[s].astype(str)

    return work

# =======================================
# Fit logic
# =======================================
def gates_ok(row, features, unit=None):
    cred = features["credit"]
    repos = features["repos"]
    job_mo_total = features["job_years"]*12 + features["job_months"]
    inc_total = features["income"] + (features["gig_income"] if features["gig"] else 0)
    down = features["down"]
    trade = features["trade_eq"]
    has_dl = (features["has_dl"] == "Yes")

    # Score window (MinScore can be None -> no lower bound)
    min_score = row["MinScore"] if row["MinScore"] is not None else -9999
    if not (min_score <= cred <= row["MaxScore"]):
        return False, "Score out of window"

    if repos > row["MaxRepos"]:
        return False, "Too many repos"

    if inc_total < row["MinIncome"]:
        return False, "Income short"

    desired_term = features["desired_term"]  # default 60
    if desired_term > row["MaxTerm"]:
        return False, "Term exceeds program max"

    if (not row["AllowNoDL"]) and not has_dl:
        return False, "DL required"

    if unit is not None:
        if unit["Miles"] > row["MaxMiles"]:
            return False, "Miles exceed program max"
        if down < row["MinDown"]:
            return False, "More down required"
        bv = max(unit["BookValue"], 1.0)
        adv = (unit["TotalCost"] - down - trade) / bv * 100.0
        if adv > row["MaxLTV"]:
            return False, f"Advance {adv:.1f}% over max {row['MaxLTV']:.0f}%"

    return True, "Meets program"

def lender_fit_score(row, features):
    cred = features["credit"]
    min_score = row["MinScore"] if row["MinScore"] is not None else cred
    mid = (min_score + row["MaxScore"]) / 2.0 if row["MinScore"] is not None else row["MaxScore"] - 20
    s = 100 - abs(cred - mid) * 0.3
    return max(0, s)

def unit_fit_score(row, unit, features):
    down = features["down"]
    trade = features["trade_eq"]
    bv = max(unit["BookValue"], 1.0)
    adv = (unit["TotalCost"] - down - trade) / bv * 100.0
    adv_score = max(0.0, 100 - abs(row["MaxLTV"] - adv))
    miles_score = max(0.0, 100 - (unit["Miles"] / max(1.0, row["MaxMiles"])) * 100)
    return adv_score * 0.6 + miles_score * 0.4, adv

def what_it_takes(row, features, unit):
    F = dict(features)
    term = F["desired_term"]
    ok, why = gates_ok(row, F, unit)
    if ok:
        return {"fits": True, "changes": {}, "reason":"Meets program"}

    changes = {}
    reasons = []

    min_down_add = max(0.0, row["MinDown"] - F["down"])
    changes["down"] = F["down"] + min_down_add
    if min_down_add > 0:
        reasons.append(f"Needs at least ${int(row['MinDown'])} down (+${int(min_down_add)}).")

    if unit is not None:
        bv = max(unit["BookValue"], 1.0)
        adv_now = (unit["TotalCost"] - changes["down"] - F["trade_eq"]) / bv * 100.0
        if adv_now > row["MaxLTV"]:
            target_down = (unit["TotalCost"] - F["trade_eq"]) - (row["MaxLTV"]/100.0)*bv
            extra = max(0.0, target_down - changes["down"])
            if extra > 0:
                changes["down"] += extra
                reasons.append(f"Lower advance to ≤{int(row['MaxLTV'])}% (+${int(extra)} more down).")

    if term > row["MaxTerm"]:
        changes["term"] = int(row["MaxTerm"])
        reasons.append(f"Max term {int(row['MaxTerm'])} months.")
    else:
        changes["term"] = term

    if unit is not None and unit["Miles"] > row["MaxMiles"]:
        reasons.append(f"Miles {int(unit['Miles'])} > {int(row['MaxMiles'])} program cap.")

    inc_total = F["income"] + (F["gig_income"] if F["gig"] else 0)
    if inc_total < row["MinIncome"]:
        short = int(row["MinIncome"] - inc_total)
        if row["AllowGig"]:
            reasons.append(f"Income short by ${short}. Add provable income (gig allowed).")
        else:
            reasons.append(f"Income short by ${short}. Need co-income or different lender.")

    if features["repos"] > row["MaxRepos"]:
        reasons.append(f"Repos {features['repos']} > {int(row['MaxRepos'])}.")

    if (not row["AllowNoDL"]) and features["has_dl"] == "No":
        reasons.append("DL required.")

    fric = 0
    fric += max(0, int((changes["down"] - F["down"]) / 100.0)) * 25
    fric += max(0, int((term - changes["term"]) / 6)) * 10
    if unit is not None and unit["Miles"] > row["MaxMiles"]:
        fric += 200
    if features["repos"] > row["MaxRepos"]:
        fric += 150
    if inc_total < row["MinIncome"]:
        fric += 150
    if (not row["AllowNoDL"]) and features["has_dl"] == "No":
        fric += 150

    return {"fits": False, "changes": changes, "reasons": reasons if reasons else [why], "friction": fric}

def desk_deal_assist(inventory_df, rules_df, features):
    fits = []
    for _, u in inventory_df.iterrows():
        for _, r in rules_df.iterrows():
            ok, _ = gates_ok(r, features, u)
            if ok:
                us, adv = unit_fit_score(r, u, features)
                ls = lender_fit_score(r, features)
                fits.append((us+ls, r, u, adv))
    if fits:
        fits.sort(key=lambda x: x[0], reverse=True)
        score, r, u, adv = fits[0]
        return {"status":"fits_now","lender":r["Lender"],"program":r["Program"],"unit":u,"advance":adv,"reason":"Meets program without changes.","alts":fits[1:4]}

    best = None
    for _, u in inventory_df.iterrows():
        for _, r in rules_df.iterrows():
            wt = what_it_takes(r, features, u)
            if wt["fits"]:
                us, adv = unit_fit_score(r, u, features)
                ls = lender_fit_score(r, features)
                total = us + ls
                best = {"status":"fits_now","lender":r["Lender"],"program":r["Program"],"unit":u,"advance":adv,"reason":"Meets after reevaluation.","score":total}
                return best
            else:
                fr = wt.get("friction", 1e9)
                if (best is None) or (best.get("friction", 1e9) > fr):
                    best = {"status":"needs_changes","lender":r["Lender"],"program":r["Program"],"unit":u,"changes":wt["changes"],"reasons":wt["reasons"],"friction":fr}
    return best

# =======================================
# Session state
# =======================================
if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_RULES.copy()

# =======================================
# Header / How it works
# =======================================
st.title("SmartDesk — Desking Assistant")
st.caption("Upload rate sheets (CSV/XLSX/PDF) and/or paste lenders in bulk, then desk deals with lender & unit picks. Desired term defaults to 60 mo.")

with st.expander("What files look like", expanded=False):
    st.markdown(
        """
**Rate sheet (CSV/XLSX) — columns (case-insensitive):**  
`Lender, Program, MinScore, MaxScore, MaxRepos, MinIncome, MinDown, MaxTerm, MaxMiles, MaxLTV, AllowGig, AllowNoDL, AllowFrame`

**Inventory (CSV/XLSX) — columns:**  
`Stock, Year, Make, Model, Trim, Miles, TotalCost (or Price), BookValue`  
POC filter: keeps units **≥ $4,000** and **excludes Stock starting with W or T**.

**PDF import:** rough heuristic parser (you can correct in the Review table).
        """
    )

# =======================================
# LEFT: Deal input
# RIGHT: Uploads / Manage lenders
# =======================================
left, right = st.columns([1.25, 1])

with left:
    st.subheader("Deal Input")
    with st.form("deal_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            credit = st.number_input("Credit Score", 300, 850, 620, 1)
            monthly_income = st.number_input("Monthly Income ($/mo)", 0, 30000, 3000, 50)
            gig_flag = st.checkbox("Gig / DoorDash income?")
            gig_income = st.number_input("Gig Income ($/mo)", 0, 20000, 0, 50)
        with c2:
            repos = st.number_input("# of Repos (reported)", 0, 10, 0, 1)
            has_dl = st.selectbox("Driver's License?", ["Yes","No"])
            job_years = st.number_input("Job Time (years)", 0, 40, 0, 1)
        with c3:
            trade_eq = st.number_input("Trade Equity ($)", -20000, 20000, 0, 100)
            down = st.number_input("Down Payment ($)", 0, 50000, 1000, 50)
            job_months = st.number_input("Job Time (months)", 0, 11, 6, 1)

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
    st.subheader("Rate Sheets")
    rs_file = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"], key="rs")
    if rs_file is not None:
        try:
            ext = ".csv" if rs_file.name.lower().endswith(".csv") else ".xlsx"
            parsed = load_rate_sheet_from_bytes(rs_file.read(), ext)
            st.success(f"Parsed {len(parsed)} lenders from {rs_file.name}. Review below, then click **Merge**.")
            st.dataframe(parsed, use_container_width=True, height=210)
            if st.button("Merge parsed rate sheet", key="merge_rs"):
                # merge into session rules
                merged = pd.concat([st.session_state["rate_rules"], parsed], ignore_index=True)
                merged = merged.drop_duplicates(subset=["Lender","Program"], keep="last").reset_index(drop=True)
                st.session_state["rate_rules"] = merged
                st.success(f"Merged. You now have {len(merged)} lenders in memory.")
        except Exception as e:
            st.error(f"Rate sheet error: {e}")

    pdf_file = st.file_uploader("Rate sheet (PDF)", type=["pdf"], key="pdf")
    if pdf_file is not None:
        if pdfplumber is None:
            st.warning("Install `pdfplumber` to enable PDF import.")
        else:
            pdf_df = parse_pdf_rates(pdf_file.read())
            if pdf_df.empty:
                st.warning("No lender rows recognized from this PDF (try CSV/XLSX or adjust manually below).")
            else:
                st.success(f"Parsed {len(pdf_df)} lenders from PDF. Review below, then click **Merge**.")
                st.dataframe(pdf_df, use_container_width=True, height=210)
                if st.button("Merge parsed PDF", key="merge_pdf"):
                    merged = pd.concat([st.session_state["rate_rules"], pdf_df], ignore_index=True)
                    merged = merged.drop_duplicates(subset=["Lender","Program"], keep="last").reset_index(drop=True)
                    st.session_state["rate_rules"] = merged
                    st.success(f"Merged. You now have {len(merged)} lenders in memory.")

    st.subheader("Bulk Add / Edit")
    st.caption("Paste CSV with header row. Columns (case-insensitive): Lender, Program, MinScore, MaxScore, MaxRepos, MinIncome, MinDown, MaxTerm, MaxMiles, MaxLTV, AllowGig, AllowNoDL, AllowFrame.")
    sample = "Lender,Program,MinScore,MaxScore,MaxRepos,MinIncome,MinDown,MaxTerm,MaxMiles,MaxLTV,AllowGig,AllowNoDL,AllowFrame\n" \
             "AmeriCredit,Near/Sub,580,740,2,2200,1000,75,150000,130,Yes,No,No"
    paste = st.text_area("Paste lenders (CSV)", sample, height=120)
    if st.button("Preview pasted CSV"):
        try:
            buf = BytesIO(paste.encode("utf-8"))
            dfp = pd.read_csv(buf)
            st.dataframe(dfp, use_container_width=True, height=210)
            st.session_state["bulk_preview"] = dfp
        except Exception as e:
            st.error(f"Parse error: {e}")

    if st.button("Merge pasted lenders"):
        dfp = st.session_state.get("bulk_preview")
        if dfp is None or dfp.empty:
            st.warning("Nothing to merge. Click 'Preview' first.")
        else:
            # normalize columns like our loader
            low = {c.lower().strip(): c for c in dfp.columns}
            def col(name, default=None):
                c = low.get(name)
                return dfp[c] if c else [default]*len(dfp)
            merged_in = pd.DataFrame({
                "Lender": col("lender","").astype(str).str.strip(),
                "Program": col("program","POC").astype(str).str.strip(),
                "MinScore": [ _num(x, None) for x in col("minscore", None) ],
                "MaxScore": [ _num(x, 999) for x in col("maxscore", 999) ],
                "MaxRepos": [ _num(x, 99) for x in col("maxrepos", 99) ],
                "MinIncome": [ _num(x, 0) for x in col("minincome", 0) ],
                "MinDown": [ _num(x, 0) for x in col("mindown", 0) ],
                "MaxTerm": [ _num(x, 84) for x in col("maxterm", 84) ],
                "MaxMiles": [ _num(x, 200000) for x in col("maxmiles", 200000) ],
                "MaxLTV": [ _num(x, 150) for x in col("maxltv", 150) ],
                "AllowGig": [ _to_bool(x, True) for x in col("allowgig","Yes") ],
                "AllowNoDL": [ _to_bool(x, False) for x in col("allownodl","No") ],
                "AllowFrame": [ _to_bool(x, False) for x in col("allowframe","No") ],
            })
            merged_in = merged_in[merged_in["Lender"]!=""].reset_index(drop=True)
            merged = pd.concat([st.session_state["rate_rules"], merged_in], ignore_index=True)
            merged = merged.drop_duplicates(subset=["Lender","Program"], keep="last").reset_index(drop=True)
            st.session_state["rate_rules"] = merged
            st.success(f"Added {len(merged_in)} lenders. Total now: {len(merged)}.")

# =======================================
# Manage / Export lenders
# =======================================
with st.expander("Manage lenders (search/export)"):
    q = st.text_input("Search lender/program")
    view = st.session_state["rate_rules"].copy()
    if q.strip():
        hay = view.apply(lambda r: " ".join(str(v) for v in r.values), axis=1).str.lower()
        view = view[hay.str.contains(q.strip().lower(), na=False)]
    st.dataframe(view, use_container_width=True)
    csv = view.to_csv(index=False).encode("utf-8")
    st.download_button("Export filtered lenders (CSV)", csv, "lenders_export.csv", "text/csv")

# =======================================
# Ask about a lender rule (quick search)
# =======================================
st.subheader("Ask about a lender rule")
rule_q = st.text_input("Example: Does Exeter allow frame damage? Or Gateway gig income?")
if rule_q.strip():
    rules = st.session_state["rate_rules"].copy()
    hay = rules.apply(lambda r: " ".join(str(v) for v in r.values), axis=1).str.lower()
    hits = rules[hay.str.contains(rule_q.strip().lower(), na=False)]
    if hits.empty:
        st.info("No obvious matches in the current rate table.")
    else:
        st.dataframe(hits, use_container_width=True)

# =======================================
# Evaluate Deal
# =======================================
st.markdown("---")
st.subheader("Desk this deal")

if "inv_choice" not in st.session_state:
    st.session_state["inv_choice"] = None

inv_file = st.file_uploader("Inventory (CSV/XLSX) (optional)", type=["csv","xlsx"], key="inv_main")

if st.button("Evaluate Deal", type="primary", use_container_width=False):
    features = {
        "credit": credit,
        "income": monthly_income,
        "gig": bool(gig_flag),
        "gig_income": gig_income if gig_flag else 0,
        "repos": repos,
        "has_dl": has_dl,
        "job_years": job_years,
        "job_months": job_months,
        "down": float(down),
        "trade_eq": float(trade_eq),
        "desired_term": 60,  # default since input removed
        "co_score": None,
        "co_income": 0,
    }

    # rules
    rules = st.session_state["rate_rules"].copy()
    num_cols = ["MinScore","MaxScore","MaxRepos","MinIncome","MinDown","MaxTerm","MaxMiles","MaxLTV"]
    for c in num_cols:
        if c in rules.columns:
            rules[c] = rules[c].apply(lambda x: _num(x, 0 if c!="MaxScore" else 999))
    bool_cols = ["AllowGig","AllowNoDL","AllowFrame"]
    for c in bool_cols:
        if c in rules.columns:
            rules[c] = rules[c].apply(lambda x: _to_bool(x, False))

    # inventory
    if inv_file is not None:
        try:
            ext = ".csv" if inv_file.name.lower().endswith(".csv") else ".xlsx"
            inv_df = pd.read_csv(BytesIO(inv_file.read())) if ext==".csv" else pd.read_excel(BytesIO(inv_file.read()))
            INV = normalize_inventory(inv_df)
            st.success(f"Loaded {len(INV)} inventory units from **{inv_file.name}** (after filters).")
        except Exception as e:
            st.error(f"Inventory error: {e}")
            INV = normalize_inventory(HARD_INVENTORY)
    else:
        INV = normalize_inventory(HARD_INVENTORY)

    # ============== Deal Desk Assist ==============
    st.markdown("## Deal Desk Assist")
    plan = desk_deal_assist(INV, rules, features)
    if plan is None:
        st.warning("No path found (check rate rules/inventory).")
    else:
        if plan["status"] == "fits_now":
            u = plan["unit"]
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="metric">✅ Recommended</div>', unsafe_allow_html=True)
            st.markdown(f"**{plan['lender']}** — {plan['program']}")
            st.markdown(
                f"- **Unit:** {int(u['Year'])} {u['Make']} {u['Model']} {u.get('Trim','') or ''}  \n"
                f"- **Miles:** {int(u['Miles'])}  •  **Price:** ${int(u['TotalCost'])}  •  **Book:** ${int(u['BookValue'])}  \n"
                f"- **Advance:** {plan['advance']:.1f}%"
            )
            st.caption(plan["reason"])
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            u = plan["unit"]
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="metric">🛠 Closest path</div>', unsafe_allow_html=True)
            st.markdown(f"**{plan['lender']}** — {plan['program']}")
            st.markdown(
                f"- **Unit:** {int(u['Year'])} {u['Make']} {u['Model']} {u.get('Trim','') or ''}  \n"
                f"- **Miles:** {int(u['Miles'])}  •  **Price:** ${int(u['TotalCost'])}  •  **Book:** ${int(u['BookValue'])}"
            )
            ch = plan.get("changes", {})
            bullets = []
            if "down" in ch and ch["down"] != features["down"]:
                bullets.append(f"Increase down to **${int(ch['down'])}**.")
            if "term" in ch and ch["term"] != features["desired_term"]:
                bullets.append(f"Reduce term to **{int(ch['term'])} mo**.")
            if bullets:
                st.markdown("**Proposed tweaks:**  \n- " + "\n- ".join(bullets))
            if plan.get("reasons"):
                st.markdown("**Why:**  \n- " + "\n- ".join(plan["reasons"]))
            st.markdown("</div>", unsafe_allow_html=True)

        # quick talking points
        st.markdown("### Call-in summary")
        buyer_pitch = [
            "Why this car and structure fits (book/advance/miles).",
            "How the down / term was chosen.",
            "Preview expected stips (POI, POR, references, etc.).",
        ]
        bank_pitch = [
            "Stability story (job time, income).",
            "Unit: miles within cap, advance within program.",
            "Backup structure if needed (slightly shorter term or small down bump).",
        ]
        st.markdown("**Buyer**  \n- " + "\n- ".join(buyer_pitch))
        st.markdown("**Lender**  \n- " + "\n- ".join(bank_pitch))

    # ============== Top lender matches (as-is) ==============
    st.markdown("### Top Lender Matches")
    rows = []
    for _, r in rules.iterrows():
        ok, why = gates_ok(r, features, None)
        if ok:
            rows.append({
                "Lender": r["Lender"],
                "Program": r["Program"],
                "Reason": "Meets program",
                "Score": round(lender_fit_score(r, features),1)
            })
        else:
            rows.append({
                "Lender": r["Lender"],
                "Program": r["Program"],
                "Reason": why,
                "Score": 0.0
            })
    lenders_df = pd.DataFrame(rows)
    if not lenders_df.empty:
        lenders_df = lenders_df.sort_values("Score", ascending=False).head(10)
        st.dataframe(lenders_df, use_container_width=True)
    else:
        st.info("No lender fits with the current customer inputs.")

    # ============== Top 5 units (best lender–unit pairs) ==============
    st.markdown("### Top 5 Units (best lender–unit pairs)")
    best_rows = []
    for _, u in INV.iterrows():
        best_for_unit = []
        for _, r in rules.iterrows():
            ok, _ = gates_ok(r, features, u)
            if ok:
                us, adv = unit_fit_score(r, u, features)
                ls = lender_fit_score(r, features)
                best_for_unit.append((us+ls, r, adv))
        if best_for_unit:
            best_for_unit.sort(key=lambda x: x[0], reverse=True)
            score, r, adv = best_for_unit[0]
            best_rows.append({
                "Stock": u["Stock"],
                "Unit": f"{int(u['Year'])} {u['Make']} {u['Model']} {u.get('Trim','') or ''}",
                "Miles": int(u["Miles"]),
                "Price": int(u["TotalCost"]),
                "Book": int(u["BookValue"]),
                "Advance%": round(adv,1),
                "Lender": r["Lender"],
                "Program": r["Program"],
                "FitScore": round(score,1)
            })

    if best_rows:
        top_units = pd.DataFrame(best_rows).sort_values("FitScore", ascending=False).head(5)
        st.dataframe(top_units, use_container_width=True)
    else:
        st.info("No units fit with any lender using these rules & filters.")
else:
    st.info("Fill out the form and click **Evaluate Deal** to see recommendations.")
