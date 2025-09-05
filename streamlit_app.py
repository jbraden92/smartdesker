import streamlit as st
import pandas as pd
from io import BytesIO

# --------------------------
# Page / Style
# --------------------------
st.set_page_config(page_title="SmartDesk – Desking Assistant", page_icon="📋", layout="wide")
st.markdown(
    """
    <style>
      .card {border-radius: 10px; padding: 14px 16px; border: 1px solid rgba(250, 250, 250, 0.12); background: rgba(250,250,250,0.03);}
      .metric {font-size:26px; font-weight:700; margin-bottom:4px}
      .em {opacity:0.8}
      .ok {color:#7DD97C; font-weight:600}
      .warn {color:#F2C14E; font-weight:600}
      .bad {color:#EF6C6C; font-weight:600}
      .small {font-size:12px; opacity:.8}
    </style>
    """,
    unsafe_allow_html=True
)

# --------------------------
# Helpers
# --------------------------
def yn(val, default=False):
    if pd.isna(val):
        return default
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("y","yes","true","1"):
            return True
        if v in ("n","no","false","0"):
            return False
        return default
    if isinstance(val, (int, float)):
        return bool(val)
    return default

def _num(x, default=None):
    try:
        if x in ("", None):
            return default
        return float(x)
    except Exception:
        return default

# --------------------------
# Default Rate Rules
# (No score cap for Gateway, Exeter, CPS)
# Leave MinScore/MaxScore as None to mean "no cap"
# --------------------------
DEFAULT_RATE_RULES = pd.DataFrame([
    # Lender, MinScore, MaxScore, MaxRepos, MinJobMonths, MinIncome, MinDown, AllowGig, AllowNoDL, AllowFrame
    {"Lender":"Gateway Financial Solutions", "MinScore":None, "MaxScore":None, "MaxRepos":1, "MinJobMonths":3,  "MinIncome":1800, "MinDown":500,  "AllowGig":True,  "AllowNoDL":False, "AllowFrame":False},
    {"Lender":"Global Lending Services",     "MinScore":580,  "MaxScore":720,  "MaxRepos":2, "MinJobMonths":6,  "MinIncome":2200, "MinDown":1000, "AllowGig":True,  "AllowNoDL":False, "AllowFrame":False},
    {"Lender":"Flagship Credit",             "MinScore":600,  "MaxScore":750,  "MaxRepos":2, "MinJobMonths":6,  "MinIncome":2400, "MinDown":1000, "AllowGig":True,  "AllowNoDL":False, "AllowFrame":True},
    {"Lender":"Regional Acceptance",         "MinScore":590,  "MaxScore":720,  "MaxRepos":1, "MinJobMonths":12, "MinIncome":2500, "MinDown":1000, "AllowGig":False, "AllowNoDL":False, "AllowFrame":False},
    {"Lender":"Prestige",                    "MinScore":600,  "MaxScore":750,  "MaxRepos":0, "MinJobMonths":12, "MinIncome":2600, "MinDown":1000, "AllowGig":False, "AllowNoDL":False, "AllowFrame":False},
    {"Lender":"Exeter Finance",              "MinScore":None, "MaxScore":None, "MaxRepos":2, "MinJobMonths":6,  "MinIncome":2000, "MinDown":500,  "AllowGig":True,  "AllowNoDL":False, "AllowFrame":False},
    {"Lender":"Consumer Portfolio (CPS)",    "MinScore":None, "MaxScore":None, "MaxRepos":2, "MinJobMonths":6,  "MinIncome":2000, "MinDown":500,  "AllowGig":True,  "AllowNoDL":False, "AllowFrame":False},
    {"Lender":"Kemba CU",                    "MinScore":640,  "MaxScore":800,  "MaxRepos":0, "MinJobMonths":12, "MinIncome":3000, "MinDown":1000, "AllowGig":False, "AllowNoDL":False, "AllowFrame":False},
])

@st.cache_data(show_spinner=False)
def load_rate_sheet_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    """Parse CSV/XLSX → normalized rule table (blank Min/Max score = no cap)."""
    df = pd.read_csv(BytesIO(data)) if ext == ".csv" else pd.read_excel(BytesIO(data))
    cols = {c.lower().strip(): c for c in df.columns}

    def get(name):
        return df[cols[name]] if name in cols else None

    def colnum(s, default=None):
        if s is None:
            return [default]*len(df)
        return [(_num(x, default)) for x in s]

    def colbool(s, default=False):
        if s is None:
            return [default]*len(df)
        return [yn(x, default) for x in s]

    out = pd.DataFrame({
        "Lender":        get("lender") if get("lender") is not None else [""]*len(df),
        "MinScore":      colnum(get("minscore"), default=None),  # None = no cap
        "MaxScore":      colnum(get("maxscore"), default=None),  # None = no cap
        "MaxRepos":      colnum(get("maxrepos"), 99),
        "MinJobMonths":  colnum(get("minjobmonths"), 0),
        "MinIncome":     colnum(get("minincome"), 0),
        "MinDown":       colnum(get("mindown"), 0),
        "AllowGig":      colbool(get("allowgig"), True),
        "AllowNoDL":     colbool(get("allownodl"), False),
        "AllowFrame":    colbool(get("allowframe"), False),
    })
    out = out[out["Lender"].astype(str).str.strip()!=""].reset_index(drop=True)
    return out

if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_RATE_RULES.copy()

# --------------------------
# Default Inventory (POC)
# --------------------------
DEFAULT_SAMPLE_INVENTORY = pd.DataFrame([
    {"Stock":"A001","Year":2016,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93500,"Price":9990,"BookValue":11800},
    {"Stock":"A002","Year":2017,"Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"Price":10450,"BookValue":12200},
    {"Stock":"A003","Year":2014,"Make":"Toyota","Model":"Camry","Trim":"SE","Miles":128500,"Price":8495,"BookValue":10250},
    {"Stock":"A004","Year":2015,"Make":"Nissan","Model":"Altima","Trim":"2.5 S","Miles":119400,"Price":7795,"BookValue":9300},
    {"Stock":"X005","Year":2016,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111200,"Price":8995,"BookValue":10600},  # X=frame flag
    {"Stock":"B006","Year":2011,"Make":"Kia","Model":"Soul","Trim":"Base","Miles":171500,"Price":3390,"BookValue":4200},   # will be excluded (<4500)
    {"Stock":"B007","Year":2010,"Make":"Hyundai","Model":"Sonata","Trim":"GLS","Miles":189000,"Price":2995,"BookValue":3900},# excluded
    {"Stock":"B008","Year":2012,"Make":"Chevrolet","Model":"Cruze","Trim":"LS","Miles":164200,"Price":4295,"BookValue":5200}, # excluded
])

def normalize_inventory(df: pd.DataFrame):
    """Return (clean_df, excluded_count). Filters out Price < $4500."""
    if df is None or len(df) == 0:
        return pd.DataFrame(), 0
    raw = df.copy()
    cols = {c.lower().strip(): c for c in raw.columns}

    def pick(name, *aliases, default=None):
        for key in (name, *aliases):
            if key in cols:
                return raw[cols[key]]
        return default

    out = pd.DataFrame({
        "Stock":     pick("stock", "stock#", "stocknum", "stock number", default=pd.Series([""]*len(raw))),
        "Year":      pd.to_numeric(pick("year", default=pd.Series([None]*len(raw))), errors="coerce"),
        "Make":      pick("make", default=pd.Series([""]*len(raw))),
        "Model":     pick("model", default=pd.Series([""]*len(raw))),
        "Trim":      pick("trim", default=pd.Series([""]*len(raw))),
        "Miles":     pd.to_numeric(pick("miles","mileage", default=pd.Series([None]*len(raw))), errors="coerce"),
        "Price":     pd.to_numeric(pick("price","total cost","cost","selling price","sale price", default=pd.Series([None]*len(raw))), errors="coerce"),
        "BookValue": pd.to_numeric(pick("kbblsim","bbwhsale","nadasiminv","nada retail","book","bookvalue", default=pd.Series([None]*len(raw))), errors="coerce"),
    })
    out["Spread"] = (out["BookValue"] - out["Price"]).fillna(0)
    out["Frame"]  = out["Stock"].astype(str).str.upper().str.startswith("X")
    out["Label"]  = (
        out["Year"].fillna("").astype(str).str.replace(".0","",regex=False).str.strip() + " " +
        out["Make"].fillna("").astype(str).str.strip() + " " +
        out["Model"].fillna("").astype(str).str.strip() + " " +
        out["Trim"].fillna("").astype(str).str.strip()
    ).str.replace(r"\s+"," ", regex=True).str.strip()

    before = len(out)
    out = out[pd.to_numeric(out["Price"], errors="coerce") >= 4500]
    excluded = before - len(out)

    out = out.reset_index(drop=True)
    return out, excluded

# --------------------------
# Lender Decision
# --------------------------
def score_lender(row, fx):
    """Return (eligible, reason, score). No-score-cap lenders use None bounds."""
    cred = fx["credit"]
    repos = fx["repos"]
    job   = fx["job_months"]
    income = fx["income"] + fx["gig_income"]
    down   = fx["down"]
    has_dl = fx["has_dl"]
    gig    = fx["gig"]

    # Hard gates
    if (row.MinScore is not None) and (cred < row.MinScore):
        return (False, f"Min score {int(row.MinScore)}", 0)
    if (row.MaxScore is not None) and (cred > row.MaxScore):
        return (False, f"Max score {int(row.MaxScore)}", 0)
    if repos > (row.MaxRepos or 0):
        return (False, "Too many repos", 0)
    if job < (row.MinJobMonths or 0):
        return (False, "Insufficient job time", 0)
    if income < (row.MinIncome or 0):
        return (False, "Insufficient income", 0)
    if down < (row.MinDown or 0):
        return (False, "Needs more down", 0)
    if (not row.AllowNoDL) and (has_dl == "No"):
        return (False, "DL required", 0)
    if (not row.AllowGig) and gig and fx["gig_income"] > 0:
        return (False, "Gig income not allowed", 0)

    # Soft ranking
    score = 0.0
    if (row.MinScore is not None) and (row.MaxScore is not None):
        window_mid = (row.MinScore + row.MaxScore)/2.0
        score += 100 - abs(cred - window_mid) * 0.5
    else:
        score += 90  # no-cap lenders get a base bump so they can still rank

    score += min(1000, down) / 20
    score += min(4000, income) / 40
    score += (30 if gig and row.AllowGig else 0)
    score += (10 if (has_dl == "Yes") else 0)
    return (True, "Meets program guidelines", round(score,1))

def recommend_lenders(rules_df: pd.DataFrame, fx: dict, topn=3):
    rows = []
    for _, r in rules_df.iterrows():
        ok, why, s = score_lender(r, fx)
        rows.append({
            "Lender": r.Lender,
            "Eligible": ok,
            "Reason": why,
            "Score": s,
            "MinDown": r.MinDown,
            "MinIncome": r.MinIncome,
            "MinJobMonths": r.MinJobMonths,
            "MaxRepos": r.MaxRepos,
            "MinScore": r.MinScore,
            "MaxScore": r.MaxScore
        })
    df = pd.DataFrame(rows).sort_values(["Eligible","Score"], ascending=[False, False]).reset_index(drop=True)
    top = df[df["Eligible"]].head(topn)
    pick = top.iloc[0] if len(top) > 0 else None
    return pick, top, df

# --------------------------
# Unit Scoring / Selection
# --------------------------
def score_unit(r, lender_row):
    """Simple unit score: spread heavy, miles light, frame slight penalty."""
    spread = _num(r["Spread"], 0) or 0
    miles  = _num(r["Miles"], 0) or 0
    frame  = bool(r["Frame"])
    score = spread * 0.7 + max(0, 160000 - miles) / 800
    if frame and not getattr(lender_row, "AllowFrame", False):
        score -= 10
    return round(score, 2)

def pick_units_for_lender(inventory_df: pd.DataFrame, lender_row: dict, topn=5):
    if inventory_df is None or len(inventory_df) == 0 or lender_row is None:
        return pd.DataFrame()
    work = inventory_df.copy()
    work = work[pd.to_numeric(work["Price"], errors="coerce") >= 4500]  # safeguard
    work["UnitScore"] = work.apply(lambda r: score_unit(r, lender_row), axis=1)
    work = work.sort_values("UnitScore", ascending=False).head(topn)
    return work[["Stock","Label","Miles","Price","BookValue","Spread","Frame","UnitScore"]]

# --------------------------
# UI
# --------------------------
st.title("SmartDesk – Desking Assistant")
st.caption("Upload a rate sheet + inventory. Enter basics. Get lender + Top 5 units. Blanks for Min/Max score = **no cap**.")

with st.expander("What files look like", expanded=False):
    st.markdown(
        """
        **Rate sheet** (CSV/XLSX):  
        Lender, MinScore, MaxScore, MaxRepos, MinJobMonths, MinIncome, MinDown, AllowGig, AllowNoDL, AllowFrame  
        - Leave **MinScore/MaxScore blank** for **no score cap** (e.g., Gateway, Exeter, CPS).

        **Inventory** (CSV/XLSX):  
        Stock, Year, Make, Model, Trim, Miles, Price (total cost), and a book value column like KBB/BlackBook/NADA.  
        - Units with **Price < $4,500 are auto-excluded**.
        - Stock starting with **X** is treated as frame-damage flag.
        """
    )

# --- Inputs ---
left, right = st.columns([1.35, 1])

with left:
    st.subheader("Deal Input")
    with st.form("deal_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            credit = st.number_input("Credit Score", 300, 850, 620, 1)
            income = st.number_input("Monthly Income ($/mo)", 0, 20000, 3000, 50)
            job_months = st.number_input("Job Time (months)", 0, 360, 6, 1)
        with c2:
            repos = st.number_input("# of Repos (reported)", 0, 10, 0, 1)
            has_dl = st.selectbox("Driver's License?", ["Yes","No"])
            down = st.number_input("Down Payment ($)", 0, 20000, 1000, 50)
        with c3:
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
            co_score = None
            co_income = 0

        submitted = st.form_submit_button("Evaluate Deal", type="primary")

with right:
    st.subheader("Uploads")

    # Rate rules
    rs_file = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"], key="rs_up")
    if rs_file is not None:
        try:
            ext = ".csv" if rs_file.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["rate_rules"] = load_rate_sheet_from_bytes(rs_file.read(), ext)
            st.success(f"Loaded {len(st.session_state['rate_rules'])} rules from {rs_file.name}")
        except Exception as e:
            st.error(f"Rate sheet error: {e}")

    # Inventory upload or default
    inv_file = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"], key="inv_up")
    inventory_df = pd.DataFrame(); excluded_under_4500 = 0
    try:
        if inv_file is not None:
            inv_ext = ".csv" if inv_file.name.lower().endswith(".csv") else ".xlsx"
            raw_inv = pd.read_csv(BytesIO(inv_file.read())) if inv_ext == ".csv" else pd.read_excel(BytesIO(inv_file.read()))
            inventory_df, excluded_under_4500 = normalize_inventory(raw_inv)
            st.success(f"Inventory loaded: {len(inventory_df)} units (excluded {excluded_under_4500} under $4,500).")
        else:
            inventory_df, excluded_under_4500 = normalize_inventory(DEFAULT_SAMPLE_INVENTORY)
            st.info(f"Using built-in sample inventory: {len(inventory_df)} units (excluded {excluded_under_4500} under $4,500).")
    except Exception as e:
        st.error(f"Inventory error: {e}")

    with st.expander("Current Rate Rules (top 20)", expanded=False):
        st.dataframe(st.session_state["rate_rules"].head(20), use_container_width=True, height=300)

    with st.expander("Preview inventory (cleaned)", expanded=False):
        if len(inventory_df) > 0:
            st.dataframe(
                inventory_df[["Stock","Label","Miles","Price","BookValue","Spread","Frame"]],
                use_container_width=True, height=300
            )
        else:
            st.caption("No inventory loaded yet.")

# --------------------------
# Decision + Output
# --------------------------
if submitted:
    fx = {
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
    pick, top, audit = recommend_lenders(rules, fx, topn=3)

    st.markdown("### Result")
    cL, cR = st.columns([1.1, 1])
    with cL:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        if pick is not None:
            st.markdown('<div class="metric">✅ Recommended Lender</div>', unsafe_allow_html=True)
            st.markdown(f"**{pick['Lender']}**  \n<span class='em'>{pick['Reason']}</span>", unsafe_allow_html=True)
            # Scores and mins
            ms = "—" if pd.isna(pick['MinScore']) or pick['MinScore'] is None else int(pick['MinScore'])
            xs = "—" if pd.isna(pick['MaxScore']) or pick['MaxScore'] is None else int(pick['MaxScore'])
            st.markdown(f"- **Score Window**: {ms} – {xs}")
            st.markdown(f"- **Min Down**: ${int(pick['MinDown'] or 0)}  •  **Min Income**: ${int(pick['MinIncome'] or 0)}/mo")
            st.markdown(f"- **Max Repos**: {int(pick['MaxRepos'] or 0)}  •  **Min Job**: {int(pick['MinJobMonths'] or 0)} mo")
        else:
            st.markdown('<div class="metric">❌ No Eligible Lender Found</div>', unsafe_allow_html=True)
            st.markdown("Try more down, add co-app, or pick a cleaner unit.", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with cR:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="metric">Top Lender Matches</div>', unsafe_allow_html=True)
        if len(top) > 0:
            st.dataframe(
                top[["Lender","Score","Reason","MinScore","MaxScore","MinDown","MinIncome","MinJobMonths","MaxRepos"]],
                use_container_width=True, height=210
            )
        else:
            st.caption("No eligible lenders with the current inputs.")
        st.markdown("</div>", unsafe_allow_html=True)

    # Units for recommended lender
    st.markdown("### Suggested Units (Top 5)")
    if pick is not None and len(inventory_df) > 0:
        # Find the underlying rule row for frame permission
        rule_row = rules[rules["Lender"] == pick["Lender"]]
        lender_rule = rule_row.iloc[0] if len(rule_row) else None
        top_units = pick_units_for_lender(inventory_df, lender_rule, topn=5)
        if len(top_units) > 0:
            st.dataframe(top_units, use_container_width=True, height=300)
            st.caption(f"{excluded_under_4500} unit(s) were filtered out for being under $4,500.")
        else:
            st.caption("No units pass the cost filter or scoring.")
    else:
        st.caption("Load inventory and/or get a recommended lender to see unit picks.")

    # Snapshot + full audit
    with st.expander("Deal Snapshot", expanded=False):
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
        st.dataframe(audit, use_container_width=True, height=350)

else:
    st.info("Fill out the form and click **Evaluate Deal**.")
