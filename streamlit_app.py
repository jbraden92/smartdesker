import streamlit as st
import pandas as pd
from io import BytesIO

# --------------------------
# App Config
# --------------------------
st.set_page_config(page_title="SmartDesk – Desking Assistant", page_icon="📋", layout="wide")
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

            # Years + Months -> total job months
            job_years = st.number_input("Job Time (years)", 0, 60, 0, 1)
            job_months_extra = st.number_input("Job Time (months)", 0, 11, 6, 1)
            job_months = job_years * 12 + job_months_extra

        with col2:
            repos = st.number_input("# of Repos (reported)", 0, 10, 0, 1)
            has_dl = st.selectbox("Driver's License?", ["Yes","No"])
            down = st.number_input("Down Payment ($)", 0, 20000, 1000, 50)

        with col3:
            trade_eq = st.number_input("Trade Equity ($)", -20000, 20000, 0, 100)
            gig_flag = st.checkbox("Gig / DoorDash income?")
            gig_income = st.number_input("Gig Income ($/month)", 0, 20000, 0, 50, disabled=not gig_flag)

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
            st.success(f"Loaded {len
