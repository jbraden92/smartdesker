# -----------------------------
# SmartDesk – Desking Assistant (RightWay Edition)
# -----------------------------
# Branding + roles + lender picks + snapshot
# -----------------------------

import io
import json
import base64
import pandas as pd
import numpy as np
import streamlit as st

# ==============
# BRAND SETTINGS
# ==============
DEALERSHIP_NAME = "RightWay Auto Sales"
OWNER_NAME = "Built by JBraden"
APP_NAME = "SmartDesk – Desking Assistant"

# Approx RightWay palette (adjust anytime)
COLOR_PRIMARY = "#C8102E"    # deep red
COLOR_DARK = "#121316"       # app background
COLOR_CARD = "#1A1C1F"       # card bg
COLOR_TEXT = "#E9ECF1"       # body text
COLOR_MUTED = "#9AA3AE"
COLOR_ACCENT = "#27AE60"     # success green
COLOR_WARNING = "#F39C12"    # amber

# ==============
# SIMPLE AUTH / ROLES  (prototype)
# Replace later with Okta/AzureAD/streamlit-authenticator
# ==============
DEMO_USERS = {
    # username: {password, role}
    "rep":     {"password": "rep123", "role": "sales"},
    "manager": {"password": "mgr123", "role": "manager"},
    "admin":   {"password": "adm123", "role": "admin"},
}
VALID_ROLES = ["sales", "manager", "admin"]

# ========
# CSS THEME
# ========
CSS = f"""
<style>
/* Layout */
.stApp {{
  background: {COLOR_DARK};
  color: {COLOR_TEXT};
}}
/* Sidebar */
[data-testid="stSidebar"] {{
  background: {COLOR_CARD};
  border-right: 1px solid #24262B;
}}
/* Headers */
h1, h2, h3, h4, h5 {{
  color: {COLOR_TEXT};
}}
/* Buttons */
.stButton>button {{
  background: {COLOR_PRIMARY};
  color: white;
  border: 1px solid {COLOR_PRIMARY};
  border-radius: 10px;
}}
.stButton>button:hover {{
  filter: brightness(1.08);
}}
/* Inputs / cards */
.block-container {{
  padding-top: 1rem;
}}
.stTextInput>div>div>input,
.stNumberInput input,
.stSelectbox div[data-baseweb="select"]>div {{
  background: {COLOR_CARD};
  color: {COLOR_TEXT};
  border: 1px solid #2A2D33;
  border-radius: 8px;
}}
.stDownloadButton button {{
  background: {COLOR_ACCENT};
  color: white;
  border: none;
}}
/* Pills / tags */
.badge {{
  display:inline-block;
  padding:.2rem .5rem;
  border-radius:999px;
  font-size:.78rem;
  font-weight:600;
  margin-left:.5rem;
}}
.badge-sales {{ background:#2D6CDF; color:white; }}
.badge-manager {{ background:#8E44AD; color:white; }}
.badge-admin {{ background:#16A085; color:white; }}
/* Footer */
.footer-wrap {{
  margin-top: 1rem;
  padding-top: .75rem;
  border-top: 1px dashed #2b2e34;
  color: {COLOR_MUTED};
  font-size: .9rem;
}}
/* Table polish */
table td, table th {{
  border-color: #2C2F35 !important;
}}
</style>
"""

# ==============
# UTILITIES
# ==============
def yn(val):
    if isinstance(val, str):
        return val.strip().lower() in ("y", "yes", "true", "1")
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
    """
    Parse a CSV/XLSX rate sheet into a normalized rule table.
    Supported headers (examples):
      lender, min_score, max_score, allow_repos, max_repos, allow_open_auto, min_job_months,
      require_dl, max_pti, max_dti, tier_label, base_buy_rate, notes
    """
    if ext == ".csv":
        df = pd.read_csv(io.BytesIO(data))
    else:
        df = pd.read_excel(io.BytesIO(data))
    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]

    # Create safe defaults if any column missing
    expected = {
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
    for k, default in expected.items():
        if k not in df.columns:
            df[k] = default

    # Coerce types
    df["min_score"] = pd.to_numeric(df["min_score"], errors="coerce").fillna(0).astype(int)
    df["max_score"] = pd.to_numeric(df["max_score"], errors="coerce").fillna(999).astype(int)
    df["max_repos"] = pd.to_numeric(df["max_repos"], errors="coerce").fillna(0).astype(int)
    df["min_job_months"] = pd.to_numeric(df["min_job_months"], errors="coerce").fillna(0).astype(int)
    for b in ["allow_repos", "allow_open_auto", "require_dl"]:
        df[b] = df[b].apply(yn)
    for n in ["max_pti", "max_dti", "base_buy_rate"]:
        df[n] = pd.to_numeric(df[n], errors="coerce").fillna(0.0)

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
    """Simple filter/scoring that returns the top K lenders."""
    if rules is None or rules.empty:
        return pd.DataFrame()

    df = rules.copy()

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

    # Simple score — closer to mid-band + lower base rate
    df["band_center"] = (df["min_score"] + df["max_score"]) / 2
    df["band_fit"] = -abs(df["band_center"] - score)
    df["rank_score"] = df["band_fit"] - df["base_buy_rate"].fillna(0) * 2.0

    df = df.sort_values(["rank_score"], ascending=False)
    return df.head(top_k)[[
        "lender", "tier_label", "base_buy_rate", "min_score", "max_score",
        "max_repos", "allow_open_auto", "min_job_months", "require_dl", "max_pti", "max_dti", "notes"
    ]].reset_index(drop=True)

def pdf_download_button(filename: str, content: str, label: str):
    b64 = base64.b64encode(content.encode("utf-8")).decode()
    href = f'<a download="{filename}" href="data:text/plain;base64,{b64}"><button class="css-1n543e5 edgvbvh4">{label}</button></a>'
    st.markdown(href, unsafe_allow_html=True)

# =========
# SESSION
# =========
if "user" not in st.session_state:
    st.session_state.user = None         # dict like {"name":..., "role":...}
if "rules" not in st.session_state:
    st.session_state.rules = None        # pd.DataFrame (rate sheet)
if "license_ok" not in st.session_state:
    st.session_state.license_ok = True   # Gate here if you want to monetize now

# ==============
# SIDEBAR (login + monetization)
# ==============
st.markdown(CSS, unsafe_allow_html=True)
with st.sidebar:
    st.markdown(f"### {DEALERSHIP_NAME}")
    st.caption(OWNER_NAME)

    if st.session_state.user is None:
        st.subheader("Sign in")
        u = st.text_input("Username", placeholder="rep / manager / admin")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            if u in DEMO_USERS and DEMO_USERS[u]["password"] == p:
                st.session_state.user = {"name": u, "role": DEMO_USERS[u]["role"]}
                st.success(f"Welcome, {u}!")
                st.rerun()
            else:
                st.error("Invalid credentials.")
        st.markdown("---")
        st.caption("Don’t have access? Click **Request Access**.")
        st.link_button("Request Access", "https://example.com/request-access")  # replace
    else:
        role = st.session_state.user["role"]
        st.markdown(
            f"**User:** {st.session_state.user['name']} "
            f"<span class='badge badge-{role}'> {role.title()} </span>",
            unsafe_allow_html=True,
        )
        if st.button("Logout"):
            st.session_state.user = None
            st.rerun()

    # Monetization hook: license key / plan display
    st.markdown("---")
    st.subheader("Plan")
    st.write("Starter plan • 3 seats • Rate sheet learning")
    st.link_button("Upgrade (Stripe)", "https://buy.stripe.com/test_123")  # replace with your link

# ==============
# HEADER
# ==============
st.markdown(f"## {APP_NAME}")
st.caption(f"Upload a rate sheet, enter the basics, and get lender picks + a clean structure snapshot.")
st.markdown(
    f"<div class='footer-wrap'>© {DEALERSHIP_NAME} — {OWNER_NAME}</div>",
    unsafe_allow_html=True,
)

# ========
# ACCESS
# ========
if st.session_state.user is None:
    st.info("Sign in from the left sidebar to use SmartDesk.")
    st.stop()

# ===========================
# MANAGER / ADMIN: RATE SHEET
# ===========================
with st.expander("How it learns from rate sheets", expanded=False):
    st.markdown("""
- Upload a **CSV/XLSX** rate sheet with columns like:
  `lender, min_score, max_score, allow_repos, max_repos, allow_open_auto, min_job_months, require_dl, max_pti, max_dti, tier_label, base_buy_rate, notes`
- The tool normalizes and caches it so reps get **Top-5 lender picks** that match the deal basics.
- Managers can upload new sheets anytime.
    """)

if st.session_state.user["role"] in ("manager", "admin"):
    st.markdown("### Rate Sheet")
    up = st.file_uploader("Upload rate sheet (.csv or .xlsx)", type=["csv", "xlsx"])
    if up:
        ext = ".csv" if up.name.lower().endswith(".csv") else ".xlsx"
        st.session_state.rules = load_rate_sheet_from_bytes(up.read(), ext)
        st.success(f"Loaded {len(st.session_state.rules)} rules from **{up.name}**.")
        st.dataframe(st.session_state.rules.head(20), use_container_width=True)
else:
    if st.session_state.rules is None:
        st.warning("No rate sheet loaded. Ask a manager to upload one under 'Rate Sheet'.")

# =================
# DEAL INPUT (UI)
# =================
st.markdown("### Deal Input")

with st.form("deal_form"):

    c1, c2, c3 = st.columns(3)

    with c1:
        credit_score = st.number_input("Credit Score", min_value=350, max_value=850, value=620, step=5)
        monthly_income = st.number_input("Monthly Income ($)", min_value=0, value=3000, step=100)
        # Years + months — converted to total months for lender rules
        job_years = st.number_input("Job Time (years)", min_value=0, value=0, step=1)
        job_months_rem = st.number_input("Job Time (months)", min_value=0, max_value=11, value=6, step=1)

    with c2:
        num_repos = st.number_input("# of Repos (reported)", min_value=0, value=0, step=1)
        has_dl = st.selectbox("Driver's License?", ["Yes", "No"])
        down_payment = st.number_input("Down Payment ($)", min_value=0, value=1000, step=100)

    with c3:
        trade_equity = st.number_input("Trade Equity ($)", value=0, step=100)
        gig_income_on = st.checkbox("Gig / DoorDash income?")
        gig_income = st.number_input("Gig Income ($/month)", value=0, step=50, disabled=not gig_income_on)

    st.markdown("**Optional co-applicant**")
    colx, coly = st.columns(2)
    with colx:
        include_co = st.checkbox("Include Co-Applicant?")
        co_score = st.number_input("Co-Applicant Score", value=600, step=1, disabled=not include_co)
    with coly:
        co_income = st.number_input("Co-Applicant Income ($/month)", value=0, step=100, disabled=not include_co)

    # Simple PTI/DTI placeholders (can wire to Promax-style calc later)
    st.markdown("**Optional structure (for PTI/DTI checks)**")
    c4, c5 = st.columns(2)
    with c4:
        est_payment = st.number_input("Estimated Payment ($)", value=0, step=10)
        pti = round(est_payment / monthly_income * 100.0, 2) if monthly_income > 0 and est_payment > 0 else None
    with c5:
        total_monthly_debt = st.number_input("Other Monthly Debt ($)", value=0, step=10)
        gross_income = monthly_income + (co_income if include_co else 0) + (gig_income if gig_income_on else 0)
        dti = round((total_monthly_debt + (est_payment or 0)) / gross_income * 100.0, 2) if gross_income > 0 else None

    submitted = st.form_submit_button("Evaluate Deal")

if submitted:
    # Collapse job time -> months
    total_job_months = int(job_years * 12 + job_months_rem)
    total_income = monthly_income + (co_income if include_co else 0) + (gig_income if gig_income_on else 0)

    # Snapshot (clean, branded)
    snapshot = {
        "Primary Applicant": {
            "Credit Score": credit_score,
            "Monthly Income": float(monthly_income),
            "Job Time (months)": total_job_months,
            "Repos": int(num_repos),
            "Driver's License": "Yes" if has_dl == "Yes" else "No",
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
        "Income": {
            "Base Income": float(monthly_income),
            "Gig Income": float(gig_income) if gig_income_on else 0.0,
            "Total Income": float(total_income),
        },
    }

    with st.container(border=True):
        st.success("Deal captured")
        st.json(snapshot)

    # Top-5 lender picks (if rules available)
    if st.session_state.rules is not None:
        picks = pick_top_lenders(
            st.session_state.rules,
            score=credit_score,
            job_months=total_job_months,
            repos=num_repos,
            has_dl=(has_dl == "Yes"),
            pti=pti,
            dti=dti,
            open_auto=False,
            top_k=5
        )

        st.markdown("### Top-5 Lender Picks")
        if picks.empty:
            st.warning("No lenders matched this structure. Try a different down payment, vehicle, or lender path.")
        else:
            # Light presentation polish
            picks_ = picks.copy()
            if "base_buy_rate" in picks_.columns:
                picks_["base_buy_rate"] = picks_["base_buy_rate"].map(lambda x: f"{x:0.2f}%")
            st.dataframe(picks_, use_container_width=True)

    # RouteOne/Credit report uploads (for your rehash pipeline)
    st.markdown("### Uploads (optional, to rehash or archive)")
    cA, cB = st.columns(2)
    with cA:
        routeone_pdf = st.file_uploader("RouteOne Deal Recap (PDF)", type=["pdf"])
    with cB:
        credit_report = st.file_uploader("Credit Report (PDF/Image)", type=["pdf", "png", "jpg", "jpeg"])

    # “PDF” snapshot (simple text for now; replace with real PDF lib if needed)
    if st.button("Download Snapshot (txt)"):
        txt = json.dumps(snapshot, indent=2)
        pdf_download_button("deal_snapshot.txt", txt, "Download")

# ==========
# MANAGER: Users/Seats (placeholder)
# ==========
if st.session_state.user["role"] in ("manager", "admin"):
    with st.expander("Manager – Users & Seats"):
        st.write("Prototype: control who can access and track seats. Replace with real auth later.")
        st.table(pd.DataFrame([
            {"user": "rep", "role": "sales"},
            {"user": "manager", "role": "manager"},
            {"user": "admin", "role": "admin"},
        ]))
        st.caption("For production, plug in Okta/AzureAD or streamlit-authenticator and Stripe for billing.")

# ========
# FOOTER
# ========
st.markdown(
    f"<div class='footer-wrap'>© {DEALERSHIP_NAME} • {OWNER_NAME}</div>",
    unsafe_allow_html=True,
)
