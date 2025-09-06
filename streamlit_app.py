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
# Hardwired Inventory (POC)
# --------------------------
HARD_INVENTORY = pd.DataFrame([
    {"Stock":"A001","Year":2016,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93500,"Price":9990,"BookValue":11800},
    {"Stock":"A002","Year":2017,"Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"Price":10450,"BookValue":12200},
    {"Stock":"A003","Year":2014,"Make":"Toyota","Model":"Camry","Trim":"SE","Miles":128500,"Price":8495,"BookValue":10250},
    {"Stock":"A004","Year":2015,"Make":"Nissan","Model":"Altima","Trim":"2.5 S","Miles":119400,"Price":7795,"BookValue":9300},
    {"Stock":"A005","Year":2010,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111200,"Price":8995,"BookValue":10600},
    {"Stock":"A007","Year":2018,"Make":"Hyundai","Model":"Elantra","Trim":"SEL","Miles":84500,"Price":10990,"BookValue":12500},
    {"Stock":"A008","Year":2019,"Make":"Nissan","Model":"Versa","Trim":"SV","Miles":61200,"Price":9995,"BookValue":11200},
])

# Only keep units above $4,000 and exclude stock starting W/T
HARD_INVENTORY = HARD_INVENTORY[
    (HARD_INVENTORY["Price"] >= 4000) &
    (~HARD_INVENTORY["Stock"].str.startswith(("W","T")))
].reset_index(drop=True)

# --------------------------
# Default Sample Rate Sheet
# --------------------------
DEFAULT_RATE_SHEET = pd.DataFrame([
    {"Lender":"Gateway Financial Solutions","Program":"Near/Sub","MinScore":None,"MaxScore":670,"MaxRepos":1,"MinJobMonths":3,"MinIncome":1800,"MinDown":500,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":135,"MaxTerm":72,"MaxMiles":150000},
    {"Lender":"Global Lending Services","Program":"Near/Sub","MinScore":580,"MaxScore":720,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2200,"MinDown":1000,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":124,"MaxTerm":72,"MaxMiles":140000},
    {"Lender":"Flagship Credit","Program":"Near/Sub","MinScore":600,"MaxScore":750,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2400,"MinDown":1000,"AllowGig":True,"AllowNoDL":False,"AllowFrame":True,"MaxLTV":124,"MaxTerm":75,"MaxMiles":150000},
    {"Lender":"Regional Acceptance","Program":"Near/Sub","MinScore":590,"MaxScore":720,"MaxRepos":1,"MinJobMonths":12,"MinIncome":2500,"MinDown":1000,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":124,"MaxTerm":72,"MaxMiles":120000},
    {"Lender":"Prestige","Program":"Near/Sub","MinScore":600,"MaxScore":750,"MaxRepos":0,"MinJobMonths":12,"MinIncome":2600,"MinDown":1000,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":124,"MaxTerm":72,"MaxMiles":100000},
    {"Lender":"Exeter","Program":"Near/Sub","MinScore":550,"MaxScore":700,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2000,"MinDown":500,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":135,"MaxTerm":72,"MaxMiles":150000},
    {"Lender":"Kemba CU","Program":"Prime/CU","MinScore":640,"MaxScore":800,"MaxRepos":0,"MinJobMonths":12,"MinIncome":3000,"MinDown":1000,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False,"MaxLTV":115,"MaxTerm":75,"MaxMiles":100000},
])

if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_RATE_SHEET.copy()

# --------------------------
# Deal Input
# --------------------------
st.subheader("Deal Input")
with st.form("deal_form"):
    col1, col2, col3 = st.columns(3)

    with col1:
        credit = st.number_input("Credit Score", 300, 850, 620, 1)
        income = st.number_input("Monthly Income ($/mo)", 0, 20000, 3000, 50)
        job_years = st.number_input("Job Time (years)", 0, 40, 0, 1)
        job_months = st.number_input("Job Time (months)", 0, 11, 6, 1)

    with col2:
        repos = st.number_input("# of Repos (reported)", 0, 10, 0, 1)
        has_dl = st.selectbox("Driver's License?", ["Yes","No"])
        down = st.number_input("Down Payment ($)", 0, 20000, 1000, 50)

    with col3:
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

# --------------------------
# Lender Fit Function
# --------------------------
def gates_ok(row, F, unit=None):
    cred = F["credit"]
    income = F["income"] + (F["gig_income"] if F["gig"] else 0)
    job_total = F["job_years"]*12 + F["job_months"]

    if row["MinScore"] is not None and cred < row["MinScore"]:
        return False, "Below lender score window"
    if row["MaxScore"] is not None and cred > row["MaxScore"]:
        return False, "Above lender score window"
    if F["repos"] > row["MaxRepos"]:
        return False, "Too many repos"
    if job_total < row["MinJobMonths"]:
        return False, "Insufficient job time"
    if income < row["MinIncome"]:
        return False, "Income too low"
    if F["down"] < row["MinDown"]:
        return False, "Needs more down"
    if not row["AllowNoDL"] and F["has_dl"]=="No":
        return False, "DL required"
    if not row["AllowGig"] and F["gig"] and F["gig_income"]>0:
        return False, "Gig not allowed"
    return True, "Meets program"

# --------------------------
# Evaluate
# --------------------------
if submitted:
    F = {
        "credit": credit,
        "income": income,
        "job_years": job_years,
        "job_months": job_months,
        "repos": repos,
        "down": down,
        "trade_eq": trade_eq,
        "gig": gig_flag,
        "gig_income": gig_income,
        "has_dl": has_dl,
        "co_score": co_score,
        "co_income": co_income
    }

    rules = st.session_state["rate_rules"].copy()
    lenders = []
    for _, r in rules.iterrows():
        ok, why = gates_ok(r, F)
        lenders.append({"Lender": r.Lender, "Program": r.Program, "Reason": why, "Eligible": ok})
    lender_df = pd.DataFrame(lenders).sort_values(["Eligible","Lender"], ascending=[False,True])

    st.markdown("### Top Lender Matches")
    if len(lender_df[lender_df["Eligible"]])>0:
        st.dataframe(lender_df, use_container_width=True)
    else:
        st.warning("No lender fits with the current customer inputs.")

    st.markdown("### Top 5 Units (best lender–unit pairs)")
    best_rows = []
    for _, r in rules.iterrows():
        ok, why = gates_ok(r, F)
        if not ok: continue
        for _, u in HARD_INVENTORY.iterrows():
            adv = (u.Price - trade_eq - down)/max(u.BookValue,1)*100
            if adv <= r.MaxLTV and u.Miles <= r.MaxMiles:
                best_rows.append({
                    "Stock": u.Stock,
                    "Unit": f"{u.Year} {u.Make} {u.Model} {u.Trim}",
                    "Miles": u.Miles,
                    "Price": u.Price,
                    "Book": u.BookValue,
                    "Advance%": round(adv,1),
                    "Lender": r.Lender,
                    "Program": r.Program
                })
    if best_rows:
        st.dataframe(pd.DataFrame(best_rows).sort_values("Advance%", ascending=False).head(5), use_container_width=True)
    else:
        st.warning("No units fit with any lender using these rules & filters.")
