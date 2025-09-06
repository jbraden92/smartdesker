# streamlit_app.py
import math
from io import BytesIO
import pandas as pd
import numpy as np
import streamlit as st

st.set_page_config(page_title="SmartDesk — Deal Picker", page_icon="🚗", layout="wide")

# ---------- UI polish ----------
st.markdown("""
<style>
.small {opacity:.75;font-size:12px}
.metric {font-weight:700;font-size:18px}
.card {border:1px solid rgba(255,255,255,.15);padding:12px 14px;border-radius:12px;background:rgba(255,255,255,.03)}
</style>""", unsafe_allow_html=True)

# ---------- Defaults ----------
DEFAULT_RULES = pd.DataFrame([
    # Lender, Program, MinScore, MinIncome, MinJobMonths, MaxRepos, AllowNoDL, AllowGig, MaxLTV, MaxMiles, MinBook, RateAPR, MaxTerm, MinTerm, Priority, DealerFee, FeeFinanced
    # GATEWAY: include both Select and Select Plus so we can show side-by-side
    ["Gateway Financial Solutions","Select",      0,   1800, 6, 3, False, True,  1.35, 200000, 0, 25.0, 72, 48, 1, 0,  False],
    ["Gateway Financial Solutions","Select Plus", 0,   2000, 6, 2, False, True,  1.24, 200000, 0, 24.9, 72, 48, 1, 0,  False],

    ["Westlake Financial","Standard", 520,1600, 6,5, False,True, 1.20,250000,0, 24.9,66,36, 3, 0, False],
    ["Consumer Portfolio Services","CPS", 560,1800,12,2, False,True, 1.24,175000,0, 23.0,72,48, 2, 0, False],
    ["Exeter Finance","Bronze", 560,2000,12,1, False,False, 1.20,140000,0, 25.0,75,36, 4, 0, False],
    ["Flagship Credit Acceptance","Nickel", 580,2000,12,1, False,True, 1.24,130000,0, 24.9,72,48, 5, 0, False],
], columns=["Lender","Program","MinScore","MinIncome","MinJobMonths","MaxRepos",
            "AllowNoDL","AllowGig","MaxLTV","MaxMiles","MinBook","RateAPR",
            "MaxTerm","MinTerm","Priority","DealerFee","FeeFinanced"])

DEFAULT_INVENTORY = pd.DataFrame([
    ["A001", 2016, "Chevrolet", "Equinox", "LT",   93500,  9990, 11890, 7200],
    ["A002", 2017, "Ford",      "Edge",    "SEL", 102300, 10450, 12200, 7900],
    ["A007", 2018, "Hyundai",   "Elantra", "SEL",  84500, 10990, 12500, 8400],
    ["A008", 2019, "Nissan",    "Versa",   "SV",   61200,  9995, 11200, 8200],
    ["A010", 2015, "Toyota",    "Camry",   "SE",  128500,  8495, 10600, 6800],
], columns=["Stock","Year","Make","Model","Trim","Miles","Book","Asking","Cost"])

# ---------- Helpers ----------
def pmnt(apr, term, amt):
    if term <= 0: return None
    r = apr/1200.0
    if r == 0: return round(amt/term, 2)
    return round(amt * (r*(1+r)**term)/((1+r)**term - 1), 2)

def boolish(x):
    if isinstance(x, str): return x.strip().lower() in ("y","yes","true","1")
    return bool(x)

def clean_num(x, default=None):
    try:
        if pd.isna(x) or x == "": return default
        return float(x)
    except:
        return default

# ---------- Layout ----------
st.title("SmartDesk — Deal Picker (Best Lender × Best Unit)")

colU, colR = st.columns([1.25, 1])

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
    st.caption("Rules columns (case-insens): Lender, Program, MinScore, MinIncome, MinJobMonths, MaxRepos, AllowNoDL, AllowGig, MaxLTV, MaxMiles, MinBook, RateAPR, MaxTerm, MinTerm, Priority, DealerFee, FeeFinanced")
    st.caption("Inventory: Stock, Year, Make, Model, Trim, Miles, Book, Asking, Cost")

# ---------- Data loaders ----------
def load_rules(file):
    if file is None: return DEFAULT_RULES.copy()
    ext = ".csv" if file.name.lower().endswith(".csv") else ".xlsx"
    df  = pd.read_csv(file) if ext==".csv" else pd.read_excel(file)
    # coerce
    for c in ("AllowNoDL","AllowGig","FeeFinanced"):
        if c in df.columns: df[c] = df[c].map(boolish)
    numcols = ["MinScore","MinIncome","MinJobMonths","MaxRepos","MaxLTV",
               "MaxMiles","MinBook","RateAPR","MaxTerm","MinTerm","Priority","DealerFee"]
    for c in numcols:
        if c in df.columns: df[c] = df[c].apply(lambda x: clean_num(x, 0))
    if "DealerFee" not in df.columns: df["DealerFee"] = 0
    if "FeeFinanced" not in df.columns: df["FeeFinanced"] = False
    return df

def load_inv(file):
    if file is None: df = DEFAULT_INVENTORY.copy()
    else:
        ext = ".csv" if file.name.lower().endswith(".csv") else ".xlsx"
        df  = pd.read_csv(file) if ext==".csv" else pd.read_excel(file)
    for c in ["Miles","Book","Asking","Cost"]:
        if c in df.columns: df[c] = df[c].apply(lambda x: clean_num(x, 0))
    # dealer filters
    df = df[df["Asking"].fillna(0) >= 4000]
    df = df[~df["Stock"].astype(str).str.upper().str.startswith(("W","T"))]
    return df.reset_index(drop=True)

rules = load_rules(rs_file)
inv   = load_inv(inv_file)

with st.expander("Current Rules (top 20)"):
    st.dataframe(rules.sort_values(["Lender","Program"]).head(20), use_container_width=True)
with st.expander("Inventory (top 20)"):
    st.dataframe(inv.head(20), use_container_width=True)

# ---------- Decision Engine ----------
def eligible(row, F):
    if F["score"] < row.MinScore:       return False, "Below min score"
    if F["income_total"] < row.MinIncome:return False, "Insufficient income"
    if F["job_months_total"] < row.MinJobMonths: return False, "Insufficient job time"
    if F["repos"] > row.MaxRepos:       return False, "Too many repos"
    if (not row.AllowNoDL) and (F["dl"]!="Yes"): return False, "DL required"
    if F["gig_on"] and (not row.AllowGig): return False, "Gig not allowed"
    return True, "Meets"

def build_structure(row, unit, F):
    # unit gates
    if unit["Miles"] > row.MaxMiles: return None, "Miles over limit"
    if unit["Book"] < row.MinBook:   return None, "Book below min"

    cap_price = math.floor(unit["Book"] * row.MaxLTV)
    sell_price = cap_price                              # POC: always set to cap
    doc_fee = 0
    af = sell_price + doc_fee - F["down"] - F["trade"]  # finance amount

    if af <= 0: return None, "Down/Trade exceeds cap"

    term = int(row.MaxTerm)
    pay  = pmnt(row.RateAPR, term, af)
    if pay is None: return None, "Bad term"

    # Dealer fee handling
    dealer_fee = float(row.DealerFee) if "DealerFee" in row else 0.0
    fee_financed = bool(row.FeeFinanced) if "FeeFinanced" in row else False

    # Gross & proceeds
    cost = unit.get("Cost", np.nan)
    cost = 0 if pd.isna(cost) else cost
    gross = sell_price - cost
    if not fee_financed:
        gross -= dealer_fee            # fee deducted from proceeds/gross
        net_proceeds = af - dealer_fee
    else:
        net_proceeds = af              # fee added to AF (we're not adding it in AF calc now)

    data = {
        "Lender": row.Lender,
        "Program": row.Program,
        "Priority": row.Priority,
        "RateAPR": row.RateAPR,
        "Term": term,
        "SellPrice": sell_price,
        "AF": af,
        "NetProceeds": net_proceeds,
        "Payment": pay,
        "Gross": round(gross,2),
        "CapLTV": row.MaxLTV,
        "DealerFee": dealer_fee,
        "FeeFinanced": fee_financed,
        "Proofs": "POI, POR, DL" if not row.AllowNoDL else "POI, POR",
        "Reason": f"Cap @{int(row.MaxLTV*100)}% of book. Dealer fee ${int(dealer_fee)} {'financed' if fee_financed else 'deducted'}."
    }
    return data, None

def pick_best(rules_df, inv_df, F, topn=5, gateway_bias=True):
    rows=[]
    for _, r in rules_df.iterrows():
        ok, _ = eligible(r, F)
        if not ok: continue
        for _, u in inv_df.iterrows():
            s, err = build_structure(r, u, F)
            if s is None: continue

            lender_bias = -r.Priority
            if gateway_bias and ("gateway" in r.Lender.strip().lower()):
                lender_bias += 3

            pay_pressure = -max(0, (s["Payment"] - F["income_total"]*0.20))/50.0
            score = s["Gross"]*1.0 + pay_pressure + lender_bias

            rows.append({
                "Score": round(score,2),
                "Stock": str(u["Stock"]),                           # exact stock number
                "Unit": f'{int(u["Year"])} {u["Make"]} {u["Model"]} {u["Trim"]}',
                "Miles": int(u["Miles"]),
                "Book": int(u["Book"]),
                "Asking": int(u["Asking"]),
                "Cost": int(u.get("Cost", 0)) if not pd.isna(u.get("Cost", np.nan)) else 0,
                **s
            })
    if not rows:
        return None, pd.DataFrame()
    df = pd.DataFrame(rows).sort_values(["Score","Gross"], ascending=[False, False]).reset_index(drop=True)
    return df.iloc[0].to_dict(), df.head(topn), df

# ---------- Run ----------
if submitted:
    F = {
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

    best, top5, allpairs = pick_best(rules, inv, F, topn=5, gateway_bias=True)

    st.subheader("Recommendation")
    if best is None:
        st.warning("No lender fits with current inputs and inventory.")
    else:
        L, R = st.columns([1.1, 1])
        with L:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown(f"<div class='metric'>✅ {best['Lender']} — {best['Program']}</div>", unsafe_allow_html=True)
            st.write(f"**Unit**: {best['Unit']}")
            st.write(f"**Stock**: {best['Stock']}")  # exact stock number
            st.write(f"**Miles**: {best['Miles']:,}  |  **Book**: ${best['Book']:,}")
            st.write(f"**Sell @ Cap**: ${best['SellPrice']:,}  \n**AF**: ${int(best['AF']):,}  \n**Net Proceeds**: ${int(best['NetProceeds']):,}")
            st.write(f"**Term**: {best['Term']}  |  **Rate**: {best['RateAPR']}%  |  **Est. Pmt**: ${best['Payment']:,}")
            st.write(f"**Dealer Fee**: ${int(best['DealerFee'])} ({'Financed' if best['FeeFinanced'] else 'Deducted'})")
            st.write(f"**Front Gross (rough)**: ${best['Gross']:,}")
            st.write(f"**Why**: {best['Reason']}")
            st.write(f"**Proofs**: {best['Proofs']}")
            st.markdown('</div>', unsafe_allow_html=True)

        with R:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("<div class='metric'>Top 5 Unit × Lender</div>", unsafe_allow_html=True)
            show = top5[["Score","Stock","Unit","Lender","Program","SellPrice","AF","NetProceeds","Payment","Gross","Miles","Book","Asking"]]
            st.dataframe(show, use_container_width=True, height=260)
            st.markdown('</div>', unsafe_allow_html=True)

        # ---------- Gateway Select vs Select Plus side-by-side (if Gateway appears) ----------
        gmask = allpairs["Lender"].str.contains("gateway", case=False, na=False)
        if gmask.any():
            st.subheader("Gateway programs side-by-side")
            # For the exact recommended unit, show Select vs Select Plus if they exist
            unit_stock = best["Stock"]
            gthis = allpairs[gmask & (allpairs["Stock"]==unit_stock)]
            # pick top Gateway rows per program label
            select_row = gthis[gthis["Program"].str.contains("select", case=False, na=False) & ~gthis["Program"].str.contains("plus", case=False, na=False)]
            plus_row   = gthis[gthis["Program"].str.contains("select plus", case=False, na=False)]

            if len(select_row) or len(plus_row):
                cA, cB = st.columns(2)
                if len(select_row):
                    r = select_row.sort_values("Score", ascending=False).iloc[0]
                    with cA:
                        st.markdown("**Gateway — Select**")
                        st.markdown(f"- **Stock**: {r['Stock']}")
                        st.markdown(f"- **Sell @ Cap**: ${int(r['SellPrice']):,}")
                        st.markdown(f"- **AF / Net**: ${int(r['AF']):,} / ${int(r['NetProceeds']):,}")
                        st.markdown(f"- **Term/Rate**: {int(r['Term'])} @ {r['RateAPR']}%")
                        st.markdown(f"- **Payment**: ${r['Payment']:,}")
                        st.markdown(f"- **Dealer Fee**: ${int(r['DealerFee'])} ({'Financed' if r['FeeFinanced'] else 'Deducted'})")
                        st.markdown(f"- **Gross (rough)**: ${r['Gross']:,}")
                if len(plus_row):
                    r = plus_row.sort_values("Score", ascending=False).iloc[0]
                    with cB:
                        st.markdown("**Gateway — Select Plus**")
                        st.markdown(f"- **Stock**: {r['Stock']}")
                        st.markdown(f"- **Sell @ Cap**: ${int(r['SellPrice']):,}")
                        st.markdown(f"- **AF / Net**: ${int(r['AF']):,} / ${int(r['NetProceeds']):,}")
                        st.markdown(f"- **Term/Rate**: {int(r['Term'])} @ {r['RateAPR']}%")
                        st.markdown(f"- **Payment**: ${r['Payment']:,}")
                        st.markdown(f"- **Dealer Fee**: ${int(r['DealerFee'])} ({'Financed' if r['FeeFinanced'] else 'Deducted'})")
                        st.markdown(f"- **Gross (rough)**: ${r['Gross']:,}")

    st.subheader("Audit")
    st.json({
        "Applicant": {
            "Score": score, "Income/mo": income, "Gig?": gig_on, "GigIncome": gig_inc,
            "CoIncome": co_income, "Repos": repos, "JobMonths": F["job_months_total"],
            "DL": dl, "Down": down, "Trade": trade
        }
    }, expanded=False)
else:
    st.info("Enter applicant inputs and click **Evaluate**. The app will pick the best lender × unit, show Gateway Select vs Select Plus when relevant, and include dealer fees in gross/net.")
