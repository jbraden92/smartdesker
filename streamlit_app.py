# -----------------------------
# SmartDesk — Promax-Style Desking (No dealer name)
# -----------------------------
# Promax-like UI + Lender Top-5 + Payment/Structure math + Rate Sheet learning
# -----------------------------

import io, json, base64, math
import pandas as pd
import streamlit as st

APP_TITLE  = "SmartDesk — Desking Assistant"
OWNER_NAME = "Built by JBraden"     # leave "" to hide

# ===== Promax-ish theme (slate, light borders, blue actions)
CSS = """
<style>
/* App skin */
.stApp { background:#13151A; color:#E6E9EF; }
.block-container{ padding-top:0.8rem; }

/* Panels */
.panel {
  background:#1A1D24;
  border:1px solid #2B2F38;
  border-radius:8px;
  padding:12px 14px;
  margin-bottom:10px;
}
.panel h4 { margin:0 0 8px 0; font-weight:700; letter-spacing:.2px; }

/* Labels / inputs */
label, .stSelectbox label, .stNumberInput label, .stTextInput label { color:#BFC6D4 !important; font-weight:600; }
.stNumberInput input, .stTextInput input,
div[data-baseweb="select"]>div {
  background:#13161C !important; color:#E6E9EF !important; border:1px solid #2B2F38; border-radius:6px;
}

/* Tables */
thead th{ background:#15181E !important; }

/* Buttons */
.stButton>button {
  background:#2D6CDF; color:white; border:none; border-radius:8px; font-weight:700;
}
.stButton>button:hover{ filter:brightness(1.08); }

/* “Totals“ box */
.totals {
  background:#10131A; border:1px solid #2B2F38; border-radius:8px; padding:10px 12px;
}
.totals h5 { margin:.2rem 0 .6rem 0; }

/* Footer */
.footer { margin-top:.5rem; color:#9AA3AE; font-size:.9rem; border-top:1px dashed #2B2F38; padding-top:.6rem; }
</style>
"""

st.set_page_config(page_title="SmartDesk", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

# Title bar
left, right = st.columns([0.8,0.2])
with left:
    st.markdown(f"## {APP_TITLE}")
with right:
    if OWNER_NAME:
        st.markdown(f"<div style='text-align:right;color:#9AA3AE'>{OWNER_NAME}</div>", unsafe_allow_html=True)

# --------------------------
# Helpers
# --------------------------
def yn(val):
    if isinstance(val,str): return val.strip().lower() in ("y","yes","true","1")
    if isinstance(val,(int,float)): return val==1
    return bool(val)

@st.cache_data(show_spinner=False)
def load_rate_sheet_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(data)) if ext==".csv" else pd.read_excel(io.BytesIO(data))
    df.columns = [c.strip().lower() for c in df.columns]

    # expected fields w/ defaults
    defaults = {
        "lender":"", "min_score":0,"max_score":999,
        "allow_repos":True,"max_repos":99,
        "allow_open_auto":True,"min_job_months":0,"require_dl":True,
        "max_pti":999.0,"max_dti":999.0,
        "tier_label":"","base_buy_rate":0.0,
        "notes":""
    }
    for k,v in defaults.items():
        if k not in df.columns: df[k]=v

    df["min_score"]=pd.to_numeric(df["min_score"],errors="coerce").fillna(0).astype(int)
    df["max_score"]=pd.to_numeric(df["max_score"],errors="coerce").fillna(999).astype(int)
    df["max_repos"]=pd.to_numeric(df["max_repos"],errors="coerce").fillna(0).astype(int)
    df["min_job_months"]=pd.to_numeric(df["min_job_months"],errors="coerce").fillna(0).astype(int)
    for b in ["allow_repos","allow_open_auto","require_dl"]: df[b]=df[b].apply(yn)
    for n in ["max_pti","max_dti","base_buy_rate"]: df[n]=pd.to_numeric(df[n],errors="coerce").fillna(0.0)
    return df

def pick_top_lenders(rules: pd.DataFrame, score:int, job_months:int, repos:int,
                     has_dl:bool, pti:float|None, dti:float|None, open_auto=False, top_k=5)->pd.DataFrame:
    if rules is None or rules.empty: return pd.DataFrame()
    df = rules.copy()
    df = df[
        (df["min_score"]<=score) & (df["max_score"]>=score) &
        ((df["allow_repos"]) | (repos==0)) & (df["max_repos"]>=repos) &
        ((df["allow_open_auto"]) | (open_auto==False)) &
        (df["min_job_months"]<=job_months) & ((df["require_dl"]==False) | (has_dl))
    ]
    if pti is not None: df = df[(df["max_pti"]>=pti) | (df["max_pti"]==0)]
    if dti is not None: df = df[(df["max_dti"]>=dti) | (df["max_dti"]==0)]
    if df.empty: return df
    df["band_center"]=(df["min_score"]+df["max_score"])/2
    df["band_fit"]=-abs(df["band_center"]-score)
    df["rank_score"]=df["band_fit"]-df["base_buy_rate"].fillna(0)*2
    cols = ["lender","tier_label","base_buy_rate","min_score","max_score","max_repos",
            "allow_open_auto","min_job_months","require_dl","max_pti","max_dti","notes"]
    return df.sort_values("rank_score",ascending=False).head(top_k)[cols].reset_index(drop=True)

def pmt(apr:float, term:int, amount:float)->float:
    """Standard loan payment calc."""
    if term<=0: return 0.0
    r = apr/100/12.0
    if abs(r)<1e-8: return round(amount/term,2)
    return round(amount * (r/(1-(1+r)**(-term))), 2)

# --------------------------
# Rate sheet (everyone can upload for now)
# --------------------------
rs_col1, rs_col2 = st.columns([0.7,0.3])
with rs_col1:
    with st.expander("Rate Sheet Learning (CSV/XLSX)", expanded=False):
        up = st.file_uploader("Upload rate sheet", type=["csv","xlsx"], key="rs")
        if up:
            ext=".csv" if up.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["rules"]=load_rate_sheet_from_bytes(up.read(), ext)
            st.success(f"Loaded {len(st.session_state['rules'])} rows from {up.name}.")
            st.dataframe(st.session_state["rules"].head(20), use_container_width=True)

# --------------------------
# PROMAX-STYLE DESK
# --------------------------
st.markdown("### Promax-Style Desk")

left, mid, right = st.columns([0.35,0.35,0.30])

# ---- LEFT: Customer Basics
with left:
    st.markdown("<div class='panel'><h4>Customer</h4>", unsafe_allow_html=True)
    credit_score = st.number_input("Credit Score", 350, 850, 620, step=5)
    monthly_income = st.number_input("Monthly Income ($)", 0, 100000, 3000, step=100)
    y = st.number_input("Job Time (Years)", 0, 50, 0, 1)
    m = st.number_input("Job Time (Months)", 0, 11, 6, 1)
    total_job_months = y*12 + m
    repos = st.number_input("# Repos", 0, 10, 0, 1)
    has_dl = st.selectbox("Driver’s License", ["Yes","No"])
    include_co = st.checkbox("Include Co-Applicant")
    co_score = st.number_input("Co-App Score", 350, 850, 600, 1, disabled=not include_co)
    co_income = st.number_input("Co-App Income ($/mo)", 0, 100000, 0, 50, disabled=not include_co)
    st.markdown("</div>", unsafe_allow_html=True)

# ---- MID: Vehicle/Structure
with mid:
    st.markdown("<div class='panel'><h4>Vehicle / Structure</h4>", unsafe_allow_html=True)
    sale_price = st.number_input("Sale Price ($)", 0, 200000, 15995, step=100)
    doc_fee    = st.number_input("Doc Fee ($)", 0, 1000, 387, step=10)
    lender_fee = st.number_input("Lender Fees ($)", 0, 5000, 0, step=25)
    tax_rate   = st.number_input("Sales Tax (%)", 0.0, 15.0, 7.25, step=0.25)
    dp         = st.number_input("Cash Down ($)", 0, 50000, 1000, step=100)
    trade_eq   = st.number_input("Trade Equity ($)", -20000, 50000, 0, step=100)
    term       = st.number_input("Term (months)", 12, 96, 72, step=1)
    buy_rate   = st.number_input("Buy/Customer Rate (%)", 0.0, 29.99, 23.95, step=0.1)
    est_payment_hint = st.caption("Payment uses standard PMT with APR/term on finance amount.")
    st.markdown("</div>", unsafe_allow_html=True)

# ---- Right: Calculated
with right:
    st.markdown("<div class='panel'><h4>Calculated</h4>", unsafe_allow_html=True)

    taxable = sale_price        # tweak if you tax warranty/GAP later
    tax_amt = round(taxable * (tax_rate/100.0), 2)
    amt_fin = round(sale_price + doc_fee + lender_fee + tax_amt - dp - trade_eq, 2)
    est_pmt = pmt(buy_rate, term, max(0, amt_fin))

    gross_inc = monthly_income + (co_income if include_co else 0)
    other_debt = st.number_input("Other Monthly Debt ($)", 0, 20000, 0, step=10)
    pti = round(est_pmt / monthly_income * 100.0, 2) if monthly_income>0 else None
    dti = round((other_debt + est_pmt) / gross_inc * 100.0, 2) if gross_inc>0 else None

    st.markdown("<div class='totals'>", unsafe_allow_html=True)
    st.markdown(f"**Amount Financed:** ${amt_fin:,.2f}")
    st.markdown(f"**Est. Payment:** ${est_pmt:,.2f}")
    st.markdown(f"**PTI:** {pti if pti is not None else '—'} %")
    st.markdown(f"**DTI:** {dti if dti is not None else '—'} %")
    st.markdown(f"<small>Tax: ${tax_amt:,.2f}</small>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# --------------------------
# Snapshot + Top-5
# --------------------------
colA, colB = st.columns([0.52, 0.48])

with colA:
    st.markdown("<div class='panel'><h4>Deal Snapshot</h4>", unsafe_allow_html=True)
    snapshot = {
        "Applicant": {
            "Score": credit_score,
            "Monthly Income": monthly_income,
            "Job Months": total_job_months,
            "Repos": repos,
            "DL": has_dl
        },
        "Co-Applicant": {
            "Included": include_co,
            "Score": co_score if include_co else None,
            "Income": co_income if include_co else 0
        },
        "Structure": {
            "Sale Price": sale_price,
            "Doc Fee": doc_fee,
            "Lender Fees": lender_fee,
            "Tax Rate %": tax_rate,
            "Cash Down": dp,
            "Trade Equity": trade_eq,
            "Term": term,
            "Buy Rate %": buy_rate,
            "Amount Financed": amt_fin,
            "Est Payment": est_pmt,
            "PTI%": pti,
            "DTI%": dti
        }
    }
    st.json(snapshot)
    st.markdown("</div>", unsafe_allow_html=True)

with colB:
    st.markdown("<div class='panel'><h4>Top-5 Lender Picks</h4>", unsafe_allow_html=True)
    rules = st.session_state.get("rules")
    if rules is None or rules.empty:
        st.info("Upload a rate sheet above to see lender picks.")
    else:
        picks = pick_top_lenders(
            rules, score=credit_score, job_months=total_job_months, repos=repos,
            has_dl=(has_dl=="Yes"), pti=pti, dti=dti, open_auto=False, top_k=5
        )
        if picks.empty:
            st.warning("No lenders matched this profile.")
        else:
            out = picks.copy()
            if "base_buy_rate" in out.columns:
                out["base_buy_rate"] = out["base_buy_rate"].map(lambda x: f"{x:.2f}%")
            st.dataframe(out, use_container_width=True, height=260)
    st.markdown("</div>", unsafe_allow_html=True)

# --------------------------
# Uploads (rehash archive)
# --------------------------
st.markdown("### Uploads")
u1, u2, u3 = st.columns(3)
with u1:
    st.file_uploader("RouteOne Deal Recap (PDF)", type=["pdf"], key="r1")
with u2:
    st.file_uploader("Credit Report (PDF/Image)", type=["pdf","png","jpg","jpeg"], key="cr")
with u3:
    st.file_uploader("Other Docs (PNG/JPG/PDF)", type=["pdf","png","jpg","jpeg"], key="od")

# Footer
st.markdown(f"<div class='footer'>This tool mimics Promax screen layout for speed & clarity. {OWNER_NAME if OWNER_NAME else ''}</div>", unsafe_allow_html=True)
