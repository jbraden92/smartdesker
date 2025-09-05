# streamlit_app.py
# SmartDesk – AI Desking Assistant (POC)
# --------------------------------------
# - Deal input form + uploads
# - Hard-coded lender rules (POC)
# - Learn-from-Recaps (beta): parse RouteOne PDFs, train model, re-rank lenders

import os, io, re, json, joblib
import streamlit as st
import pandas as pd

# ---------- Page setup ----------
st.set_page_config(page_title="SmartDesk – POC", page_icon="🚗", layout="wide")

st.title("SmartDesk – AI Desking Assistant (POC)")
st.caption(
    "Step 1: Deal input form + uploads. Next step we’ll add lender rules, vehicle picks, and a Promax-style structure."
)

with st.expander("How this works", expanded=False):
    st.markdown("""
    **Today (POC):**
    1) Enter a simple customer profile  
    2) (Optional) Upload RouteOne Decision PDFs to *teach* the app  
    3) Click **Evaluate Deal** to see the snapshot + lender suggestions  
    4) (Optional) **Train model** to re-rank lenders by learned approval probability

    **Notes:** Rules are intentionally simplified for a quick demo. Tweak any thresholds to match your store.
    """)

# ---------- Deal Input ----------
st.header("Deal Input")

with st.form("deal_form"):
    col1, col2, col3 = st.columns(3)

    with col1:
        credit_score   = st.number_input("Credit Score", min_value=350, max_value=850, value=620, step=10)
        monthly_income = st.number_input("Monthly Income ($)", min_value=0, value=3000, step=100)
        job_months     = st.number_input("Job Time (months)", min_value=0, value=6, step=1)

    with col2:
        num_repos = st.number_input("# of Repos (reported)", min_value=0, value=0, step=1)
        has_dl    = st.selectbox("Driver's License?", ["Yes", "No"])
        down_payment = st.number_input("Down Payment ($)", min_value=0, value=1000, step=100)

    with col3:
        trade_equity = st.number_input("Trade Equity ($)", min_value=-20000, max_value=50000, value=0, step=500)
        gig          = st.checkbox("Gig / DoorDash income?")
        gig_income   = st.number_input("Gig Income ($/month)", min_value=0, value=0, step=50, disabled=not gig)

    st.markdown("---")
    st.subheader("Optional co-applicant")
    co = st.checkbox("Include Co-Applicant?")
    co_col1, co_col2 = st.columns(2)
    with co_col1:
        co_score = st.number_input("Co-Applicant Credit Score", min_value=350, max_value=850, value=600, step=10, disabled=not co)
    with co_col2:
        co_income = st.number_input("Co-Applicant Income ($/month)", min_value=0, value=0, step=100, disabled=not co)

    submitted = st.form_submit_button("Evaluate Deal", type="primary", use_container_width=True)

# ---------- Upload placeholders (we’ll use in Learning panel too) ----------
st.subheader("Uploads")
up1, up2, up3, up4 = st.columns(4)
with up1:
    credit_report = st.file_uploader("Credit Report (PDF / image)", type=["pdf","png","jpg","jpeg"])
with up2:
    routeone_pdf = st.file_uploader("RouteOne Deal Recap (PDF)", type=["pdf"])
with up3:
    inventory_file = st.file_uploader("Inventory (.csv / .xlsx)", type=["csv","xlsx"])
with up4:
    rate_sheets = st.file_uploader("Rate Sheets (.csv / .xlsx)", type=["csv","xlsx"], accept_multiple_files=True)

# ---------- Utility: build a friendly snapshot ----------
def build_snapshot():
    base_income = monthly_income
    total_income = base_income + (gig_income if gig else 0) + (co_income if co else 0)
    snap = {
        "Primary Applicant": {
            "Credit Score": credit_score,
            "Monthly Income": base_income,
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
            "Base Income": base_income,
            "Gig Income": gig_income if gig else 0,
            "Total Income": total_income,
        },
        "Files": {
            "Credit Report Uploaded": bool(credit_report),
            "RouteOne Recap Uploaded": bool(routeone_pdf),
            "Inventory Uploaded": bool(inventory_file),
            "Rate Sheets Uploaded": bool(rate_sheets),
        }
    }
    return snap

# ---------- Rule-based lender suggestions (POC) ----------
def lender_rules(profile: dict):
    """
    Very simple, **hard-coded** lender rules to illustrate logic.
    Modify freely to mirror your store.
    Returns list of dicts: {lender, why, structure, stips}
    """
    cs   = profile["credit_score"]
    inc  = profile["monthly_income"]
    dti  = 0.0  # we aren’t computing full DTI yet; placeholder
    repos = profile["num_repos"]
    dl    = profile["has_dl"] == "Yes"
    dp    = profile["down_payment"]
    jobm  = profile["job_months"]
    teq   = profile["trade_equity"]
    gig_i = profile["gig_income"]
    co    = profile["co"]
    co_s  = profile["co_score"]
    co_i  = profile["co_income"]

    recs = []

    # Ally (prime-ish)
    if cs >= 640 and repos == 0 and dl and jobm >= 6:
        recs.append({
            "lender": "Ally",
            "why": "Primeish profile, no repos, DL yes, job ≥6 mo.",
            "structure": "60–72 mo, sell price near clean book, minimal backend to start.",
            "stips": "POI, POR, 1 ref. No frame-damage units."
        })

    # Gateway Financial Solutions (GFS)
    # - Often OK w/ thin files, some subprime; stricter on >1 repo + open autos
    if cs >= 520 and dl and jobm >= 3:
        if repos <= 1:
            note = "≤1 repo OK. If DoorDash/gig income present, include VOE/Equifax VOF if requested."
            recs.append({
                "lender": "Gateway Financial Solutions",
                "why": f"Score {cs} w/ DL and job time. {note}",
                "structure": "69–72 mo typical, 18–25% APR band depending on tier. Keep PTI reasonable.",
                "stips": "POI, POR, 5 refs, valid DL. Avoid open autos. Frame-damage units generally not favored."
            })

    # Exeter Finance (deep subprime; cautious on frame damage)
    if cs >= 480 and dl:
        warn = "Declines frame/unibody damage in most cases; favor clean titles and no severe accidents."
        recs.append({
            "lender": "Exeter Finance",
            "why": f"Will consider deep subprime w/ DL. {warn}",
            "structure": "72 mo max; high LTV tolerances but keep ACV conservative; DP helps.",
            "stips": "POI, POR, 5 refs, DL front/back. No recent open auto. Prior repos OK depending on aging."
        })

    # Westlake Financial (broad box; often OK with light credit / BK)
    recs.append({
        "lender": "Westlake Financial",
        "why": "Wide box from near-prime down to deep; flexible programs.",
        "structure": "Term 60–72 mo depending tier; present book-to-cost margin; DP helps lower PTI.",
        "stips": "POI/POR, references; check program matrix if BK or thin file."
    })

    # Global Lending Services (GLS / Global LS)
    if cs >= 520 and dl:
        recs.append({
            "lender": "Global Lending Services",
            "why": "Subprime program OK with stable income, DL yes. Usually 0–1 repo tolerance.",
            "structure": "60–72 mo; price close to book; DP ≥ $1000 recommended.",
            "stips": "POI, POR, references; avoid frame-damage; 1 repo max; no open autos."
        })

    # Rank a bit by rough fit (very coarse)
    def score_row(r):
        base = 0
        if "Gateway" in r["lender"]: base += 2
        if "Westlake" in r["lender"]: base += 1
        if "Exeter" in r["lender"] and cs < 560: base += 2
        if "Ally" in r["lender"] and cs >= 640: base += 2
        if "Global" in r["lender"] and repos <= 1: base += 1
        return base

    recs = sorted(recs, key=score_row, reverse=True)
    return recs

# ---------- Evaluate ----------
if submitted:
    snapshot = build_snapshot()
    st.success("Inputs captured.")
    st.json(snapshot)

    # Build a simple profile for rules
    profile = {
        "credit_score": credit_score,
        "monthly_income": monthly_income,
        "job_months": job_months,
        "num_repos": num_repos,
        "has_dl": has_dl,
        "down_payment": down_payment,
        "trade_equity": trade_equity,
        "gig_income": gig_income if gig else 0,
        "co": co,
        "co_score": co_score if co else None,
        "co_income": co_income if co else 0,
    }

    recs = lender_rules(profile)

    # We’ll let the **Learning** section (below) re-rank by ML if available.
    st.session_state["__last_recs__"] = recs  # stash so ML section can see it

    st.markdown("### Rule-based Lender Suggestions")
    for r in recs:
        with st.container(border=True):
            st.markdown(f"**{r['lender']}**")
            st.caption(r["why"])
            st.write(f"**Structure:** {r['structure']}")
            st.write(f"**Likely stips:** {r['stips']}")

# ------------------------------
# LEARNING FROM RECAPS (BETA)
# ------------------------------
import pdfplumber
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

DATA_DIR = "data"
MODEL_DIR = "models"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)
LEARN_FILE = os.path.join(DATA_DIR, "learned_deals.csv")
MODEL_FILE = os.path.join(MODEL_DIR, "lender_model.pkl")

def _clean_num(x):
    if x is None: return None
    x = str(x)
    x = re.sub(r"[,$%]", "", x)
    m = re.search(r"(-?\d+(\.\d+)?)", x)
    return float(m.group(1)) if m else None

def parse_routeone_pdf(uploaded) -> list[dict]:
    rows = []
    with pdfplumber.open(io.BytesIO(uploaded.read())) as pdf:
        full = "\n".join([p.extract_text() or "" for p in pdf.pages])

    def find(pattern, default=None, flags=re.IGNORECASE):
        m = re.search(pattern, full, flags)
        return m.group(1).strip() if m else default

    lender  = find(r"Decision:\s*(?:Approved|Conditioned|Declined)\s*by\s*([^\n]+)") \
              or find(r"^\s*([A-Z][A-Za-z &/]+)\s*Decision:", default="Unknown")
    decision = "Approved" if re.search(r"Decision:\s*Approved", full, re.I) else \
               "Declined" if re.search(r"Decision:\s*Declined", full, re.I) else \
               "Conditioned" if re.search(r"Decision:\s*Conditioned", full, re.I) else "Unknown"

    term     = _clean_num(find(r"\bTerm\b.*?(\d{2,3})", None))
    rate     = _clean_num(find(r"(?:Customer Rate|Buy Rate)[^\d%]*([\d\.]+)%", None))
    buy_rate = _clean_num(find(r"\bBuy Rate\b[^0-9]*([\d\.]+)", None))
    pymt     = _clean_num(find(r"(?:Total Monthly Payment|Payment)[^\d]*([\d\.]+)", None))
    amount   = _clean_num(find(r"(?:Financed Amount|Amount Paid To Dealer)[^\d]*([\d,\.]+)", None))
    cash     = _clean_num(find(r"(?:Cash Down|Cash)[^\d-]*(-?[\d,\.]+)", None))

    rows.append({
        "lender": lender or "Unknown",
        "decision": decision,
        "term": term, "customer_rate": rate, "buy_rate": buy_rate,
        "monthly_payment": pymt, "amount_financed": amount, "cash_down": cash,
    })
    return rows

def append_training_rows(rows, current_inputs: dict):
    # enrich with the current deal form inputs (so the model learns from *your* profiles)
    enriched = []
    for r in rows:
        enriched.append({
            **r,
            "score": current_inputs.get("credit_score"),
            "repos": current_inputs.get("num_repos"),
            "has_dl": 1 if current_inputs.get("has_dl") == "Yes" else 0,
            "job_months": current_inputs.get("job_months"),
            "base_income": current_inputs.get("monthly_income"),
            "gig_income": current_inputs.get("gig_income", 0),
            "trade_equity": current_inputs.get("trade_equity", 0),
            "dp_input": current_inputs.get("down_payment"),
            "approved": 1 if str(r.get("decision","")).lower()=="approved" else (0 if str(r.get("decision","")).lower()=="declined" else None)
        })
    df_new = pd.DataFrame(enriched)
    df_new = df_new.dropna(subset=["approved"])
    if df_new.empty:
        return 0
    if os.path.exists(LEARN_FILE):
        df_old = pd.read_csv(LEARN_FILE)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new
    df_all.to_csv(LEARN_FILE, index=False)
    return len(df_new)

def train_model():
    if not os.path.exists(LEARN_FILE):
        return False, "No training data yet."
    df = pd.read_csv(LEARN_FILE)
    df = df.dropna(subset=["approved", "lender"])
    if df["approved"].nunique() < 2:
        return False, "Need both approved and declined to train."

    X = df[[
        "lender","score","repos","has_dl","job_months","base_income","gig_income",
        "trade_equity","dp_input","term","customer_rate","buy_rate","monthly_payment",
        "amount_financed","cash_down"
    ]]
    y = df["approved"].astype(int)

    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder
    from sklearn.pipeline import Pipeline
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score

    cat = ["lender"]
    num = [c for c in X.columns if c not in cat]
    pre = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), cat),
            ("num", "passthrough", num),
        ]
    )
    clf = Pipeline([
        ("pre", pre),
        ("model", LogisticRegression(max_iter=200))
    ])

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    clf.fit(Xtr, ytr)
    try:
        yhat = clf.predict_proba(Xte)[:,1]
        auc = roc_auc_score(yte, yhat)
        msg = f"Model trained. AUC={auc:.3f} on holdout."
    except Exception:
        msg = "Model trained."

    joblib.dump(clf, MODEL_FILE)
    return True, msg

def predict_lender_scores(form_inputs: dict, lenders: list[str]) -> dict:
    if not os.path.exists(MODEL_FILE):
        return {}
    clf = joblib.load(MODEL_FILE)
    base = {
        "score": form_inputs["credit_score"],
        "repos": form_inputs["num_repos"],
        "has_dl": 1 if form_inputs["has_dl"] == "Yes" else 0,
        "job_months": form_inputs["job_months"],
        "base_income": form_inputs["monthly_income"],
        "gig_income": form_inputs.get("gig_income",0),
        "trade_equity": form_inputs.get("trade_equity",0),
        "dp_input": form_inputs["down_payment"],
        # neutral placeholders (model still learns correlations)
        "term": 72,
        "customer_rate": None,
        "buy_rate": None,
        "monthly_payment": None,
        "amount_financed": None,
        "cash_down": form_inputs["down_payment"],
    }
    rows = [{**base, "lender": L} for L in lenders]
    df = pd.DataFrame(rows)
    probs = clf.predict_proba(df)[:,1]
    return {L: float(p) for L,p in zip(lenders, probs)}

# ---------- Learning UI ----------
st.markdown("### Learn from Deal Recaps (beta)")
with st.expander("Upload past deal PDFs to teach the app", expanded=False):
    learn_pdfs = st.file_uploader("Upload RouteOne Decision Details PDFs", type=["pdf"], accept_multiple_files=True, key="learn_pdfs")
    if learn_pdfs:
        current_inputs = {
            "credit_score": credit_score,
            "monthly_income": monthly_income,
            "job_months": job_months,
            "num_repos": num_repos,
            "has_dl": has_dl,
            "down_payment": down_payment,
            "trade_equity": trade_equity,
            "gig_income": gig_income if gig else 0
        }
        total_added = 0
        for up in learn_pdfs:
            try:
                rows = parse_routeone_pdf(up)
                added = append_training_rows(rows, current_inputs)
                total_added += added
            except Exception as e:
                st.warning(f"Failed to parse {up.name}: {e}")
        if total_added > 0:
            st.success(f"Added {total_added} labeled rows to training data. (Stored in {LEARN_FILE})")
        else:
            st.info("No usable (Approved/Declined) rows found in these PDFs.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Train model"):
            ok, msg = train_model()
            st.success(msg) if ok else st.warning(msg)
    with c2:
        if os.path.exists(LEARN_FILE):
            st.download_button("Download training CSV", data=open(LEARN_FILE,"rb"), file_name="learned_deals.csv")

# ---------- ML re-rank (if Evaluate Deal ran and model exists) ----------
if "__last_recs__" in st.session_state and st.session_state["__last_recs__"]:
    try:
        lenders_considered = [r["lender"] for r in st.session_state["__last_recs__"]]
        model_scores = predict_lender_scores(
            {
                "credit_score": credit_score,
                "monthly_income": monthly_income,
                "job_months": job_months,
                "num_repos": num_repos,
                "has_dl": has_dl,
                "down_payment": down_payment,
                "trade_equity": trade_equity,
                "gig_income": gig_income if gig else 0
            },
            lenders_considered
        )
        if model_scores:
            st.markdown("### ML Re-ranked (beta)")
            # attach and resort
            recs = st.session_state["__last_recs__"]
            for r in recs:
                r["ml_prob"] = round(model_scores.get(r["lender"], 0.0), 3)
            recs = sorted(recs, key=lambda x: x.get("ml_prob", 0.0), reverse=True)
            for r in recs:
                with st.container(border=True):
                    st.markdown(f"**{r['lender']}**  —  Prob. approve: `{r['ml_prob']}`")
                    st.caption(r["why"])
                    st.write(f"**Structure:** {r['structure']}")
                    st.write(f"**Likely stips:** {r['stips']}")
        else:
            st.caption("Train a model to see ML-based ranking here.")
    except Exception as e:
        st.warning(f"ML re-rank skipped: {e}")
