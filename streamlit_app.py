# streamlit_app.py
import math
from io import BytesIO
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="SmartDesk — Deal Picker", page_icon="🚗", layout="wide")

# ---------------------------
# Simple styling
# ---------------------------
st.markdown("""
<style>
.small {opacity:.75;font-size:12px}
.metric {font-weight:700;font-size:18px}
.card {border:1px solid rgba(255,255,255,.15);padding:12px 14px;border-radius:12px;background:rgba(255,255,255,.03)}
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Defaults
# ---------------------------
DEFAULT_RULES = pd.DataFrame([
    # Lender, Program, MinScore, MinIncome, MinJobMonths, MaxRepos, AllowNoDL, AllowGig, MaxLTV, MaxMiles, MinBook, RateAPR, MaxTerm, MinTerm, Priority
    ["Gateway Financial Solutions", "Select", 0,   1800,  6,  3, False, True,  1.35, 200000,   0, 25.0, 72, 48,  1],
    ["Westlake Financial",          "Standard", 520, 1600,  6,  5, False, True,  1.20, 250000,   0, 24.9, 66, 36,  3],
    ["Consumer Portfolio Services", "CPS",      560, 1800, 12,  2, False, True,  1.24, 175000,   0, 23.0, 72, 48,  2],
    ["Exeter Finance",              "Bronze",   560, 2000, 12,  1, False, False, 1.20, 140000,   0, 25.0, 75, 36,  4],
    ["Flagship Credit Acceptance",  "Nickel",   580, 2000, 12,  1, False, True,  1.24, 130000,   0, 24.9, 72, 48,  5],
], columns=["Lender","Program","MinScore","MinIncome","MinJobMonths","MaxRepos",
            "AllowNoDL","AllowGig","MaxLTV","MaxMiles","MinBook","RateAPR",
            "MaxTerm","MinTerm","Priority"])

DEFAULT_INVENTORY = pd.DataFrame([
    # Stock, Year, Make, Model, Trim, Miles, Book, Asking, Cost
    ["A001", 2016, "Chevrolet", "Equinox", "LT",   93500,  9990, 11890, 7200],
    ["A002", 2017, "Ford",      "Edge",    "SEL", 102300, 10450, 12200, 7900],
    ["A007", 2018, "Hyundai",   "Elantra", "SEL",  84500, 10990, 12500, 8400],
    ["A008", 2019, "Nissan",    "Versa",   "SV",   61200,  9995, 11200, 8200],
    ["A010", 2015, "Toyota",    "Camry",   "SE",  128500,  8495, 10600, 6800],
], columns=["Stock","Year","Make","Model","Trim","Miles","Book","Asking","Cost"])

# ---------------------------
# Helpers
# ---------------------------
def pmnt(apr, term, amt):
    if term <= 0: return None
    r = apr/1200.0
    if r == 0: return round(amt/term, 2)
    p = amt * (r * (1+r)**term)/((1+r)**term - 1)
    return round(p, 2)

def boolish(x):  # faster CSV coercion
    if isinstance(x, str):
        return x.strip().lower() in ("y","yes","true","1")
    return bool(x)

def clean_num(x, default=None):
    try:
        if pd.isna(x) or x == "": return default
        return float(x)
    except:
        return default

# ---------------------------
# Uploads / in-session data
# ---------------------------
st.title("SmartDesk — Deal Picker (Best Lender × Best Unit)")

colU, colR = st.columns([1.2, 1])

with colU:
    st.subheader("Applicant")
    with st.form("appform"):
        c1,c2,c3 = st.columns(3)
        with c1:
            score = st.number_input("Credit Score", 300, 850, 580, 1)
            repos  = st.number_input("of Repos (reported)", 0, 10, 0, 1)
            dl     = st.selectbox("Driver’s License?", ["Yes","No"])
        with c2:
            income = st.number_input("Monthly Income ($)", 0, 30000, 5800, 50)
            job_years  = st.number_input("Job Time (years)", 0, 40, 1, 1)
            job_months = st.number_input("Job Time (months)", 0, 11, 6, 1)
        with c3:
            down   = st.number_input("Down Payment ($)", 0, 30000, 1000, 50)
            trade  = st.number_input("Trade Equity ($)", -20000, 50000, 0, 100)
            gig_on = st.checkbox("Gig / DoorDash income?")
            gig_inc= st.number_input("Gig Income ($/mo)", 0, 20000, 0, 50)

        include_co = st.checkbox("Include Co-Applicant?")
        if include_co:
            co1,co2 = st.columns(2)
            with co1:
                co_score  = st.number_input("Co-Applicant Score", 300, 850, 600, 1)
            with co2:
                co_income = st.number_input("Co-Applicant Income ($/mo)", 0, 20000, 0, 50)
        else:
            co_score  = None
            co_income = 0

        submitted = st.form_submit_button("Evaluate", type="primary")

with colR:
    st.subheader("Uploads")
    rs_file = st.file_uploader("Lender rules (CSV/XLSX)", type=["csv","xlsx"])
    inv_file= st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"])
    st.caption("Rules columns expected (case-insens): Lender,Program,MinScore,MinIncome,MinJobMonths,MaxRepos,AllowNoDL,AllowGig,MaxLTV,MaxMiles,MinBook,RateAPR,MaxTerm,MinTerm,Priority")
    st.caption("Inventory required: Stock,Year,Make,Model,Trim,Miles,Book,Asking,Cost")

# rules
def load_rules(file):
    if file is None: return DEFAULT_RULES.copy()
    ext = ".csv" if file.name.lower().endswith(".csv") else ".xlsx"
    df  = pd.read_csv(file) if ext==".csv" else pd.read_excel(file)
    # Coerce booleans/numbers
    df["AllowNoDL"] = df["AllowNoDL"].map(boolish)
    df["AllowGig"]  = df["AllowGig"].map(boolish)
    numcols = ["MinScore","MinIncome","MinJobMonths","MaxRepos","MaxLTV","MaxMiles","MinBook","RateAPR","MaxTerm","MinTerm","Priority"]
    for c in numcols: df[c] = df[c].apply(lambda x: clean_num(x, 0))
    return df

# inventory
def load_inv(file):
    if file is None: df = DEFAULT_INVENTORY.copy()
    else:
        ext = ".csv" if file.name.lower().endswith(".csv") else ".xlsx"
        df  = pd.read_csv(file) if ext==".csv" else pd.read_excel(file)
    # normalize + dealer filters used earlier: price > 4k and exclude stock starting W/T
    for c in ["Miles","Book","Asking","Cost"]: 
        df[c] = df[c].apply(lambda x: clean_num(x, 0))
    df = df[df["Book"]>=0]
    df = df[df["Asking"].fillna(0) >= 4000]
    df = df[~df["Stock"].astype(str).str.upper().str.startswith(("W","T"))]
    return df.reset_index(drop=True)

rules = load_rules(rs_file)
inv   = load_inv(inv_file)

with st.expander("Current Rules (top 20)"):
    st.dataframe(rules.sort_values("Priority").head(20), use_container_width=True)

with st.expander("Inventory (top 20)"):
    st.dataframe(inv.head(20), use_container_width=True)

# ---------------------------
# Gate & scoring
# ---------------------------
def eligible(row, F):
    # Applicant features
    score   = F["score"]
    income  = F["income_total"]
    job_tot = F["job_months_total"]
    repos   = F["repos"]
    dl_ok   = (F["dl"]=="Yes")
    gig_on  = F["gig_on"]
    # Hard gates
    if score < row.MinScore:          return False, "Below min score"
    if income < row.MinIncome:        return False, "Insufficient income"
    if job_tot < row.MinJobMonths:    return False, "Insufficient job time"
    if repos > row.MaxRepos:          return False, "Too many repos"
    if (not row.AllowNoDL) and (not dl_ok): return False, "DL required"
    if gig_on and (not row.AllowGig): return False, "Gig not allowed"
    return True, "Meets program"

def structure_for_unit(row, unit, F):
    """
    Return a dict with the lender-unit structure
    Sets sell price to LTV cap (your flow), then computes AF & payment
    """
    # Miles check
    if unit["Miles"] > row.MaxMiles: 
        return None, "Miles over program limit"

    # Book floor check
    if unit["Book"] < row.MinBook:
        return None, "Book under program minimum"

    # Price cap by LTV
    cap_price = math.floor(unit["Book"] * row.MaxLTV)
    sell_price = cap_price  # POC: set to max advance price

    # Amount financed rough (doc/taxes not modelled; you can add your state calc here)
    doc_fee = 0
    af = sell_price + doc_fee - F["down"] - F["trade"]
    if af <= 0:
        return None, "Down/Trade exceeds cap"

    # Term selection — pick highest allowed within program, can make smarter by age/miles
    term = int(row.MaxTerm)

    pay = pmnt(row.RateAPR, term, af)
    if pay is None: 
        return None, "Bad term"

    # Soft payment guard (20% of income default); tweak as needed
    max_pay = F["income_total"] * 0.20
    pay_ok = (pay <= max_pay)

    # Simple front gross heuristic: sell - cost (or fallback to sell - book)
    cost = unit.get("Cost", np.nan)
    if pd.isna(cost) or cost <= 0:
        gross = sell_price - unit["Book"]
    else:
        gross = sell_price - cost

    data = {
        "Lender": row.Lender,
        "Program": row.Program,
        "Priority": row.Priority,
        "RateAPR": row.RateAPR,
        "Term": term,
        "SellPrice": sell_price,
        "AF": af,
        "Payment": pay,
        "Gross": round(gross,2),
        "CapLTV": row.MaxLTV,
        "Reason": f"Cap @ {int(row.MaxLTV*100)}% of book; set price to cap.",
        "Proofs": "POI, POR, DL" if not row.AllowNoDL else "POI, POR",
    }
    if not pay_ok:
        data["Reason"] += " Payment above internal comfort (20% of income)."
    return data, None

def pick_best(rules_df, inv_df, F, topn=5, gateway_priority=True):
    rows=[]
    for _, r in rules_df.iterrows():
        ok, why = eligible(r, F)
        if not ok: 
            continue
        for _, u in inv_df.iterrows():
            s, err = structure_for_unit(r, u, F)
            if s is None:
                continue
            # Composite score: front gross first, then payment fit, then lender priority
            # Gateway first for POC
            lender_bias = -r.Priority
            if gateway_priority and ("gateway" in r.Lender.strip().lower()):
                lender_bias += 3  # gentle nudge

            pay_pressure = -max(0, (s["Payment"] - F["income_total"]*0.20)) / 50.0
            score = s["Gross"]*1.0 + pay_pressure + lender_bias
            rows.append({
                "Score": round(score,2),
                "Stock": u["Stock"],
                "Unit": f'{u["Year"]} {u["Make"]} {u["Model"]} {u["Trim"]}',
                "Miles": int(u["Miles"]),
                "Book": int(u["Book"]),
                "Asking": int(u["Asking"]),
                "Cost": int(u.get("Cost", np.nan)) if not pd.isna(u.get("Cost", np.nan)) else None,
                **s
            })
    if not rows:
        return None, pd.DataFrame()

    df = pd.DataFrame(rows).sort_values(["Score","Gross"], ascending=[False, False]).reset_index(drop=True)
    return df.iloc[0].to_dict(), df.head(topn)

# ---------------------------
# Run
# ---------------------------
if submitted:
    features = {
        "score": score,
        "income_total": income + (gig_inc if gig_on else 0) + co_income,
        "job_months_total": int(job_years)*12 + int(job_months),
        "repos": repos,
        "dl": dl,
        "gig_on": bool(gig_on),
        "down": down,
        "trade": trade,
        "co_score": co_score,
        "co_income": co_income,
    }

    best, top = pick_best(rules, inv, features, topn=5, gateway_priority=True)

    st.subheader("Recommendation")
    left, right = st.columns([1.1, 1])
    if best is None:
        with left:
            st.warning("No lender fits with current inputs and inventory.")
        with right:
            st.info("Upload/update rules or inventory, or adjust applicant inputs.")
    else:
        with left:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown(f"<div class='metric'>✅ {best['Lender']} — {best['Program']}</div>", unsafe_allow_html=True)
            st.write(f"**Unit**: {best['Unit']}  \n**Stock**: {best['Stock']}  \n**Miles**: {best['Miles']:,}  \n**Book**: ${best['Book']:,}")
            st.write(f"**Sell @ Cap**: ${best['SellPrice']:,}  \n**AF**: ${int(best['AF']):,}  \n**Term**: {best['Term']}  \n**Rate**: {best['RateAPR']}%  \n**Est. Pmt**: ${best['Payment']:,}")
            st.write(f"**Front Gross (rough)**: ${best['Gross']:,}")
            st.write(f"**Why**: {best['Reason']}")
            st.write(f"**Proofs**: {best['Proofs']}")
            st.markdown('</div>', unsafe_allow_html=True)

        with right:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("<div class='metric'>Top 5 Unit × Lender</div>", unsafe_allow_html=True)
            show = top[["Score","Stock","Unit","Lender","Program","SellPrice","AF","Payment","Gross","Miles","Book","Asking"]]
            st.dataframe(show, use_container_width=True, height=240)
            st.markdown('</div>', unsafe_allow_html=True)

    st.subheader("Audit")
    st.json({
        "Applicant": {
            "Score": score, "Income/mo": income, "Gig?": gig_on, "GigIncome": gig_inc,
            "CoIncome": co_income, "Repos": repos, "JobMonths": features["job_months_total"],
            "DL": dl, "Down": down, "Trade": trade
        }
    }, expanded=False)
else:
    st.info("Enter applicant inputs and click **Evaluate**. The app will select the best lender × unit and provide a turn-key structure.")
