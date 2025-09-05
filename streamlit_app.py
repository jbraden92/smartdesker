# streamlit_app.py
# SmartDesk — Desking Assistant (simple layout)
# - Applicant inputs (years + months)
# - Rate sheet upload (CSV/XLSX) and use for matching
# - Top-5 lender picks
# - Deal snapshot
# - Basic uploads for recap/credit report
# - Optional footer tag with your name

import io
import json
import pandas as pd
import streamlit as st

APP_TITLE  = "SmartDesk — Desking Assistant"
OWNER_NAME = "Built by JBraden"  # set "" to hide

st.set_page_config(page_title="SmartDesk", page_icon="🚘", layout="wide")

# --------------------------
# Helpers
# --------------------------
def yn(val):
    if isinstance(val, str):
        return val.strip().lower() in ("y","yes","true","1")
    if isinstance(val, (int, float)):
        return val == 1
    return bool(val)

@st.cache_data(show_spinner=False)
def load_rate_sheet_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    """Parse CSV/XLSX rate sheet into a normalized rule table."""
    df = pd.read_csv(io.BytesIO(data)) if ext == ".csv" else pd.read_excel(io.BytesIO(data))
    df.columns = [c.strip().lower() for c in df.columns]

    # Expected columns (case-insensitive); we create defaults if missing
    defaults = {
        "lender": "",
        "min_score": 0,
        "max_score": 999,
        "allow_repos": True,
        "max_repos": 99,
        "allow_open_auto": True,
        "min_job_months": 0,
        "require_dl": True,
        "max_pti": 999.0,
        "max_dti": 999.0,
        "tier_label": "",
        "base_buy_rate": 0.0,
        "notes": "",
    }
    for k, v in defaults.items():
        if k not in df.columns:
            df[k] = v

    # Coerce types
    df["min_score"] = pd.to_numeric(df["min_score"], errors="coerce").fillna(0).astype(int)
    df["max_score"] = pd.to_numeric(df["max_score"], errors="coerce").fillna(999).astype(int)
    df["max_repos"] = pd.to_numeric(df["max_repos"], errors="coerce").fillna(99).astype(int)
    df["min_job_months"] = pd.to_numeric(df["min_job_months"], errors="coerce").fillna(0).astype(int)
    for b in ["allow_repos", "allow_open_auto", "require_dl"]:
        df[b] = df[b].apply(yn)
    for n in ["max_pti", "max_dti", "base_buy_rate"]:
        df[n] = pd.to_numeric(df[n], errors="coerce").fillna(0.0)

    # Keep only lenders with a name
    df = df[df["lender"].astype(str).str.strip() != ""].reset_index(drop=True)
    return df

def pick_top_lenders(
    rules: pd.DataFrame,
    score: int,
    job_months: int,
    repos: int,
    has_dl: bool,
    pti: float | None,
    dti: float | None,
    open_auto: bool = False,
    top_k: int = 5,
) -> pd.DataFrame:
    """Simple filter/scoring returning Top-K lenders."""
    if rules is None or rules.empty:
        return pd.DataFrame()

    df = rules.copy()
    # Hard gates
    df = df[
        (df["min_score"] <= score) &
        (df["max_score"] >= score) &
        ((df["allow_repos"]) | (repos == 0)) &
        (df["max_repos"] >= repos) &
        ((df["allow_open_auto"]) | (open_auto == False)) &
        (df["min_job_months"] <= job_months) &
        ((df["require_dl"] == False) | (has_dl == True))
    ]
    if pti is not None and "max_pti" in df.columns:
        df = df[(df["max_pti"] >= pti) | (df["max_pti"] == 0)]
    if dti is not None and "max_dti" in df.columns:
        df = df[(df["max_dti"] >= dti) | (df["max_dti"] == 0)]
    if df.empty:
        return df

    # Soft ranking: center of score band + lower base rate
    df["band_center"] = (df["min_score"] + df["max_score"]) / 2
    df["band_fit"] = -abs(df["band_center"] - score)
    df["rank_score"] = df["band_fit"] - df["base_buy_rate"].fillna(0) * 2.0

    cols = [
        "lender", "tier_label", "base_buy_rate",
        "min_score", "max_score", "max_repos",
        "allow_open_auto", "min_job_months", "require_dl",
        "max_pti", "max_dti", "notes"
    ]
    return df.sort_values("rank_score", ascending=False).head(top_k)[cols].reset_index(drop=True)

# --------------------------
# Header
# --------------------------
st.title(APP_TITLE)
if OWNER_NAME:
    st.caption(OWNER_NAME)

# --------------------------
# Rate Sheet (upload + preview)
# --------------------------
with st.expander("Rate Sheet (CSV/XLSX)", expanded=False):
    up = st.file_uploader("Upload a lender rate sheet", type=["csv", "xlsx"])
    if up:
        try:
            ext = ".csv" if up.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["rules"] = load_rate_sheet_from_bytes(up.read(), ext)
            st.success(f"Loaded {len(st.session_state['rules'])} rows from **{up.name}**.")
        except Exception as e:
            st.error(f"Could not read file: {e}")

    if "rules" in st.session_state and st.session_state["rules"] is not None:
        st.dataframe(st.session_state["rules"].head(20), use_container_width=True)
    else:
        st.caption("Tip: include columns like lender, min_score, max_score, max_repos, min_job_months, require_dl, max_pti, max_dti, tier_label, base_buy_rate, notes.")

st.markdown("---")

# --------------------------
# Deal Input (simple layout)
# --------------------------
st.subheader("Applicant Basics")
with st.form("deal_form"):
    c1, c2, c3 = st.columns(3)
    with c1:
        credit_score = st.number_input("Credit Score", min_value=350, max_value=850, value=620, step=5)
        monthly_income = st.number_input("Monthly Income ($/mo)", min_value=0, value=3000, step=100)
        job_years = st.number_input("Job Time (years)", min_value=0, value=0, step=1)
    with c2:
        job_months_rem = st.number_input("Job Time (months)", min_value=0, max_value=11, value=6, step=1)
        num_repos = st.number_input("# of Repos (reported)", min_value=0, value=0, step=1)
        has_dl = st.selectbox("Driver's License?", ["Yes", "No"])
    with c3:
        down_payment = st.number_input("Down Payment ($)", min_value=0, value=1000, step=100)
        trade_equity = st.number_input("Trade Equity ($)", value=0, step=100)
        include_co = st.checkbox("Include Co-Applicant?")

    co_score, co_income = None, 0
    if include_co:
        co1, co2 = st.columns(2)
        with co1:
            co_score = st.number_input("Co-Applicant Score", min_value=350, max_value=850, value=600, step=5)
        with co2:
            co_income = st.number_input("Co-Applicant Income ($/mo)", min_value=0, value=0, step=100)

    st.markdown("**Optional PTI/DTI check** (enter if you want Top-5 to honor them)")
    c4, c5 = st.columns(2)
    with c4:
        est_payment = st.number_input("Estimated Payment ($/mo)", min_value=0, value=0, step=10)
        pti = round(est_payment / monthly_income * 100.0, 2) if (monthly_income > 0 and est_payment > 0) else None
    with c5:
        other_monthly_debt = st.number_input("Other Monthly Debt ($/mo)", min_value=0, value=0, step=10)
        gross_income = monthly_income + (co_income if include_co else 0)
        dti = round((other_monthly_debt + (est_payment or 0)) / gross_income * 100.0, 2) if gross_income > 0 else None

    submitted = st.form_submit_button("Evaluate Deal", type="primary")

# --------------------------
# Evaluate → Snapshot + Top-5
# --------------------------
if submitted:
    total_job_months = int(job_years * 12 + job_months_rem)
    total_income = monthly_income + (co_income if include_co else 0)

    snapshot = {
        "Primary Applicant": {
            "Credit Score": credit_score,
            "Monthly Income": float(monthly_income),
            "Job Time": f"{job_years}y {job_months_rem}m",
            "Job Months (total)": total_job_months,
            "Repos": int(num_repos),
            "Driver's License": has_dl,
        },
        "Structure": {
            "Down Payment": float(down_payment),
            "Trade Equity": float(trade_equity),
            "PTI%": pti,
            "DTI%": dti,
        },
        "Co-Applicant": {
            "Included": bool(include_co),
            "Co Score": int(co_score) if include_co else None,
            "Co Income": float(co_income) if include_co else 0.0,
        },
    }

    st.success("Deal captured.")
    st.json(snapshot, expanded=False)

    # Top-5 lender picks
    st.subheader("Top-5 Lender Matches")
    rules = st.session_state.get("rules")
    if rules is None or rules.empty:
        st.info("Upload a rate sheet above to see lender matches.")
    else:
        picks = pick_top_lenders(
            rules=rules,
            score=credit_score,
            job_months=total_job_months,
            repos=num_repos,
            has_dl=(has_dl == "Yes"),
            pti=pti,
            dti=dti,
            open_auto=False,
            top_k=5
        )
        if picks.empty:
            st.warning("No lenders matched this profile. Try adjusting DP/PTI/DTI or pick a cleaner unit.")
        else:
            out = picks.copy()
            if "base_buy_rate" in out.columns:
                out["base_buy_rate"] = out["base_buy_rate"].map(lambda x: f"{x:.2f}%")
            st.dataframe(out, use_container_width=True)

    st.markdown("---")
    st.subheader("Uploads (optional)")
    u1, u2 = st.columns(2)
    with u1:
        st.file_uploader("RouteOne Deal Recap (PDF)", type=["pdf"], key="routeone")
    with u2:
        st.file_uploader("Credit Report (PDF/Image)", type=["pdf","png","jpg","jpeg"], key="credit")

else:
    st.info("Fill out the form and click **Evaluate Deal** to see a snapshot and Top-5 lender matches.")

# --------------------------
# Footer
# --------------------------
if OWNER_NAME:
    st.caption(OWNER_NAME)
