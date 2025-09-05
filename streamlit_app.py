import streamlit as st
import pandas as pd
import pdfplumber
from sklearn.tree import DecisionTreeClassifier
import json

st.set_page_config(page_title="SmartDesk – AI Desking Assistant", layout="wide")

# --- HEADER ---
st.title("SmartDesk – AI Desking Assistant (POC)")
st.caption("Proof of Concept: Capture deal inputs, evaluate basic lender rules, and upload files.")

with st.expander("ℹ️ How this works"):
    st.markdown("""
    1. Enter deal info (credit score, income, repos, etc.)
    2. Upload files (Credit Report, RouteOne Recap, Inventory, Rate Sheets).
    3. See snapshot + preliminary lender recommendation.
    """)

# --- DEAL INPUT FORM ---
st.subheader("📝 Deal Input")
with st.form("deal_form"):
    col1, col2, col3 = st.columns(3)

    with col1:
        credit_score = st.number_input("Credit Score", 350, 850, 620)
        monthly_income = st.number_input("Monthly Income ($)", 0, 20000, 3000, step=100)
        job_months = st.number_input("Job Time (months)", 0, 360, 6)

    with col2:
        num_repos = st.number_input("# of Repos", 0, 10, 0)
        has_dl = st.selectbox("Driver's License?", ["Yes", "No"])
        down_payment = st.number_input("Down Payment ($)", 0, 20000, 1000, step=100)

    with col3:
        trade_equity = st.number_input("Trade Equity ($)", -10000, 20000, 0)
        gig_income_flag = st.checkbox("Gig / DoorDash income?")
        gig_income = st.number_input("Gig Income ($/month)", 0, 10000, 0, step=50) if gig_income_flag else 0

    # Optional Co-Applicant
    co_app = st.checkbox("Include Co-Applicant?")
    if co_app:
        co_score = st.number_input("Co-Applicant Credit Score", 350, 850, 600)
        co_income = st.number_input("Co-Applicant Income ($)", 0, 20000, 2000, step=100)
    else:
        co_score, co_income = None, 0

    submitted = st.form_submit_button("Evaluate Deal")

# --- UPLOADS ---
st.subheader("📂 Uploads")
credit_report = st.file_uploader("Credit Report (PDF/Image)", type=["pdf", "png", "jpg"])
routeone_pdf = st.file_uploader("RouteOne Deal Recap (PDF)", type=["pdf"])
inventory_file = st.file_uploader("Inventory (.csv/.xlsx)", type=["csv", "xlsx"])
rate_sheets = st.file_uploader("Rate Sheets (.csv/.xlsx)", type=["csv", "xlsx"])

# --- BASIC LENDER RULES ---
def lender_rules(credit_score, num_repos, income, job_months, dp):
    """ Very simple example lender rules (expand later) """
    if credit_score >= 640 and dp >= 1000:
        return "Ally - Near Prime"
    elif credit_score >= 550 and num_repos <= 1 and income >= 2000:
        return "CPS - Subprime"
    elif credit_score >= 500 and job_months >= 6:
        return "Westlake - Deep Subprime"
    else:
        return "Buy Here Pay Here / No Fit"

# --- PROCESS ---
if submitted:
    total_income = monthly_income + gig_income + co_income

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
            "Included": co_app,
            "Co Score": co_score,
            "Co Income": co_income,
        },
        "Income": {
            "Base Income": monthly_income,
            "Gig Income": gig_income,
            "Total Income": total_income,
        },
        "Files": {
            "Credit Report": bool(credit_report),
            "RouteOne Recap": bool(routeone_pdf),
            "Inventory": bool(inventory_file),
            "Rate Sheets": bool(rate_sheets),
        }
    }

    st.success("✅ Deal Captured")
    st.json(snapshot)

    # Evaluate basic lender fit
    decision = lender_rules(credit_score, num_repos, total_income, job_months, down_payment)
    st.subheader("🏦 Recommended Lender")
    st.info(f"**{decision}**")

    # Placeholder: store uploaded deal recaps to learn later
    if routeone_pdf:
        st.write("📌 RouteOne recap uploaded — future versions will extract & learn from this.")

else:
    st.warning("Fill out the form and click 'Evaluate Deal' to see results.")
