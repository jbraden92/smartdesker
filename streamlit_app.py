import re
from io import BytesIO

import pandas as pd
import streamlit as st

# =========================
# Page config + light theming
# =========================
st.set_page_config(page_title="SmartDesk — Desking Assistant", page_icon="📋", layout="wide")
st.markdown(
    """
    <style>
    .card {
        border-radius: 12px;
        padding: 14px 16px;
        border: 1px solid rgba(250, 250, 250, 0.12);
        background: rgba(250,250,250,0.03);
        margin-bottom: 12px;
    }
    .metric {font-size: 22px; font-weight: 700; margin-bottom: 6px}
    .em {opacity:.75}
    .tight th, .tight td { padding-top: 6px !important; padding-bottom: 6px !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# Helpers
# =========================

def yn(val):
    """Convert many truthy forms to bool."""
    if isinstance(val, str):
        return val.strip().lower() in ("y", "yes", "true", "1")
    if isinstance(val, (int, float)):
        return val == 1
    return bool(val)

def clean_num(x, default=None):
    """Float with safe fallback."""
    try:
        if pd.isna(x) or x == "":
            return default
        return float(x)
    except Exception:
        return default

def pickcol(cols_lc, df, name, default_series=None):
    """Pick column by lower-name, else fallback to series of defaults."""
    col = cols_lc.get(name)
    if col is None:
        if default_series is not None:
            return default_series
        return pd.Series([None] * len(df))
    return df[col]

# -------------------------
# Load rate sheet
# -------------------------
@st.cache_data(show_spinner=False)
def load_rate_sheet_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    if ext == ".csv":
        df = pd.read_csv(BytesIO(data))
    else:
        df = pd.read_excel(BytesIO(data))

    # Normalize: make lower->original map
    cols_lc = {c.lower().strip(): c for c in df.columns}

    # Build normalized table with optional columns
    out = pd.DataFrame({
        "Lender": pickcol(cols_lc, df, "lender").fillna("").astype(str).str.strip(),
        "Program": pickcol(cols_lc, df, "program"),
        "MinScore": pickcol(cols_lc, df, "minscore").apply(lambda x: clean_num(x, None)),
        "MaxScore": pickcol(cols_lc, df, "maxscore").apply(lambda x: clean_num(x, None)),
        "MaxRepos": pickcol(cols_lc, df, "maxrepos").apply(lambda x: clean_num(x, None)),
        "MinJobMonths": pickcol(cols_lc, df, "minjobmonths").apply(lambda x: clean_num(x, None)),
        "MinIncome": pickcol(cols_lc, df, "minincome").apply(lambda x: clean_num(x, None)),
        "MinDown": pickcol(cols_lc, df, "mindown").apply(lambda x: clean_num(x, None)),
        "AllowGig": pickcol(cols_lc, df, "allowgig").apply(yn),
        "AllowNoDL": pickcol(cols_lc, df, "allownodl").apply(yn),
        "AllowFrame": pickcol(cols_lc, df, "allowframe").apply(yn),
        # Optional caps:
        "MaxLTV": pickcol(cols_lc, df, "maxltv").apply(lambda x: clean_num(x, None)),
        "MaxMiles": pickcol(cols_lc, df, "maxmiles").apply(lambda x: clean_num(x, None)),
        "MaxTerm": pickcol(cols_lc, df, "maxterm").apply(lambda x: clean_num(x, None)),
    })

    # Drop blanks
    out = out[out["Lender"].astype(str).str.strip() != ""].reset_index(drop=True)

    # Guarantee types
    for c in ["MinScore","MaxScore","MaxRepos","MinJobMonths","MinIncome","MinDown","MaxLTV","MaxMiles","MaxTerm"]:
        if c in out.columns:
            out[c] = out[c].astype("float64")

    return out

def adjust_special_score_rules(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove MinScore as a gate for Gateway, Exeter, and CPS
    per your request.
    """
    if df.empty:
        return df
    lowered = df["Lender"].str.lower()
    mask = (
        lowered.str.contains("gateway") |
        lowered.str.contains("exeter") |
        lowered.str.contains("cps") |
        lowered.str.contains("consumer portfolio")
    )
    # If MinScore is used, set to None (no gate)
    df.loc[mask, "MinScore"] = None
    return df

# -------------------------
# Hard-coded (current) inventory
#   – You can paste your real list here anytime
#   – Filter rule applied later: Price >= 4000 and Stock not starting W/T
# -------------------------
HARD_INVENTORY = pd.DataFrame([
    {"Stock":"A001","Year":2016,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93500,"Price":9990,"BookValue":11800},
    {"Stock":"A002","Year":2017,"Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"Price":10450,"BookValue":12200},
    {"Stock":"A003","Year":2014,"Make":"Toyota","Model":"Camry","Trim":"SE","Miles":128590,"Price":8495,"BookValue":10250},
    {"Stock":"A004","Year":2015,"Make":"Nissan","Model":"Altima","Trim":"2.5 S","Miles":119400,"Price":7795,"BookValue":9300},
    {"Stock":"A005","Year":2014,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111200,"Price":8895,"BookValue":10600},
    {"Stock":"A006","Year":2016,"Make":"Volkswagen","Model":"Jetta","Trim":"S","Miles":98800,"Price":7990,"BookValue":9100},
    {"Stock":"B006","Year":2011,"Make":"Kia","Model":"Soul","Trim":"Base","Miles":171500,"Price":3390,"BookValue":4200},  # excluded by price
    {"Stock":"X100","Year":2012,"Make":"BMW","Model":"328i","Trim":"Base","Miles":122300,"Price":7500,"BookValue":8000},
    {"Stock":"W100","Year":2014,"Make":"Ford","Model":"Focus","Trim":"SE","Miles":134200,"Price":5200,"BookValue":6700},   # excluded by 'W'
    {"Stock":"T200","Year":2016,"Make":"Toyota","Model":"RAV4","Trim":"LE","Miles":99000,"Price":13990,"BookValue":15800}, # excluded by 'T'
    {"Stock":"H123","Year":2015,"Make":"Honda","Model":"CR-V","Trim":"EX","Miles":125000,"Price":11990,"BookValue":14000},
    {"Stock":"K777","Year":2012,"Make":"Chevrolet","Model":"Malibu","Trim":"LS","Miles":145000,"Price":4995,"BookValue":5200},
    {"Stock":"S888","Year":2018,"Make":"Nissan","Model":"Sentra","Trim":"SV","Miles":72000,"Price":10995,"BookValue":12800},
])

def load_inventory_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    if ext == ".csv":
        df = pd.read_csv(BytesIO(data))
    else:
        df = pd.read_excel(BytesIO(data))

    cols_lc = {c.lower().strip(): c for c in df.columns}
    def get(name, default=None):
        c = cols_lc.get(name)
        if c is None:
            return [default] * len(df) if not isinstance(default, list) else default
        return df[c]

    out = pd.DataFrame({
        "Stock": get("stock", ""),
        "Year": get("year", None),
        "Make": get("make", ""),
        "Model": get("model", ""),
        "Trim": get("trim", ""),
        "Miles": pd.Series(get("miles", None)).apply(lambda x: clean_num(x, None)),
        "Price": pd.Series(get("price", None)).apply(lambda x: clean_num(x, None)),
        "BookValue": pd.Series(get("bookvalue", None)).apply(lambda x: clean_num(x, None)),
    })
    return out

def normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Stock","Year","Make","Model","Trim","Miles","Price","BookValue","LTV"])
    # basic types
    for c in ["Year","Miles","Price","BookValue"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # filter: price >= 4000
    df = df[(df["Price"] >= 4000)]
    # filter: exclude stock starting with W or T (case-insensitive)
    df = df[~df["Stock"].astype(str).str.upper().str.startswith(("W", "T"))]

    # compute LTV (if BookValue available)
    df["LTV"] = (df["Price"] / df["BookValue"] * 100.0).round(1)
    return df.reset_index(drop=True)

# -------------------------
# Scoring / recommendation
# -------------------------
def score_lender(row, features):
    """
    Gates + rank for borrower features (not vehicle).
    Gates (if value is not None): repos, job months, income, down, score.
    """
    cred = features["credit"]
    repos = features["repos"]
    job = features["job_months"]
    income = features["income"] + features["gig_income"]
    down = features["down"]
    has_dl = features["has_dl"]
    gig = features["gig"]

    # score gates (MinScore disabled for special lenders via adjust_special_score_rules)
    if row.MinScore is not None and row.MaxScore is not None:
        if not (row.MinScore <= cred <= row.MaxScore):
            return (False, "Score outside window", 0.0)
    elif row.MaxScore is not None:
        if cred > row.MaxScore:
            return (False, "Above max score", 0.0)
    elif row.MinScore is not None:
        if cred < row.MinScore:
            return (False, "Below min score", 0.0)

    if row.MaxRepos is not None and repos > row.MaxRepos:
        return (False, "Too many repos", 0.0)
    if row.MinJobMonths is not None and job < row.MinJobMonths:
        return (False, "Insufficient job time", 0.0)
    if row.MinIncome is not None and income < row.MinIncome:
        return (False, "Insufficient income", 0.0)
    if row.MinDown is not None and down < row.MinDown:
        return (False, "Needs more down", 0.0)
    if (not bool(row.AllowNoDL)) and (has_dl == "No"):
        return (False, "DL required", 0.0)
    if (not bool(row.AllowGig)) and gig and features["gig_income"] > 0:
        return (False, "Gig income not allowed", 0.0)

    # soft rank
    score = 0.0
    if row.MinScore is not None and row.MaxScore is not None:
        window_mid = (row.MinScore + row.MaxScore) / 2.0
        score += 100.0 - abs(cred - window_mid) * 0.5
    score += min(1000, down) / 20.0
    score += min(4000, income) / 40.0
    score += (30.0 if gig and bool(row.AllowGig) else 0.0)
    score += (10.0 if has_dl == "Yes" else 0.0)
    return (True, "Meets borrower guidelines", round(score, 1))

def recommend_lenders(rules: pd.DataFrame, features: dict, topn=5):
    rows = []
    for _, r in rules.iterrows():
        ok, why, s = score_lender(r, features)
        rows.append({
            "Lender": r.Lender,
            "Eligible": ok,
            "Reason": why,
            "Score": s,
            "MinDown": r.MinDown,
            "MinIncome": r.MinIncome,
            "MinJobMonths": r.MinJobMonths,
            "MaxRepos": r.MaxRepos,
            "MaxLTV": r.MaxLTV if "MaxLTV" in r else None,
            "MaxMiles": r.MaxMiles if "MaxMiles" in r else None,
            "MaxTerm": r.MaxTerm if "MaxTerm" in r else None,
        })
    df = pd.DataFrame(rows).sort_values(["Eligible", "Score"], ascending=[False, False]).reset_index(drop=True)
    top = df[df["Eligible"]].head(topn)
    pick = top.iloc[0] if len(top) > 0 else None
    return pick, top, df

def recommend_units_for_lender(inventory: pd.DataFrame, lender_row: pd.Series, desired_term: int, topk=5):
    """
    Use LTV / miles / term constraints if present; otherwise defaults: MaxLTV 140%, MaxMiles 200k, MaxTerm 72.
    Rank by: lower LTV (<= MaxLTV), lower miles, and better spread (Book-Price).
    """
    if inventory is None or inventory.empty:
        return pd.DataFrame()

    max_ltv = lender_row.get("MaxLTV", None)
    max_miles = lender_row.get("MaxMiles", None)
    max_term = lender_row.get("MaxTerm", None)

    if pd.isna(max_ltv) or max_ltv is None: max_ltv = 140.0
    if pd.isna(max_miles) or max_miles is None: max_miles = 200000
    if pd.isna(max_term) or max_term is None: max_term = 72

    # term gate (only if lender has a max term and we exceeded it)
    term_ok = desired_term <= max_term

    df = inventory.copy()
    # LTV gate
    df = df[(df["BookValue"] > 0) & (df["LTV"] > 0)]
    df = df[df["LTV"] <= max_ltv + 1e-9]
    # miles gate
    df = df[df["Miles"] <= max_miles]
    # term gate
    if not term_ok:
        # If desired term exceeds lender cap, we'll show none
        return pd.DataFrame(columns=df.columns)

    # score: lower LTV better, lower miles better, bigger spread (book-price) better
    df["Spread"] = (df["BookValue"] - df["Price"]).fillna(0.0)
    df["UnitScore"] = (-df["LTV"] * 0.6) + (-df["Miles"] / 10000.0 * 0.2) + (df["Spread"] / 100.0 * 0.4)
    df = df.sort_values("UnitScore", ascending=False)
    keep_cols = ["Stock","Year","Make","Model","Trim","Miles","Price","BookValue","LTV","Spread","UnitScore"]
    return df[keep_cols].head(topk).reset_index(drop=True)

# -------------------------
# Rule Q&A
# -------------------------
def answer_rule_question(q: str, rules: pd.DataFrame):
    """
    Very simple keyword Q&A over the loaded rule table.
    Examples:
      - "Does Exeter allow frame damage?"
      - "Gateway gig income?"
      - "What is CPS min income?"
    """
    if rules is None or rules.empty or not q.strip():
        return None, None

    ql = q.lower()

    # guess lender by partial match
    lender_hits = []
    for lender in rules["Lender"].unique():
        l = lender.lower()
        if any(tok and tok in l for tok in re.split(r"[^a-z0-9]+", ql)):
            lender_hits.append(lender)

    # pick attribute(s)
    field_map = {
        "gig": "AllowGig",
        "doordash": "AllowGig",
        "no dl": "AllowNoDL",
        "license": "AllowNoDL",
        "frame": "AllowFrame",
        "frame damage": "AllowFrame",
        "repo": "MaxRepos",
        "repos": "MaxRepos",
        "score": "MinScore",
        "min score": "MinScore",
        "max score": "MaxScore",
        "income": "MinIncome",
        "down": "MinDown",
        "job": "MinJobMonths",
        "time": "MinJobMonths",
        "ltv": "MaxLTV",
        "miles": "MaxMiles",
        "term": "MaxTerm",
    }
    attr = None
    for key, col in field_map.items():
        if key in ql:
            attr = col
            break

    matched = rules
    if lender_hits:
        matched = matched[matched["Lender"].isin(lender_hits)]

    if attr and attr in matched.columns:
        view = matched[["Lender", attr]].drop_duplicates().reset_index(drop=True)
        return attr, view
    # fallback: show the row(s)
    return None, matched.drop_duplicates().reset_index(drop=True)

# =========================
# Session state for rules
# =========================
if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = pd.DataFrame(columns=[
        "Lender","Program","MinScore","MaxScore","MaxRepos","MinJobMonths",
        "MinIncome","MinDown","AllowGig","AllowNoDL","AllowFrame","MaxLTV","MaxMiles","MaxTerm"
    ])

# =========================
# UI
# =========================
st.title("SmartDesk — Desking Assistant")
st.caption("Upload a rate sheet + inventory. Enter basics. Get lender + Top 5 units.")

with st.expander("What files look like", expanded=False):
    st.markdown(
        """
        **Rate sheet (CSV/XLSX)** — column names (case-insensitive):
        `Lender, Program, MinScore, MaxScore, MaxRepos, MinJobMonths, MinIncome, MinDown, AllowGig, AllowNoDL, AllowFrame, MaxLTV, MaxMiles, MaxTerm`

        **Inventory (CSV/XLSX)** — column names:  
        `Stock, Year, Make, Model, Trim, Miles, Price, BookValue`
        """
    )

left, right = st.columns([1.25, 1])

# ---------- Deal inputs
with left:
    st.subheader("Deal Input")
    with st.form("deal_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            credit = st.number_input("Credit Score", 300, 850, 620, 1)
            income = st.number_input("Monthly Income ($/mo)", 0, 20000, 3000, 50)
            job_years = st.number_input("Job Time (years)", 0, 50, 0, 1)
        with c2:
            repos = st.number_input("of Repos", 0, 10, 0, 1)
            has_dl = st.selectbox("Driver's License?", ["Yes", "No"])
            job_months_only = st.number_input("Job Time (months)", 0, 11, 6, 1)
        with c3:
            trade_eq = st.number_input("Trade Equity ($)", -20000, 20000, 0, 100)
            down = st.number_input("Down Payment ($)", 0, 20000, 1000, 50)
            desired_term = st.number_input("Desired Term (months)", 12, 96, 60, 6)

        gig_flag = st.checkbox("Gig / DoorDash income?")
        gig_income = st.number_input("Gig Income ($/mo)", 0, 10000, 0, 50)

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

# ---------- Uploads / Q&A
with right:
    st.subheader("Uploads")
    # Rate sheet
    rs_file = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"])
    if rs_file is not None:
        try:
            ext = ".csv" if rs_file.name.lower().endswith(".csv") else ".xlsx"
            rules = load_rate_sheet_from_bytes(rs_file.read(), ext)
            rules = adjust_special_score_rules(rules)
            st.session_state["rate_rules"] = rules
            st.success(f"Loaded {len(rules)} lender rules from **{rs_file.name}**")
        except Exception as e:
            st.error(f"Rate sheet error: {e}")

    # Inventory
    inv_file = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"])
    used_inventory = None
    if inv_file is not None:
        try:
            ext = ".csv" if inv_file.name.lower().endswith(".csv") else ".xlsx"
            used_inventory = load_inventory_from_bytes(inv_file.read(), ext)
            st.success(f"Loaded {len(used_inventory)} inventory rows from **{inv_file.name}**")
        except Exception as e:
            st.error(f"Inventory error: {e}")

    st.caption("If no inventory provided, the app uses a built-in sample list.")

    with st.expander("Current Rate Rules (top 20)", expanded=False):
        if st.session_state["rate_rules"].empty:
            st.info("No rate sheet loaded yet.")
        else:
            st.dataframe(st.session_state["rate_rules"].head(20), use_container_width=True)

    st.subheader("Ask about a lender rule")
    q = st.text_input("Example: *Does Exeter allow frame damage?*  or  *Gateway gig income?*")
    if q:
        attr, view = answer_rule_question(q, st.session_state["rate_rules"])
        if view is None or view.empty:
            st.warning("No matching lender/rule found.")
        else:
            if attr:
                st.write(f"**Answer column:** `{attr}`")
            st.dataframe(view, use_container_width=True)

# =========================
# Evaluate
# =========================
if submitted:
    total_job_months = int(job_years * 12 + job_months_only)

    features = {
        "credit": credit,
        "income": income,
        "job_months": total_job_months,
        "repos": repos,
        "down": down,
        "trade_eq": trade_eq,
        "gig": bool(gig_flag),
        "gig_income": gig_income if gig_flag else 0,
        "has_dl": has_dl,
        "co_score": co_score,
        "co_income": co_income,
        "term": desired_term,
    }

    # rules + inventory
    rules = adjust_special_score_rules(st.session_state["rate_rules"].copy())
    inv = used_inventory if used_inventory is not None else HARD_INVENTORY.copy()
    inv = normalize_inventory(inv)

    # Lender picks
    pick, top, audit = recommend_lenders(rules, features, topn=5)

    st.markdown("### Result")
    cols = st.columns([1.1, 1])
    with cols[0]:
        if pick is not None:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="metric">✅ Recommended Lender</div>', unsafe_allow_html=True)
            st.markdown(f"**{pick['Lender']}**  \n<span class='em'>{pick['Reason']}</span>", unsafe_allow_html=True)
            st.markdown("<hr/>", unsafe_allow_html=True)
            st.markdown(f"- Est. **Rank**: {pick['Score']}")
            st.markdown(f"- **Min Down**: ${0 if pd.isna(pick['MinDown']) or pick['MinDown'] is None else int(pick['MinDown'])}  •  "
                        f"**Min Income**: ${0 if pd.isna(pick['MinIncome']) or pick['MinIncome'] is None else int(pick['MinIncome'])}/mo")
            st.markdown(f"- **Max Repos**: {int(pick['MaxRepos']) if not pd.isna(pick['MaxRepos']) else '—'}  •  "
                        f"**Min Job**: {int(pick['MinJobMonths']) if not pd.isna(pick['MinJobMonths']) else '—'} mo")
            # Optional caps if present
            s_caps = []
            if not pd.isna(pick.get("MaxLTV", None)):
                s_caps.append(f"Max LTV {int(pick['MaxLTV'])}%")
            if not pd.isna(pick.get("MaxMiles", None)):
                s_caps.append(f"Max Miles {int(pick['MaxMiles'])}")
            if not pd.isna(pick.get("MaxTerm", None)):
                s_caps.append(f"Max Term {int(pick['MaxTerm'])} mo")
            if s_caps:
                st.markdown("• " + "  •  ".join(s_caps))
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="metric">❌ No Eligible Lender Found</div>', unsafe_allow_html=True)
            st.markdown("Try more down, add co-app income, or pick a unit with lower LTV/miles.", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    with cols[1]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="metric">Top 5 Lenders</div>', unsafe_allow_html=True)
        if len(top) > 0:
            st.dataframe(
                top[["Lender","Score","Reason","MinDown","MinIncome","MinJobMonths","MaxRepos","MaxLTV","MaxMiles","MaxTerm"]],
                use_container_width=True, height=210, column_config={"Score":{"format":"%.1f"}}
            )
        else:
            st.caption("No eligible lenders for current inputs.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### Suggested Units for the Picked Lender")
    if pick is None or inv.empty:
        st.caption("No suggestions available.")
    else:
        units = recommend_units_for_lender(inv, pick, desired_term, topk=5)
        if units.empty:
            st.caption("No units fit LTV/miles/term for this lender.")
        else:
            st.dataframe(units, use_container_width=True, height=250, column_config={
                "Price":{"format":"$%.0f"},
                "BookValue":{"format":"$%.0f"},
                "LTV":{"format":"%.1f%%"},
                "Spread":{"format":"$%.0f"},
                "UnitScore":{"format":"%.2f"},
            }, classes="tight")

    st.markdown("### Deal Snapshot")
    snapshot = {
        "Primary Applicant": {
            "Credit Score": credit,
            "Monthly Income": income,
            "Job Months": total_job_months,
            "Repos": repos,
            "Driver's License": has_dl,
        },
        "Structure": {
            "Down Payment": down,
            "Trade Equity": trade_eq,
            "Gig Income": gig_income if gig_flag else 0,
            "Desired Term (mo)": desired_term
        },
        "Decision": {
            "Picked Lender": None if pick is None else pick["Lender"],
            "Rank Score": None if pick is None else pick["Score"],
        }
    }
    st.json(snapshot, expanded=False)

    with st.expander("Audit (all lenders)", expanded=False):
        st.dataframe(audit, use_container_width=True, height=260)
else:
    st.info("Fill out the form and click **Evaluate Deal**.")

