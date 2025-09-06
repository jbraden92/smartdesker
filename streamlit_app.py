# streamlit_app.py
import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="SmartDesk — Desking Assistant (POC)", page_icon="📋", layout="wide")

# ---------- Small CSS ----------
st.markdown("""
<style>
.card {border-radius:10px; padding:14px 16px; border:1px solid rgba(250,250,250,0.12); background:rgba(250,250,250,0.03);}
.metric {font-size:22px; font-weight:700; margin-bottom:6px}
.em {opacity:.75}
</style>
""", unsafe_allow_html=True)

# ---------- Helpers ----------
def yn(val):
    if isinstance(val, str):
        return val.strip().lower() in ("y","yes","true","1")
    if isinstance(val, (int, float)):
        return val == 1
    return bool(val)

def _num(x, default=None):
    try:
        if x is None or x == "" or (isinstance(x, float) and pd.isna(x)):
            return default
        return float(x)
    except Exception:
        return default

# ---------- DEFAULT RATE RULES (sample) ----------
DEFAULT_RULES = pd.DataFrame([
    # Gateway/Exeter/CPS: no min score cap per your guidance (blank treated as None)
    {"Lender":"Gateway Financial Solutions","Program":"Select","MinScore":None,"MaxScore":None,"MaxRepos":2,"MinJobMonths":3,"MinIncome":1800,"MinDown":500,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":120,"MaxMiles":150000,"MaxTerm":72},
    {"Lender":"Exeter Finance","Program":"Std","MinScore":None,"MaxScore":None,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2000,"MinDown":500,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":125,"MaxMiles":150000,"MaxTerm":72},
    {"Lender":"CPS","Program":"Std","MinScore":None,"MaxScore":None,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2100,"MinDown":750,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":125,"MaxMiles":165000,"MaxTerm":72},

    # A few more as examples
    {"Lender":"Flagship Credit","Program":"Nickel","MinScore":600,"MaxScore":750,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2400,"MinDown":1000,"AllowGig":True,"AllowNoDL":False,"AllowFrame":True,"MaxLTV":130,"MaxMiles":160000,"MaxTerm":72},
    {"Lender":"Global Lending Services","Program":"Std","MinScore":580,"MaxScore":720,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2200,"MinDown":1000,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":125,"MaxMiles":160000,"MaxTerm":72},
    {"Lender":"Regional Acceptance","Program":"Std","MinScore":590,"MaxScore":720,"MaxRepos":1,"MinJobMonths":12,"MinIncome":2500,"MinDown":1000,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":120,"MaxMiles":140000,"MaxTerm":72},
    {"Lender":"Prestige","Program":"Std","MinScore":600,"MaxScore":750,"MaxRepos":0,"MinJobMonths":12,"MinIncome":2600,"MinDown":1000,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":115,"MaxMiles":140000,"MaxTerm":72},
    {"Lender":"Kemba CU","Program":"CU","MinScore":640,"MaxScore":800,"MaxRepos":0,"MinJobMonths":12,"MinIncome":3000,"MinDown":1000,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":115,"MaxMiles":120000,"MaxTerm":72},
])

# ---------- HARD-WIRED SAMPLE INVENTORY ----------
HARD_INVENTORY = pd.DataFrame([
    {"Stock":"A001","Year":2016,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93580,"Price":9990,"BookValue":11800,"Cost":7990},
    {"Stock":"A002","Year":2017,"Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"Price":10450,"BookValue":12200,"Cost":8450},
    {"Stock":"A003","Year":2014,"Make":"Toyota","Model":"Camry","Trim":"SE","Miles":128590,"Price":8495,"BookValue":10250,"Cost":6495},
    {"Stock":"A004","Year":2015,"Make":"Nissan","Model":"Altima","Trim":"2.5 S","Miles":119400,"Price":7795,"BookValue":9300,"Cost":5895},
    {"Stock":"A005","Year":2016,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111280,"Price":8995,"BookValue":10600,"Cost":6995},
    # These two will be auto-filtered out: Stock starts with T/W or total cost < 4000
    {"Stock":"T200","Year":2016,"Make":"Toyota","Model":"RAV4","Trim":"LE","Miles":99000,"Price":13990,"BookValue":15800,"Cost":11800},  # filtered by Stock=T...
    {"Stock":"W100","Year":2014,"Make":"VW","Model":"Jetta","Trim":"S","Miles":98080,"Price":7990,"BookValue":9100,"Cost":6200},       # filtered by Stock=W...
    {"Stock":"B006","Year":2011,"Make":"Kia","Model":"Soul","Trim":"Base","Miles":171500,"Price":3390,"BookValue":4200,"Cost":3400},  # filtered by total cost < 4000
])

# ---------- SESSION RULES ----------
if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_RULES.copy()

# ---------- Load Rate Sheet ----------
@st.cache_data(show_spinner=False)
def load_rate_sheet_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(data)) if ext == ".csv" else pd.read_excel(BytesIO(data))
    cols = {c.lower().strip(): c for c in df.columns}
    get = lambda k: df[cols[k]] if k in cols else None

    def col(k, default=None, cast="num"):
        s = get(k)
        if s is None:
            return [default]*len(df)
        if cast == "yn":
            return [yn(v) for v in s]
        if cast == "str":
            return [str(v) if (v is not None and not (isinstance(v,float) and pd.isna(v))) else "" for v in s]
        return [_num(v, default) for v in s]

    out = pd.DataFrame({
        "Lender": col("lender", "", "str"),
        "Program": col("program", "", "str"),
        "MinScore": col("minscore", None),
        "MaxScore": col("maxscore", None),
        "MaxRepos": col("maxrepos", 99),
        "MinJobMonths": col("minjobmonths", 0),
        "MinIncome": col("minincome", 0),
        "MinDown": col("mindown", 0),
        "AllowGig": col("allowgig", True, "yn"),
        "AllowNoDL": col("allownodl", False, "yn"),
        "AllowFrame": col("allowframe", False, "yn"),
        "MaxLTV": col("maxltv", None),
        "MaxMiles": col("maxmiles", None),
        "MaxTerm": col("maxterm", None),
    })
    out = out[out["Lender"].astype(str).str.strip()!=""].reset_index(drop=True)
    return out

# ---------- Normalize Inventory ----------
def normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    # Column aliasing
    cols = {c.lower().strip(): c for c in df.columns}
    def take(*names, default=None):
        for n in names:
            if n in cols: return df[cols[n]]
        return pd.Series([default]*len(df))

    out = pd.DataFrame({
        "Stock": take("stock","stock#","stocknum","stocknumber","unit","id","vin", default="").astype(str),
        "Year": take("year", default=None),
        "Make": take("make", default=""),
        "Model": take("model", default=""),
        "Trim": take("trim", default=""),
        "Miles": take("miles","odometer", default=None),
        "Price": take("price","saleprice","retail","list", default=None),
        "BookValue": take("book","kbb","nada","bb","bbwhsale","nadaretail","kbblsim", default=None),
        "Cost": take("cost","totalcost","acq","acquisition","floor","buy","allin", default=None),
    })
    # Numeric
    for c in ("Year","Miles","Price","BookValue","Cost"):
        out[c] = pd.to_numeric(out[c], errors="coerce")

    # Business rules: exclude price+cost total < 4000; exclude Stock starting with W or T
    out["TotalCost"] = out[["Price","Cost"]].sum(axis=1, skipna=True)
    out = out[out["TotalCost"] >= 4000]
    out = out[~out["Stock"].str.upper().str.startswith(("W","T"))]
    out = out.reset_index(drop=True)
    return out

# ---------- Score / Lender logic ----------
def score_lender(row, features, unit=None):
    cred = features["credit"]
    repos = features["repos"]
    job = features["job_months"]
    income = features["income"] + features["gig_income"]
    down = features["down"]
    has_dl = features["has_dl"]
    gig = features["gig"]

    # Hard gates (consumer)
    if row.MinScore is not None and cred is not None and cred < row.MinScore:
        return (False, "Below min score", 0)
    if row.MaxScore is not None and cred is not None and cred > row.MaxScore:
        return (False, "Above max score", 0)
    if repos is not None and row.MaxRepos is not None and repos > row.MaxRepos:
        return (False, "Too many repos", 0)
    if job is not None and row.MinJobMonths is not None and job < row.MinJobMonths:
        return (False, "Insufficient job time", 0)
    if income is not None and row.MinIncome is not None and income < row.MinIncome:
        return (False, "Insufficient income", 0)
    if down is not None and row.MinDown is not None and down < row.MinDown:
        return (False, "Needs more down", 0)
    if (not row.AllowNoDL) and (has_dl == "No"):
        return (False, "DL required", 0)
    if (not row.AllowGig) and gig and features["gig_income"] > 0:
        return (False, "Gig income not allowed", 0)

    # Unit based checks
    if unit is not None:
        # Basic LTV calc (Retail vs Book) – use BookValue if provided
        price = unit.get("Price")
        book = unit.get("BookValue")
        miles = unit.get("Miles")
        # LTV check if book available
        if book and price and row.MaxLTV:
            ltv = (price / book) * 100.0
            if ltv > row.MaxLTV:
                return (False, f"LTV {ltv:.0f}% over lender cap", 0)
        if row.MaxMiles and miles and miles > row.MaxMiles:
            return (False, "Miles exceed cap", 0)
        # Term gate handled in structure display; we do not reject unless term is requested
        if row.MaxTerm and features.get("desired_term"):
            if int(features["desired_term"]) > int(row.MaxTerm):
                return (False, "Term exceeds cap", 0)

    # Soft score
    window_mid = None
    if row.MinScore is not None and row.MaxScore is not None:
        window_mid = (row.MinScore + row.MaxScore)/2.0
    score = 50.0
    if window_mid and cred:
        score += 100 - abs(cred - window_mid)*0.5
    score += min(1000, (down or 0))/20
    score += min(4000, (income or 0))/40
    score += (30 if gig and row.AllowGig else 0)
    score += (10 if (has_dl == "Yes") else 0)
    return (True, "Meets program guidelines", score)

def recommend_lenders(rules: pd.DataFrame, features: dict, topn=5, unit=None):
    """
    Safe even when rules is empty.
    """
    cols = [
        "Lender","Program","Eligible","Reason","Score",
        "MinDown","MinIncome","MinJobMonths","MaxRepos",
        "MaxLTV","MaxMiles","MaxTerm",
    ]
    if rules is None or rules.empty:
        empty = pd.DataFrame(columns=cols)
        return None, empty.copy(), empty.copy()

    rows = []
    for _, r in rules.iterrows():
        ok, why, s = score_lender(r, features, unit)
        rows.append({
            "Lender": r.Lender,
            "Program": r.get("Program",""),
            "Eligible": bool(ok),
            "Reason": why,
            "Score": float(s),
            "MinDown": r.get("MinDown", None),
            "MinIncome": r.get("MinIncome", None),
            "MinJobMonths": r.get("MinJobMonths", None),
            "MaxRepos": r.get("MaxRepos", None),
            "MaxLTV": r.get("MaxLTV", None),
            "MaxMiles": r.get("MaxMiles", None),
            "MaxTerm": r.get("MaxTerm", None),
        })
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = pd.Series(dtype="object")
    if not df.empty:
        df = df.sort_values(["Eligible","Score"], ascending=[False, False]).reset_index(drop=True)
    top = df[df["Eligible"] == True].head(topn) if "Eligible" in df.columns else df.head(0)
    pick = top.iloc[0] if len(top) > 0 else None
    return pick, top, df

# ---------- UI ----------
st.title("SmartDesk — Desking Assistant (POC)")
st.caption("Upload a rate sheet + inventory. Enter basics. Get lender + Top 5 units.")

with st.expander("What files look like", expanded=False):
    st.markdown("""
**Rate sheet (CSV/XLSX)** — columns (case-insensitive OK):  
`Lender, Program, MinScore, MaxScore, MaxRepos, MinJobMonths, MinIncome, MinDown, AllowGig, AllowNoDL, AllowFrame, MaxLTV, MaxMiles, MaxTerm`

**Inventory (CSV/XLSX)** — columns such as:  
`Stock, Year, Make, Model, Trim, Miles, Price, BookValue, Cost`  
*App auto-filters: removes total cost < $4,000 and any Stock starting with W or T.*
    """)

left, right = st.columns([1.2, 1])

with left:
    st.subheader("Deal Input")
    with st.form("deal_input"):
        c1, c2, c3 = st.columns(3)
        with c1:
            credit = st.number_input("Credit Score", 300, 850, 620, 1)
            income = st.number_input("Monthly Income ($/mo)", 0, 20000, 3000, 50)
            job_years = st.number_input("Job Time (years)", 0, 40, 0, 1)
        with c2:
            repos = st.number_input("of Repos (reported)", 0, 10, 0, 1)
            has_dl = st.selectbox("Driver’s License?", ["Yes","No"])
            down = st.number_input("Down Payment ($)", 0, 20000, 1000, 50)
        with c3:
            trade_eq = st.number_input("Trade Equity ($)", -20000, 20000, 0, 100)
            gig_flag = st.checkbox("Gig / DoorDash income?")
            gig_income = st.number_input("Gig Income ($/mo)", 0, 20000, 0, 50)
        job_months = st.number_input("Job Time (months)", 0, 360, 6, 1)
        desired_term = st.number_input("Desired Term (months)", 0, 96, 60, 6)
        include_co = st.checkbox("Include Co-Applicant?")
        if include_co:
            colx, coly = st.columns(2)
            with colx:
                co_score = st.number_input("Co-Applicant Score", 300, 850, 600, 1)
            with coly:
                co_income = st.number_input("Co-Applicant Income ($/mo)", 0, 20000, 0, 50)
        else:
            co_score, co_income = None, 0

        submitted = st.form_submit_button("Evaluate Deal", type="primary")

with right:
    st.subheader("Uploads")
    # Rate sheet
    rs_file = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"])
    if rs_file is not None:
        ext = ".csv" if rs_file.name.lower().endswith(".csv") else ".xlsx"
        try:
            rules = load_rate_sheet_from_bytes(rs_file.read(), ext)
            st.session_state["rate_rules"] = rules
            st.success(f"Loaded {len(rules)} rules from {rs_file.name}.")
        except Exception as e:
            st.error(f"Rate sheet error: {e}")

    # Inventory
    inv_file = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"])
    if inv_file is not None:
        ext = ".csv" if inv_file.name.lower().endswith(".csv") else ".xlsx"
        try:
            inv_raw = pd.read_csv(BytesIO(inv_file.read())) if ext == ".csv" else pd.read_excel(BytesIO(inv_file.read()))
            st.session_state["inventory"] = normalize_inventory(inv_raw)
            st.success(f"Inventory loaded: {len(st.session_state['inventory'])} units after filters.")
        except Exception as e:
            st.error(f"Inventory error: {e}")

    with st.expander("Current Rate Rules (top 20)"):
        st.dataframe(st.session_state["rate_rules"].head(20), use_container_width=True)

st.markdown("---")

# ---------- Ask about a lender rule (simple search) ----------
st.subheader("Ask about a lender rule")
query = st.text_input("Example: Does Exeter allow frame damage? or Gateway gig income?")
if query:
    q = query.strip().lower()
    rules = st.session_state["rate_rules"]
    hits = rules[rules.apply(lambda r: q in f"{r.Lender} {r.Program}".lower(), axis=1)]
    if hits.empty:
        # fallback: search Allow/Min fields in a very simple way
        def row_text(r):
            return " ".join([str(x) for x in [
                r.Lender, r.Program, r.MinScore, r.MaxScore, r.MaxRepos,
                r.MinJobMonths, r.MinIncome, r.MinDown, r.AllowGig,
                r.AllowNoDL, r.AllowFrame, r.MaxLTV, r.MaxMiles, r.MaxTerm
            ]]).lower()
        hits = rules[rules.apply(lambda r: q in row_text(r), axis=1)]

    if hits.empty:
        st.info("No direct match in the current rules.")
    else:
        st.dataframe(hits, use_container_width=True)

# ---------- Evaluate ----------
if submitted:
    rules = st.session_state["rate_rules"]
    features = {
        "credit": credit,
        "income": income,
        "job_months": job_months + job_years*12,
        "repos": repos,
        "down": down,
        "trade_eq": trade_eq,
        "gig": bool(gig_flag),
        "gig_income": gig_income if gig_flag else 0,
        "has_dl": has_dl,
        "co_score": co_score,
        "co_income": co_income,
        "desired_term": desired_term,
    }

    if rules is None or rules.empty:
        st.warning("No rate sheet loaded yet — using defaults. (Upload a sheet to override.)")

    # Inventory: use uploaded, else sample
    inv = st.session_state.get("inventory", None)
    if inv is None or inv.empty:
        inv = normalize_inventory(HARD_INVENTORY.copy())

    # Score each unit to get top 5 picks for this customer profile
    best_rows = []
    for _, unit in inv.iterrows():
        pick, top, audit = recommend_lenders(st.session_state["rate_rules"], features, topn=5, unit=unit)
        # Save the unit if there is at least one eligible lender
        if pick is not None:
            best_rows.append({
                "Stock": unit["Stock"],
                "Year": unit["Year"],
                "Make": unit["Make"],
                "Model": unit["Model"],
                "Trim": unit["Trim"],
                "Miles": unit["Miles"],
                "Price": unit["Price"],
                "BookValue": unit["BookValue"],
                "Picked Lender": pick["Lender"],
                "Why": pick["Reason"],
                "Score": pick["Score"]
            })

    top_units = pd.DataFrame(best_rows).sort_values("Score", ascending=False).head(5).reset_index(drop=True)

    # --- Output ---
    cA, cB = st.columns([1.1, 1])
    with cA:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="metric">Recommended Units (Top 5)</div>', unsafe_allow_html=True)
        if not top_units.empty:
            st.dataframe(top_units, use_container_width=True, height=260)
        else:
            st.caption("No eligible units with current rules/inputs.")
        st.markdown("</div>", unsafe_allow_html=True)

    with cB:
        # Also show currently eligible lenders for the *best* unit (if any)
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="metric">Top Lenders for Best Unit</div>', unsafe_allow_html=True)
        if not top_units.empty:
            best_stock = top_units.iloc[0]["Stock"]
            best_unit = inv[inv["Stock"] == best_stock].iloc[0].to_dict()
            _, top_lenders, audit = recommend_lenders(st.session_state["rate_rules"], features, topn=5, unit=best_unit)
            st.dataframe(top_lenders, use_container_width=True, height=260)
        else:
            st.caption("No lenders to show.")
        st.markdown("</div>", unsafe_allow_html=True)

    # Snapshot
    st.markdown("### Deal Snapshot")
    snapshot = {
        "Primary Applicant": {
            "Credit Score": credit,
            "Monthly Income": income,
            "Job Months": job_months + job_years*12,
            "Repos": repos,
            "Driver's License": has_dl,
        },
        "Structure": {
            "Down Payment": down,
            "Trade Equity": trade_eq,
            "Gig Income": gig_income if gig_flag else 0,
            "Desired Term": desired_term,
        },
        "Co-Applicant": {
            "Included": include_co,
            "Co Score": co_score if include_co else None,
            "Co Income": co_income if include_co else 0,
        }
    }
    st.json(snapshot, expanded=False)
else:
    st.info("Fill out the form and click **Evaluate Deal** to see matches.")
