# streamlit_app.py
import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# =========================
# App Config / Minimal Theme
# =========================
st.set_page_config(page_title="SmartDesk — Desking Assistant", page_icon="📋", layout="wide")
st.markdown("""
<style>
.card {border-radius: 10px; padding: 14px 16px; border: 1px solid rgba(250,250,250,.12); background: rgba(250,250,250,.03);}
.metric {font-size:26px; font-weight:700; margin-bottom:4px}
.em {opacity:.75}
.tight td{padding-top:6px !important; padding-bottom:6px !important;}
</style>
""", unsafe_allow_html=True)

# =========================
# Sample Rate Sheet (Gateway: no min/no max)
# =========================
DEFAULT_SAMPLE_RATE_SHEET = pd.DataFrame([
    {"Lender":"Gateway Financial Solutions","MinScore":np.nan,"MaxScore":np.nan,"MaxRepos":1,"MinJobMonths":3,"MinIncome":1800,"MinDown":500,"AllowGig":"Yes","AllowNoDL":"No","AllowFrame":"No"},
    {"Lender":"Global Lending Services","MinScore":580,"MaxScore":720,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2200,"MinDown":1000,"AllowGig":"Yes","AllowNoDL":"No","AllowFrame":"No"},
    {"Lender":"Flagship Credit","MinScore":600,"MaxScore":750,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2400,"MinDown":1000,"AllowGig":"Yes","AllowNoDL":"No","AllowFrame":"Yes"},
    {"Lender":"Regional Acceptance","MinScore":590,"MaxScore":720,"MaxRepos":1,"MinJobMonths":12,"MinIncome":2500,"MinDown":1000,"AllowGig":"No","AllowNoDL":"No","AllowFrame":"No"},
    {"Lender":"Prestige","MinScore":600,"MaxScore":750,"MaxRepos":0,"MinJobMonths":12,"MinIncome":2600,"MinDown":1000,"AllowGig":"No","AllowNoDL":"No","AllowFrame":"No"},
    {"Lender":"Exeter","MinScore":550,"MaxScore":700,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2000,"MinDown":500,"AllowGig":"Yes","AllowNoDL":"No","AllowFrame":"No"},
    {"Lender":"Kemba CU","MinScore":640,"MaxScore":800,"MaxRepos":0,"MinJobMonths":12,"MinIncome":3000,"MinDown":1000,"AllowGig":"No","AllowNoDL":"No","AllowFrame":"No"},
])

def yn(v):
    if isinstance(v,str): return v.strip().lower() in ("y","yes","true","1")
    if isinstance(v,(int,float)): return v==1
    return bool(v)

def _num(x, default=np.nan):
    try:
        if pd.isna(x) or x=="":
            return default
        return float(x)
    except Exception:
        return default

@st.cache_data(show_spinner=False)
def load_rate_sheet_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(data)) if ext==".csv" else pd.read_excel(BytesIO(data))
    cols = {c.lower().strip(): c for c in df.columns}
    get = lambda name: df[cols[name]] if name in cols else None
    def pick(name, default=None):
        s = get(name)
        return s if s is not None else [default]*len(df)
    out = pd.DataFrame({
        "Lender": pick("lender",""),
        "MinScore": [_num(x, np.nan) for x in pick("minscore", np.nan)],
        "MaxScore": [_num(x, np.nan) for x in pick("maxscore", np.nan)],
        "MaxRepos": [_num(x, 99) for x in pick("maxrepos", 99)],
        "MinJobMonths": [_num(x, 0) for x in pick("minjobmonths", 0)],
        "MinIncome": [_num(x, 0) for x in pick("minincome", 0)],
        "MinDown": [_num(x, 0) for x in pick("mindown", 0)],
        "AllowGig": [yn(x) for x in pick("allowgig","Yes")],
        "AllowNoDL": [yn(x) for x in pick("allownodl","No")],
        "AllowFrame": [yn(x) for x in pick("allowframe","No")],
    })
    out = out[out["Lender"].astype(str).str.strip()!=""].reset_index(drop=True)
    return out

# =========================
# Ohio Inventory Loader (handles your headers)
# =========================
@st.cache_data(show_spinner=False)
def load_inventory_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    inv = pd.read_csv(BytesIO(data)) if ext==".csv" else pd.read_excel(BytesIO(data))
    # Normalize: lower, strip, remove \r and spaces/underscores
    norm = {}
    for c in inv.columns:
        key = c.lower().replace("\r"," ").replace("\n"," ").strip()
        key = " ".join(key.split())  # collapse multiple spaces
        norm[key] = c
    def get(name_list):
        for n in name_list:
            if n in norm: return inv[norm[n]]
        return None

    stock = get(["stock number","stock","stock#","stock_number"]) or pd.Series([""]*len(inv))
    year  = get(["year"])
    make  = get(["make"])
    model = get(["model"])
    style = get(["style","trim"])

    miles = get(["mileage","miles"])
    price = get(["price","sale price","sale_price","cashprice"])
    cost  = get(["total cost","cost","all in cost","acq cost","total_cost"])

    nada_ts = get(["nadat siminv","nada ts","nada trade sub"])
    kbb_ls  = get(["kbbl siminv","kbb lending"])
    bb_wh   = get(["bbwhsale clean","bbwhsale"])
    retail  = get(["nada retail","retail"])
    trade_minus_cost   = get(["trade -cost","trade - cost","trade_minus_cost"])
    lending_minus_cost = get(["lending -cost","lending - cost","lending_minus_cost"])
    bbwclean_minus_cost= get(["bbw clean -cost","bbw clean - cost"])

    df = pd.DataFrame({
        "Stock": stock.astype(str).fillna(""),
        "Year": pd.to_numeric(year, errors="coerce") if year is not None else np.nan,
        "Make": (make.astype(str) if make is not None else pd.Series([""]*len(inv))),
        "Model": (model.astype(str) if model is not None else pd.Series([""]*len(inv))),
        "Style": (style.astype(str) if style is not None else pd.Series([""]*len(inv))),
        "Miles": pd.to_numeric(miles, errors="coerce") if miles is not None else np.nan,
        "Price": pd.to_numeric(price, errors="coerce") if price is not None else np.nan,
        "Cost":  pd.to_numeric(cost,  errors="coerce") if cost  is not None else np.nan,

        "NADA_TS":  pd.to_numeric(nada_ts, errors="coerce") if nada_ts is not None else np.nan,
        "KBB_LS":   pd.to_numeric(kbb_ls,  errors="coerce") if kbb_ls  is not None else np.nan,
        "BB_Wh":    pd.to_numeric(bb_wh,  errors="coerce") if bb_wh  is not None else np.nan,
        "Retail":   pd.to_numeric(retail, errors="coerce") if retail is not None else np.nan,

        "TradeMinusCost":   pd.to_numeric(trade_minus_cost,   errors="coerce") if trade_minus_cost   is not None else np.nan,
        "LendingMinusCost": pd.to_numeric(lending_minus_cost, errors="coerce") if lending_minus_cost is not None else np.nan,
        "BBWCleanMinusCost":pd.to_numeric(bbwclean_minus_cost,errors="coerce") if bbwclean_minus_cost is not None else np.nan,
    })

    # Exclude low-cost units (< $2,000 total cost)
    df = df[~df["Cost"].isna()]
    df = df[df["Cost"] >= 2000].copy()

    # Frame damage: stock numbers starting with X
    df["FrameDamageFlag"] = df["Stock"].str.upper().str.startswith("X")

    # Compute BestSpread using everything available
    best = []
    for _, r in df.iterrows():
        cands = []
        for col in ["LendingMinusCost","TradeMinusCost","BBWCleanMinusCost"]:
            v = r.get(col)
            if pd.notna(v): cands.append(v)
        # derive from books vs cost if present
        if pd.notna(r.get("NADA_TS")) and pd.notna(r.get("Cost")):
            cands.append(r["NADA_TS"] - r["Cost"])
        if pd.notna(r.get("KBB_LS")) and pd.notna(r.get("Cost")):
            cands.append(r["KBB_LS"] - r["Cost"])
        if pd.notna(r.get("BB_Wh")) and pd.notna(r.get("Cost")):
            cands.append(r["BB_Wh"] - r["Cost"])
        if pd.notna(r.get("Retail")) and pd.notna(r.get("Cost")):
            cands.append(r["Retail"] - r["Cost"])
        # fallback to price-cost if needed
        if pd.notna(r.get("Price")) and pd.notna(r.get("Cost")):
            cands.append(r["Price"] - r["Cost"])
        best.append(np.nan if len(cands)==0 else np.nanmax(cands))
    df["BestSpread"] = best

    # Pretty vehicle label
    vm = df[["Year","Make","Model","Style"]].astype(str).agg(" ".join, axis=1).str.replace(" nan","", regex=False).str.replace(" None","", regex=False)
    df["Vehicle"] = vm.str.strip()
    return df.reset_index(drop=True)

# =========================
# Lender logic
# =========================
def score_lender(row, features):
    cred = features["credit"]; repos = features["repos"]; job = features["job_months"]
    income = features["income"] + features["gig_income"]; down = features["down"]
    has_dl = features["has_dl"]; gig = features["gig"]

    # Score window: ignore side that's blank
    lower_ok = True if pd.isna(row.MinScore) else (cred >= row.MinScore)
    upper_ok = True if pd.isna(row.MaxScore) else (cred <= row.MaxScore)
    if not (lower_ok and upper_ok):
        return (False, "Score outside lender window", 0)

    if repos > row.MaxRepos:   return (False, "Too many repos", 0)
    if job < row.MinJobMonths: return (False, "Insufficient job time", 0)
    if income < row.MinIncome: return (False, "Insufficient income", 0)
    if down < row.MinDown:     return (False, "Needs more down", 0)
    if (not row.AllowNoDL) and (has_dl == "No"):
        return (False, "DL required", 0)
    if (not row.AllowGig) and gig and features["gig_income"] > 0:
        return (False, "Gig income not allowed", 0)

    # Ranking: band center closeness + more down/income
    window_mid = np.nanmean([row.MinScore, row.MaxScore])
    if np.isnan(window_mid): window_mid = 625
    score = 100 - abs(features["credit"] - window_mid) * 0.5
    score += min(1000, down) / 20
    score += min(4000, income) / 40
    score += (30 if gig and row.AllowGig else 0)
    score += (10 if has_dl == "Yes" else 0)
    return (True, "Meets program guidelines", round(score,1))

def recommend_lenders(rules_df: pd.DataFrame, features: dict, topn=5):
    rows = []
    for _, r in rules_df.iterrows():
        ok, why, s = score_lender(r, features)
        rows.append({
            "Lender": r.Lender, "Eligible": ok, "Reason": why, "Score": s,
            "MinDown": r.MinDown, "MinIncome": r.MinIncome, "MinJobMonths": r.MinJobMonths,
            "MaxRepos": r.MaxRepos, "AllowFrame": r.AllowFrame, "AllowNoDL": r.AllowNoDL, "AllowGig": r.AllowGig
        })
    df = pd.DataFrame(rows).sort_values(["Eligible","Score"], ascending=[False, False]).reset_index(drop=True)
    top = df[df["Eligible"]].head(topn)
    pick = top.iloc[0] if len(top) else None
    return pick, top, df

# Pmt estimate for affordability filter
def est_payment(amount, apr=0.24, term=72):
    if amount <= 0: return 0.0
    r = apr/12.0
    try:
        return float(amount * (r*(1+r)**term) / ((1+r)**term - 1))
    except ZeroDivisionError:
        return float(amount/term)

def rank_inventory_for_lender(inv: pd.DataFrame, lender_row: pd.Series, features: dict, maxn=5):
    if inv is None or inv.empty: return pd.DataFrame()
    df = inv.copy()

    # Frame rule
    if not bool(lender_row.get("AllowFrame", False)):
        df = df[~df["FrameDamageFlag"]]

    # Affordability — rough PTI cap at ~20% of income
    max_payment = (features["income"] + features["gig_income"]) * 0.20
    financed = (df["Price"].fillna(0) - features["down"]).clip(lower=0)
    df["EstPayment"] = financed.apply(lambda a: est_payment(a, apr=0.24, term=72))

    # Primary ranking by BestSpread; penalize unaffordable
    df["RankScore"] = df["BestSpread"].fillna(-1e9)
    df.loc[df["EstPayment"] > max_payment, "RankScore"] -= 1e6

    show = ["Stock","Vehicle","Miles","Price","Cost","BestSpread","EstPayment","FrameDamageFlag"]
    return df.sort_values("RankScore", ascending=False)[show].head(maxn).reset_index(drop=True)

# =========================
# Session init
# =========================
if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_SAMPLE_RATE_SHEET.copy()
if "inventory" not in st.session_state:
    st.session_state["inventory"] = None

# =========================
# UI
# =========================
st.title("SmartDesk — Desking Assistant")
st.caption("Upload a rate sheet + inventory. Enter basics. Get lender + Top 5 units.")

with st.expander("What files look like", expanded=False):
    st.markdown("""
**Rate Sheet** columns (case-insensitive):  
`Lender, MinScore, MaxScore, MaxRepos, MinJobMonths, MinIncome, MinDown, AllowGig, AllowNoDL, AllowFrame`

**Inventory (Ohio example)** — this app auto-maps your headers like:  
`Stock Number, Year, Make, Model, Style, Mileage, Total Cost, NADAT SimInv, KBBL SimInv, BBWhSale Clean, NADA Retail, Trade - Cost, Lending - Cost, BBW Clean - Cost`
""")

left, right = st.columns([1.25, 1])

with left:
    st.subheader("Deal Input")
    with st.form("deal_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            credit = st.number_input("Credit Score", 300, 850, 620, 1)
            income = st.number_input("Monthly Income ($/mo)", 0, 20000, 3000, 50)
            jy = st.number_input("Job Time (years)", 0, 50, 0, 1)
            jm = st.number_input("Job Time (months)", 0, 11, 6, 1)
            job_months = int(jy)*12 + int(jm)
        with c2:
            repos = st.number_input("# of Repos", 0, 10, 0, 1)
            has_dl = st.selectbox("Driver's License?", ["Yes","No"])
            down = st.number_input("Down Payment ($)", 0, 20000, 1000, 50)
        with c3:
            trade_eq = st.number_input("Trade Equity ($)", -20000, 20000, 0, 100)
            gig_flag = st.checkbox("Gig / DoorDash income?")
            gig_income = st.number_input("Gig Income ($/mo)", 0, 20000, 0, 50, disabled=not gig_flag)

        submitted = st.form_submit_button("Evaluate Deal", type="primary")

with right:
    st.subheader("Uploads")
    # Rate sheet
    rs = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"], key="rs")
    if rs:
        try:
            ext = ".csv" if rs.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["rate_rules"] = load_rate_sheet_from_bytes(rs.read(), ext)
            st.success(f"Loaded {len(st.session_state['rate_rules'])} lenders from **{rs.name}**.")
        except Exception as e:
            st.error(f"Rate sheet error: {e}")

    # Inventory
    inv = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"], key="inv")
    if inv:
        try:
            ext = ".csv" if inv.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["inventory"] = load_inventory_from_bytes(inv.read(), ext)
            st.success(f"Loaded {len(st.session_state['inventory'])} vehicles from **{inv.name}**.")
        except Exception as e:
            st.error(f"Inventory error: {e}")

    with st.expander("Current Rate Rules (top 20)", expanded=False):
        st.dataframe(st.session_state["rate_rules"].head(20), use_container_width=True)
    if st.session_state["inventory"] is not None:
        with st.expander("Inventory Preview (top 20)", expanded=False):
            st.dataframe(st.session_state["inventory"].head(20), use_container_width=True)

st.markdown("---")

# =========================
# Evaluate → Lender + Units
# =========================
if submitted:
    features = {
        "credit": credit, "income": income, "job_months": job_months, "repos": repos,
        "down": down, "trade_eq": trade_eq, "gig": bool(gig_flag),
        "gig_income": (gig_income if gig_flag else 0), "has_dl": has_dl
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
            st.markdown(f"- **Max Repos**: {int(pick['MaxRepos'])}  •  **Min Job**: {int(pick['MinJobMonths'])} mo")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="metric">❌ No Eligible Lender Found</div>', unsafe_allow_html=True)
            st.markdown("Try increasing down, adding a co-app, or choosing a cleaner unit.", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    with cols[1]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="metric">Top 5 Lender Matches</div>', unsafe_allow_html=True)
        if len(top) > 0:
            st.dataframe(
                top[["Lender","Score","Reason","MinDown","MinIncome","MinJobMonths","MaxRepos"]],
                use_container_width=True, height=220
            )
        else:
            st.caption("No eligible lenders with the current inputs.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### Suggested Units")
    inventory_df = st.session_state.get("inventory", None)
    if pick is not None and inventory_df is not None and not inventory_df.empty:
        top_units = rank_inventory_for_lender(inventory_df, pick, features, maxn=5)
        if not top_units.empty:
            st.dataframe(
                top_units.style.format({"Price":"${:,.0f}","Cost":"${:,.0f}","BestSpread":"${:,.0f}","EstPayment":"${:,.0f}"}).set_table_attributes('class="tight"'),
                use_container_width=True, height=260
            )
        else:
            st.caption("No units fit this lender with current inputs.")
    else:
        st.caption("Upload inventory to see vehicle suggestions.")

    # Snapshot / Audit
    st.markdown("### Deal Snapshot")
    st.json({
        "Applicant": {"Score": credit, "Income": income, "JobMonths": job_months, "Repos": repos, "DL": has_dl},
        "Structure": {"Down": down, "TradeEq": trade_eq, "GigIncome": (gig_income if gig_flag else 0)},
        "Decision": {"Lender": (None if pick is None else pick["Lender"]), "ScoreRank": (None if pick is None else pick["Score"])},
    }, expanded=False)

    with st.expander("Audit (all lenders)", expanded=False):
        st.dataframe(audit, use_container_width=True)

else:
    st.info("Fill out the form and click **Evaluate Deal** to see lender + unit picks.")
