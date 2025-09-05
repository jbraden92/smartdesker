# streamlit_app.py
import streamlit as st
import pandas as pd
from io import BytesIO
import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# Page config + light styling
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="SmartDesk – Desking Assistant", page_icon="📋", layout="wide")

st.markdown("""
<style>
.card {border-radius: 10px; padding: 14px 16px; border: 1px solid rgba(250, 250, 250, 0.12); background: rgba(250,250,250,0.03);}
.metric {font-size:22px; font-weight:700; margin-bottom:4px}
.small {opacity:.75}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Helper: truthy for Yes/No variants
# ──────────────────────────────────────────────────────────────────────────────
def yn(val, default=False):
    if pd.isna(val):
        return default
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ("y","yes","true","1"):
        return True
    if s in ("n","no","false","0"):
        return False
    return default

def _to_num(x, default=None):
    if isinstance(x, (int, float)) and not pd.isna(x):
        return float(x)
    if x is None:
        return default
    s = str(x).strip().lower()
    if s in ("", "na", "n/a", "none", "null", "-", "—", "blank"):
        return default
    try:
        return float(s.replace(",", "").replace("$", ""))
    except:
        return default

# ──────────────────────────────────────────────────────────────────────────────
# DEFAULT lender table (used until user uploads one)
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_RATE_RULES = pd.DataFrame([
    {"Lender":"Gateway Financial Solutions","MinScore":None,"MaxScore":670,"MaxRepos":1,"MinJobMonths":3,"MinIncome":1800,"MinDown":500,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Global Lending Services","MinScore":580,"MaxScore":720,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2200,"MinDown":1000,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Flagship Credit","MinScore":600,"MaxScore":750,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2400,"MinDown":1000,"AllowGig":True,"AllowNoDL":False,"AllowFrame":True},
    {"Lender":"Regional Acceptance","MinScore":590,"MaxScore":720,"MaxRepos":1,"MinJobMonths":12,"MinIncome":2500,"MinDown":1000,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Prestige","MinScore":600,"MaxScore":750,"MaxRepos":0,"MinJobMonths":12,"MinIncome":2600,"MinDown":1000,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Exeter","MinScore":550,"MaxScore":700,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2000,"MinDown":500,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Kemba CU","MinScore":640,"MaxScore":800,"MaxRepos":0,"MinJobMonths":12,"MinIncome":3000,"MinDown":1000,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},
])

# Normalize blanks → programmatic defaults
def normalize_rate_rules(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # flexible column mapping
    name_map = {}
    for c in df.columns:
        name_map[c] = c.strip()

    # Lowercase lookup to find columns
    lower_cols = {c.lower().strip(): c for c in df.columns}
    def getcol(key):
        return df[lower_cols[key]] if key in lower_cols else None

    out = pd.DataFrame({
        "Lender": (getcol("lender") or pd.Series([""]*len(df))).astype(str).str.strip(),
        "MinScore": [(0 if pd.isna(v) else _to_num(v, 0)) for v in (getcol("minscore") or pd.Series([None]*len(df)))],
        "MaxScore": [_to_num(v, 999) for v in (getcol("maxscore") or pd.Series([999]*len(df)))],
        "MaxRepos": [_to_num(v, 99) for v in (getcol("maxrepos") or pd.Series([99]*len(df)))],
        "MinJobMonths": [_to_num(v, 0) for v in (getcol("minjobmonths") or pd.Series([0]*len(df)))],
        "MinIncome": [_to_num(v, 0) for v in (getcol("minincome") or pd.Series([0]*len(df)))],
        "MinDown": [_to_num(v, 0) for v in (getcol("mindown") or pd.Series([0]*len(df)))],
        "AllowGig": [yn(v, True) for v in (getcol("allowgig") or pd.Series([True]*len(df)))],
        "AllowNoDL": [yn(v, False) for v in (getcol("allownodl") or pd.Series([False]*len(df)))],
        "AllowFrame": [yn(v, False) for v in (getcol("allowframe") or pd.Series([False]*len(df)))],
    })

    # Gateway: if lender contains 'gateway' and MinScore is None/blank → set 0 explicitly
    mask_gateway = out["Lender"].str.contains("gateway", case=False, na=False)
    out.loc[mask_gateway & (pd.isna(out["MinScore"]) | (out["MinScore"]==0)), "MinScore"] = 0

    # Drop empty lender names
    out = out[out["Lender"].str.len()>0].reset_index(drop=True)
    return out

@st.cache_data(show_spinner=False)
def load_rate_sheet(file_bytes: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(file_bytes)) if ext == ".csv" else pd.read_excel(BytesIO(file_bytes))
    return normalize_rate_rules(df)

# ──────────────────────────────────────────────────────────────────────────────
# Inventory loader/cleaner
# ──────────────────────────────────────────────────────────────────────────────
def normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flexible cleaner that tries to find common columns by fuzzy keys,
    coerces numbers, and adds helpful derived fields.
    """
    df = df.copy()

    # Normalize string columns
    for c in df.columns:
        if df[c].dtype == "object":
            df[c] = df[c].fillna("").astype(str).str.strip()

    # Build a lowercase map for fuzzy matching
    lower = {c.lower(): c for c in df.columns}

    def pick(*keys, default=None):
        for k in keys:
            for cand in list(lower.keys()):
                if k in cand:
                    return lower[cand]
        return default

    # Try to map typical fields
    col_stock = pick("stock", "stk", default=None)
    col_year  = pick("year", default=None)
    col_make  = pick("make", default=None)
    col_model = pick("model", default=None)
    col_trim  = pick("trim", default=None)
    col_miles = pick("mile", default=None)
    col_price = pick("price", "sale price", "retail", default=None)

    # Book/spread candidates (we'll take the max of available estimates)
    col_nada  = pick("nada", "nadatsiminv", "nada retail", default=None)
    col_kbb   = pick("kbb", "kelly", "kelley", "kbb retail", default=None)
    col_bb    = pick("black book", "bbwh", "bbwhsale", "bb", default=None)
    col_book  = pick("book", "book value", default=None)

    out = pd.DataFrame()
    out["Stock"] = df[col_stock] if col_stock else pd.Series([""]*len(df))
    out["Year"] = df[col_year] if col_year else ""
    out["Make"] = df[col_make] if col_make else ""
    out["Model"] = df[col_model] if col_model else ""
    out["Trim"] = df[col_trim] if col_trim else ""

    # numerics
    def to_num_series(s):
        if s is None:
            return pd.Series([np.nan]*len(df))
        return pd.to_numeric(s.apply(_to_num), errors="coerce")

    out["Miles"] = to_num_series(df[col_miles] if col_miles else None).fillna(0)
    out["Price"] = to_num_series(df[col_price] if col_price else None).fillna(0)

    # best book value we can assemble
    candidates = []
    for c in [col_book, col_nada, col_kbb, col_bb]:
        if c:
            candidates.append(to_num_series(df[c]))
    if len(candidates) > 0:
        out["BookValue"] = pd.concat(candidates, axis=1).max(axis=1)
    else:
        out["BookValue"] = np.nan

    # Spread/profit-ish signal
    out["Spread"] = (out["BookValue"] - out["Price"]).fillna(0)

    # Frame damage indicator: Stock starting with "X"
    out["Frame"] = out["Stock"].astype(str).str.upper().str.startswith("X")

    # Human-friendly label
    out["Label"] = (
        out["Year"].astype(str).str.replace(".0", "", regex=False).str.strip() + " " +
        out["Make"].astype(str).str.strip() + " " +
        out["Model"].astype(str).str.strip() + " " +
        out["Trim"].astype(str).str.strip()
    ).str.replace(r"\s+", " ", regex=True).str.strip()

    return out

@st.cache_data(show_spinner=False)
def load_inventory(file_bytes: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(file_bytes)) if ext == ".csv" else pd.read_excel(BytesIO(file_bytes))
    return normalize_inventory(df)

# ──────────────────────────────────────────────────────────────────────────────
# Lender scoring / selection
# ──────────────────────────────────────────────────────────────────────────────
def score_lender(row, features):
    cred = features["credit"]
    repos = features["repos"]
    job = features["job_months"]
    income = features["income"] + features["gig_income"]
    down = features["down"]
    has_dl = features["has_dl"]
    gig = features["gig"]

    # Hard gates
    if not (float(row.MinScore or 0) <= cred <= float(row.MaxScore or 999)):
        return (False, "Score outside program", 0.0)
    if repos > float(row.MaxRepos or 99):                 return (False, "Too many repos", 0.0)
    if job   < float(row.MinJobMonths or 0):              return (False, "Insufficient job time", 0.0)
    if income < float(row.MinIncome or 0):                return (False, "Insufficient income", 0.0)
    if down   < float(row.MinDown or 0):                  return (False, "Needs more down", 0.0)
    if (not bool(row.AllowNoDL)) and has_dl == "No":      return (False, "DL required", 0.0)
    if (not bool(row.AllowGig)) and gig and features["gig_income"] > 0:
        return (False, "Gig income not allowed", 0.0)

    # Soft score — center of score window + more down + more income
    mid = (float(row.MinScore or 0) + float(row.MaxScore or 999))/2.0
    score = 0
    score += 100 - abs(cred - mid)*0.5
    score += min(1000, down)/20
    score += min(4000, income)/40
    score += 10 if has_dl == "Yes" else 0
    score += 15 if (gig and bool(row.AllowGig)) else 0
    return (True, "Meets guidelines", float(score))

def recommend_lenders(rules_df: pd.DataFrame, features: dict, topn=5):
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
            "MaxRepos": r.MaxRepos,
            "AllowFrame": bool(r.AllowFrame),
        })
    df = pd.DataFrame(rows).sort_values(["Eligible","Score"], ascending=[False, False]).reset_index(drop=True)
    top = df[df["Eligible"]].head(topn)
    pick = top.iloc[0] if len(top) else None
    return pick, top, df

# ──────────────────────────────────────────────────────────────────────────────
# Inventory scoring / selection (based on selected lender)
# ──────────────────────────────────────────────────────────────────────────────
def score_unit(row, lender: dict):
    """
    Higher spread, lower miles, lower price → better.
    Disallow frame if lender doesn't allow frame.
    """
    if (not lender["AllowFrame"]) and bool(row.get("Frame", False)):
        return -1e9  # harshly penalize

    spread = float(row.get("Spread", 0) or 0)
    miles  = float(row.get("Miles", 0) or 0)
    price  = float(row.get("Price", 0) or 0)

    score = 0.0
    score += spread / 150.0
    score += (50000 - min(miles, 50000)) / 2000.0
    score += (20000 - min(price, 20000)) / 2000.0
    return float(score)

def pick_units_for_lender(inventory_df: pd.DataFrame, lender_row: dict, topn=5):
    if inventory_df is None or len(inventory_df)==0 or lender_row is None:
        return pd.DataFrame()

    work = inventory_df.copy()
    work["UnitScore"] = work.apply(lambda r: score_unit(r, lender_row), axis=1)
    work = work.sort_values("UnitScore", ascending=False).head(topn)
    return work[["Stock","Label","Miles","Price","BookValue","Spread","Frame","UnitScore"]]

# ──────────────────────────────────────────────────────────────────────────────
# Session state defaults
# ──────────────────────────────────────────────────────────────────────────────
if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_RATE_RULES.copy()

if "inventory" not in st.session_state:
    st.session_state["inventory"] = None

st.title("SmartDesk – Desking Assistant")
st.caption("Upload a rate sheet + inventory. Enter basics. Get lender + Top 5 units.")

with st.expander("What files look like", expanded=False):
    st.markdown("""
**Rate sheet:** columns (case-insensitive) →  
`Lender, MinScore, MaxScore, MaxRepos, MinJobMonths, MinIncome, MinDown, AllowGig, AllowNoDL, AllowFrame`  

- Blank `MinScore` = **no minimum** (Gateway case)
- “blank / n/a / —” are treated as empty

**Inventory:** we try to detect columns:
- Stock, Year, Make, Model, Trim, Miles, Price
- Any of: Book, NADA, KBB, Black Book (we take the **max** available as BookValue)

**Frame damage:** stock numbers starting with **“X”** are flagged and excluded if the lender doesn’t allow frame.
""")

# ──────────────────────────────────────────────────────────────────────────────
# Inputs + uploads
# ──────────────────────────────────────────────────────────────────────────────
left, right = st.columns([1.15, 1])

with left:
    st.subheader("Deal Input")
    with st.form("deal_form"):
        c1,c2,c3 = st.columns(3)
        with c1:
            credit = st.number_input("Credit Score", 300, 850, 620, 1)
            income = st.number_input("Monthly Income ($/mo)", 0, 20000, 3000, 50)
            job_years = st.number_input("Job Time (years)", 0, 40, 0, 1)
        with c2:
            repos = st.number_input("of Repos", 0, 10, 0, 1)
            has_dl = st.selectbox("Driver's License?", ["Yes","No"])
            gig_flag = st.checkbox("Gig / DoorDash income?")
        with c3:
            trade_eq = st.number_input("Trade Equity ($)", -20000, 20000, 0, 100)
            down = st.number_input("Down Payment ($)", 0, 20000, 1000, 50)
            gig_income = st.number_input("Gig Income ($/mo)", 0, 20000, 0, 50)

        job_months = job_years*12 + st.number_input("Job Time (months)", 0, 11, 6, 1)

        submitted = st.form_submit_button("Evaluate Deal", type="primary")

with right:
    st.subheader("Uploads")
    rs_file = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"])
    if rs_file is not None:
        try:
            rs_ext = ".csv" if rs_file.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["rate_rules"] = load_rate_sheet(rs_file.read(), rs_ext)
            st.success(f"Loaded {len(st.session_state['rate_rules'])} lender rows.")
        except Exception as e:
            st.error(f"Rate sheet error: {e}")

    inv_file = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"])
    if inv_file is not None:
        try:
            inv_ext = ".csv" if inv_file.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["inventory"] = load_inventory(inv_file.read(), inv_ext)
            st.success(f"Loaded {len(st.session_state['inventory'])} inventory rows.")
        except Exception as e:
            st.error(f"Inventory error: {e}")

    with st.expander("Current Rate Rules (top 20)", expanded=False):
        st.dataframe(st.session_state["rate_rules"].head(20), use_container_width=True)

# ──────────────────────────────────────────────────────────────────────────────
# Decision + output
# ──────────────────────────────────────────────────────────────────────────────
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
    }

    rules = st.session_state["rate_rules"].copy()
    pick, top_lenders, audit_lenders = recommend_lenders(rules, features, topn=5)

    st.markdown("### Result")
    lcol, rcol = st.columns([1.1, 1])
    with lcol:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        if pick is not None:
            st.markdown('<div class="metric">✅ Recommended Lender</div>', unsafe_allow_html=True)
            st.markdown(f"**{pick['Lender']}**  \n<span class='small'>{pick['Reason']}</span>", unsafe_allow_html=True)
            st.markdown("<hr/>", unsafe_allow_html=True)
            st.markdown(f"- Est. **Score Rank**: {pick['Score']}")
            st.markdown(f"- **Min Down**: ${int(pick['MinDown'] or 0)} • **Min Income**: ${int(pick['MinIncome'] or 0)}/mo")
            st.markdown(f"- **Max Repos**: {int(pick['MaxRepos'] or 0)} • **Min Job**: {int(pick['MinJobMonths'] or 0)} mo")
        else:
            st.markdown('<div class="metric">❌ No Eligible Lender Found</div>', unsafe_allow_html=True)
            st.markdown("Try increasing down, adding a co-app, or choosing a cleaner unit.")
        st.markdown("</div>", unsafe_allow_html=True)

    with rcol:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="metric">Top 5 Lenders</div>', unsafe_allow_html=True)
        if len(top_lenders):
            st.dataframe(top_lenders[["Lender","Score","Reason","MinDown","MinIncome","MinJobMonths","MaxRepos"]],
                         use_container_width=True, height=210)
        else:
            st.caption("No eligible lenders with current inputs.")
        st.markdown("</div>", unsafe_allow_html=True)

    # Top 5 units for the chosen lender
    st.markdown("### Inventory Matches")
    inv = st.session_state["inventory"]
    if inv is None or len(inv)==0:
        st.info("Upload inventory to see Top 5 matching units.")
    else:
        top_units = pick_units_for_lender(inv, pick.to_dict() if pick is not None else None, topn=5)
        if len(top_units)==0:
            st.caption("No matching units (or no lender).")
        else:
            st.dataframe(top_units, use_container_width=True, height=280)

    with st.expander("Audit (all lenders)", expanded=False):
        st.dataframe(audit_lenders, use_container_width=True)

else:
    st.info("Fill out the form and click **Evaluate Deal**.")
