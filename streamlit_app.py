# streamlit_app.py
import re
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st

# Optional: PDF support (install pdfplumber in requirements.txt)
try:
    import pdfplumber
    PDF_OK = True
except Exception:
    PDF_OK = False

# =========================
# Page config / styles
# =========================
st.set_page_config(page_title="SmartDesk — Desking Assistant", page_icon="📋", layout="wide")
st.markdown(
    """
    <style>
      .card {border-radius:10px;padding:14px 16px;border:1px solid rgba(250,250,250,.12);background:rgba(250,250,250,.03)}
      .metric {font-size:26px;font-weight:700;margin-bottom:4px}
      .em {opacity:.7}
      .ok {color:#7DD97C}
      .warn {color:#F2C14E}
      .bad {color:#EF6C6C}
      .tight p {margin:0}
    </style>
    """,
    unsafe_allow_html=True
)

# =========================
# Helpers
# =========================
def _to_bool(x, default=False):
    if isinstance(x, str):
        return x.strip().lower() in ("y","yes","true","1","ok","allowed")
    if isinstance(x, (int, float, np.integer, np.floating)):
        return bool(x)
    return default

def _num(x, default=None):
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)) or (isinstance(x, str) and x.strip()==""):
            return default
        return float(x)
    except Exception:
        return default

def _safe_int(x, default=0):
    n = _num(x, None)
    return int(round(n)) if n is not None else default

def clamp(v, lo, hi):
    try:
        return min(max(v, lo), hi)
    except Exception:
        return v

# =========================
# Default (POC) lender programs
# =========================
DEFAULT_RULES = pd.DataFrame([
    {"Lender":"Gateway Financial Solutions","Program":"Near/Sub","MinScore":None,"MaxScore":700,"MaxRepos":2,"MinIncome":2000,"MinDown":500,"MaxTerm":72,"MaxMiles":160000,"MaxLTV":130,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Global Lending Services","Program":"Near/Sub","MinScore":580,"MaxScore":720,"MaxRepos":2,"MinIncome":2200,"MinDown":1000,"MaxTerm":75,"MaxMiles":150000,"MaxLTV":135,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Flagship Credit","Program":"Near/Sub","MinScore":600,"MaxScore":750,"MaxRepos":2,"MinIncome":2400,"MinDown":1000,"MaxTerm":75,"MaxMiles":155000,"MaxLTV":125,"AllowGig":True,"AllowNoDL":False,"AllowFrame":True},
    {"Lender":"Regional Acceptance","Program":"Near/Sub","MinScore":590,"MaxScore":720,"MaxRepos":1,"MinIncome":2500,"MinDown":1000,"MaxTerm":72,"MaxMiles":140000,"MaxLTV":125,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Prestige","Program":"Near/Sub","MinScore":600,"MaxScore":750,"MaxRepos":0,"MinIncome":2600,"MinDown":1000,"MaxTerm":72,"MaxMiles":140000,"MaxLTV":120,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Exeter","Program":"Near/Sub","MinScore":550,"MaxScore":700,"MaxRepos":2,"MinIncome":2000,"MinDown":500,"MaxTerm":72,"MaxMiles":160000,"MaxLTV":135,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False},
    {"Lender":"Kemba CU","Program":"Prime/CU","MinScore":640,"MaxScore":850,"MaxRepos":0,"MinIncome":3000,"MinDown":1000,"MaxTerm":84,"MaxMiles":120000,"MaxLTV":115,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False},
])

# =========================
# POC Hard Inventory (filtered later)
# =========================
HARD_INVENTORY = pd.DataFrame([
    {"Stock":"A001","Year":2016,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93500,"TotalCost":9990,"BookValue":11800},
    {"Stock":"A002","Year":2017,"Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"TotalCost":10450,"BookValue":12200},
    {"Stock":"A003","Year":2014,"Make":"Toyota","Model":"Camry","Trim":"SE","Miles":128500,"TotalCost":8495,"BookValue":10250},
    {"Stock":"A004","Year":2015,"Make":"Nissan","Model":"Altima","Trim":"2.5 S","Miles":119400,"TotalCost":7795,"BookValue":9300},
    {"Stock":"X005","Year":2010,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111200,"TotalCost":8995,"BookValue":10600},  # excluded by stock prefix
    {"Stock":"W100","Year":2016,"Make":"Volkswagen","Model":"Jetta","Trim":"S","Miles":98800,"TotalCost":7990,"BookValue":9100},   # excluded by stock prefix
    {"Stock":"T200","Year":2016,"Make":"Toyota","Model":"RAV4","Trim":"LE","Miles":99000,"TotalCost":13990,"BookValue":15800},   # excluded by stock prefix
    {"Stock":"B006","Year":2011,"Make":"Kia","Model":"Soul","Trim":"Base","Miles":171500,"TotalCost":3390,"BookValue":4200},     # excluded by price
    {"Stock":"A007","Year":2018,"Make":"Hyundai","Model":"Elantra","Trim":"SEL","Miles":84500,"TotalCost":10990,"BookValue":12500},
    {"Stock":"A008","Year":2019,"Make":"Nissan","Model":"Versa","Trim":"SV","Miles":61200,"TotalCost":9995,"BookValue":11200},
])

# =========================
# Rate sheet loaders (CSV/XLSX/PDF)
# =========================
@st.cache_data(show_spinner=False)
def load_rate_sheet_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(data)) if ext == ".csv" else pd.read_excel(BytesIO(data))
    low = {c.lower().strip(): c for c in df.columns}
    def col(name, default=None):
        c = low.get(name)
        return df[c] if c else [default]*len(df)

    out = pd.DataFrame({
        "Lender": col("lender","").astype(str).str.strip(),
        "Program": col("program","POC").astype(str).str.strip(),
        "MinScore": [ _num(x, None) for x in col("minscore", None) ],
        "MaxScore": [ _num(x, 999) for x in col("maxscore", 999) ],
        "MaxRepos": [ _num(x, 99) for x in col("maxrepos", 99) ],
        "MinIncome": [ _num(x, 0) for x in col("minincome", 0) ],
        "MinDown": [ _num(x, 0) for x in col("mindown", 0) ],
        "MaxTerm": [ _num(x, 84) for x in col("maxterm", 84) ],
        "MaxMiles": [ _num(x, 200000) for x in col("maxmiles", 200000) ],
        "MaxLTV": [ _num(x, 150) for x in col("maxltv", 150) ],
        "AllowGig": [ _to_bool(x, True) for x in col("allowgig","Yes") ],
        "AllowNoDL": [ _to_bool(x, False) for x in col("allownodl","No") ],
        "AllowFrame": [ _to_bool(x, False) for x in col("allowframe","No") ],
    })
    out = out[out["Lender"]!=""].reset_index(drop=True)
    return out

def parse_rate_pdf(pdf_bytes: bytes) -> pd.DataFrame:
    if not PDF_OK:
        return pd.DataFrame()
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        return pd.DataFrame()

    KNOWN_LENDERS = [
        "Gateway Financial Solutions","Global Lending Services","Flagship Credit",
        "Regional Acceptance","Prestige","Exeter","Kemba","Kemba CU",
        "CPS","Credit Acceptance","Santander","Westlake","AmeriCredit","GM Financial",
        "United Auto Credit","Ally","Capital One"
    ]
    rows = []
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b:
            continue
        lender = None
        m = re.search(r"lender\s*[:\-]\s*(.+)", b, flags=re.I)
        if m:
            lender = m.group(1).strip()
        else:
            for name in KNOWN_LENDERS:
                if re.search(re.escape(name), b, flags=re.I):
                    lender = name
                    break
        if not lender:
            continue

        def find_num(pattern, default=None, coerce_int=False):
            m = re.search(pattern, b, flags=re.I)
            if not m: 
                return default
            v = _num(m.group(1).replace(",",""), default)
            return int(v) if (coerce_int and v is not None) else v

        min_score = find_num(r"(?:min(?:imum)?\s*score).*?(\d{2,3})", None, True)
        max_score = find_num(r"(?:max(?:imum)?\s*score).*?(\d{2,3})", 999, True)
        max_repos = find_num(r"(?:max(?:imum)?\s*repos?).*?(\d+)", 99, True)
        min_income = find_num(r"(?:min(?:imum)?\s*income).*?\$?([\d,]+)", 0, True)
        min_down = find_num(r"(?:min(?:imum)?\s*down).*?\$?([\d,]+)", 0, True)
        max_term = find_num(r"(?:max(?:imum)?\s*term).*?(\d{2,3})", 84, True)
        max_miles = find_num(r"(?:max(?:imum)?\s*(?:miles|mileage)).*?([\d,]+)", 200000, True)
        max_ltv = find_num(r"(?:max(?:imum)?\s*(?:ltv|advance)).*?(\d{2,3})\s*%", 150, True)

        allow_gig   = bool(re.search(r"\b(gig|doordash|uber|lyft)\b.*?(ok|allow|yes)", b, flags=re.I))
        allow_nodl  = bool(re.search(r"(no\s*dl|without\s*dl).*(ok|allow|yes)", b, flags=re.I))
        allow_frame = bool(re.search(r"frame\s*(?:damage)?\s*(ok|allow|yes)", b, flags=re.I))

        rows.append({
            "Lender": lender, "Program": "PDF",
            "MinScore": min_score, "MaxScore": max_score, "MaxRepos": max_repos,
            "MinIncome": min_income, "MinDown": min_down, "MaxTerm": max_term,
            "MaxMiles": max_miles, "MaxLTV": max_ltv,
            "AllowGig": allow_gig, "AllowNoDL": allow_nodl, "AllowFrame": allow_frame
        })
    out = pd.DataFrame(rows)
    return out[out["Lender"].astype(str).str.strip()!=""].reset_index(drop=True)

def merge_rules(base: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if new is None or new.empty:
        return base.copy()
    union = base.copy()
    for _, r in new.iterrows():
        name = str(r["Lender"]).strip()
        if not name:
            continue
        mask = union["Lender"].astype(str).str.strip().str.lower() == name.lower()
        if not mask.any():
            union = pd.concat([union, pd.DataFrame([r])], ignore_index=True)
        else:
            idx = union.index[mask][0]
            for c in new.columns:
                if c == "Lender": 
                    continue
                val = r[c]
                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                    union.at[idx, c] = val
    # coerce dtypes
    num_cols = ["MinScore","MaxScore","MaxRepos","MinIncome","MinDown","MaxTerm","MaxMiles","MaxLTV"]
    for c in num_cols:
        if c in union.columns:
            union[c] = union[c].apply(lambda x: _num(x, 0 if c!="MaxScore" else 999))
    for c in ["AllowGig","AllowNoDL","AllowFrame"]:
        if c in union.columns:
            union[c] = union[c].apply(lambda x: _to_bool(x, False))
    if "Program" not in union.columns:
        union["Program"] = "POC"
    return union.reset_index(drop=True)

# =========================
# Inventory normalization & filters
# - Keep TotalCost >= $4,000
# - Exclude Stock starting with W or T
# =========================
def normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if "Price" in work.columns and "TotalCost" not in work.columns:
        work["TotalCost"] = work["Price"]
    for must in ["Stock","Year","Make","Model","Miles","TotalCost","BookValue"]:
        if must not in work.columns:
            work[must] = np.nan
    work["Stock"] = work["Stock"].astype(str).str.strip()
    work["Miles"] = work["Miles"].apply(_safe_int)
    work["Year"] = work["Year"].apply(_safe_int)
    work["TotalCost"] = work["TotalCost"].apply(lambda x: max(_num(x, 0.0), 0.0))
    work["BookValue"] = work["BookValue"].apply(lambda x: max(_num(x, 0.0), 0.0))
    work["StockUpper"] = work["Stock"].str.upper()
    work = work[work["TotalCost"] >= 4000.0]
    work = work[~work["StockUpper"].str.startswith(("W","T"))]
    work = work.drop(columns=["StockUpper"], errors="ignore").reset_index(drop=True)
    for s in ["Make","Model","Trim"]:
        if s not in work.columns:
            work[s] = ""
        work[s] = work[s].astype(str)
    return work

# =========================
# Fit / Desk logic
# =========================
def gates_ok(row, features, unit=None):
    cred = features["credit"]
    repos = features["repos"]
    inc_total = features["income"] + (features["gig_income"] if features["gig"] else 0)
    down = features["down"]
    trade = features["trade_eq"]
    has_dl = (features["has_dl"] == "Yes")
    desired_term = features["desired_term"]

    min_score = row["MinScore"] if row["MinScore"] is not None else -9999
    if not (min_score <= cred <= row["MaxScore"]):
        return False, "Score out of window"
    if repos > row["MaxRepos"]:
        return False, "Too many repos"
    if inc_total < row["MinIncome"]:
        return False, "Income short"
    if desired_term > row["MaxTerm"]:
        return False, "Term exceeds program max"
    if (not row["AllowNoDL"]) and (not has_dl):
        return False, "DL required"

    if unit is not None:
        if unit["Miles"] > row["MaxMiles"]:
            return False, "Miles exceed program max"
        if down < row["MinDown"]:
            return False, "More down required"
        bv = max(unit["BookValue"], 1.0)
        adv = (unit["TotalCost"] - down - trade) / bv * 100.0
        if adv > row["MaxLTV"]:
            return False, f"Advance {adv:.1f}% over max {row['MaxLTV']:.0f}%"
    return True, "Meets program"

def lender_fit_score(row, features):
    cred = features["credit"]
    min_score = row["MinScore"] if row["MinScore"] is not None else cred
    mid = (min_score + row["MaxScore"])/2.0 if row["MinScore"] is not None else row["MaxScore"]-20
    s = 100 - abs(cred - mid) * 0.3
    return max(0, s)

def unit_fit_score(row, unit, features):
    """Higher is better. In aggressive mode, reward high advance & long term."""
    down = features["down"]
    trade = features["trade_eq"]
    bv = max(unit["BookValue"], 1.0)
    adv = (unit["TotalCost"] - down - trade) / bv * 100.0
    adv_gap = abs(row["MaxLTV"] - adv)
    adv_score = max(0.0, 100 - adv_gap)  # closer to MaxLTV = better

    if features.get("aggressive"):
        term_pref = features.get("desired_term", 60)
        term_score = 100.0 * clamp(min(row["MaxTerm"], term_pref) / max(1.0, row["MaxTerm"]), 0, 1)
        w_adv, w_term, w_miles = 0.65, 0.25, 0.10
    else:
        term_score = 60.0
        w_adv, w_term, w_miles = 0.60, 0.15, 0.25

    miles_score = max(0.0, 100 - (unit["Miles"] / max(1.0, row["MaxMiles"])) * 100)

    total = adv_score * w_adv + term_score * w_term + miles_score * w_miles
    return total, adv

def what_it_takes(row, features, unit):
    F = dict(features)
    term_in = F["desired_term"]

    # Aggressive: target lender edges
    if F.get("aggressive"):
        target_term = int(row["MaxTerm"])
        target_down = float(row["MinDown"])
    else:
        target_term = min(term_in, int(row["MaxTerm"]))
        target_down = max(float(F["down"]), float(row["MinDown"]))

    changes = {"term": target_term, "down": target_down}
    reasons = []

    # Re-check base gates (without unit specifics)
    temp = dict(F); temp["desired_term"] = target_term
    ok, why = gates_ok(row, temp, None)
    if not ok:
        reasons.append(why)

    if unit is not None:
        if unit["Miles"] > row["MaxMiles"]:
            reasons.append(f"Miles {int(unit['Miles'])} > {int(row['MaxMiles'])} program cap.")

        # Ensure advance <= MaxLTV by adding down if needed
        bv = max(unit["BookValue"], 1.0)
        adv_now = (unit["TotalCost"] - changes["down"] - F["trade_eq"]) / bv * 100.0
        if adv_now > row["MaxLTV"]:
            need_down = (unit["TotalCost"] - F["trade_eq"]) - (row["MaxLTV"]/100.0)*bv
            extra = max(0.0, need_down - changes["down"])
            if extra > 0:
                changes["down"] += extra
                reasons.append(f"Lower advance to ≤{int(row['MaxLTV'])}% (+${int(extra)} down).")

    inc_total = F["income"] + (F["gig_income"] if F["gig"] else 0)
    if inc_total < row["MinIncome"]:
        short = int(row["MinIncome"] - inc_total)
        if row["AllowGig"]:
            reasons.append(f"Income short by ${short}. Add provable income (gig allowed).")
        else:
            reasons.append(f"Income short by ${short}. Need co-income or different lender.")
    if F["repos"] > row["MaxRepos"]:
        reasons.append(f"Repos {F['repos']} > {int(row['MaxRepos'])}.")
    if (not row["AllowNoDL"]) and F["has_dl"] == "No":
        reasons.append("DL required.")

    # Final gates with proposed term
    temp2 = dict(F); temp2["desired_term"] = changes["term"]
    ok2, why2 = gates_ok(row, temp2, unit)
    if ok2 and not reasons:
        return {"fits": True, "changes": changes, "reason":"Meets program at lender edges"}

    # Friction score (smaller is better)
    fric = 0
    fric += max(0, int((changes["down"] - F["down"]) / 100.0)) * (10 if F.get("aggressive") else 25)
    if changes["term"] < term_in: fric += 30
    if unit is not None and unit["Miles"] > row["MaxMiles"]: fric += 300
    if inc_total < row["MinIncome"]: fric += 200
    if F["repos"] > row["MaxRepos"]: fric += 200
    if (not row["AllowNoDL"]) and F["has_dl"] == "No": fric += 200
    if not ok2 and not reasons:
        reasons = [why2]
    return {"fits": False, "changes": changes, "reasons": reasons, "friction": fric}

def desk_deal_assist(inventory_df, rules_df, features):
    # Direct fits first
    fits = []
    for _, u in inventory_df.iterrows():
        for _, r in rules_df.iterrows():
            ok, _ = gates_ok(r, features, u)
            if ok:
                us, adv = unit_fit_score(r, u, features)
                ls = lender_fit_score(r, features)
                fits.append((us+ls, r, u, adv))
    if fits:
        fits.sort(key=lambda x: x[0], reverse=True)
        score, r, u, adv = fits[0]
        return {"status":"fits_now","lender":r["Lender"],"program":r["Program"],"unit":u,"advance":adv,"reason":"Meets program without changes.","alts":fits[1:4]}

    # Otherwise smallest friction across all lender/unit pairs
    best = None
    for _, u in inventory_df.iterrows():
        for _, r in rules_df.iterrows():
            wt = what_it_takes(r, features, u)
            if wt["fits"]:
                us, adv = unit_fit_score(r, u, features)
                ls = lender_fit_score(r, features)
                total = us + ls
                best = {"status":"fits_now","lender":r["Lender"],"program":r["Program"],"unit":u,"advance":adv,"reason":"Meets after reevaluation.","score":total}
                return best
            else:
                fr = wt.get("friction", 1e9)
                if (best is None) or (best.get("friction", 1e9) > fr):
                    best = {"status":"needs_changes","lender":r["Lender"],"program":r["Program"],"unit":u,"changes":wt["changes"],"reasons":wt["reasons"],"friction":fr}
    return best

# =========================
# Session state
# =========================
if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_RULES.copy()

# =========================
# UI — header
# =========================
st.title("SmartDesk — Desking Assistant")
st.caption("Upload a rate sheet (CSV/XLSX/PDF) and/or inventory, enter basics, and get a lender pick + the smallest change to get an approval. Aggressive mode maxes LTV/term per lender.")

with st.expander("File formats", expanded=False):
    st.markdown(
        """
**Rate sheet (CSV/XLSX/PDF):**  
`Lender, Program, MinScore, MaxScore, MaxRepos, MinIncome, MinDown, MaxTerm, MaxMiles, MaxLTV, AllowGig, AllowNoDL, AllowFrame`  
PDFs parsed heuristically (min score, term, miles, LTV, gig/No DL/frame keywords).

**Inventory (CSV/XLSX):**  
`Stock, Year, Make, Model, Trim, Miles, TotalCost (or Price), BookValue`  
Filters always applied: **TotalCost ≥ $4,000**, exclude **Stock starting with W or T**.
        """
    )

# =========================
# Layout: Left inputs / Right uploads
# =========================
left, right = st.columns([1.25, 1])

with left:
    st.subheader("Deal Input")
    with st.form("deal_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            credit = st.number_input("Credit Score", 300, 850, 620, 1)
            monthly_income = st.number_input("Monthly Income ($/mo)", 0, 30000, 3000, 50)
            gig_flag = st.checkbox("Gig / DoorDash income?")
            gig_income = st.number_input("Gig Income ($/mo)", 0, 20000, 0, 50)
        with c2:
            repos = st.number_input("# of Repos (reported)", 0, 10, 0, 1)
            has_dl = st.selectbox("Driver's License?", ["Yes","No"])
            job_years = st.number_input("Job Time (years)", 0, 40, 0, 1)
        with c3:
            trade_eq = st.number_input("Trade Equity ($)", -20000, 20000, 0, 100)
            down = st.number_input("Down Payment ($)", 0, 50000, 1000, 50)
            job_months = st.number_input("Job Time (months)", 0, 11, 6, 1)

        st.markdown("—")
        aggressive = st.checkbox("Aggressive (Max-Out) mode", value=True,
                                 help="Prefer highest allowed advance and longest term per lender.")
        show_backend_reminder = st.checkbox("Show Backend Products Reminder (no calc impact)", value=True)

        include_co = st.checkbox("Include Co-Applicant?")
        if include_co:
            co1, co2 = st.columns(2)
            with co1:
                co_score = st.number_input("Co-Applicant Score", 300, 850, 600, 1)
            with co2:
                co_income = st.number_input("Co-Applicant Income ($/mo)", 0, 20000, 0, 50)
        else:
            co_score, co_income = None, 0

        submitted = st.form_submit_button("Evaluate Deal", type="primary")

with right:
    st.subheader("Uploads")

    rs_files = st.file_uploader("Rate sheets (CSV/XLSX/PDF) — multiple allowed",
                                type=["csv","xlsx","pdf"], accept_multiple_files=True, key="rs_multi")
    inv_file = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"], key="inv")

    # Merge uploaded rate sheets into active rules
    merged = st.session_state["rate_rules"].copy()
    if rs_files:
        pdf_cnt, tab_cnt = 0, 0
        for f in rs_files:
            name = f.name.lower()
            try:
                if name.endswith(".pdf"):
                    if not PDF_OK:
                        st.warning("Install pdfplumber to parse PDFs (requirements.txt).")
                        continue
                    dfpdf = parse_rate_pdf(f.read())
                    if not dfpdf.empty:
                        merged = merge_rules(merged, dfpdf); pdf_cnt += len(dfpdf)
                else:
                    ext = ".csv" if name.endswith(".csv") else ".xlsx"
                    dftab = load_rate_sheet_from_bytes(f.read(), ext)
                    if not dftab.empty:
                        merged = merge_rules(merged, dftab); tab_cnt += len(dftab)
            except Exception as e:
                st.error(f"Failed to read {f.name}: {e}")
        st.session_state["rate_rules"] = merged
        st.success(f"Merged {tab_cnt} table rows + {pdf_cnt} PDF-derived rows into active rules.")

    with st.expander("Current Rate Rules (top 20)", expanded=False):
        st.dataframe(st.session_state["rate_rules"].head(20), use_container_width=True)

# =========================
# Lender Q&A (keyword search)
# =========================
st.subheader("Ask about a lender rule")
q = st.text_input("Example: Does Exeter allow frame damage? or Gateway gig income?")
if q.strip():
    rules = st.session_state["rate_rules"].copy()
    hay = rules.apply(lambda r: " ".join(str(v) for v in r.values), axis=1).str.lower()
    hits = rules[hay.str.contains(q.strip().lower(), na=False)]
    if hits.empty:
        st.info("No obvious matches in the current rate table.")
    else:
        st.dataframe(hits, use_container_width=True)

# =========================
# Evaluate Deal (assume desired term = 60 mo)
# =========================
if submitted:
    features = {
        "credit": credit,
        "income": monthly_income,
        "gig": bool(gig_flag),
        "gig_income": gig_income if gig_flag else 0,
        "repos": repos,
        "has_dl": has_dl,
        "job_years": job_years,
        "job_months": job_months,
        "down": float(down),
        "trade_eq": float(trade_eq),
        "desired_term": 60,  # fixed; no user input
        "co_score": co_score,
        "co_income": co_income,
        "aggressive": aggressive,
        "backend_reminder": show_backend_reminder,
    }

    # rules
    rules = st.session_state["rate_rules"].copy()
    for c in ["MinScore","MaxScore","MaxRepos","MinIncome","MinDown","MaxTerm","MaxMiles","MaxLTV"]:
        if c in rules.columns:
            rules[c] = rules[c].apply(lambda x: _num(x, 0 if c!="MaxScore" else 999))
    for c in ["AllowGig","AllowNoDL","AllowFrame"]:
        if c in rules.columns:
            rules[c] = rules[c].apply(lambda x: _to_bool(x, False))
    if "Program" not in rules.columns:
        rules["Program"] = "POC"

    # inventory
    if inv_file is not None:
        try:
            ext = ".csv" if inv_file.name.lower().endswith(".csv") else ".xlsx"
            data = inv_file.read()
            inv_df = pd.read_csv(BytesIO(data)) if ext==".csv" else pd.read_excel(BytesIO(data))
            INV = normalize_inventory(inv_df)
            st.success(f"Loaded {len(INV)} inventory units from **{inv_file.name}** (after filters).")
        except Exception as e:
            st.error(f"Inventory error: {e}")
            INV = normalize_inventory(HARD_INVENTORY)
    else:
        INV = normalize_inventory(HARD_INVENTORY)

    # ===== Deal Desk Assist =====
    st.markdown("## Deal Desk Assist")
    plan = desk_deal_assist(INV, rules, features)
    if plan is None:
        st.warning("No path found (check rate rules/inventory).")
    else:
        if plan["status"] == "fits_now":
            u = plan["unit"]
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="metric">✅ Recommended</div>', unsafe_allow_html=True)
            st.markdown(f"**{plan['lender']}** — {plan['program']}")
            st.markdown(
                f"- **Unit:** {int(u['Year'])} {u['Make']} {u['Model']} {u.get('Trim','') or ''}  \n"
                f"- **Miles:** {int(u['Miles'])}  •  **Price:** ${int(u['TotalCost'])}  •  **Book:** ${int(u['BookValue'])}  \n"
                f"- **Advance:** {plan['advance']:.1f}%"
            )
            if features.get("aggressive"):
                st.caption("Aggressive mode: targeting lender max term and highest allowed advance within caps.")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            u = plan["unit"]
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="metric">🛠 Closest path</div>', unsafe_allow_html=True)
            st.markdown(f"**{plan['lender']}** — {plan['program']}")
            st.markdown(
                f"- **Unit:** {int(u['Year'])} {u['Make']} {u['Model']} {u.get('Trim','') or ''}  \n"
                f"- **Miles:** {int(u['Miles'])}  •  **Price:** ${int(u['TotalCost'])}  •  **Book:** ${int(u['BookValue'])}"
            )
            ch = plan.get("changes", {})
            bullets = []
            if "down" in ch and ch["down"] != features["down"]:
                bullets.append(f"Increase down to **${int(ch['down'])}**.")
            if "term" in ch and ch["term"] != features["desired_term"]:
                bullets.append(f"Set term to **{int(ch['term'])} mo**.")
            if bullets:
                st.markdown("**Proposed tweaks:**  \n- " + "\n- ".join(bullets))
            if plan.get("reasons"):
                st.markdown("**Why:**  \n- " + "\n- ".join(plan["reasons"]))
            st.markdown("</div>", unsafe_allow_html=True)

        # Optional: Backend reminder (no calc effect)
        if features.get("backend_reminder"):
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="metric">🔔 Backend Products Reminder</div>', unsafe_allow_html=True)
            st.markdown(
                "- If lender permits: consider **GAP** and/or **service contract** on delivery.\n"
                "- Confirm **max advance** headroom before penciling products.\n"
                "- Verify **stip stack** first (POI, POR, 5 refs, insurance) to keep call clean."
            )
            st.caption("Reminder only — products are NOT included in any advance calculations here.")
            st.markdown('</div>', unsafe_allow_html=True)

    # ===== Top lender matches (as-is) =====
    st.markdown("### Top Lender Matches")
    rows = []
    for _, r in rules.iterrows():
        ok, why = gates_ok(r, features, None)
        rows.append({
            "Lender": r["Lender"],
            "Program": r["Program"],
            "Reason": "Meets program" if ok else why,
            "Score": round(lender_fit_score(r, features),1) if ok else 0.0
        })
    lenders_df = pd.DataFrame(rows).sort_values("Score", ascending=False).head(10)
    if not lenders_df.empty:
        st.dataframe(lenders_df, use_container_width=True)
    else:
        st.info("No lender fits with the current customer inputs.")

    # ===== Top 5 units (best lender–unit pairs) =====
    st.markdown("### Top 5 Units (best lender–unit pairs)")
    best_rows = []
    for _, u in INV.iterrows():
        best_for_unit = []
        for _, r in rules.iterrows():
            ok, _ = gates_ok(r, features, u)
            if ok:
                us, adv = unit_fit_score(r, u, features)
                ls = lender_fit_score(r, features)
                best_for_unit.append((us+ls, r, adv))
        if best_for_unit:
            best_for_unit.sort(key=lambda x: x[0], reverse=True)
            score, r, adv = best_for_unit[0]
            best_rows.append({
                "Stock": u["Stock"],
                "Unit": f"{int(u['Year'])} {u['Make']} {u['Model']} {u.get('Trim','') or ''}",
                "Miles": int(u["Miles"]),
                "Price": int(u["TotalCost"]),
                "Book": int(u["BookValue"]),
                "Advance%": round(adv,1),
                "Lender": r["Lender"],
                "Program": r["Program"],
                "FitScore": round(score,1)
            })
    if best_rows:
        top_units = pd.DataFrame(best_rows).sort_values("FitScore", ascending=False).head(5)
        st.dataframe(top_units, use_container_width=True)
    else:
        st.info("No units fit with any lender using these rules & filters.")
else:
    st.info("Fill out the form and click **Evaluate Deal** to see recommendations.")
