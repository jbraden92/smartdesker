import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# --------------------------
# App Config / Theme
# --------------------------
st.set_page_config(page_title="SmartDesk – Desking Assistant", page_icon="📋", layout="wide")
st.markdown(
    """
    <style>
    .card {border-radius: 10px; padding: 14px 16px; border: 1px solid rgba(250,250,250,.12); background: rgba(250,250,250,.03);}
    .metric {font-size:26px; font-weight:700; margin-bottom:4px}
    .em {opacity:.75}
    .muted {opacity:.6}
    .tight td {padding-top:6px !important; padding-bottom:6px !important;}
    </style>
    """,
    unsafe_allow_html=True
)

# --------------------------
# Helpers / Defaults
# --------------------------
DEFAULT_SAMPLE_RATE_SHEET = pd.DataFrame([
    {"Lender":"Gateway Financial Solutions","MinScore":560,"MaxScore":670,"MaxRepos":1,"MinJobMonths":3,"MinIncome":1800,"MinDown":500,"AllowGig":"Yes","AllowNoDL":"No","AllowFrame":"No"},
    {"Lender":"Global Lending Services","MinScore":580,"MaxScore":720,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2200,"MinDown":1000,"AllowGig":"Yes","AllowNoDL":"No","AllowFrame":"No"},
    {"Lender":"Flagship Credit","MinScore":600,"MaxScore":750,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2400,"MinDown":1000,"AllowGig":"Yes","AllowNoDL":"No","AllowFrame":"Yes"},
    {"Lender":"Regional Acceptance","MinScore":590,"MaxScore":720,"MaxRepos":1,"MinJobMonths":12,"MinIncome":2500,"MinDown":1000,"AllowGig":"No","AllowNoDL":"No","AllowFrame":"No"},
    {"Lender":"Prestige","MinScore":600,"MaxScore":750,"MaxRepos":0,"MinJobMonths":12,"MinIncome":2600,"MinDown":1000,"AllowGig":"No","AllowNoDL":"No","AllowFrame":"No"},
    {"Lender":"Exeter","MinScore":550,"MaxScore":700,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2000,"MinDown":500,"AllowGig":"Yes","AllowNoDL":"No","AllowFrame":"No"},
    {"Lender":"Kemba CU","MinScore":640,"MaxScore":800,"MaxRepos":0,"MinJobMonths":12,"MinIncome":3000,"MinDown":1000,"AllowGig":"No","AllowNoDL":"No","AllowFrame":"No"},
])

def yn(val):
    if isinstance(val, str):
        return val.strip().lower() in ("y","yes","true","1")
    if isinstance(val, (int, float)):
        return val == 1
    return bool(val)

def _clean_numeric(x, default=None):
    try:
        if pd.isna(x) or x == "":
            return default
        return float(x)
    except Exception:
        return default

@st.cache_data(show_spinner=False)
def load_rate_sheet_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    if ext == ".csv":
        df = pd.read_csv(BytesIO(data))
    else:
        df = pd.read_excel(BytesIO(data))
    cols = {c.lower().strip(): c for c in df.columns}
    get = lambda name: df[cols[name]] if name in cols else None

    def pickcol(name, default=None):
        s = get(name)
        return s if s is not None else [default]*len(df)

    out = pd.DataFrame({
        "Lender": pickcol("lender",""),
        "MinScore": [_clean_numeric(x, 0) for x in pickcol("minscore", 0)],
        "MaxScore": [_clean_numeric(x, 999) for x in pickcol("maxscore", 999)],
        "MaxRepos": [_clean_numeric(x, 99) for x in pickcol("maxrepos", 99)],
        "MinJobMonths": [_clean_numeric(x, 0) for x in pickcol("minjobmonths", 0)],
        "MinIncome": [_clean_numeric(x, 0) for x in pickcol("minincome", 0)],
        "MinDown": [_clean_numeric(x, 0) for x in pickcol("mindown", 0)],
        "AllowGig": [yn(x) for x in pickcol("allowgig","Yes")],
        "AllowNoDL": [yn(x) for x in pickcol("allownodl","No")],
        "AllowFrame": [yn(x) for x in pickcol("allowframe","No")],
    })
    out = out[out["Lender"].astype(str).str.strip()!=""].reset_index(drop=True)
    return out

# Inventory loader that tolerates different headers & computes spreads
@st.cache_data(show_spinner=False)
def load_inventory_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    if ext == ".csv":
        inv = pd.read_csv(BytesIO(data))
    else:
        inv = pd.read_excel(BytesIO(data))

    # normalize columns (case-insensitive)
    cl = {c.lower().strip(): c for c in inv.columns}

    def get_any(names, default=None):
        for n in names:
            if n in cl: 
                return inv[cl[n]]
        return default

    # required-ish columns (best effort)
    stock = get_any(["stock","stock#","stock_number","stk","unit"]) or pd.Series([""]*len(inv))
    year  = get_any(["year","yr"]) or pd.Series([None]*len(inv))
    make  = get_any(["make"]) or pd.Series([""]*len(inv))
    model = get_any(["model"]) or pd.Series([""]*len(inv))
    trim  = get_any(["trim"]) or pd.Series([""]*len(inv))
    miles = get_any(["miles","mileage"]) or pd.Series([np.nan]*len(inv))
    price = get_any(["price","sale price","sale_price","saleprice","cashprice"]) or pd.Series([np.nan]*len(inv))
    cost  = get_any(["cost","total cost","acq cost","all in cost","total_cost"]) or pd.Series([np.nan]*len(inv))

    # book-like fields (optional)
    nada_ts  = get_any(["nadatsiminv","nada_ts","nada trade sub"])  # NADA trade sub or similar
    kbb_ls   = get_any(["kbblsim","kbb_ls"])                        # KBB lending similarity
    bb_wh    = get_any(["bbwhsale","blackbook_wholesale"])
    lend_min = get_any(["lending - cost","lending_minus_cost","lend_minus_cost"])
    trade_min= get_any(["trade - cost","trade_minus_cost"])

    df = pd.DataFrame({
        "Stock": stock,
        "Year": year, "Make": make, "Model": model, "Trim": trim,
        "Miles": pd.to_numeric(miles, errors="coerce"),
        "Price": pd.to_numeric(price, errors="coerce"),
        "Cost": pd.to_numeric(cost, errors="coerce"),
        "NADA_TS": pd.to_numeric(nada_ts, errors="coerce") if nada_ts is not None else np.nan,
        "KBB_LS": pd.to_numeric(kbb_ls, errors="coerce") if kbb_ls is not None else np.nan,
        "BB_Wholesale": pd.to_numeric(bb_wh, errors="coerce") if bb_wh is not None else np.nan,
        "LendingMinusCost": pd.to_numeric(lend_min, errors="coerce") if lend_min is not None else np.nan,
        "TradeMinusCost": pd.to_numeric(trade_min, errors="coerce") if trade_min is not None else np.nan,
    })

    # Frame flag: many stores mark frame damage with stock numbers starting with "X"
    df["FrameDamageFlag"] = df["Stock"].astype(str).str.upper().str.startswith("X")

    # Compute a "best spread" using whatever is present
    spreads = []
    for _, r in df.iterrows():
        candidates = []
        if pd.notna(r.get("LendingMinusCost")): candidates.append(r["LendingMinusCost"])
        if pd.notna(r.get("TradeMinusCost")):   candidates.append(r["TradeMinusCost"])
        if pd.notna(r.get("NADA_TS")) and pd.notna(r.get("Cost")): 
            candidates.append(r["NADA_TS"] - r["Cost"])
        if pd.notna(r.get("KBB_LS")) and pd.notna(r.get("Cost")): 
            candidates.append(r["KBB_LS"] - r["Cost"])
        if pd.notna(r.get("BB_Wholesale")) and pd.notna(r.get("Cost")):
            candidates.append(r["BB_Wholesale"] - r["Cost"])
        # fallback: price - cost
        if pd.notna(r.get("Price")) and pd.notna(r.get("Cost")):
            candidates.append(r["Price"] - r["Cost"])

        spreads.append(np.nan if len(candidates)==0 else np.nanmax(candidates))
    df["BestSpread"] = spreads

    # pretty combined name
    df["Vehicle"] = df[["Year","Make","Model","Trim"]].astype(str).agg(" ".join, axis=1).str.replace(" None","", regex=False)
    return df

def est_payment(amount, apr=0.24, term=72):
    """Simple payment estimate for ranking vehicles."""
    if amount <= 0: return 0.0
    r = apr/12
    try:
        pmt = amount * (r*(1+r)**term) / ((1+r)**term - 1)
    except ZeroDivisionError:
        pmt = amount/term
    return float(pmt)

def score_lender(row, features):
    cred = features["credit"]
    repos = features["repos"]
    job = features["job_months"]
    income = features["income"] + features["gig_income"]
    down = features["down"]
    has_dl = features["has_dl"]
    gig = features["gig"]

    if not (row.MinScore <= cred <= row.MaxScore):   return (False, "Score outside lender window", 0)
    if repos > row.MaxRepos:                         return (False, "Too many repos for lender", 0)
    if job < row.MinJobMonths:                       return (False, "Insufficient job time", 0)
    if income < row.MinIncome:                       return (False, "Insufficient income", 0)
    if down < row.MinDown:                           return (False, "Needs more down", 0)
    if (not row.AllowNoDL) and (has_dl == "No"):     return (False, "DL required", 0)
    if (not row.AllowGig) and gig and features["gig_income"] > 0:
                                                    return (False, "Gig income not allowed", 0)

    window_mid = (row.MinScore + row.MaxScore)/2.0
    score = 0
    score += 100 - abs(cred - window_mid) * 0.5
    score += min(1000, down) / 20
    score += min(4000, income) / 40
    score += (30 if gig and row.AllowGig else 0)
    score += (10 if (has_dl == "Yes") else 0)
    return (True, "Meets program guidelines", score)

def recommend_lenders(rules_df: pd.DataFrame, features: dict, topn=5):
    rows = []
    for _, r in rules_df.iterrows():
        ok, why, s = score_lender(r, features)
        rows.append({
            "Lender": r.Lender,
            "Eligible": ok,
            "Reason": why,
            "Score": round(s,1),
            "MinDown": r.MinDown,
            "MinIncome": r.MinIncome,
            "MinJobMonths": r.MinJobMonths,
            "MaxRepos": r.MaxRepos,
            "AllowFrame": r.AllowFrame,
            "AllowNoDL": r.AllowNoDL,
            "AllowGig": r.AllowGig
        })
    df = pd.DataFrame(rows).sort_values(["Eligible","Score"], ascending=[False, False]).reset_index(drop=True)
    top = df[df["Eligible"]].head(topn)
    pick = top.iloc[0] if len(top) > 0 else None
    return pick, top, df

def rank_inventory_for_lender(inv: pd.DataFrame, lender_row: pd.Series, features: dict, maxn=5):
    """POC ranking: favor spread; penalize frame if disallowed; keep payment under ~20% of income."""
    if inv is None or len(inv)==0:
        return pd.DataFrame()

    # Filter: frame damage if not allowed
    df = inv.copy()
    if not bool(lender_row.get("AllowFrame", False)):
        df = df[~df["FrameDamageFlag"]]

    # Affordability (very rough)
    max_payment = (features["income"] + features["gig_income"]) * 0.20
    amount_financed = (df["Price"].fillna(0) - features["down"]).clip(lower=0)
    df["EstPayment"] = amount_financed.apply(lambda a: est_payment(a, apr=0.24, term=72))

    # Score: spread primary; heavy penalty if pmt above budget
    df["Score"] = df["BestSpread"].fillna(-1e9)
    df.loc[df["EstPayment"] > max_payment, "Score"] -= 1e6  # push unaffordable units to bottom

    # Return Top N sorted
    keep_cols = ["Stock","Vehicle","Miles","Price","Cost","BestSpread","EstPayment","FrameDamageFlag"]
    df = df.sort_values("Score", ascending=False)[keep_cols].head(maxn).reset_index(drop=True)
    return df

# Session store
if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_SAMPLE_RATE_SHEET.copy()
if "inventory" not in st.session_state:
    st.session_state["inventory"] = None

# --------------------------
# Header
# --------------------------
st.title("SmartDesk – Desking Assistant")
st.caption("Upload a rate sheet (to teach programs) and inventory (CSV/XLSX). Enter the basics, and get lender + Top 5 units.")

with st.expander("How it learns & picks units", expanded=False):
    st.markdown(
        """
        **Rate sheets** (CSV/XLSX) columns it reads (case-insensitive):  
        `Lender, MinScore, MaxScore, MaxRepos, MinJobMonths, MinIncome, MinDown, AllowGig, AllowNoDL, AllowFrame`

        **Inventory** (CSV/XLSX): bring whatever you have; the app tries to map common fields like  
        `Stock, Year, Make, Model, Trim, Miles, Price, Cost` and book columns such as  
        `nadatsiminv, kbblsim, bbwhsale, lending - cost, trade - cost`.  
        It computes a **BestSpread** from any book/cost fields it finds, and ranks Top 5 units for the chosen lender.
        """
    )

# --------------------------
# Inputs & Uploads
# --------------------------
left, right = st.columns([1.25, 1])

with left:
    st.subheader("Deal Input")
    with st.form("deal_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            credit = st.number_input("Credit Score", 300, 850, 620, 1)
            income = st.number_input("Monthly Income ($)", 0, 20000, 3000, 50)
            job_years = st.number_input("Job Time – Years", 0, 40, 0, 1)
            job_months_only = st.number_input("Job Time – Months", 0, 11, 6, 1)
            job_months = int(job_years) * 12 + int(job_months_only)
        with col2:
            repos = st.number_input("# of Repos (reported)", 0, 10, 0, 1)
            has_dl = st.selectbox("Driver's License?", ["Yes","No"])
            down = st.number_input("Down Payment ($)", 0, 20000, 1000, 50)
        with col3:
            trade_eq = st.number_input("Trade Equity ($)", -20000, 20000, 0, 100)
            gig_flag = st.checkbox("Gig / DoorDash income?")
            gig_income = st.number_input("Gig Income ($/month)", 0, 20000, 0, 50)

        include_co = st.checkbox("Include Co-Applicant?")
        if include_co:
            co1, co2 = st.columns(2)
            with co1:
                co_score = st.number_input("Co-Applicant Score", 300, 850, 600, 1)
            with co2:
                co_income = st.number_input("Co-Applicant Income ($/month)", 0, 20000, 0, 50)
        else:
            co_score = None
            co_income = 0

        submitted = st.form_submit_button("Evaluate Deal", type="primary")

with right:
    st.subheader("Uploads")
    rs_file = st.file_uploader("Rate sheet (CSV or XLSX)", type=["csv","xlsx"])
    if rs_file is not None:
        try:
            ext = ".csv" if rs_file.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["rate_rules"] = load_rate_sheet_from_bytes(rs_file.read(), ext)
            st.success(f"Loaded {len(st.session_state['rate_rules'])} lenders from **{rs_file.name}**.")
        except Exception as e:
            st.error(f"Could not read rate sheet: {e}")

    inv_file = st.file_uploader("Inventory (CSV or XLSX)", type=["csv","xlsx"])
    if inv_file is not None:
        try:
            ext = ".csv" if inv_file.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["inventory"] = load_inventory_from_bytes(inv_file.read(), ext)
            st.success(f"Loaded {len(st.session_state['inventory'])} vehicles from **{inv_file.name}**.")
        except Exception as e:
            st.error(f"Could not read inventory: {e}")

    with st.expander("Current rules (top 20)", expanded=False):
        st.dataframe(st.session_state["rate_rules"].head(20), use_container_width=True)
    if st.session_state["inventory"] is not None:
        with st.expander("Inventory preview (top 20)", expanded=False):
            st.dataframe(st.session_state["inventory"].head(20), use_container_width=True)

# --------------------------
# Decision + Suggestions
# --------------------------
if submitted:
    features = {
        "credit": credit,
        "income": income,
        "job_months": job_months,
        "repos": repos,
        "down": down,
        "trade_eq": trade_eq,
        "gig": bool(gig_flag),
        "gig_income": gig_income if gig_flag else 0,
        "has_dl": has_dl,
        "co_score": co_score,
        "co_income": co_income,
    }

    rules = st.session_state["rate_rules"].copy()
    pick, top, audit = recommend_lenders(rules, features, topn=5)

    st.markdown("### Result")
    cols = st.columns([1.1, 1])
    with cols[0]:
        if pick is not None:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="metric">✅ Recommended Lender</div>', unsafe_allow_html=True)
            st.markdown(f"**{pick['Lender']}**  \n<span class='em'>{pick['Reason']}</span>", unsafe_allow_html=True)
            st.markdown("<hr/>", unsafe_allow_html=True)
            st.markdown(f"- Est. **Score Rank**: {pick['Score']}")
            st.markdown(f"- **Min Down**: ${int(pick['MinDown'])}  •  **Min Income**: ${int(pick['MinIncome'])}/mo")
            st.markdown(f"- **Max Repos** allowed: {int(pick['MaxRepos'])}  •  **Min Job**: {int(pick['MinJobMonths'])} mo")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="metric">❌ No Eligible Lender Found</div>', unsafe_allow_html=True)
            st.markdown("Try increasing down, adding a co-app, or choosing a vehicle with cleaner history.", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    with cols[1]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="metric">Top Lender Matches</div>', unsafe_allow_html=True)
        if len(top) > 0:
            st.dataframe(
                top[["Lender","Score","Reason","MinDown","MinIncome","MinJobMonths","MaxRepos"]].style.set_table_attributes('class="tight"'),
                use_container_width=True, height=200
            )
        else:
            st.caption("No eligible lenders with the current inputs.")
        st.markdown("</div>", unsafe_allow_html=True)

    # --- Top 5 Vehicles for PICKED lender (if any) ---
    st.markdown("### Suggested Units")
    inv = st.session_state.get("inventory", None)
    if pick is not None and inv is not None and len(inv) > 0:
        top_units = rank_inventory_for_lender(inv, pick, features, maxn=5)
        if len(top_units) > 0:
            st.dataframe(
                top_units.style.format({"Price":"${:,.0f}","Cost":"${:,.0f}","BestSpread":"${:,.0f}","EstPayment":"${:,.0f}"}).set_table_attributes('class="tight"'),
                use_container_width=True, height=260
            )
        else:
            st.caption("No units fit this lender with the current inputs.")
    else:
        st.caption("Upload inventory and evaluate a deal to see vehicle suggestions.")

    # --- JSON Snapshot (for audit/notes) ---
    st.markdown("### Deal Snapshot")
    snapshot = {
        "Primary Applicant": {
            "Credit Score": credit,
            "Monthly Income": income,
            "Job Months": job_months,
            "Repos": repos,
            "Driver's License": has_dl,
        },
        "Structure": {
            "Down Payment": down,
            "Trade Equity": trade_eq,
            "Gig Income": gig_income if gig_flag else 0
        },
        "Co-Applicant": {
            "Included": include_co,
            "Co Score": co_score if include_co else None,
            "Co Income": co_income if include_co else 0
        },
        "Decision": {
            "Picked Lender": None if pick is None else pick["Lender"],
            "Reason": None if pick is None else pick["Reason"],
            "Score": None if pick is None else pick["Score"],
        }
    }
    st.json(snapshot, expanded=False)

    with st.expander("Audit (all lenders)", expanded=False):
        st.dataframe(audit, use_container_width=True)

else:
    st.info("Fill out the form and click **Evaluate Deal**.")
