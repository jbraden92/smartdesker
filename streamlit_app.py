import streamlit as st

st.set_page_config(page_title="SmartDesk – POC", page_icon="🚗", layout="wide")

# --- Header ---
st.title("SmartDesk – AI Desking Assistant (POC)")
st.caption("Step 1: Deal input form + uploads. Next step we’ll add lender rules, vehicle picks, and a Promax-style structure.")

with st.expander("How this works", expanded=False):
    st.markdown("""
    **Step 1 (today):** Capture all deal inputs and files in a clean layout.  
    **Step 2 (next):** Add your lender rules, vehicle scoring, Promax-style structure, and a PDF recap export.  
    """)

# --- Deal Input Form ---
st.subheader("Deal Input")

with st.form("deal_form"):
    col1, col2, col3 = st.columns(3)

    with col1:
        credit_score = st.number_input("Credit Score", min_value=350, max_value=850, value=620, step=1)
        monthly_income = st.number_input("Monthly Income ($)", min_value=0, value=3000, step=100)
        job_months = st.number_input("Job Time (months)", min_value=0, value=6, step=1)

    with col2:
        num_repos = st.number_input("# of Repos (reported)", min_value=0, value=0, step=1)
        has_dl = st.selectbox("Driver's License?", ["Yes", "No"])
        down_payment = st.number_input("Down Payment ($)", min_value=0, value=1000, step=100)

    with col3:
        trade_equity = st.number_input("Trade Equity ($)", value=0, step=500, help="Enter negative equity as a negative number")
        gig = st.checkbox("Gig / DoorDash income?")
        gig_income = st.number_input("Gig Income ($/month)", min_value=0, value=0, step=100, disabled=not gig)

    st.markdown("---")
    st.write("**Optional co-applicant**")
    co = st.checkbox("Include Co-Applicant?")
    co_col1, co_col2 = st.columns(2)
    if co:
        with co_col1:
            co_score = st.number_input("Co-Applicant Credit Score", min_value=350, max_value=850, value=610, step=1)
        with co_col2:
            co_income = st.number_input("Co-Applicant Monthly Income ($)", min_value=0, value=0, step=100)
    else:
        co_score, co_income = None, 0

    submitted = st.form_submit_button("Evaluate Deal")

# --- File Uploads (captured, not processed yet) ---
st.subheader("Uploads")
u_col1, u_col2, u_col3, u_col4 = st.columns(4)

with u_col1:
    credit_report = st.file_uploader("Credit Report (PDF / image)", type=["pdf", "png", "jpg", "jpeg"])
with u_col2:
    routeone_pdf = st.file_uploader("RouteOne Deal Recap (PDF)", type=["pdf"])
with u_col3:
    inventory_file = st.file_uploader("Inventory (.csv / .xlsx)", type=["csv", "xlsx"])
with u_col4:
    rate_sheets = st.file_uploader("Rate Sheets (.csv / .xlsx)", type=["csv", "xlsx"])

# --- On Submit: Show Snapshot (Step 1 proof it works) ---
if submitted:
    total_income = monthly_income + (gig_income if gig else 0) + (co_income if co else 0)

    snapshot = {
        "Primary Applicant": {
            "Credit Score": credit_score,
            "Monthly Income": monthly_income,
            "Job Months": job_months,
            "Repos": num_repos,
            "Driver's License": has_dl,
        },
        "Structure": {
            "Down Payment": down_payment,
            "Trade Equity": trade_equity,
        },
        "Co-Applicant": {
            "Included": co,
            "Co Score": co_score if co else None,
            "Co Income": co_income if co else 0,
        },
        "Income": {
            "Base Income": monthly_income,
            "Gig Income": gig_income if gig else 0,
            "Total Income": total_income,
        },
        "Files": {
            "Credit Report Uploaded": bool(credit_report),
            "RouteOne Recap Uploaded": bool(routeone_pdf),
            "Inventory Uploaded": bool(inventory_file),
            "Rate Sheets Uploaded": bool(rate_sheets),
        },
    }

    st.success("✅ Inputs captured. This confirms the UI is working.")
    st.json(snapshot)

    st.info("**Next step**: We’ll add lender fit rules, vehicle selection from your inventory, a Promax-style structure, and a PDF recap button.")
else:
    st.warning("Fill out the form and click **Evaluate Deal** to see the snapshot.")

st.markdown("---")
st.caption("v0.1 POC • SmartDesk")
