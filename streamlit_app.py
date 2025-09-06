# streamlit_app.py
import streamlit as st
import pandas as pd
from io import BytesIO
import math

st.set_page_config(page_title="SmartDesk — Desking Assistant", page_icon="📋", layout="wide")

# --------------------------
# Style / chrome
# --------------------------
st.markdown(
    """
    <style>
      .card {border-radius:10px;padding:14px 16px;border:1px solid rgba(250,250,250,.12);background:rgba(250,250,250,.03)}
      .metric {font-size:20px;font-weight:700;margin-bottom:4px}
      .muted {opacity:.75}
      .ok {color:#7DD97C;font-weight:600}
      .warn {color:#F2C14E;font-weight:600}
      .bad {color:#EF6C6C;font-weight:600}
      .small {font-size:12px;opacity:.75}
      #MainMenu {visibility:hidden} footer {visibility:hidden}
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# Helpers
# =========================================================
def _yn(x, default=False):
    if isinstance(x, str):
        return x.strip().lower() in ("y","yes","true","1")
    if isinstance(x, (int, float)):
        return x == 1
    return bool(x) if x is not None else default

def _num(x, default=0.0):
    try:
        if pd.isna(x) or x == "":
            return default
        return float(x)
    except Exception:
        return default

def parse_bands(val):
    """
    Accepts:
      - dict already (e.g., {"0":1.2,"560":1.35})
      - JSON-like string '0:1.20;560:1.35;600:1.49' or '0=1.2,560=1.35'
      - blank -> {}
    Returns dict with int score floors -> float LTV
    """
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return {}
    if isinstance(val, dict):
        try:
            return {int(k): float(v) for k, v in val.items()}
        except Exception:
            return {}
    s = str(val).strip()
    if not s:
        return {}
    # Normalize separators
    s = s.replace(",", ";").replace("|", ";")
    pairs = []
    for part in s.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
        elif "=" in part:
            k, v = part.split("=", 1)
        else:
            continue
        try:
            pairs.append((int(k.strip()), float(v.strip())))
        except Exception:
            continue
    return dict(pairs)

def ltv_from_bands(score, base_ltv, bands: dict):
    """Pick the highest score floor <= score, else fall back to base_ltv."""
    if not bands:
        return float(base_ltv)
    best = None
    for floor, l in bands.items():
        if score >= int(floor):
            if best is None or int(floor) > best[0]:
                best = (int(floor), float(l))
    return best[1] if best else float(base_ltv)

def price_cap_from_book(book, ltv):
    try:
        return round(max(0.0, float(book)*float(ltv)), 2)
    except Exception:
        return 0.0

# =========================================================
# Defaults (can be overridden by uploads)
# Includes score-band LTVs, term/miles caps
# =========================================================
DEFAULT_RULES = pd.DataFrame([
    # Lender, MinScore, MaxScore, MaxRepos, MinJobMonths, MinIncome, MinDown, AllowGig, AllowNoDL, AllowFrame, Program, Base LTV, Bands, MaxBackEnd, MaxTerm, MaxMiles, Notes
    ["Gateway Financial Solutions",  0,  750, 2, 12, 1800, 0,  True, False, False, "Near/Sub",
     1.49, "0:1.35;560:1.49;600:1.51", 2400, 72, 140000, "Gateway likes stable job time & generous advance on stronger scores."],
    ["Global Lending Services",     520, 720, 2,  6, 2200, 500, True, False, False, "Near/Sub",
     1.30, "0:1.20;560:1.30;600:1.35", 1800, 72, 135000, "GLS conservative advance; solid when payment matters."],
    ["Consumer Portfolio Services", 520, 720, 3,  3, 2000, 0,  True, False, False, "Near/Sub",
     1.32, "0:1.25;560:1.32;600:1.36", 2000, 75, 150000, "CPS flexible, decent stretch."],
    ["Exeter Finance",              520, 710, 2,  6, 2000, 500, True, False, False, "Near/Sub",
     1.20, "0:1.15;560:1.20;600:1.25", 1500, 75, 130000, "Tighter advance; watch second income rules."],
    ["Westlake Financial",          0,   800, 9,  0, 1500, 0,  True, True,  False, "Subprime",
     1.18, "0:1.15;560:1.18;600:1.20", 1000, 72, 200000, "Catch-all; fast approvals; conservative advance."],
    ["Flagship Credit Acceptance",  560, 720, 2, 12, 2500, 500, False,False, True,  "Near/Sub",
     1.40, "560:1.40;600:1.49",       2200, 72, 125000, "Great for cleaner near-sub with higher income."],
], columns=["Lender","MinScore","MaxScore","MaxRepos","MinJobMonths","MinIncome","MinDown",
           "AllowGig","AllowNoDL","AllowFrame","Program","LTV","Bands","MaxBackEnd","MaxTerm","MaxMiles","Notes"]
)

DEFAULT_INVENTORY = pd.DataFrame([
    ["A001", 2016, "Chevrolet", "Equinox", "LT",     93500,  9990, 11990],
    ["A002", 2017, "Ford",      "Edge",    "SEL",   102300, 10450, 12990],
    ["A003", 2014, "Toyota",    "Camry",   "SE",    118500,  8495, 10495],
    ["A004", 2012, "Nissan",    "Altima",  "2.5 S", 119400,  7795,  9495],
    ["A005", 2016, "Dodge",     "Journey", "SXT",   111200,  8995, 10995],
    ["A006", 2011, "Kia",       "Soul",    "Base",  171500,  3390,  4990], # will be filtered
    ["A007", 2018, "Hyundai",   "Elantra", "SEL",    84500, 10990, 13990],
    ["A008", 2019, "Nissan",    "Versa",   "SV",     61200,  9995, 12495],
], columns=["Stock","Year","Make","Model","Trim","Miles","BookValue","Price"])

# Session
if "rules" not in st.session_state:
    st.session_state["rules"] = DEFAULT_RULES.copy()
if "inventory" not in st.session_state:
    st.session_state["inventory"] = DEFAULT_INVENTORY.copy()

# =========================================================
# Upload parsers (rate sheets + inventory)
# Support extra columns: MaxTerm, MaxMiles, Bands
# =========================================================
@st.cache_data(show_spinner=False)
def parse_rate_sheet(data: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(data)) if ext == ".csv" else pd.read_excel(BytesIO(data))
    cols = {c.lower().strip(): c for c in df.columns}
    def col(name, default=None):
        c = cols.get(name, None)
        return df[c] if c else [default]*len(df)

    out = pd.DataFrame({
        "Lender":       col("lender",""),
        "MinScore":     [_num(x,0)   for x in col("minscore",0)],
        "MaxScore":     [_num(x,999) for x in col("maxscore",999)],
        "MaxRepos":     [_num(x,99)  for x in col("maxrepos",99)],
        "MinJobMonths": [_num(x,0)   for x in col("minjobmonths",0)],
        "MinIncome":    [_num(x,0)   for x in col("minincome",0)],
        "MinDown":      [_num(x,0)   for x in col("mindown",0)],
        "AllowGig":     [_yn(x,True) for x in col("allowgig","Yes")],
        "AllowNoDL":    [_yn(x,False)for x in col("allownodl","No")],
        "AllowFrame":   [_yn(x,False)for x in col("allowframe","No")],
        "Program":      col("program","Near/Sub"),
        "LTV":          [_num(x,1.25) for x in col("ltv",1.25)],
        "Bands":        [parse_bands(x) for x in col("bands", None)],
        "MaxBackEnd":   [_num(x,2000) for x in col("maxbackend",2000)],
        "MaxTerm":      [_num(x,72)   for x in col("maxterm",72)],
        "MaxMiles":     [_num(x,150000) for x in col("maxmiles",150000)],
        "Notes":        col("notes",""),
    })
    out = out[out["Lender"].astype(str).str.strip()!=""].reset_index(drop=True)
    return out

@st.cache_data(show_spinner=False)
def parse_inventory_file(data: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(data)) if ext == ".csv" else pd.read_excel(BytesIO(data))
    cols = {c.lower().strip(): c for c in df.columns}
    def col(name, default=None):
        c = cols.get(name, None)
        return df[c] if c else [default]*len(df)

    inv = pd.DataFrame({
        "Stock":     col("stock",""),
        "Year":      col("year",0),
        "Make":      col("make",""),
        "Model":     col("model",""),
        "Trim":      col("trim",""),
        "Miles":     [_num(x,0) for x in col("miles",0)],
        "BookValue": [_num(x,0) for x in col("book", col("bookvalue",0))],
        "Price":     [_num(x,0) for x in col("price",0)],
    })
    inv = inv[inv["Stock"].astype(str).str.strip()!=""].reset_index(drop=True)
    return inv

# =========================================================
# UI
# =========================================================
st.title("SmartDesk — Desking Assistant")
st.caption("Uploads optional; we’ll use defaults if you skip them. We rank lenders, then show best 5 lender–unit pairs with lender cap pricing.")

with st.expander("What files look like", expanded=False):
    st.markdown(
        """
        **Rate sheet (case-insensitive columns):**  
        `Lender, MinScore, MaxScore, MaxRepos, MinJobMonths, MinIncome, MinDown, AllowGig, AllowNoDL, AllowFrame, Program, LTV, Bands, MaxBackEnd, MaxTerm, MaxMiles, Notes`  
        - `Bands` can be like: `0:1.20;560:1.35;600:1.49` (score floors → LTVs)

        **Inventory:**  
        `Stock, Year, Make, Model, Trim, Miles, Book (or BookValue), Price`
        """
    )

left, right = st.columns([1.25, 1])

with left:
    st.subheader("Deal Input")
    c1,c2,c3 = st.columns(3)
    with c1:
        score = st.number_input("Credit Score", 300, 850, 620, 1)
        monthly_income = st.number_input("Monthly Income ($/mo)", 0, 30000, 3000, 50)
        job_years = st.number_input("Job Time (years)", 0, 50, 1, 1)
    with c2:
        repos = st.number_input("# of Repos (reported)", 0, 10, 0, 1)
        dl = st.selectbox("Driver's License?", ["Yes","No"])
        down = st.number_input("Down Payment ($)", 0, 50000, 1000, 50)
    with c3:
        trade = st.number_input("Trade Equity ($)", -20000, 50000, 0, 100)
        gig_flag = st.checkbox("Gig / DoorDash income?")
        gig_income = st.number_input("Gig Income ($/mo)", 0, 20000, 0, 50)

    include_co = st.checkbox("Include Co-Applicant?")
    if include_co:
        co1, co2 = st.columns(2)
        with co1:
            co_score = st.number_input("Co-Applicant Score", 300, 850, 580, 1)
        with co2:
            co_income = st.number_input("Co-Applicant Income ($/mo)", 0, 20000, 0, 50)
    else:
        co_score, co_income = None, 0

    evaluate = st.button("Evaluate Deal", type="primary")

with right:
    st.subheader("Uploads")
    rs = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"])
    if rs:
        try:
            ext = ".csv" if rs.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["rules"] = parse_rate_sheet(rs.read(), ext)
            st.success(f"Loaded {len(st.session_state['rules'])} lenders from {rs.name}.")
        except Exception as e:
            st.error(f"Rate sheet error: {e}")

    inv_file = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"])
    if inv_file:
        try:
            ext = ".csv" if inv_file.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["inventory"] = parse_inventory_file(inv_file.read(), ext)
            st.success(f"Loaded {len(st.session_state['inventory'])} units from {inv_file.name}.")
        except Exception as e:
            st.error(f"Inventory error: {e}")

    with st.expander("Current Rate Rules (top 20)"):
        view_cols = ["Lender","Program","MinScore","MaxScore","MinIncome","MinDown","LTV","Bands","MaxBackEnd","MaxTerm","MaxMiles","Notes"]
        show_rules = st.session_state["rules"].copy()
        st.dataframe(show_rules[view_cols].head(20), use_container_width=True)

# =========================================================
# Core logic (gates, ranking, pairing)
# =========================================================
def normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df)==0:
        return pd.DataFrame(columns=["Stock","Year","Make","Model","Trim","Miles","BookValue","Price"])
    out = df.copy()
    out["Price"] = pd.to_numeric(out["Price"], errors="coerce").fillna(0)
    out = out[out["Price"] >= 4500]  # price gate
    out = out[~out["Stock"].astype(str).str.upper().str.startswith(("W","T"))]  # remove W*/T*
    return out.reset_index(drop=True)

def gates_ok(rule_row, F, vehicle=None):
    """Hard gates — if vehicle provided, enforce miles + (optionally) frame."""
    # customer gates
    job_months_total = int(F["job_years"]*12 + F["job_months"])
    if not (rule_row.MinScore <= F["score"] <= rule_row.MaxScore):
        return False, "Score outside window"
    if F["repos"] > rule_row.MaxRepos:
        return False, "Too many repos"
    if job_months_total < rule_row.MinJobMonths:
        return False, "Insufficient job time"
    if (F["income"] + (F["gig_income"] if F["gig"] else 0) + F["co_income"]) < rule_row.MinIncome:
        return False, "Income below minimum"
    if F["down"] < rule_row.MinDown:
        return False, "Needs more down"
    if (not rule_row.AllowNoDL) and (F["dl"] == "No"):
        return False, "DL required"
    if (not rule_row.AllowGig) and F["gig"] and F["gig_income"]>0:
        return False, "Gig income not allowed"

    # vehicle gates (miles)
    if vehicle is not None and "Miles" in vehicle:
        if float(vehicle["Miles"]) > float(rule_row.MaxMiles):
            return False, f"Exceeds max miles ({int(rule_row.MaxMiles)})"

    return True, "Meets program"

def rank_score(rule_row, F):
    mid = (rule_row.MinScore + rule_row.MaxScore)/2
    s = 100 - abs(F["score"] - mid)*0.5
    avail_income = min(7000, F["income"] + (F["gig_income"] if F["gig"] else 0) + F["co_income"])
    s += avail_income/70
    s += min(3000, F["down"])/30
    if str(rule_row.Lender).lower().startswith("gateway"):
        s += 6
    return round(float(s),1)

def recommend_lenders(rules: pd.DataFrame, F: dict, topn=7):
    rows = []
    for _, r in rules.iterrows():
        ok, why = gates_ok(r, F)
        score = rank_score(r, F) if ok else 0
        rows.append({
            "Lender": r.Lender, "Program": r.Program, "Eligible": ok, "Reason": why, "Score": score,
            "BaseLTV": float(r.LTV), "Bands": r.Bands if isinstance(r.Bands, dict) else parse_bands(r.Bands),
            "CapLTV": ltv_from_bands(F["score"], r.LTV, r.Bands if isinstance(r.Bands, dict) else parse_bands(r.Bands)),
            "MaxBackEnd": float(r.MaxBackEnd), "MinDown": float(r.MinDown), "MinIncome": float(r.MinIncome),
            "MaxTerm": int(r.MaxTerm), "MaxMiles": int(r.MaxMiles), "Notes": r.Notes
        })
    df = pd.DataFrame(rows).sort_values(["Eligible","Score"], ascending=[False, False]).reset_index(drop=True)
    return df.head(topn), df

def pair_units_with_lenders(inv: pd.DataFrame, rules: pd.DataFrame, F: dict, max_pairs=5):
    inv = normalize_inventory(inv)
    if inv.empty:
        return pd.DataFrame(columns=["Stock","Unit","Miles","Book","Ask","MaxPrice","Advance%","Lender","Program","CapLTV","MaxTerm","MaxMiles","FitScore"])
    lender_top, _ = recommend_lenders(rules, F, topn=12)
    lender_top = lender_top[lender_top["Eligible"]==True]
    pairs = []
    for _, L in lender_top.iterrows():
        for _, U in inv.iterrows():
            # vehicle gates that depend on the lender (miles etc.)
            ok, why = gates_ok(
                # reconstruct minimal rule row for gates that need row fields
                pd.Series({
                    "MinScore": F["score"], "MaxScore": F["score"],  # already checked in lender_top
                    "MaxRepos":  99, "MinJobMonths": 0, "MinIncome": 0, "MinDown": 0,
                    "AllowNoDL": True, "AllowGig": True, "MaxMiles": L["MaxMiles"]
                }),
                F, vehicle=U
            )
            if not ok:
                continue
            cap_ltv = float(L["CapLTV"])
            cap = price_cap_from_book(U["BookValue"], cap_ltv)
            ask = float(U["Price"])
            book = float(U["BookValue"])
            if cap <= 0 or book <= 0:
                continue
            target_price = min(cap, ask if ask>0 else cap)
            if target_price < 4500:
                continue
            adv_pct = round((target_price/book)*100,1) if book>0 else 0
            fit = float(L["Score"])
            m = float(U["Miles"])
            if m > 120000: fit -= 4
            elif m > 90000: fit -= 2
            if ask > cap: fit -= min(10, (ask-cap)/500)
            pairs.append({
                "Stock": U["Stock"],
                "Unit": f"{int(U['Year'])} {U['Make']} {U['Model']} {U['Trim']}",
                "Miles": int(m),
                "Book": int(book),
                "Ask": int(ask),
                "MaxPrice": int(cap),
                "Advance%": adv_pct,
                "Lender": L["Lender"],
                "Program": L["Program"],
                "CapLTV": round(cap_ltv*100,1),
                "MaxTerm": int(L["MaxTerm"]),
                "MaxMiles": int(L["MaxMiles"]),
                "FitScore": round(fit,1)
            })
    if not pairs:
        return pd.DataFrame(columns=["Stock","Unit","Miles","Book","Ask","MaxPrice","Advance%","Lender","Program","CapLTV","MaxTerm","MaxMiles","FitScore"])
    out = pd.DataFrame(pairs).sort_values(["FitScore","Advance%"], ascending=[False, False]).reset_index(drop=True)
    return out.head(max_pairs)

# =========================================================
# Ask about rule helper
# =========================================================
def answer_rule_question(text: str, rules: pd.DataFrame) -> str:
    if not text or text.strip()=="":
        return ""
    t = text.lower()
    hits = []
    for _, r in rules.iterrows():
        blob = " ".join([str(r[k]) for k in r.index])
        if any(k in blob.lower() for k in t.split()):
            hits.append(r)
    if not hits:
        return "Nothing obvious; try a lender name or policy word (e.g., 'Gateway miles', 'GLS LTV 600')."
    df = pd.DataFrame(hits)
    cols = ["Lender","Program","MinScore","MaxScore","MaxRepos","MinJobMonths","MinIncome","MinDown","LTV","Bands","MaxBackEnd","MaxTerm","MaxMiles","Notes"]
    df = df[cols]
    st.dataframe(df, use_container_width=True)
    return "Relevant rows shown."

# =========================================================
# Evaluate
# =========================================================
F = {
    "score": int(score),
    "income": float(monthly_income),
    "job_years": int(job_years),
    "job_months": 0,
    "repos": int(repos),
    "down": float(down),
    "trade_eq": float(trade),
    "gig": bool(gig_flag),
    "gig_income": float(gig_income) if gig_flag else 0.0,
    "dl": dl,
    "co_income": float(co_income) if include_co else 0.0,
    "co_score": int(co_score) if include_co and co_score else None,
}

rules_df = st.session_state["rules"].copy()
# Ensure Bands column is dicts for internal use
if "Bands" in rules_df.columns:
    rules_df["Bands"] = rules_df["Bands"].apply(parse_bands)
else:
    rules_df["Bands"] = [{} for _ in range(len(rules_df))]

inv_df = st.session_state["inventory"].copy()

if st.button("Run Lender Picks & Top Units", type="secondary") or evaluate:
    top_lenders, audit_lenders = recommend_lenders(rules_df, F, topn=7)

    st.markdown("### Top Lender Matches")
    if top_lenders[top_lenders["Eligible"]==True].empty:
        st.info("No lender fits with the current customer inputs.")
    else:
        st.dataframe(
            top_lenders[["Lender","Program","Score","Reason","CapLTV","MaxBackEnd","MaxTerm","MaxMiles","MinIncome","MinDown","Notes"]],
            use_container_width=True, height=250
        )

    st.markdown("### Top 5 Units (best lender–unit pairs, with cap pricing)")
    pairs = pair_units_with_lenders(inv_df, rules_df, F, max_pairs=5)
    if pairs.empty:
        st.info("No units fit with any lender using these rules & filters.")
    else:
        st.dataframe(pairs, use_container_width=True, height=260)

    with st.expander("Deal Snapshot (inputs)"):
        st.json(F)

st.markdown("---")
st.subheader("Ask about a lender rule")
q = st.text_input("Try: 'Gateway miles', 'GLS LTV 600', 'Exeter repos', 'Flagship max term'.", value="")
if q:
    msg = answer_rule_question(q, rules_df)
    if msg:
        st.caption(msg)

st.markdown(
    "<div class='small muted'>Reminder only — backend products are NOT included in any advance computations here.</div>",
    unsafe_allow_html=True
)
