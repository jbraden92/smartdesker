# streamlit_app.py
import streamlit as st
import pandas as pd
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
# DEFAULT LENDER RULES (you can tune numbers anytime)
#  - "Extras" carries program gates the unit checker uses
#  - Leave MinScore/MaxScore None for "no cap"
# ─────────────────────────────────────────────────────────────
def L(lender, program="", minscore=None, maxscore=None, maxrepos=99, minjob=0, mininc=0, mindown=0,
      gig=True, nodl=False, frame=False, extras=None):
    return {
        "Lender": lender, "Program": program, "MinScore": minscore, "MaxScore": maxscore, "MaxRepos": maxrepos,
        "MinJobMonths": minjob, "MinIncome": mininc, "MinDown": mindown,
        "AllowGig": gig, "AllowNoDL": nodl, "AllowFrame": frame, "Extras": (extras or {})
    }

DEFAULT_RATE_RULES = pd.DataFrame([
    # ── Gateway ─────────────────────────────────────────────
    L("Gateway Financial Solutions – Select","Select",
      None,None, maxrepos=1, minjob=3, mininc=1500, mindown=500, gig=True, nodl=False, frame=False,
      extras=dict(
        max_ltv=2.25, max_frontend_advance=1.35, max_financed=30000, min_book=4000,
        term_by_miles=[(0,75000,72),(75001,100000,66),(100001,125000,60),(125001,150000,54),(150001,175000,48),(175001,999999,42)],
        pti_cap=0.18,
        disallowed_makes=["Audi","Jaguar","Land Rover","Mercedes","Mini","Porsche","Saab"]
      )
    ),
    L("Gateway Financial Solutions – Select Plus","Select Plus",
      None,None, maxrepos=1, minjob=3, mininc=1500, mindown=500, gig=True, nodl=True, frame=False,
      extras=dict(
        max_ltv=2.30, max_frontend_advance=1.90, max_financed=18000, min_book=4000,
        term_by_miles=[(0,75000,60),(75001,100000,54),(100001,125000,48),(125001,150000,42),(150001,999999,36)],
        max_payment_by_state={"OH":600,"IN":600,"MI":600,"KY":600,"IL":635,"MO":635,"WI":635},
        disallowed_makes=["Audi","Jaguar","Land Rover","Mercedes","Mini","Porsche","Saab"]
      )
    ),

    # ── Exeter ──────────────────────────────────────────────
    L("Exeter Finance","Standard",
      None,None, maxrepos=2, minjob=6, mininc=1700, mindown=500, gig=True, nodl=False, frame=False,
      extras=dict(
        max_age_years=13, max_miles=200000,
        term_by_miles=[(0,90000,72),(90001,130000,66),(130001,180000,60),(180001,200000,54),(200001,999999,0)],
        max_ltv=2.00, max_frontend_advance=1.40,
        block_recent_repo_under_days=60
      )
    ),

    # ── CPS ─────────────────────────────────────────────────
    L("Consumer Portfolio Services (CPS)","Standard",
      None,None, maxrepos=2, minjob=6, mininc=1800, mindown=500, gig=True, nodl=False, frame=False,
      extras=dict(
        max_age_years=15, max_miles=200000,
        term_by_miles=[(0,90000,72),(90001,130000,66),(130001,170000,60),(170001,200000,54),(200001,999999,0)],
        max_ltv=2.10, max_frontend_advance=1.50
      )
    ),

    # ── GLS ────────────────────────────────────────────────
    L("Global Lending Services","Standard",
      580,720, maxrepos=2, minjob=6, mininc=2200, mindown=1000, gig=True, nodl=False, frame=False,
      extras=dict(max_term_default=72, max_ltv=1.80, max_frontend_advance=1.30)
    ),

    # ── Flagship ───────────────────────────────────────────
    L("Flagship Credit","Standard",
      600,750, maxrepos=2, minjob=6, mininc=2400, mindown=1000, gig=True, nodl=False, frame=True,
      extras=dict(max_term_default=72, max_ltv=1.90, max_frontend_advance=1.35)
    ),

    # ── Regional Acceptance ────────────────────────────────
    L("Regional Acceptance","Standard",
      590,720, maxrepos=1, minjob=12, mininc=2500, mindown=1000, gig=False, nodl=False, frame=False,
      extras=dict(max_term_default=72, max_ltv=1.80, max_frontend_advance=1.30)
    ),

    # ── Prestige ───────────────────────────────────────────
    L("Prestige Financial","Tiered",
      600,750, maxrepos=0, minjob=12, mininc=3000, mindown=1000, gig=False, nodl=False, frame=False,
      extras=dict(
        max_age_years=12,
        term_by_miles=[(0,75000,75),(75001,110000,66),(110001,150000,60),(150001,999999,54)],
        max_ltv=1.80, max_frontend_advance=1.30, pti_cap=0.18
      )
    ),

    # ── Kemba CU ───────────────────────────────────────────
    L("Kemba CU","CU",
      640,800, maxrepos=0, minjob=12, mininc=3000, mindown=1000, gig=False, nodl=False, frame=False,
      extras=dict(max_term_default=72, max_ltv=1.20, max_frontend_advance=1.10)
    ),

    # ── Ally (CPO bump supported) ──────────────────────────
    L("Ally Auto (CPO Eligible)","CPO",
      600,800, maxrepos=1, minjob=6, mininc=2500, mindown=1000, gig=False, nodl=False, frame=False,
      extras=dict(
        cpo_bump=1000,              # +$1,000 to Book if CPO checked and vehicle qualifies
        cpo_min_years=10,           # up to 10 MY old
        cpo_max_miles=100000,       # under 100k mi (typical)
        max_term_default=72, max_ltv=1.20, max_frontend_advance=1.10
      )
    ),

    # ── AmeriCredit / GM Financial ─────────────────────────
    L("AmeriCredit / GM Financial","Standard",
      580,800, maxrepos=2, minjob=6, mininc=2200, mindown=1000, gig=True, nodl=False, frame=False,
      extras=dict(
        max_term_default=75, max_ltv=1.90, max_frontend_advance=1.35,
        term_by_miles=[(0,90000,75),(90001,120000,66),(120001,150000,60),(150001,999999,54)]
      )
    ),

    # ── Santander Consumer USA ─────────────────────────────
    L("Santander Consumer USA","Standard",
      560,750, maxrepos=2, minjob=6, mininc=2000, mindown=500, gig=True, nodl=False, frame=False,
      extras=dict(
        max_term_default=72, max_ltv=2.00, max_frontend_advance=1.40,
        term_by_miles=[(0,90000,72),(90001,130000,66),(130001,170000,60),(170001,200000,54)]
      )
    ),

    # ── Westlake Financial ─────────────────────────────────
    L("Westlake Financial","Standard",
      None,None, maxrepos=2, minjob=3, mininc=1800, mindown=500, gig=True, nodl=False, frame=False,
      extras=dict(
        max_term_default=72, max_ltv=2.10, max_frontend_advance=1.50,
        term_by_miles=[(0,100000,72),(100001,150000,60),(150001,999999,54)]
      )
    ),

    # ── Credit Acceptance (CAC) ────────────────────────────
    L("Credit Acceptance (CAC)","Standard",
      None,None, maxrepos=99, minjob=0, mininc=0, mindown=0, gig=True, nodl=False, frame=True,
      extras=dict(
        max_term_default=72, max_ltv=2.50, max_frontend_advance=2.00
      )
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
# Default Inventory (POC if none uploaded)
# ─────────────────────────────────────────────────────────────
DEFAULT_SAMPLE_INVENTORY = pd.DataFrame([
    {"Stock":"A001","Year":2016,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93500,"Price":9990,"BookValue":11800},
    {"Stock":"A002","Year":2017,"Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"Price":10450,"BookValue":12200},
    {"Stock":"A003","Year":2014,"Make":"Toyota","Model":"Camry","Trim":"SE","Miles":128500,"Price":8495,"BookValue":10250},
    {"Stock":"A004","Year":2015,"Make":"Nissan","Model":"Altima","Trim":"2.5 S","Miles":119400,"Price":7795,"BookValue":9300},
    {"Stock":"X005","Year":2016,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111200,"Price":8995,"BookValue":10600},  # X = frame flag
    {"Stock":"B006","Year":2011,"Make":"Kia","Model":"Soul","Trim":"Base","Miles":171500,"Price":3390,"BookValue":4200},   # excluded (<4500)
    {"Stock":"B007","Year":2010,"Make":"Hyundai","Model":"Sonata","Trim":"GLS","Miles":189000,"Price":2995,"BookValue":3900},
    {"Stock":"B008","Year":2012,"Make":"Chevrolet","Model":"Cruze","Trim":"LS","Miles":164200,"Price":4295,"BookValue":5200},
])

def normalize_inventory(df: pd.DataFrame):
    if df is None or len(df) == 0:
        return pd.DataFrame(), 0
    raw = df.copy()
    cols = {c.lower().strip(): c for c in raw.columns}
    def pick(name, *aliases, default=None):
        for key in (name, *aliases):
            if key in cols: return raw[cols[key]]
        return default
    out = pd.DataFrame({
        "Stock":     pick("stock","stock#","stocknum","stock number", default=pd.Series([""]*len(raw))),
        "Year":      pd.to_numeric(pick("year", default=pd.Series([None]*len(raw))), errors="coerce"),
        "Make":      pick("make", default=pd.Series([""]*len(raw))),
        "Model":     pick("model", default=pd.Series([""]*len(raw))),
        "Trim":      pick("trim","style", default=pd.Series([""]*len(raw))),
        "Miles":     pd.to_numeric(pick("miles","mileage", default=pd.Series([None]*len(raw))), errors="coerce"),
        "Price":     pd.to_numeric(pick("price","total cost","cost","selling price","sale price", default=pd.Series([None]*len(raw))), errors="coerce"),
        "BookValue": pd.to_numeric(pick("kbblsim","bbwhsale","nadasiminv","nada retail","book","bookvalue","kbb lending", default=pd.Series([None]*len(raw))), errors="coerce"),
    })
    out["Spread"] = (out["BookValue"] - out["Price"]).fillna(0)
    out["Frame"]  = out["Stock"].astype(str).str.upper().str.startswith("X")
    out["Label"]  = (
        out["Year"].fillna("").astype(str).str.replace(".0","",regex=False).str.strip()+" "+
        out["Make"].fillna("").astype(str).str.strip()+" "+
        out["Model"].fillna("").astype(str).str.strip()+" "+
        out["Trim"].fillna("").astype(str).str.strip()
    ).str.replace(r"\s+"," ", regex=True).str.strip()
    before = len(out)
    out = out[pd.to_numeric(out["Price"], errors="coerce") >= 4500]
    excluded = before - len(out)
    out = out.reset_index(drop=True)
    return out, excluded

# ─────────────────────────────────────────────────────────────
# Lender (person-level) eligibility
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

    score = 0.0
    if (lr["MinScore"] is not None) and (lr["MaxScore"] is not None):
        mid = (lr["MinScore"] + lr["MaxScore"]) / 2.0
        score += 100 - abs(cred - mid) * 0.5
    else:
        score += 90  # no-cap baseline
    score += min(1000, down)/20
    score += min(4000, income)/40
    score += (10 if has_dl == "Yes" else 0)
    score += (15 if (gig and lr["AllowGig"]) else 0)
    return (True, "Meets program guidelines", round(score,1))

def recommend_lenders(rules_df: pd.DataFrame, fx: dict, topn=5):
    rows = []
    for _, r in rules_df.iterrows():
        ok, why, s = score_lender_person(r, fx)
        rows.append({
            "Lender": r.Lender, "Program": r.Program, "Eligible": ok, "Reason": why, "Score": s,
            "MinScore": r.MinScore, "MaxScore": r.MaxScore, "MinDown": r.MinDown, "MinIncome": r.MinIncome,
            "MinJobMonths": r.MinJobMonths, "MaxRepos": r.MaxRepos, "AllowFrame": r.AllowFrame,
            "AllowNoDL": r.AllowNoDL, "AllowGig": r.AllowGig, "Extras": r.Extras
        })
    df = pd.DataFrame(rows).sort_values(["Eligible","Score"], ascending=[False, False]).reset_index(drop=True)
    top = df[df["Eligible"]].head(topn)
    pick = top.iloc[0] if len(top) else None
    return pick, top, df

# ─────────────────────────────────────────────────────────────
# Unit-level gates (LTV, Advance, term-by-miles, CPO bump, etc.)
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

    # Frame
    if unit.get("Frame", False) and not allow_frame:
        return (False, "Frame not allowed")

    # Age / miles
    yr = unit.get("Year"); miles = unit.get("Miles")
    if ex.get("max_age_years") is not None and pd.notna(yr):
        age = THIS_YEAR - int(yr)
        if age > ex["max_age_years"]:
            return (False, f"Age>{ex['max_age_years']}y")
    if ex.get("max_miles") is not None and pd.notna(miles):
        if miles > ex["max_miles"]:
            return (False, f"Miles>{ex['max_miles']:,}")

    # Disallowed makes (Gateway)
    make = str(unit.get("Make","")).strip()
    bad_makes = ex.get("disallowed_makes")
    if bad_makes and any(make.lower()==bm.lower() for bm in bad_makes):
        return (False, "Make not allowed")

    # Book / price (+ Ally CPO bump if toggled and lender is Ally CPO)
    book = to_num(unit.get("BookValue"), 0) or 0
    price = to_num(unit.get("Price"), 0) or 0
    if "Ally Auto (CPO Eligible)" in lender_row.get("Lender","") and cpo_checked:
        # quick CPO reasonableness gate
        if (yr is not None) and (miles is not None):
            # typical Ally CPO: <=10 MY old and <100k mi (simplified)
            age = THIS_YEAR - int(yr)
            if age <= (ex.get("cpo_min_years",10)) and miles <= ex.get("cpo_max_miles",100000):
                book += ex.get("cpo_bump", 1000)
    if book <= 0 or price <= 0:
        return (False, "Missing book/price")
    if ex.get("min_book") and book < ex["min_book"]:
        return (False, f"Book<{ex['min_book']:.0f}")

    # Financed, LTV, front-end advance
    down = float(fx.get("down",0) or 0)
    trade_eq = float(fx.get("trade_eq",0) or 0)
    financed = max(0.0, price - down - trade_eq)  # adjust if you roll fees/neg eq
    front_end_adv = price / book
    ltv = (financed / book) if book > 0 else 999

    if ex.get("max_financed") and financed > ex["max_financed"]:
        return (False, f"Financed>{ex['max_financed']:.0f}")
    if ex.get("max_frontend_advance") and front_end_adv > ex["max_frontend_advance"]:
        return (False, f"Advance>{int(ex['max_frontend_advance']*100)}%")
    if ex.get("max_ltv") and ltv > ex["max_ltv"]:
        return (False, f"LTV>{int(ex['max_ltv']*100)}%")

    # Term by miles ladder and PTI / max payment
    term = ladder_term_for_unit(ex, miles)
    if term <= 0:
        return (False, "Term blocked by miles")
    apr = 0.24  # placeholder; can add per-lender pricing later
    pmt = est_payment(financed, apr=apr, term=term)

    # PTI
    pti_cap = ex.get("pti_cap")
    if pti_cap is not None:
        income_total = float(fx["income"] + fx["gig_income"])
        if income_total <= 0: return (False, "No income")
        if pmt > income_total * pti_cap:
            return (False, f"PTI>{int(pti_cap*100)}%")

    # State max payment (GFS Select Plus)
    max_pay_map = ex.get("max_payment_by_state")
    if max_pay_map:
        max_pay = max_pay_map.get(dealer_state, None)
        if max_pay and pmt > max_pay:
            return (False, f"Max pay>{max_pay}")

    return (True, f"OK (Term {term} mo, LTV {ltv:.2f}, Adv {front_end_adv:.2f})")

def score_unit(unit, lender_row, fx):
    spread = to_num(unit.get("Spread"), 0) or 0
    miles  = to_num(unit.get("Miles"), 0) or 0
    price  = to_num(unit.get("Price"), 0) or 0
    book   = to_num(unit.get("BookValue"), 0) or 0
    ltv = (max(0.0, price - float(fx.get("down",0)) - float(fx.get("trade_eq",0))) / book) if book>0 else 5.0
    adv = (price / book) if book>0 else 5.0
    # favor spread; reward lower LTV/advance, lower miles/price
    score = spread*0.6 + (1.5 - min(ltv,1.5))*40 + (1.4 - min(adv,1.4))*35 \
            + max(0, 160000 - miles)/900 + max(0, 20000 - min(price,20000))/2200
    return float(round(score,2))

def pick_units_for_lender(inventory_df: pd.DataFrame, lender_row: dict, fx: dict, dealer_state="OH", topn=5, cpo_checked=False):
    if inventory_df is None or len(inventory_df)==0 or lender_row is None:
        return pd.DataFrame()
    work = inventory_df.copy()
    work = work[pd.to_numeric(work["Price"], errors="coerce") >= 4500]  # safeguard

    passes = []; reasons = []
    for _, u in work.iterrows():
        ok, why = unit_passes_lender_rules(u, lender_row, fx, dealer_state=dealer_state, cpo_checked=cpo_checked)
        passes.append(ok); reasons.append(why)
    work["Pass"] = passes; work["Why"] = reasons
    work = work[work["Pass"]==True].copy()
    if work.empty:
        return pd.DataFrame(columns=["Stock","Label","Miles","Price","BookValue","Spread","Frame","Why","UnitScore"])

    work["UnitScore"] = work.apply(lambda r: score_unit(r, lender_row, fx), axis=1)
    work = work.sort_values("UnitScore", ascending=False).head(topn)
    return work[["Stock","Label","Miles","Price","BookValue","Spread","Frame","Why","UnitScore"]]

# ─────────────────────────────────────────────────────────────
# Session defaults
# ─────────────────────────────────────────────────────────────
if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_RATE_RULES.copy()

# ─────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────
st.title("SmartDesk – Desking Assistant")
st.caption("All lenders loaded. Respects **LTV, Front-End Advance, Term-by-Miles, PTI, Max Payment**. Ally CPO bump supported.")

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
    rs = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"], key="rs")
    if rs:
        try:
            ext = ".csv" if rs.name.lower().endswith(".csv") else ".xlsx"
            st.session_state["rate_rules"] = load_rate_sheet_from_bytes(rs.read(), ext)
            st.success(f"Loaded {len(st.session_state['rate_rules'])} lender rows from **{rs.name}**.")
        except Exception as e:
            st.error(f"Rate sheet error: {e}")

    inv = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"], key="inv")
    if "inventory_df" not in st.session_state:
        st.session_state["inventory_df"], st.session_state["excluded_under_4500"] = normalize_inventory(DEFAULT_SAMPLE_INVENTORY)

    if inv:
        try:
            ext = ".csv" if inv.name.lower().endswith(".csv") else ".xlsx"
            raw_inv = pd.read_csv(BytesIO(inv.read())) if ext==".csv" else pd.read_excel(BytesIO(inv.read()))
            st.session_state["inventory_df"], st.session_state["excluded_under_4500"] = normalize_inventory(raw_inv)
            st.success(f"Inventory loaded: {len(st.session_state['inventory_df'])} units (excluded {st.session_state['excluded_under_4500']} under $4,500).")
        except Exception as e:
            st.error(f"Inventory error: {e}")
    else:
        st.info(f"Using built-in sample inventory: {len(st.session_state['inventory_df'])} units (excluded {st.session_state['excluded_under_4500']} under $4,500).")

    with st.expander("Current Rate Rules (top 20)", expanded=False):
        st.dataframe(st.session_state["rate_rules"].head(20), use_container_width=True)

    with st.expander("Inventory Preview (cleaned)", expanded=False):
        st.dataframe(st.session_state["inventory_df"][["Stock","Label","Miles","Price","BookValue","Spread","Frame"]].head(25),
                     use_container_width=True, height=280)

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

def recommend_and_render():
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

    # Units for picked lender
    st.markdown("### Suggested Units (Top 5)")
    inv_df = st.session_state["inventory_df"]
    if pick is not None and len(inv_df) > 0:
        # pull full rule row by lender name
        full_rule = rules[rules["Lender"] == pick["Lender"]]
        lender_rule = full_rule.iloc[0].to_dict() if len(full_rule) else pick.to_dict()
        top_units = pick_units_for_lender(inv_df, lender_rule, fx, dealer_state=dealer_state, topn=5, cpo_checked=cpo_checked)
        if len(top_units) > 0:
            st.dataframe(
                top_units.style.format({"Price":"${:,.0f}","BookValue":"${:,.0f}","Spread":"${:,.0f}","UnitScore":"{:.2f}"}).set_table_attributes('class="tight"'),
                use_container_width=True, height=300
            )
            st.caption(f"{st.session_state['excluded_under_4500']} unit(s) were filtered out for being under $4,500.")
        else:
            st.caption("No units pass program gates (LTV/Advance/Term/Cost).")
    else:
        st.caption("Load inventory and/or get a recommended lender to see unit picks.")

    with st.expander("Audit (all lenders)", expanded=False):
        st.dataframe(audit, use_container_width=True, height=360)

if submitted:
    recommend_and_render()
else:
    st.info("Fill out the form and click **Evaluate Deal**.")
