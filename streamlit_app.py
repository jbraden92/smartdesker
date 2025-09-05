# streamlit_app.py
import math
import streamlit as st

st.set_page_config(page_title="SmartDesk – POC", page_icon="🚗", layout="wide")

# ---------------------------
# Utilities
# ---------------------------

def pmt(annual_rate, n_months, principal):
    """Basic monthly payment calculator. If principal is 0, returns 0."""
    if principal <= 0:
        return 0.0
    r = (annual_rate or 0) / 12.0
    if abs(r) < 1e-9:
        return round(principal / max(n_months, 1), 2)
    return round((r * principal) / (1 - (1 + r) ** (-n_months)), 2)

def bucket_apr(score: int) -> float:
    """Very rough APR buckets to estimate a payment for structure context."""
    if score >= 660:
        return 0.1299  # prime-ish
    if score >= 600:
        return 0.1949  # near-prime
    return 0.2499      # subprime

def lender_notes():
    return {
        "Ally": "Prime. Clean file, full DL required. Strong income, no recent repos.",
        "Gateway Financial Solutions": "Near-prime/subprime. DL required. ≤1 repo; avoid open autos (shop rule).",
        "Global Lending Services": "Near-prime. Prefers 580+, stable job time. Avoid very recent repos.",
        "Exeter Finance": "Subprime. DL required. ≤1 older repo preferred.",
        "Westlake Financial": "Wide box, flexible on score/income. Good for gig income. Watch rate.",
        "Kemba CU": "Credit union/prime. Clean history. Uses retail/NADA for LTV (prime logic).",
        "Flagship Credit Acceptance": "Deep subprime. Income ≥ 1800, watch LTV (~125% cap typical).",
        "Consumer Portfolio Services": "Deep subprime. DL required. Can stretch but rate is high.",
        "Regional Acceptance": "Subprime. Income strength matters; repos should be older/limited.",
    }

def recommend_lenders(
    credit_score: int,
    monthly_income: float,
    job_months: int,
    num_repos: int,
    has_dl: str,
    gig_on: bool,
    gig_income: float,
    trade_equity: float,
    down_payment: float,
):
    """
    Very simple hard-coded rule set. These are *starting points* you can tweak.
    We only use inputs you’re collecting today (no open-auto/DTI pull here).
    """
    lenders = []

    # Normalize
    has_driver_license = (has_dl or "").strip().lower().startswith("y")
    base_income = monthly_income or 0
    extra_gig = gig_income if gig_on else 0
    total_income = base_income + extra_gig

    # 1) Prime-ish: Ally / Kemba CU
    if credit_score >= 640 and has_driver_license and num_repos == 0 and job_months >= 6 and total_income >= 2000:
        lenders.append("Ally")
    if credit_score >= 660 and has_driver_license and num_repos == 0 and job_months >= 12 and total_income >= 2500:
        lenders.append("Kemba CU")

    # 2) Near-prime/Subprime: GFS, GLS, Exeter
    # GFS: “allows only 1 repo and no open autos; DL required”
    if has_driver_license and num_repos <= 1 and credit_score >= 540 and total_income >= 1800 and job_months >= 3:
        lenders.append("Gateway Financial Solutions")

    # GLS: prefers 580+, stable job; no recent repo
    if credit_score >= 580 and has_driver_license and job_months >= 3 and num_repos <= 1 and total_income >= 1800:
        lenders.append("Global Lending Services")

    # Exeter: subprime with ≤1 older repo (we only check count here)
    if credit_score >= 560 and has_driver_license and num_repos <= 1 and job_months >= 6 and total_income >= 1700:
        lenders.append("Exeter Finance")

    # 3) Broad box: Westlake, CPS, Flagship, Regional
    if has_driver_license and total_income >= 1500 and credit_score >= 500:
        lenders.append("Westlake Financial")

    if has_driver_license and total_income >= 1800 and credit_score >= 520:
        lenders.append("Flagship Credit Acceptance")

    if has_driver_license and total_income >= 1700 and credit_score >= 500:
        lenders.append("Consumer Portfolio Services")

    if has_driver_license and total_income >= 2000 and credit_score >= 560 and num_repos <= 1:
        lenders.append("Regional Acceptance")

    # De-dup while preserving order
    dedup = []
    for L in lenders:
        if L not in dedup:
            dedup.append(L)
    return dedup, total_income

# ---------------------------
# UI
# ---------------------------

st.title("SmartDesk – AI Desking Assistant (POC)")
with st.expander("How this works", expanded=False):
    st.markdown(
        """
        **Step 1 (today):** Capture the basic deal inputs and any files you want to keep with the desk  
        **Step 2 (soon):** Add embedded bank rules (your gray), vehicle picks by book/advance, a Promax-style structure, and a PDF recap.
        """
    )

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
        trade_equity = st.number_input("Trade Equity ($)", min_value=-50000, value=0, step=500)
        gig_on = st.checkbox("Gig / DoorDash income?")
        gig_income = st.number_input("Gig Income ($/month)", min_value=0, value=0, step=50, disabled=not gig_on)

    st.markdown("---")
    co = st.checkbox("Include Co-Applicant?")
    if co:
        co_cols = st.columns(2)
        with co_cols[0]:
            co_score = st.number_input("Co-Applicant Credit Score", min_value=350, max_value=850, value=600, step=1)
        with co_cols[1]:
            co_income = st.number_input("Co-Applicant Income ($/month)", min_value=0, value=0, step=100)
    else:
        co_score, co_income = None, 0

    submitted = st.form_submit_button("Evaluate Deal")

# Uploads (kept simple; parsing comes later)
st.subheader("Uploads")
up_cols = st.columns(4)
with up_cols[0]:
    credit_report = st.file_uploader("Credit Report (PDF / image)", type=["pdf", "png", "jpg", "jpeg"])
with up_cols[1]:
    routeone_pdf = st.file_uploader("RouteOne Deal Recap (PDF)", type=["pdf"])
with up_cols[2]:
    inventory_file = st.file_uploader("Inventory (.csv / .xlsx)", type=["csv", "xlsx"])
with up_cols[3]:
    rate_sheets = st.file_uploader("Rate Sheets (.csv / .xlsx)", type=["csv", "xlsx"], accept_multiple_files=True)

# ---------------------------
# Evaluation
# ---------------------------

if submitted:
    # Build the snapshot
    total_income = (monthly_income or 0) + (gig_income if gig_on else 0) + (co_income or 0)

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
            "Gig Income": gig_income if gig_on else 0,
            "Total Income": total_income,
        },
        "Files": {
            "Credit Report Uploaded": bool(credit_report),
            "RouteOne Recap Uploaded": bool(routeone_pdf),
            "Inventory Uploaded": bool(inventory_file),
            "Rate Sheets Uploaded": bool(rate_sheets),
        },
    }

    # Lender recommendations
    recs, total_income_calc = recommend_lenders(
        credit_score=credit_score,
        monthly_income=monthly_income,
        job_months=job_months,
        num_repos=num_repos,
        has_dl=has_dl,
        gig_on=gig_on,
        gig_income=gig_income,
        trade_equity=trade_equity,
        down_payment=down_payment,
    )
    snapshot["Recommended Lenders"] = recs if recs else ["No fit found"]

    # Provide a simple structure suggestion placeholder
    # (When you wire inventory in, you’ll replace principal with (Price + TTL - DP - Trade equity).)
    # For now, we just show an *affordability* example using ~20% of total income as target payment.
    target_payment = round(max(total_income_calc * 0.2, 150), 2)
    apr_guess = bucket_apr(credit_score)
    for term in (60, 69, 72, 75):
        # Reverse-calc a "principal capacity" at target payment for quick context
        r = apr_guess / 12.0
        if abs(r) < 1e-9:
            capacity = target_payment * term
        else:
            capacity = target_payment * (1 - (1 + r) ** (-term)) / r
        snapshot.setdefault("Structure Suggestions", []).append(
            {
                "Term": term,
                "APR (est)": f"{round(apr_guess*100,2)}%",
                "Target Payment (~20% income)": target_payment,
                "Supports Principal ≈": round(capacity, 2),
                "Note": "Replace principal with your real cash price calc once inventory is wired in."
            }
        )

    # Show results
    st.success("Inputs captured. Here’s the snapshot + lender recs.")
    st.json(snapshot)

    st.subheader("Recommended Lenders (with quick notes)")
    if recs:
        notes = lender_notes()
        for L in recs:
            st.markdown(f"- **{L}** — {notes.get(L, 'No note yet.')}")
    else:
        st.info("No lender fit matched these quick rules. Tweak inputs or use a different structure.")

    st.caption("Next up: wire in your Kokomo rules, inventory pick by book/advance, and PDF recap export.")
else:
    st.info("Fill out the form and click **Evaluate Deal** to see the snapshot and lender recommendations.")
