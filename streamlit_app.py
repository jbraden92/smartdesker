import streamlit as st
import pandas as pd
from io import BytesIO

# --------------------------
# App Config
# --------------------------
st.set_page_config(page_title="SmartDesk – AI Desking Assistant", page_icon="📋", layout="wide")
st.markdown(
    """
    <style>
    .card {
        border-radius: 10px;
        padding: 14px 16px;
        border: 1px solid rgba(250, 250, 250, 0.12);
        background: rgba(250,250,250,0.03);
    }
    .ok {color: #7DD97C; font-weight:600}
    .warn {color: #F2C14E; font-weight:600}
    .bad {color: #EF6C6C; font-weight:600}
    .em {opacity:0.7}
    .metric {font-size:26px; font-weight:700; margin-bottom:4px}
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
    """Parse a CSV/XLSX file into a normalized lender rule table."""
    if ext == ".csv":
        df = pd.read_csv(BytesIO(data))
    else:
        df = pd.read_excel(BytesIO(data))
    # Normalize columns (case-insensitive)
    cols = {c.lower().strip(): c for c in df.columns}
    get = lambda name: df[cols[name]] if name in cols else None

    def pickcol(name, default=None):
        s = get(name)
        if s is None:
            return [default]*len(df)
        return s

    out = pd.DataFrame({
        "Lender": pickcol("lender", ""),
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
    # Drop blank lenders
    out = out[out["Lender"].astype(str).str.strip()!=""].reset_index(drop=True)
    return out

# Keep the active rule table in session
if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_SAMPLE_RATE_SHEET.copy()

# --------------------------
# Header
# --------------------------
st.title("SmartDesk – Desking Assistant")
st.caption("Upload a rate sheet, enter the customer basics, and get a lender pick + clean structure snapshot.")

with st.expander("How it learns from rate sheets", expanded=False):
    st.markdown(
        """
        - Upload a **CSV/XLSX** with lender rows. Columns it reads (case-insensitive):  
          **Lender, MinScore, MaxScore, MaxRepos, MinJobMonths, MinIncome, MinDown, AllowGig, AllowNoDL, AllowFrame**  
        - As soon as you upload a new sheet, **SmartDesk switches to those rules** for the rest of your session.  
        - You’ll see the top matching lenders + the best pick with a short reason.  
        """
    )

# --------------------------
# Deal Input + Uploads (left/right)
# --------------------------
left, right = st.columns([1.3, 1])

with left:
    st.subheader("Deal Input")
    with st.form("deal_form"):
        col1, col2, col3 = st.columns(3)

        with col1:
            credit = st.number_input("Credit Score", 300, 850, 620, 1)
            income = st.number_input("Monthly Income ($)", 0, 20000, 3000, 50)
            job_months = st.number_input("Job Time (months)", 0, 360, 6, 1)

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
    st.subheader("Rate Sheet")
    rs_file = st.file_uploader("Upload rate sheet (CSV or XLSX)", type=["csv","xlsx"])
    if rs_file is not None:
        try:
            ext = ".csv" if rs_file.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["rate_rules"] = load_rate_sheet_from_bytes(rs_file.read(), ext)
            st.success(f"Loaded {len(st.session_state['rate_rules'])} lender rows from **{rs_file.name}**.")
        except Exception as e:
            st.error(f"Could not read file: {e}")

    with st.expander("See current rules (top 20)", expanded=False):
        st.dataframe(st.session_state["rate_rules"].head(20), use_container_width=True)

# --------------------------
# Decision Logic
# --------------------------
def score_lender(row, features):
    """
    Return (eligible: bool, reason: str, score: float) for a lender row
    based on the current deal 'features'.
    The 'score' ranks eligible lenders (higher = better fit).
    """
    cred = features["credit"]
    repos = features["repos"]
    job = features["job_months"]
    income = features["income"] + features["gig_income"]
    down = features["down"]
    has_dl = features["has_dl"]
    gig = features["gig"]

    # Hard gates
    if not (row.MinScore <= cred <= row.MaxScore):   return (False, "Score outside lender window", 0)
    if repos > row.MaxRepos:                         return (False, "Too many repos for lender", 0)
    if job < row.MinJobMonths:                       return (False, "Insufficient job time", 0)
    if income < row.MinIncome:                       return (False, "Insufficient income", 0)
    if down < row.MinDown:                           return (False, "Needs more down", 0)
    if (not row.AllowNoDL) and (has_dl == "No"):     return (False, "DL required", 0)
    if (not row.AllowGig) and gig and features["gig_income"] > 0:
                                                    return (False, "Gig income not allowed", 0)

    # Soft ranking: prefer near-middle of score window, more down, more income
    # Keep it simple for now.
    window_mid = (row.MinScore + row.MaxScore)/2.0
    score = 0
    score += 100 - abs(cred - window_mid) * 0.5
    score += min(1000, down) / 20
    score += min(4000, income) / 40
    score += (30 if gig and row.AllowGig else 0)
    score += (10 if (has_dl == "Yes") else 0)
    return (True, "Meets program guidelines", score)

def recommend_lenders(rules_df: pd.DataFrame, features: dict, topn=3):
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
            "MaxRepos": r.MaxRepos
        })
    df = pd.DataFrame(rows).sort_values(["Eligible","Score"], ascending=[False, False]).reset_index(drop=True)
    top = df[df["Eligible"]].head(topn)
    pick = top.iloc[0] if len(top) > 0 else None
    return pick, top, df

# --------------------------
# Output
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
    pick, top, audit = recommend_lenders(rules, features, topn=3)

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
        st.markdown('<div class="metric">Top Matches</div>', unsafe_allow_html=True)
        if len(top) > 0:
            st.dataframe(
                top[["Lender","Score","Reason","MinDown","MinIncome","MinJobMonths","MaxRepos"]],
                use_container_width=True, height=180
            )
        else:
            st.caption("No eligible lenders with the current inputs.")
        st.markdown("</div>", unsafe_allow_html=True)

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

