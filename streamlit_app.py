# streamlit_app.py
import streamlit as st
import pandas as pd
import re
from io import BytesIO

# ─────────────────────────────────────────────────────────────
# Page / Style
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="SmartDesk – Desking Assistant", page_icon="📋", layout="wide")
st.markdown("""
<style>
.card {border-radius: 10px; padding: 14px 16px; border: 1px solid rgba(250,250,250,.12); background: rgba(250,250,250,.03);}
.metric {font-size:26px; font-weight:700; margin-bottom:4px}
.em {opacity:.8}
.small {font-size:12px; opacity:.75}
.tight td{padding-top:6px !important; padding-bottom:6px !important;}
</style>
""", unsafe_allow_html=True)

THIS_YEAR = 2025

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def yn(val, default=False):
    if pd.isna(val): return default
    if isinstance(val, (int,float)): return bool(val)
    s = str(val).strip().lower()
    if s in ("y","yes","true","1"): return True
    if s in ("n","no","false","0"): return False
    return default

def to_num(x, default=None):
    try:
        if x in ("", None): return default
        return float(str(x).replace(",","").replace("$",""))
    except: return default

def est_payment(amount, apr=0.24, term=72):
    if amount <= 0 or term <= 0: return 0.0
    r = apr/12.0
    try:
        return float(amount * (r*(1+r)**term) / ((1+r)**term - 1))
    except ZeroDivisionError:
        return float(amount/term)

# ─────────────────────────────────────────────────────────────
# Lender rules (same as you approved previously; trimmed for brevity)
# ─────────────────────────────────────────────────────────────
def L(lender, program="", minscore=None, maxscore=None, maxrepos=99, minjob=0, mininc=0, mindown=0,
      gig=True, nodl=False, frame=False, extras=None):
    return {
        "Lender": lender, "Program": program, "MinScore": minscore, "MaxScore": maxscore, "MaxRepos": maxrepos,
        "MinJobMonths": minjob, "MinIncome": mininc, "MinDown": mindown,
        "AllowGig": gig, "AllowNoDL": nodl, "AllowFrame": frame, "Extras": (extras or {})
    }

DEFAULT_RATE_RULES = pd.DataFrame([
    L("Gateway Financial Solutions – Select","Select", None,None,1,3,1500,500, True, False, False,
      extras=dict(max_ltv=2.25, max_frontend_advance=1.35, max_financed=30000, min_book=4000,
                  term_by_miles=[(0,75000,72),(75001,100000,66),(100001,125000,60),(125001,150000,54),(150001,175000,48),(175001,999999,42)],
                  pti_cap=0.18, disallowed_makes=["Audi","Jaguar","Land Rover","Mercedes","Mini","Porsche","Saab"])
    ),
    L("Gateway Financial Solutions – Select Plus","Select Plus", None,None,1,3,1500,500, True, True, False,
      extras=dict(max_ltv=2.30, max_frontend_advance=1.90, max_financed=18000, min_book=4000,
                  term_by_miles=[(0,75000,60),(75001,100000,54),(100001,125000,48),(125001,150000,42),(150001,999999,36)],
                  max_payment_by_state={"OH":600,"IN":600,"MI":600,"KY":600,"IL":635,"MO":635,"WI":635},
                  disallowed_makes=["Audi","Jaguar","Land Rover","Mercedes","Mini","Porsche","Saab"])
    ),
    L("Exeter Finance","Standard", None,None,2,6,1700,500, True, False, False,
      extras=dict(max_age_years=13, max_miles=200000,
                  term_by_miles=[(0,90000,72),(90001,130000,66),(130001,180000,60),(180001,200000,54),(200001,999999,0)],
                  max_ltv=2.00, max_frontend_advance=1.40, block_recent_repo_under_days=60)
    ),
    L("Consumer Portfolio Services (CPS)","Standard", None,None,2,6,1800,500, True, False, False,
      extras=dict(max_age_years=15, max_miles=200000,
                  term_by_miles=[(0,90000,72),(90001,130000,66),(130001,170000,60),(170001,200000,54),(200001,999999,0)],
                  max_ltv=2.10, max_frontend_advance=1.50)
    ),
    L("Global Lending Services","Standard", 580,720,2,6,2200,1000, True, False, False,
      extras=dict(max_term_default=72, max_ltv=1.80, max_frontend_advance=1.30)
    ),
    L("Flagship Credit","Standard", 600,750,2,6,2400,1000, True, False, True,
      extras=dict(max_term_default=72, max_ltv=1.90, max_frontend_advance=1.35)
    ),
    L("Regional Acceptance","Standard", 590,720,1,12,2500,1000, False, False, False,
      extras=dict(max_term_default=72, max_ltv=1.80, max_frontend_advance=1.30)
    ),
    L("Prestige Financial","Tiered", 600,750,0,12,3000,1000, False, False, False,
      extras=dict(max_age_years=12,
                  term_by_miles=[(0,75000,75),(75001,110000,66),(110001,150000,60),(150001,999999,54)],
                  max_ltv=1.80, max_frontend_advance=1.30, pti_cap=0.18)
    ),
    L("Kemba CU","CU", 640,800,0,12,3000,1000, False, False, False,
      extras=dict(max_term_default=72, max_ltv=1.20, max_frontend_advance=1.10)
    ),
    L("Ally Auto (CPO Eligible)","CPO", 600,800,1,6,2500,1000, False, False, False,
      extras=dict(cpo_bump=1000, cpo_min_years=10, cpo_max_miles=100000,
                  max_term_default=72, max_ltv=1.20, max_frontend_advance=1.10)
    ),
    L("AmeriCredit / GM Financial","Standard", 580,800,2,6,2200,1000, True, False, False,
      extras=dict(max_term_default=75, max_ltv=1.90, max_frontend_advance=1.35,
                  term_by_miles=[(0,90000,75),(90001,120000,66),(120001,150000,60),(150001,999999,54)])
    ),
    L("Santander Consumer USA","Standard", 560,750,2,6,2000,500, True, False, False,
      extras=dict(max_term_default=72, max_ltv=2.00, max_frontend_advance=1.40,
                  term_by_miles=[(0,90000,72),(90001,130000,66),(130001,170000,60),(170001,200000,54)])
    ),
    L("Westlake Financial","Standard", None,None,2,3,1800,500, True, False, False,
      extras=dict(max_term_default=72, max_ltv=2.10, max_frontend_advance=1.50,
                  term_by_miles=[(0,100000,72),(100001,150000,60),(150001,999999,54)])
    ),
    L("Credit Acceptance (CAC)","Standard", None,None,99,0,0,0, True, False, True,
      extras=dict(max_term_default=72, max_ltv=2.50, max_frontend_advance=2.00)
    ),
])

@st.cache_data(show_spinner=False)
def load_rate_sheet_from_bytes(data: bytes, ext: str) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(data)) if ext==".csv" else pd.read_excel(BytesIO(data))
    cols = {c.lower().strip(): c for c in df.columns}
    def get(name): return df[cols[name]] if name in cols else None
    def colnum(s, default=None):
        if s is None: return [default]*len(df)
        return [to_num(x, default) for x in s]
    def colbool(s, default=False):
        if s is None: return [default]*len(df)
        return [yn(x, default) for x in s]
    out = pd.DataFrame({
        "Lender": get("lender") if get("lender") is not None else [""]*len(df),
        "Program": get("program") if get("program") is not None else [""]*len(df),
        "MinScore": colnum(get("minscore"), None),
        "MaxScore": colnum(get("maxscore"), None),
        "MaxRepos": colnum(get("maxrepos"), 99),
        "MinJobMonths": colnum(get("minjobmonths"), 0),
        "MinIncome": colnum(get("minincome"), 0),
        "MinDown": colnum(get("mindown"), 0),
        "AllowGig": colbool(get("allowgig"), True),
        "AllowNoDL": colbool(get("allownodl"), False),
        "AllowFrame": colbool(get("allowframe"), False),
    })
    out = out[out["Lender"].astype(str).str.strip()!=""].reset_index(drop=True)
    if "Extras" not in out.columns: out["Extras"] = [{} for _ in range(len(out))]
    return out

# ─────────────────────────────────────────────────────────────
# HARD-WIRED (CURRENT) INVENTORY
#  - You can paste your true current list here anytime.
#  - Filter rules: price >= $4,000, and exclude Stock starting with W or T.
# ─────────────────────────────────────────────────────────────
HARD_INVENTORY = pd.DataFrame([
    # <<< REPLACE/EXTEND WITH YOUR REAL UNITS >>>
    {"Stock":"A001","Year":2016,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93500,"Price":9990,"BookValue":11800},
    {"Stock":"A002","Year":2017","Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"Price":10450,"BookValue":12200},
    {"Stock":"A003","Year":2014,"Make":"Toyota","Model":"Camry","Trim":"SE","Miles":128500,"Price":8495,"BookValue":10250},
    {"Stock":"A004","Year":2015,"Make":"Nissan","Model":"Altima","Trim":"2.5 S","Miles":119400,"Price":7795,"BookValue":9300},
    {"Stock":"X005","Year":2016,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111200,"Price":8995,"BookValue":10600},  # X = frame flag
    {"Stock":"W100","Year":2016,"Make":"Volkswagen","Model":"Jetta","Trim":"S","Miles":98000,"Price":7990,"BookValue":9100}, # will be excluded (W*)
    {"Stock":"T200","Year":2016,"Make":"Toyota","Model":"RAV4","Trim":"LE","Miles":99000,"Price":13990,"BookValue":15800},   # excluded (T*)
    {"Stock":"B006","Year":2011,"Make":"Kia","Model":"Soul","Trim":"Base","Miles":171500,"Price":3390,"BookValue":4200},     # excluded (<4000)
])

def normalize_inventory(df: pd.DataFrame):
    """
    Clean + filter inventory:
      - Require Price >= $4,000
      - Exclude stock numbers starting with W or T (case-insensitive)
      - Compute Spread and Frame flag (Stock starts with 'X')
    """
    if df is None or len(df) == 0:
        return pd.DataFrame(), 0

    raw = df.copy()
    cols = {c.lower().strip(): c for c in raw.columns}
    def pick(name, *aliases, default=None):
        for key in (name, *aliases):
            k = key.lower().strip()
            if k in cols: return raw[cols[k]]
        return default
    def num(series):
        if series is None: return pd.Series([None]*len(raw))
        return pd.to_numeric(series.astype(str).str.replace(r"[,$]", "", regex=True), errors="coerce")

    out = pd.DataFrame({
        "Stock":     (pick("stock","stock#","stocknum","stock number","stk","stk#") or pd.Series([""]*len(raw))),
        "Year":      num(pick("year","yr")),
        "Make":      (pick("make","manufacturer","mfr") or pd.Series([""]*len(raw))),
        "Model":     (pick("model") or pd.Series([""]*len(raw))),
        "Trim":      (pick("trim","style","series") or pd.Series([""]*len(raw))),
        "Miles":     num(pick("miles","mileage","odom","odometer")),
        "Price":     num(pick("price","total cost","totalcost","selling price","sale price","retail","ask","amount")),
        "BookValue": num(pick("kbblsim","bbwhsale","nadasiminv","nada retail","kbb lending","book","bookvalue","lending"))
    })

    out["Spread"] = (out["BookValue"] - out["Price"]).fillna(0)
    stock_str = out["Stock"].astype(str).str.strip().str.upper()
    out["Frame"] = stock_str.str.startswith("X")
    out["Label"] = (
        out["Year"].fillna("").astype(str).str.replace(".0","",regex=False).str.strip()+" "+
        out["Make"].fillna("").astype(str).str.strip()+" "+
        out["Model"].fillna("").astype(str).str.strip()+" "+
        out["Trim"].fillna("").astype(str).str.strip()
    ).str.replace(r"\s+"," ", regex=True).str.strip()

    before = len(out)
    out = out[pd.to_numeric(out["Price"], errors="coerce") >= 4000]
    starts_w_or_t = stock_str.str.startswith(("W","T"))
    out = out[~starts_w_or_t]
    excluded = before - len(out)
    out = out.reset_index(drop=True)
    return out, excluded

# ─────────────────────────────────────────────────────────────
# Person-level lender fit
# ─────────────────────────────────────────────────────────────
def score_lender_person(lr, fx):
    cred = fx["credit"]; repos = fx["repos"]; job = fx["job_months"]
    income = fx["income"] + fx["gig_income"]; down = fx["down"]
    has_dl = fx["has_dl"]; gig = fx["gig"]
    if lr["MinScore"] is not None and cred < lr["MinScore"]:
        return (False, f"Min score {int(lr['MinScore'])}", 0.0)
    if lr["MaxScore"] is not None and cred > lr["MaxScore"]:
        return (False, f"Max score {int(lr['MaxScore'])}", 0.0)
    if repos > (lr["MaxRepos"] or 0): return (False, "Too many repos", 0.0)
    if job   < (lr["MinJobMonths"] or 0): return (False, "Insufficient job time", 0.0)
    if income < (lr["MinIncome"] or 0): return (False, "Insufficient income", 0.0)
    if down   < (lr["MinDown"] or 0): return (False, "Needs more down", 0.0)
    if (not lr["AllowNoDL"]) and (has_dl == "No"): return (False, "DL required", 0.0)
    if (not lr["AllowGig"]) and gig and fx["gig_income"] > 0: return (False, "Gig income not allowed", 0.0)
    if lr["Lender"].startswith("Exeter") and fx.get("recent_repo_under_60", False):
        return (False, "Recent repo < 60 days", 0.0)
    score = 90 if (lr["MinScore"] is None or lr["MaxScore"] is None) else 100 - abs(cred - (lr["MinScore"]+lr["MaxScore"])/2)*0.5
    score += min(1000, down)/20 + min(4000, income)/40 + (10 if has_dl=="Yes" else 0) + (15 if (gig and lr["AllowGig"]) else 0)
    return (True, "Meets program guidelines", round(score,1))

def recommend_lenders(rules_df: pd.DataFrame, fx: dict, topn=5):
    rows = []
    for _, r in rules_df.iterrows():
        ok, why, s = score_lender_person(r, fx)
        rows.append({**r, **{"Eligible": ok, "Reason": why, "Score": s}})
    df = pd.DataFrame(rows).sort_values(["Eligible","Score"], ascending=[False, False]).reset_index(drop=True)
    top = df[df["Eligible"]].head(topn)
    pick = top.iloc[0] if len(top) else None
    return pick, top, df

# ─────────────────────────────────────────────────────────────
# Unit gating (LTV, advance, term-by-miles, Ally CPO bump)
# ─────────────────────────────────────────────────────────────
def ladder_term_for_unit(extras: dict, miles: float):
    if extras and "term_by_miles" in extras and miles is not None and not pd.isna(miles):
        for lo, hi, term in extras["term_by_miles"]:
            if lo <= miles <= hi:
                return int(term or 0)
    if extras and "max_term_default" in extras and extras["max_term_default"]:
        return int(extras["max_term_default"])
    return 72

def unit_passes_lender_rules(unit, lender_row, fx, dealer_state="OH", cpo_checked=False):
    ex = lender_row.get("Extras", {}) or {}
    allow_frame = bool(lender_row.get("AllowFrame", False))
    if unit.get("Frame", False) and not allow_frame:
        return (False, "Frame not allowed")
    yr = unit.get("Year"); miles = unit.get("Miles")
    if ex.get("max_age_years") is not None and pd.notna(yr):
        age = THIS_YEAR - int(yr)
        if age > ex["max_age_years"]:
            return (False, f"Age>{ex['max_age_years']}y")
    if ex.get("max_miles") is not None and pd.notna(miles):
        if miles > ex["max_miles"]:
            return (False, f"Miles>{ex['max_miles']:,}")
    make = str(unit.get("Make","")).strip()
    bad_makes = ex.get("disallowed_makes")
    if bad_makes and any(make.lower()==bm.lower() for bm in bad_makes):
        return (False, "Make not allowed")
    book = to_num(unit.get("BookValue"), 0) or 0
    price = to_num(unit.get("Price"), 0) or 0
    if "Ally Auto (CPO Eligible)" in lender_row.get("Lender","") and cpo_checked:
        if (yr is not None) and (miles is not None):
            age = THIS_YEAR - int(yr)
            if age <= ex.get("cpo_min_years",10) and miles <= ex.get("cpo_max_miles",100000):
                book += ex.get("cpo_bump", 1000)
    if book <= 0 or price <= 0:
        return (False, "Missing book/price")
    if ex.get("min_book") and book < ex["min_book"]:
        return (False, f"Book<{ex['min_book']:.0f}")
    down = float(fx.get("down",0) or 0)
    trade_eq = float(fx.get("trade_eq",0) or 0)
    financed = max(0.0, price - down - trade_eq)
    front_end_adv = price / book
    ltv = (financed / book) if book > 0 else 999
    if ex.get("max_financed") and financed > ex["max_financed"]:
        return (False, f"Financed>{ex['max_financed']:.0f}")
    if ex.get("max_frontend_advance") and front_end_adv > ex["max_frontend_advance"]:
        return (False, f"Advance>{int(ex['max_frontend_advance']*100)}%")
    if ex.get("max_ltv") and ltv > ex["max_ltv"]:
        return (False, f"LTV>{int(ex['max_ltv']*100)}%")
    term = ladder_term_for_unit(ex, miles)
    if term <= 0:
        return (False, "Term blocked by miles")
    apr = 0.24
    pmt = est_payment(financed, apr=apr, term=term)
    pti_cap = ex.get("pti_cap")
    if pti_cap is not None:
        income_total = float(fx["income"] + fx["gig_income"])
        if income_total <= 0: return (False, "No income")
        if pmt > income_total * pti_cap:
            return (False, f"PTI>{int(pti_cap*100)}%")
    max_pay_map = ex.get("max_payment_by_state")
    if max_pay_map:
        mx = max_pay_map.get("OH")
        if mx and pmt > mx:
            return (False, f"Max pay>{mx}")
    return (True, f"OK (Term {term} mo, LTV {ltv:.2f}, Adv {front_end_adv:.2f})")

def score_unit(unit, lender_row, fx):
    spread = to_num(unit.get("Spread"), 0) or 0
    miles  = to_num(unit.get("Miles"), 0) or 0
    price  = to_num(unit.get("Price"), 0) or 0
    book   = to_num(unit.get("BookValue"), 0) or 0
    ltv = (max(0.0, price - float(fx.get("down",0)) - float(fx.get("trade_eq",0))) / book) if book>0 else 5.0
    adv = (price / book) if book>0 else 5.0
    return float(round(spread*0.6 + (1.5 - min(ltv,1.5))*40 + (1.4 - min(adv,1.4))*35
                      + max(0, 160000 - miles)/900 + max(0, 20000 - min(price,20000))/2200, 2))

def pick_units_for_lender(inventory_df: pd.DataFrame, lender_row: dict, fx: dict, topn=5, cpo_checked=False):
    if inventory_df is None or len(inventory_df)==0 or lender_row is None:
        return pd.DataFrame()
    work = inventory_df.copy()
    # price >= 4000 is already enforced by normalize_inventory
    passes, reasons = [], []
    for _, u in work.iterrows():
        ok, why = unit_passes_lender_rules(u, lender_row, fx, cpo_checked=cpo_checked)
        passes.append(ok); reasons.append(why)
    work["Pass"] = passes; work["Why"] = reasons
    work = work[work["Pass"]==True].copy()
    if work.empty:
        return pd.DataFrame(columns=["Stock","Label","Miles","Price","BookValue","Spread","Frame","Why","UnitScore"])
    work["UnitScore"] = work.apply(lambda r: score_unit(r, lender_row, fx), axis=1)
    work = work.sort_values("UnitScore", ascending=False).head(topn)
    return work[["Stock","Label","Miles","Price","BookValue","Spread","Frame","Why","UnitScore"]]

# ─────────────────────────────────────────────────────────────
# NEW: Lender Rule Q&A
# ─────────────────────────────────────────────────────────────
def pretty_extras(extras: dict) -> str:
    if not extras: return "—"
    bits = []
    if "max_ltv" in extras: bits.append(f"Max LTV: {int(extras['max_ltv']*100)}%")
    if "max_frontend_advance" in extras: bits.append(f"Max Advance: {int(extras['max_frontend_advance']*100)}%")
    if "max_financed" in extras: bits.append(f"Max Financed: ${int(extras['max_financed']):,}")
    if "min_book" in extras: bits.append(f"Min Book: ${int(extras['min_book']):,}")
    if "max_age_years" in extras: bits.append(f"Max Age: {extras['max_age_years']}y")
    if "max_miles" in extras: bits.append(f"Max Miles: {int(extras['max_miles']):,}")
    if "pti_cap" in extras: bits.append(f"PTI cap: {int(extras['pti_cap']*100)}%")
    if "max_payment_by_state" in extras: bits.append("State Max Payment set")
    if "term_by_miles" in extras: bits.append("Term by miles ladder")
    if "disallowed_makes" in extras: bits.append("Make restrictions present")
    if "cpo_bump" in extras: bits.append(f"CPO bump: ${int(extras['cpo_bump']):,}")
    return " • ".join(bits) if bits else "—"

def answer_lender_question(q: str, rules_df: pd.DataFrame) -> pd.DataFrame:
    """
    Simple Q&A: fuzzy matches lender name(s) and highlights relevant fields
    """
    if not q or not q.strip():
        return pd.DataFrame()
    s = q.lower()

    # try to detect lender tokens
    poss = []
    for _, r in rules_df.iterrows():
        name = str(r["Lender"])
        if all(tok in name.lower() for tok in re.findall(r"[a-z0-9]+", s)):
            poss.append(r)
        elif any(tok in name.lower() for tok in s.split()):
            poss.append(r)

    seen = set()
    rows = []
    for r in poss[:8]:  # limit
        key = r["Lender"]
        if key in seen: continue
        seen.add(key)
        rows.append({
            "Lender": r["Lender"],
            "Program": r.get("Program",""),
            "ScoreWindow": f"{'—' if pd.isna(r['MinScore']) or r['MinScore'] is None else int(r['MinScore'])} – {'—' if pd.isna(r['MaxScore']) or r['MaxScore'] is None else int(r['MaxScore'])}",
            "Repos≤": int(r.get("MaxRepos",0) or 0),
            "Job≥(mo)": int(r.get("MinJobMonths",0) or 0),
            "Income≥/mo": int(r.get("MinIncome",0) or 0),
            "Down≥": int(r.get("MinDown",0) or 0),
            "NoDL?": "Yes" if r.get("AllowNoDL",False) else "No",
            "Gig OK?": "Yes" if r.get("AllowGig",False) else "No",
            "Frame OK?": "Yes" if r.get("AllowFrame",False) else "No",
            "Extras": pretty_extras(r.get("Extras",{}))
        })

    # if nothing matched, return top 8 showing quick scan
    if not rows:
        for _, r in rules_df.head(8).iterrows():
            rows.append({
                "Lender": r["Lender"],
                "Program": r.get("Program",""),
                "ScoreWindow": f"{'—' if pd.isna(r['MinScore']) or r['MinScore'] is None else int(r['MinScore'])} – {'—' if pd.isna(r['MaxScore']) or r['MaxScore'] is None else int(r['MaxScore'])}",
                "Repos≤": int(r.get("MaxRepos",0) or 0),
                "Job≥(mo)": int(r.get("MinJobMonths",0) or 0),
                "Income≥/mo": int(r.get("MinIncome",0) or 0),
                "Down≥": int(r.get("MinDown",0) or 0),
                "NoDL?": "Yes" if r.get("AllowNoDL",False) else "No",
                "Gig OK?": "Yes" if r.get("AllowGig",False) else "No",
                "Frame OK?": "Yes" if r.get("AllowFrame",False) else "No",
                "Extras": pretty_extras(r.get("Extras",{}))
            })
    return pd.DataFrame(rows)

# ─────────────────────────────────────────────────────────────
# Session defaults
# ─────────────────────────────────────────────────────────────
if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_RATE_RULES.copy()

# Hard-wired inventory toggle + normalization
use_hard = st.sidebar.toggle("Use hard-wired inventory", value=True, help="Always load the inventory list embedded in this app.")
if "inventory_df" not in st.session_state:
    if use_hard:
        st.session_state["inventory_df"], st.session_state["excluded_under_4000_or_WT"] = normalize_inventory(HARD_INVENTORY)
    else:
        st.session_state["inventory_df"], st.session_state["excluded_under_4000_or_WT"] = pd.DataFrame(), 0

# ─────────────────────────────────────────────────────────────
# UI – Inputs & Uploads + Q&A
# ─────────────────────────────────────────────────────────────
st.title("SmartDesk – Desking Assistant")
st.caption("Hard-wired current inventory supported. Ask lender-rule questions any time.")

left, right = st.columns([1.25, 1])

with left:
    st.subheader("Deal Input")
    with st.form("deal_form"):
        c1,c2,c3 = st.columns(3)
        with c1:
            credit = st.number_input("Credit Score", 300, 850, 620, 1)
            income = st.number_input("Monthly Income ($/mo)", 0, 20000, 3000, 50)
            job_months = st.number_input("Job Time (months)", 0, 360, 6, 1)
        with c2:
            repos = st.number_input("# of Repos (reported)", 0, 10, 0, 1)
            has_dl = st.selectbox("Driver's License?", ["Yes","No"])
            down = st.number_input("Down Payment ($)", 0, 20000, 1000, 50)
        with c3:
            trade_eq = st.number_input("Trade Equity ($)", -20000, 20000, 0, 100)
            gig_flag = st.checkbox("Gig / DoorDash income?")
            gig_income = st.number_input("Gig Income ($/mo)", 0, 20000, 0, 50)
        with st.expander("Advanced flags", expanded=False):
            recent_repo_under_60 = st.checkbox("Recent repo < 60 days? (Exeter gate)", value=False)
            dealer_state = st.selectbox("Dealer State (for GFS Select Plus max pay)", ["OH","IN","MI","KY","IL","MO","WI"], index=0)
            cpo_checked = st.checkbox("Ally CPO eligible? (+$1,000 book bump)")
        submitted = st.form_submit_button("Evaluate Deal", type="primary")

with right:
    st.subheader("Uploads")
    # Rate rules
    rs = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"], key="rs")
    if rs:
        try:
            ext = ".csv" if rs.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["rate_rules"] = load_rate_sheet_from_bytes(rs.read(), ext)
            st.success(f"Loaded {len(st.session_state['rate_rules'])} lender rows from **{rs.name}**.")
        except Exception as e:
            st.error(f"Rate sheet error: {e}")

    # Inventory
    inv = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"], key="inv")
    if inv and not use_hard:
        try:
            ext = ".csv" if inv.name.lower().endswith(".csv") else ".xlsx"
            raw_inv = pd.read_csv(BytesIO(inv.read())) if ext==".csv" else pd.read_excel(BytesIO(inv.read()))
            st.session_state["inventory_df"], st.session_state["excluded_under_4000_or_WT"] = normalize_inventory(raw_inv)
            st.success(f"Inventory loaded: {len(st.session_state['inventory_df'])} units (excluded {st.session_state['excluded_under_4000_or_WT']} under $4,000 or W*/T* stocks).")
        except Exception as e:
            st.error(f"Inventory error: {e}")
    elif use_hard:
        st.info(f"Using hard-wired inventory: {len(st.session_state['inventory_df'])} units (excluded {st.session_state['excluded_under_4000_or_WT']} under $4,000 or W*/T*).")

    with st.expander("Inventory Preview", expanded=False):
        if len(st.session_state["inventory_df"]) > 0:
            st.dataframe(st.session_state["inventory_df"][["Stock","Label","Miles","Price","BookValue","Spread","Frame"]].head(50),
                         use_container_width=True, height=280)
        else:
            st.caption("No inventory loaded yet.")

# Q&A box
st.subheader("Ask about a lender rule")
q = st.text_input("Type a question (e.g., 'Does Exeter allow 200k miles?', 'GFS Select Plus max payment in OH?')")
if q:
    ans = answer_lender_question(q, st.session_state["rate_rules"])
    if len(ans) > 0:
        st.dataframe(ans, use_container_width=True, height=300)
    else:
        st.caption("No matching lender info found. Try including the lender name in your question.")

# ─────────────────────────────────────────────────────────────
# Evaluate
# ─────────────────────────────────────────────────────────────
def build_fx():
    return {
        "credit": credit, "income": income, "job_months": job_months, "repos": repos,
        "down": down, "trade_eq": trade_eq, "gig": bool(gig_flag),
        "gig_income": (gig_income if gig_flag else 0), "has_dl": has_dl,
        "recent_repo_under_60": bool(recent_repo_under_60),
    }

def unit_block_and_pick(pick, rules, fx):
    inv_df = st.session_state["inventory_df"]
    if pick is None or len(inv_df)==0:
        st.caption("Load inventory and/or get a recommended lender to see unit picks.")
        return
    full_rule = rules[rules["Lender"] == pick["Lender"]]
    lender_rule = full_rule.iloc[0].to_dict() if len(full_rule) else pick.to_dict()
    top_units = pick_units_for_lender(inv_df, lender_rule, fx, topn=5, cpo_checked=cpo_checked)
    if len(top_units) > 0:
        st.dataframe(
            top_units.style.format({"Price":"${:,.0f}","BookValue":"${:,.0f}","Spread":"${:,.0f}","UnitScore":"{:.2f}"}).set_table_attributes('class="tight"'),
            use_container_width=True, height=300
        )
        st.caption(f"{st.session_state['excluded_under_4000_or_WT']} unit(s) were filtered out (<$4,000 or W*/T* stocks).")
    else:
        st.caption("No units pass program gates (LTV/Advance/Term/Cost).")

if submitted:
    fx = build_fx()
    rules = st.session_state["rate_rules"].copy()
    pick, top, audit = recommend_lenders(rules, fx, topn=5)

    st.markdown("### Result")
    cols = st.columns([1.1, 1])
    with cols[0]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        if pick is not None:
            st.markdown('<div class="metric">✅ Recommended Lender</div>', unsafe_allow_html=True)
            st.markdown(f"**{pick['Lender']}**  \n<span class='em'>{pick['Reason']}</span>", unsafe_allow_html=True)
            st.markdown("<hr/>", unsafe_allow_html=True)
            ms = "—" if (pd.isna(pick['MinScore']) or pick['MinScore'] is None) else int(pick['MinScore'])
            xs = "—" if (pd.isna(pick['MaxScore']) or pick['MaxScore'] is None) else int(pick['MaxScore'])
            st.markdown(f"- **Program**: {pick['Program'] or '—'}")
            st.markdown(f"- **Score Window**: {ms} – {xs}")
            st.markdown(f"- **Min Down**: ${int(pick['MinDown'] or 0)}  •  **Min Income**: ${int(pick['MinIncome'] or 0)}/mo")
            st.markdown(f"- **Max Repos**: {int(pick['MaxRepos'] or 0)}  •  **Min Job**: {int(pick['MinJobMonths'] or 0)} mo")
        else:
            st.markdown('<div class="metric">❌ No Eligible Lender Found</div>', unsafe_allow_html=True)
            st.markdown("Try increasing down, adding a co-app, or picking a cleaner unit.", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with cols[1]:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="metric">Top Lender Matches</div>', unsafe_allow_html=True)
        if len(top) > 0:
            st.dataframe(
                top[["Lender","Program","Score","Reason","MinScore","MaxScore","MinDown","MinIncome","MinJobMonths","MaxRepos"]],
                use_container_width=True, height=230
            )
        else:
            st.caption("No eligible lenders with the current inputs.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### Suggested Units (Top 5)")
    unit_block_and_pick(pick, rules, fx)

    with st.expander("Audit (all lenders)", expanded=False):
        st.dataframe(audit, use_container_width=True, height=360)
else:
    st.info("Fill out the form and click **Evaluate Deal**.")
