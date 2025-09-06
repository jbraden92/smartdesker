import math
from io import BytesIO
from typing import List, Dict, Any, Tuple

import pandas as pd
import streamlit as st

# =============== PAGE CONFIG & STYLES =================
st.set_page_config(page_title="SmartDesk — Desking Assistant", page_icon="📋", layout="wide")
st.markdown("""
<style>
/* Dark, roomy cards */
.card {border-radius:14px; padding:16px 18px; border:1px solid rgba(255,255,255,.12); background:rgba(255,255,255,.03); margin-bottom:10px;}
.hi {font-weight:700; font-size:22px}
.subtle {opacity:.75}
.kpi {font-size:26px; font-weight:800}
.badge {display:inline-block; padding:2px 8px; border-radius:999px; border:1px solid rgba(255,255,255,.18); margin-left:8px; font-size:12px; opacity:.85}
.ok{color:#7DD97C} .warn{color:#F2C14E} .bad{color:#EF6C6C}
table td, table th {font-size:14px !important}
</style>
""", unsafe_allow_html=True)

# =============== UTILITIES =================
def yn(val) -> bool:
    if isinstance(val, str):
        return val.strip().lower() in ("y","yes","true","1")
    if isinstance(val, (int, float)):
        return val == 1
    return bool(val)

def cleanf(x, default=None):
    try:
        if x is None or (isinstance(x, str) and x.strip()=="") or (isinstance(x, float) and math.isnan(x)):
            return default
        return float(x)
    except Exception:
        return default

def pmt(annual_rate_pct: float, term_months: int, amount: float) -> float:
    """Simple consumer PMT (APR monthly)."""
    r = (annual_rate_pct/100.0)/12.0
    if r == 0:
        return amount/term_months
    return amount * (r*(1+r)**term_months)/((1+r)**term_months - 1)

def format_money(v):
    return f"${int(round(v,0)):,}"

# =============== DEFAULT LENDER PROGRAMS =================
# If you upload a rate sheet, it will override these.
DEFAULT_RULES = pd.DataFrame([
    # Notes: leave MinScore=None to mean "no floor"
    # MaxAdvancePct = max amount financed ÷ NADA clean trade (or book) times 100
    dict(Lender="Gateway Financial Solutions", Program="Select", MinScore=None, MaxRepos=2, MinJobMonths=0,
         MinIncome=1800, MaxAdvancePct=135, BuyRate=25.0, MaxTerm=72,
         PTImaxPct=20, BackEndCap=2400, Notes="Waived POI/ POR often OK w/ VOE. Equifax for VOE. Max back-end ~2,400."),
    dict(Lender="Westlake Financial", Program="Standard", MinScore=None, MaxRepos=2, MinJobMonths=0,
         MinIncome=1800, MaxAdvancePct=125, BuyRate=24.9, MaxTerm=54,
         PTImaxPct=22, BackEndCap=0, Notes="Arbitration/ RISC timing. Payment-first culture."),
    dict(Lender="Global Lending Services", Program="Tier 3", MinScore=560, MaxRepos=2, MinJobMonths=3,
         MinIncome=2200, MaxAdvancePct=125, BuyRate=25.0, MaxTerm=72,
         PTImaxPct=22, BackEndCap=0, Notes="Max back-end of ~$2,400 seen in some deals; watch cap."),
    dict(Lender="Exeter Finance", Program="+ Bronze", MinScore=560, MaxRepos=2, MinJobMonths=6,
         MinIncome=2200, MaxAdvancePct=120, BuyRate=25.0, MaxTerm=75,
         PTImaxPct=22, BackEndCap=0, Notes="Multiple approvals, sometimes first in-house funds. Can be rate sensitive."),
    dict(Lender="Consumer Portfolio Services", Program="CPS", MinScore=550, MaxRepos=3, MinJobMonths=0,
         MinIncome=2000, MaxAdvancePct=124, BuyRate=23.0, MaxTerm=72,
         PTImaxPct=22, BackEndCap=1000, Notes="New MAX approvals w/ notes. Be mindful if prior CPS neg."),
    dict(Lender="Flagship Credit Acceptance", Program="Nickel", MinScore=580, MaxRepos=1, MinJobMonths=12,
         MinIncome=2500, MaxAdvancePct=118, BuyRate=24.99, MaxTerm=66,
         PTImaxPct=20, BackEndCap=0, Notes="Payment target heavy; prefers stronger income/tenure."),
])

# =============== LOAD RATE SHEET (OPTIONAL) ===============
@st.cache_data(show_spinner=False)
def load_rules_from_file(data: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_excel(BytesIO(data)) if ext==".xlsx" else pd.read_csv(BytesIO(data))
    # Try to map columns flexibly (case-insensitive)
    m = {c.lower().strip(): c for c in df.columns}
    def pick(name, default=None):
        col = m.get(name.lower())
        if col is None: return [default]*len(df)
        return df[col].tolist()
    out = pd.DataFrame({
        "Lender": pick("Lender",""),
        "Program": pick("Program",""),
        "MinScore": [cleanf(x,None) for x in pick("MinScore",None)],
        "MaxRepos": [cleanf(x,99) for x in pick("MaxRepos",99)],
        "MinJobMonths": [cleanf(x,0) for x in pick("MinJobMonths",0)],
        "MinIncome": [cleanf(x,0) for x in pick("MinIncome",0)],
        "MaxAdvancePct": [cleanf(x,999) for x in pick("MaxAdvancePct",999)],
        "BuyRate": [cleanf(x,25.0) for x in pick("BuyRate",25.0)],
        "MaxTerm": [int(cleanf(x,72)) for x in pick("MaxTerm",72)],
        "PTImaxPct": [cleanf(x,22) for x in pick("PTImaxPct",22)],
        "BackEndCap": [cleanf(x,0) for x in pick("BackEndCap",0)],
        "Notes": pick("Notes",""),
    })
    out = out[out["Lender"].astype(str).str.strip()!=""].reset_index(drop=True)
    return out

# =============== INVENTORY (POC) =================
HARD_INVENTORY = pd.DataFrame([
    {"Stock":"A001","Year":2012,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93500,"Price":9990,"Book":11800},
    {"Stock":"A002","Year":2017,"Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"Price":10450,"Book":12200},
    {"Stock":"A003","Year":2014,"Make":"Toyota","Model":"Camry","Trim":"SE","Miles":128500,"Price":8495,"Book":10250},
    {"Stock":"A007","Year":2018,"Make":"Hyundai","Model":"Elantra","Trim":"SEL","Miles":84500,"Price":10990,"Book":10900},
    {"Stock":"A008","Year":2019,"Make":"Nissan","Model":"Versa","Trim":"SV","Miles":61200,"Price":9995,"Book":11200},
    {"Stock":"X005","Year":2010,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111200,"Price":8995,"Book":10600},
])

def normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    # Expected cols: Stock, Year, Make, Model, Trim, Miles, Price, Book
    cols = {c.lower().strip(): c for c in df.columns}
    def g(name, default=None):
        col = cols.get(name.lower())
        return df[col] if col in cols else pd.Series([default]*len(df))
    out = pd.DataFrame({
        "Stock": g("stock",""),
        "Year": g("year",0),
        "Make": g("make",""),
        "Model": g("model",""),
        "Trim": g("trim",""),
        "Miles": g("miles",0).astype(float),
        "Price": g("price",0).astype(float),
        "Book": g("book",0).astype(float),
    })
    out["AdvancePct"] = (out["Price"]/out["Book"]*100).replace([float("inf"), -float("inf")], 999)
    # Filter: total cost < 4000 OR stock starts with W or T → drop
    out = out[~((out["Price"] < 4000) | (out["Stock"].astype(str).str.upper().str.startswith(("W","T"))))].copy()
    out.reset_index(drop=True, inplace=True)
    return out

# =============== LENDER LOGIC =================
def lender_gates_ok(row: pd.Series, features: Dict[str, Any]) -> Tuple[bool, str]:
    """Hard gates: income, repos, min score, job months, price/book advance & PTI later."""
    credit = features["credit"]
    income = features["income_total"]
    job_months = features["job_months"]
    repos = features["repos"]

    if row["MinScore"] is not None and credit < row["MinScore"]:
        return False, "Score below program min"
    if repos > row["MaxRepos"]:
        return False, "Too many repos"
    if job_months < row["MinJobMonths"]:
        return False, "Insufficient job time"
    if income < row["MinIncome"]:
        return False, "Insufficient income"
    return True, "Base program fit"

def price_for_lender(book: float, row: pd.Series) -> float:
    """Max price based on lender MaxAdvancePct (book * pct)."""
    if book <= 0:
        return 0
    cap = cleanf(row["MaxAdvancePct"], 999)
    return (cap/100.0) * book

def choose_term(row: pd.Series, target_payment: float, amount_financed: float) -> int:
    """Pick a term up to MaxTerm to get near target payment (or longest if TP not given)."""
    max_term = int(row["MaxTerm"])
    # try common buckets
    for t in [48, 54, 60, 66, 72, 75]:
        if t <= max_term:
            pay = pmt(row["BuyRate"], t, amount_financed)
            if target_payment and pay <= target_payment:
                return t
    return min(max_term, 72)

def evaluate_unit_for_lender(unit: pd.Series, row: pd.Series, features: Dict[str, Any]) -> Dict[str, Any]:
    """Return scoring & structure for a single lender/unit pair."""
    ok, why = lender_gates_ok(row, features)
    if not ok:
        return {"Eligible": False, "Why": why}

    max_price = max(unit["Price"], price_for_lender(unit["Book"], row))
    # We set retail price to min(max program price, unit price if lower)
    target_price = min(max_price, unit["Price"])
    amount_financed = max(target_price - features["down"], 0)

    # PTI target: PTImax% of income total
    pti_cap = (row["PTImaxPct"]/100.0) * features["income_total"]
    target_payment = pti_cap
    # Choose term to meet PTI if possible
    term = choose_term(row, target_payment, amount_financed)
    payment = pmt(row["BuyRate"], term, amount_financed)
    advance_pct = (target_price/unit["Book"]*100.0) if unit["Book"]>0 else 999

    # If payment busts PTI too high → not eligible
    if payment > pti_cap + 1:  # +$1 tolerance
        return {"Eligible": False, "Why": f"PTI {payment:.0f} > cap {pti_cap:.0f}"}

    score = 0
    # Reward being near but under max advance
    score += max(0, (row["MaxAdvancePct"] - advance_pct))
    # Reward price/book spread
    score += min(20, (unit["Book"] - target_price)/100.0)
    # Penalize high miles
    score -= min(20, unit["Miles"]/50000.0)

    return {
        "Eligible": True,
        "Why": "Meets program",
        "Lender": row["Lender"],
        "Program": row["Program"],
        "BuyRate": row["BuyRate"],
        "PTIcap": pti_cap,
        "Price": target_price,
        "Book": unit["Book"],
        "AdvancePct": advance_pct,
        "Payment": payment,
        "Term": term,
        "Score": round(score,2),
        "Notes": row["Notes"],
    }

def recommend(results: List[Dict[str, Any]]) -> pd.DataFrame:
    if not results: return pd.DataFrame()
    df = pd.DataFrame([r for r in results if r.get("Eligible")])
    if df.empty: return df
    # Gateway priority tiebreak
    df["GatewayBias"] = df["Lender"].str.contains("Gateway", case=False, na=False).astype(int)
    df.sort_values(["GatewayBias","Score"], ascending=[False, False], inplace=True)
    return df.reset_index(drop=True)

# =============== APP HEADER =================
st.markdown('<div class="hi">SmartDesk — Desking Assistant<span class="badge">POC</span></div>', unsafe_allow_html=True)
st.caption("Upload (optional) rate sheet & inventory. Enter the basics. Get lender picks & top 5 lender-unit pairs. No desired term entry — the app chooses a term to hit PTI caps.")

# =============== LAYOUT: INPUTS & UPLOADS =================
left, right = st.columns([1.15, 1])

with left:
    st.markdown('<div class="card"><span class="kpi">Applicant</span></div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        credit = st.number_input("Credit Score", 300, 850, 620, 1)
        repos = st.number_input("# of Repos (reported)", 0, 10, 0, 1)
        has_dl = st.selectbox("Driver's License?", ["Yes", "No"])
    with col2:
        base_income = st.number_input("Monthly Income ($)", 0, 20000, 3000, 50)
        job_years = st.number_input("Job Time (years)", 0, 50, 1, 1)
        job_months = st.number_input("Job Time (months)", 0, 59, 6, 1)
    with col3:
        down = st.number_input("Down Payment ($)", 0, 20000, 1000, 50)
        trade_eq = st.number_input("Trade Equity ($)", -20000, 20000, 0, 100)
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

with right:
    st.markdown('<div class="card"><span class="kpi">Uploads</span></div>', unsafe_allow_html=True)
    rs = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"])
    inv = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"])
    rules = DEFAULT_RULES.copy()
    if rs is not None:
        try:
            ext = ".xlsx" if rs.name.lower().endswith(".xlsx") else ".csv"
            rules = load_rules_from_file(rs.read(), ext)
            st.success(f"Loaded {len(rules)} lender rows from {rs.name}.")
        except Exception as e:
            st.error(f"Rate sheet error: {e}")

    with st.expander("Current Program Rules (top 20)"):
        st.dataframe(rules.head(20), use_container_width=True)

# =============== INVENTORY HANDLING =================
if inv is None:
    inventory = normalize_inventory(HARD_INVENTORY)
else:
    try:
        ext = ".xlsx" if inv.name.lower().endswith(".xlsx") else ".csv"
        df = pd.read_excel(inv) if ext==".xlsx" else pd.read_csv(inv)
        inventory = normalize_inventory(df)
        st.success(f"Loaded {len(inventory)} units from {inv.name}.")
    except Exception as e:
        st.error(f"Inventory error: {e}")
        inventory = normalize_inventory(HARD_INVENTORY)

# =============== ACTION BAR =================
evaluate = st.button("Evaluate Deal", type="primary")

# =============== RUN EVALUATION =================
if evaluate:
    # Features package for scoring
    features = dict(
        credit=credit,
        income_total = base_income + (gig_income if gig_flag else 0) + co_income,
        job_months = job_years*12 + job_months,
        repos = repos,
        down = down,
        has_dl = has_dl,
        trade_eq = trade_eq,
    )

    # Scan lenders (gates only)
    lender_rows = []
    for _, r in rules.iterrows():
        ok, why = lender_gates_ok(r, features)
        lender_rows.append({
            "Lender": r["Lender"], "Program": r["Program"], "Eligible": ok,
            "Why": why if not ok else "Base fit",
            "BuyRate": r["BuyRate"], "MaxAdvancePct": r["MaxAdvancePct"], "PTImaxPct": r["PTImaxPct"], "MaxTerm": r["MaxTerm"]
        })
    lender_df = pd.DataFrame(lender_rows)

    st.markdown("### Top Lender Matches")
    if lender_df[lender_df["Eligible"]].empty:
        st.warning("No lender passes base gates with current inputs.")
        st.dataframe(lender_df, use_container_width=True)
    else:
        # Show eligible lenders ordered with Gateway bias
        lender_df["GatewayBias"] = lender_df["Lender"].str.contains("Gateway", case=False, na=False).astype(int)
        lender_show = lender_df[lender_df["Eligible"]].sort_values(["GatewayBias"], ascending=False)[
            ["Lender","Program","BuyRate","MaxAdvancePct","PTImaxPct","MaxTerm"]
        ]
        st.dataframe(lender_show, use_container_width=True, height=220)

    # Pair lenders and inventory units
    pair_results = []
    for _, r in rules.iterrows():
        for _, u in inventory.iterrows():
            out = evaluate_unit_for_lender(u, r, features)
            if out.get("Eligible"):
                row = dict(Stock=u["Stock"], Unit=f'{int(u["Year"])} {u["Make"]} {u["Model"]} {u["Trim"]}',
                           Miles=int(u["Miles"]), **out)
                pair_results.append(row)

    pairs = recommend(pair_results)
    st.markdown("### Top 5 Units (best lender–unit pairs)")
    if pairs.empty:
        st.info("No units fit with any lender using these rules & PTI caps.")
    else:
        top5 = pairs.head(5).copy()
        top5["Price"] = top5["Price"].apply(format_money)
        top5["Book"] = top5["Book"].apply(format_money)
        top5["Payment"] = top5["Payment"].apply(format_money)
        top5["Advance%"] = (pairs.head(5)["AdvancePct"]).round(1)
        top5 = top5[["Stock","Unit","Miles","Lender","Program","Price","Book","Advance%","Payment","Term","Score","Notes"]]
        st.dataframe(top5, use_container_width=True, height=260)

    with st.expander("All lender–unit evaluations"):
        if pairs.empty:
            st.caption("—")
        else:
            show = pairs.copy()
            show["Price"] = show["Price"].apply(format_money)
            show["Book"] = show["Book"].apply(format_money)
            show["Payment"] = show["Payment"].apply(format_money)
            show["Advance%"] = show["AdvancePct"].round(1)
            show = show[["Stock","Unit","Miles","Lender","Program","Price","Book","Advance%","Payment","Term","Score","Why","Notes"]]
            st.dataframe(show, use_container_width=True, height=420)

    # Deal snapshot
    st.markdown("### Deal Snapshot")
    snap = {
        "Applicant": {
            "Score": credit, "Income/mo": base_income, "Gig Income": (gig_income if gig_flag else 0),
            "Co Income": co_income, "Job Months": features["job_months"], "Repos": repos, "DL": has_dl
        },
        "Structure": {"Down": down, "Trade Eq": trade_eq},
        "Eligible lenders": list(lender_show["Lender"]) if lender_df[lender_df["Eligible"]].shape[0] else [],
    }
    st.json(snap, expanded=False)

# =============== ASK A LENDER RULE =================
st.markdown("### Ask about a lender rule")
q = st.text_input("Example: 'Does Gateway accept short job time?' or 'PTI for Westlake?'", "")
if q:
    ql = q.lower()
    def row_hit(r):
        blob = " ".join([str(r.get(k,"")) for k in r.index]).lower()
        return all(token in blob for token in ql.split())
    hits = rules[rules.apply(row_hit, axis=1)]
    if hits.empty:
        # fallback: look for lender keyword or common fields
        hits = rules[rules["Lender"].str.lower().str.contains(ql, na=False) | rules["Notes"].str.lower().str.contains(ql, na=False)]
    if hits.empty:
        st.info("No direct match in current rule table. Try a simpler phrase or the lender name.")
    else:
        st.dataframe(hits, use_container_width=True)
