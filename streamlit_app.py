# streamlit_app.py
import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# =============================================================================
# Page config + light styling
# =============================================================================
st.set_page_config(page_title="SmartDesk — Desking Assistant (POC)", page_icon="📋", layout="wide")
st.markdown(
    """
    <style>
      .card{border-radius:12px;border:1px solid rgba(250,250,250,.12);padding:14px 16px;background:rgba(250,250,250,.03);}
      .metric{font-size:22px;font-weight:700;margin-bottom:6px}
      .em{opacity:.75}
      .good{color:#7DD97C;font-weight:600}
      .warn{color:#F2C14E;font-weight:600}
      .bad{color:#EF6C6C;font-weight:600}
      .small{font-size:12px;opacity:.8}
    </style>
    """,
    unsafe_allow_html=True
)

# =============================================================================
# Helpers
# =============================================================================
def _yn(x, default=False):
    if pd.isna(x): return default
    if isinstance(x, str):
        return x.strip().lower() in ("1","y","yes","true","t")
    if isinstance(x, (int,float,bool)):
        return bool(x)
    return default

def _num(x, default=None):
    try:
        if pd.isna(x) or x=="":
            return default
        return float(x)
    except:
        return default

# Map columns from uploaded rate sheets (case insensitive)
COLUMN_ALIASES = {
    "lender": ["lender","bank","program lender","company"],
    "program": ["program","plan","tier","product"],
    "minscore": ["minscore","min score","score min"],
    "maxscore": ["maxscore","max score","score max"],
    "maxrepos": ["maxrepos","# repos","repos max","max repos"],
    "minjobmonths": ["minjobmonths","min job months","job months min"],
    "minincome": ["minincome","min income","income min"],
    "mindown": ["mindown","min down","down min"],
    "allowgig": ["allowgig","gig ok","gig","doordash ok"],
    "allownodl": ["allownodl","no dl ok","allow no dl"],
    "allowframe": ["allowframe","frame ok","frame damage ok"],
    "maxmiles": ["maxmiles","miles max","max miles"],
    "maxterm": ["maxterm","term max","max months"],
    "maxltv": ["maxltv","advance","advance max","ltv max","max advance"],
}

def _pick(df, key, default=None):
    cols_lower = {c.lower().strip():c for c in df.columns}
    for alias in COLUMN_ALIASES[key]:
        if alias in cols_lower:
            return df[cols_lower[alias]]
    # allow missing -> default vector
    return pd.Series([default]*len(df))

@st.cache_data(show_spinner=False)
def load_rate_sheet_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(data)) if ext==".csv" else pd.read_excel(BytesIO(data))
    out = pd.DataFrame({
        "Lender":     _pick(df, "lender", ""),
        "Program":    _pick(df, "program", "Std"),
        "MinScore":   _pick(df, "minscore", None),
        "MaxScore":   _pick(df, "maxscore", 999),
        "MaxRepos":   _pick(df, "maxrepos", 9),
        "MinJobMonths": _pick(df, "minjobmonths", 0),
        "MinIncome":  _pick(df, "minincome", 0),
        "MinDown":    _pick(df, "mindown", 0),
        "AllowGig":   _pick(df, "allowgig", True).map(lambda x:_yn(x, True)),
        "AllowNoDL":  _pick(df, "allownodl", False).map(lambda x:_yn(x, False)),
        "AllowFrame": _pick(df, "allowframe", False).map(lambda x:_yn(x, False)),
        "MaxMiles":   _pick(df, "maxmiles", 999999),
        "MaxTerm":    _pick(df, "maxterm", 72),
        "MaxLTV":     _pick(df, "maxltv", 150),
    })
    out["Lender"]  = out["Lender"].astype(str).str.strip()
    out["Program"] = out["Program"].astype(str).str.strip().replace({"": "Std"})
    # normalize numerics (allow blanks)
    for c in ["MinScore","MaxScore","MaxRepos","MinJobMonths","MinIncome","MinDown","MaxMiles","MaxTerm","MaxLTV"]:
        out[c] = out[c].map(lambda x:_num(x, out[c].median() if c!="MinScore" else None))
    # drop blank lenders
    out = out[out["Lender"]!=""].reset_index(drop=True)
    # attach Extras (for future)
    if "Extras" not in out.columns:
        out["Extras"] = [{} for _ in range(len(out))]
    return out

# Default sample rules if user doesn't upload (tunable)
DEFAULT_RULES = pd.DataFrame([
    # MinScore can be None to mean "no min score"
    {"Lender":"Gateway Financial","Program":"Std","MinScore":None,"MaxScore":720,"MaxRepos":2,"MinJobMonths":3,"MinIncome":1800,"MinDown":500,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False,"MaxMiles":170000,"MaxTerm":72,"MaxLTV":135},
    {"Lender":"Exeter","Program":"Std","MinScore":None,"MaxScore":700,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2000,"MinDown":500,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False,"MaxMiles":155000,"MaxTerm":72,"MaxLTV":135},
    {"Lender":"CPS","Program":"Std","MinScore":None,"MaxScore":700,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2200,"MinDown":500,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False,"MaxMiles":165000,"MaxTerm":72,"MaxLTV":140},
    {"Lender":"Flagship Credit","Program":"Std","MinScore":600,"MaxScore":750,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2400,"MinDown":1000,"AllowGig":True,"AllowNoDL":False,"AllowFrame":True,"MaxMiles":155000,"MaxTerm":75,"MaxLTV":125},
    {"Lender":"Regional Acceptance","Program":"Std","MinScore":590,"MaxScore":720,"MaxRepos":1,"MinJobMonths":12,"MinIncome":2500,"MinDown":1000,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False,"MaxMiles":150000,"MaxTerm":72,"MaxLTV":125},
    {"Lender":"Prestige","Program":"Std","MinScore":600,"MaxScore":760,"MaxRepos":0,"MinJobMonths":12,"MinIncome":2600,"MinDown":1000,"AllowGig":False,"AllowNoDL":False,"AllowFrame":False,"MaxMiles":140000,"MaxTerm":72,"MaxLTV":120},
    {"Lender":"Global Lending Services","Program":"Std","MinScore":580,"MaxScore":720,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2200,"MinDown":1000,"AllowGig":True,"AllowNoDL":False,"AllowFrame":False,"MaxMiles":160000,"MaxTerm":72,"MaxLTV":130},
    {"Lender":"Westlake","Program":"Std","MinScore":None,"MaxScore":720,"MaxRepos":3,"MinJobMonths":3,"MinIncome":1800,"MinDown":0,"AllowGig":True,"AllowNoDL":True,"AllowFrame":True,"MaxMiles":200000,"MaxTerm":75,"MaxLTV":145},
    {"Lender":"Credit Acceptance","Program":"Std","MinScore":None,"MaxScore":720,"MaxRepos":9,"MinJobMonths":0,"MinIncome":1500,"MinDown":0,"AllowGig":True,"AllowNoDL":True,"AllowFrame":True,"MaxMiles":250000,"MaxTerm":72,"MaxLTV":150},
])

# Hard sample inventory used if none uploaded
HARD_INVENTORY = pd.DataFrame([
    {"Stock":"A001","Year":2016,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93580,"TotalCost":9990,"BookValue":11800},
    {"Stock":"A002","Year":2017,"Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"TotalCost":10450,"BookValue":12200},
    {"Stock":"A003","Year":2014,"Make":"Toyota","Model":"Camry","Trim":"SE","Miles":128590,"TotalCost":8495,"BookValue":10250},
    {"Stock":"A004","Year":2015,"Make":"Nissan","Model":"Altima","Trim":"2.5 S","Miles":119400,"TotalCost":7795,"BookValue":9300},
    {"Stock":"X005","Year":2016,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111200,"TotalCost":8995,"BookValue":10600}, # excluded by Stock W/T? (starts with X -> allowed)
    {"Stock":"A006","Year":2016,"Make":"VW","Model":"Jetta","Trim":"S","Miles":98080,"TotalCost":7990,"BookValue":9100},
    {"Stock":"A007","Year":2016,"Make":"Toyota","Model":"RAV4","Trim":"LE","Miles":99000,"TotalCost":13990,"BookValue":15800},
    {"Stock":"A008","Year":2011,"Make":"Kia","Model":"Soul","Trim":"Base","Miles":171500,"TotalCost":3390,"BookValue":4200}, # excluded by < $4k
])

def normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    """ Clean + filter inventory. """
    if df is None or len(df)==0:
        return HARD_INVENTORY.copy()
    # Column harmonization
    cols = {c.lower().strip():c for c in df.columns}
    def col(name, fallback=None):
        return df[cols[name]] if name in cols else fallback
    out = pd.DataFrame({
        "Stock": col("stock", df.index.astype(str)),
        "Year":  col("year", 0),
        "Make":  col("make", ""),
        "Model": col("model", ""),
        "Trim":  col("trim", ""),
        "Miles": col("miles", 0).map(lambda x:_num(x,0)).astype(float),
        # total cost / price
        "TotalCost": (col("totalcost", None) if "totalcost" in cols else col("price",0)).map(lambda x:_num(x,0)).astype(float),
        "BookValue": col("bookvalue", 0).map(lambda x:_num(x,0)).astype(float),
    })
    # filters: price >= 4000; exclude Stock starting with W or T (case-insensitive)
    out = out[out["TotalCost"]>=4000]
    out = out[~out["Stock"].astype(str).str.upper().str.startswith(("W","T"))]
    out = out.reset_index(drop=True)
    return out

# =============================================================================
# Core underwriting gates + scoring
# =============================================================================
def gates_ok(rule, F, unit):
    """Return (ok, why) if lender rule passes given features + unit."""
    # Score gate
    cred = F["credit"]
    min_sc = rule["MinScore"]
    max_sc = rule["MaxScore"]
    if min_sc is not None and cred < float(min_sc):
        return False, f"Score below min ({cred} < {int(min_sc)})"
    if cred > float(max_sc):
        return False, "Score over program max"

    # Repos
    if F["repos"] > float(rule["MaxRepos"]):
        return False, "Too many repos"

    # Job time
    if F["job_months"] < float(rule["MinJobMonths"]):
        return False, "Insufficient job time"

    # Income
    inc = F["income"] + (F["gig_income"] if F["gig"] else 0.0)
    if inc < float(rule["MinIncome"]):
        return False, "Insufficient income"

    # Down
    if F["down"] < float(rule["MinDown"]):
        return False, "Down below lender minimum"

    # DL
    if (not bool(rule["AllowNoDL"])) and F["has_dl"]=="No":
        return False, "DL required"

    # Gig
    if (not bool(rule["AllowGig"])) and F["gig"] and F["gig_income"]>0:
        return False, "Gig income not allowed"

    # Unit-based gates
    if unit is None:  # during lender-only scoring
        return True, "OK"

    # Miles
    if float(unit["Miles"]) > float(rule["MaxMiles"]):
        return False, "Miles over lender cap"

    # Term (we use lender's MaxTerm automatically since we removed user input)
    term = int(_num(rule["MaxTerm"], 72))

    # Advance/LTV
    bv = max(float(unit["BookValue"]), 1.0)
    advance = (float(unit["TotalCost"]) - F["down"] - F["trade_eq"]) / bv * 100.0
    if advance > float(rule["MaxLTV"]):
        return False, f"Advance {advance:.1f}% exceeds max {float(rule['MaxLTV'])}%"

    return True, "OK"

def lender_fit_score(rule, F):
    """Soft rank for lender (closer to mid score, more down/income than min, etc.)."""
    cred = F["credit"]
    min_sc = _num(rule["MinScore"], cred)  # if None, use cred as center
    max_sc = float(rule["MaxScore"])
    mid = (min_sc + max_sc)/2.0 if min_sc is not None else max_sc - 20
    score = 0.0
    score += 100 - abs(cred - mid) * 0.7
    # reward being over min
    score += min(2000, F["down"] - float(rule["MinDown"])) / 20.0
    inc = F["income"] + (F["gig_income"] if F["gig"] else 0.0)
    score += min(3000, inc - float(rule["MinIncome"])) / 30.0
    if F["has_dl"]=="Yes": score += 5
    if F["repos"]==0: score += 5
    return score

def unit_fit_score(rule, unit, F):
    """Soft score for unit fit (advance headroom, miles comfort, book spread)."""
    bv = max(float(unit["BookValue"]), 1.0)
    adv = (float(unit["TotalCost"]) - F["down"] - F["trade_eq"]) / bv * 100.0
    # headroom in LTV
    headroom = float(rule["MaxLTV"]) - adv
    s = 0.0
    s += headroom * 1.2
    # miles margin
    s += max(0, (float(rule["MaxMiles"]) - float(unit["Miles"])) / 2000.0)
    # book spread (positive is better)
    spread = bv - float(unit["TotalCost"])
    s += max(-50, min(50, spread/150.0))
    return s, adv

def recommend_lenders(rules_df, F, topn=5):
    rows = []
    for _, r in rules_df.iterrows():
        ok, why = gates_ok(r,
