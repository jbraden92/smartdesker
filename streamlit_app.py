import io, re, json, math, base64
from typing import List, Tuple, Dict, Any

import streamlit as st
import pandas as pd

# Optional imports guarded for environments without OCR
try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from PIL import Image
    import pytesseract
except Exception:
    Image, pytesseract = None, None


# ──────────────────────────────────────────────────────────────────────────────
# UI/Theme
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="SmartDesk — Rehash", page_icon="🧩", layout="wide")
st.markdown(
    """
    <style>
      .card { border:1px solid rgba(250,250,250,.12); border-radius:12px; padding:14px 16px; background:rgba(250,250,250,.03); }
      .metric { font-weight:700; font-size:20px; margin-bottom:6px; }
      .em { opacity:.75 }
      .ok{color:#7DD97C;font-weight:600;}
      .warn{color:#F2C14E;font-weight:600;}
      .bad{color:#EF6C6C;font-weight:600;}
      .call { font-family: ui-monospace, Menlo, Consolas, monospace; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# Lender fees
#   - Gateway fixed per program (Select, Select Plus)
#   - Others: dynamic via FeeBands string (score bands)
# ──────────────────────────────────────────────────────────────────────────────
FEE_TABLE = {
    ("Gateway Financial Solutions", "Select"):      {"DealerFee": 395.0, "FeeFinanced": False},
    ("Gateway Financial Solutions", "Select Plus"): {"DealerFee":   0.0, "FeeFinanced": False},
}

def _parse_fee_bands(s: str):
    # "0-559:995;560-599:795;600-639:595;640+:0"
    if not s or (isinstance(s, float) and pd.isna(s)): return []
    out = []
    for part in str(s).split(";"):
        part = part.strip()
        if not part: continue
        m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*:\s*([0-9.]+)\s*$", part)
        if m:
            out.append((int(m.group(1)), int(m.group(2)), float(m.group(3))))
            continue
        m = re.match(r"^\s*(\d+)\+\s*:\s*([0-9.]+)\s*$", part)
        if m:
            out.append((int(m.group(1)), float("inf"), float(m.group(2))))
    out.sort(key=lambda t: t[0])
    return out

def _fee_from_bands(bands, score: float) -> float:
    for lo, hi, fee in bands:
        if lo <= score <= hi: return fee
    return 0.0

def resolve_fee(lender:str, program:str, row:pd.Series, features:dict):
    lk, pk = lender.strip(), (program or "").strip()
    if (lk, pk) in FEE_TABLE:
        f = FEE_TABLE[(lk, pk)]
        return float(f["DealerFee"]), bool(f["FeeFinanced"])
    bands = _parse_fee_bands(row.get("FeeBands",""))
    if bands:
        fee = _fee_from_bands(bands, float(features.get("credit", 0)))
        financed = bool(row.get("FeeFinancedDefault", False))
        return float(fee), financed
    return 0.0, False


# ──────────────────────────────────────────────────────────────────────────────
# Minimal rules table (replace/extend by uploading your sheet later)
#   Columns supported (case-insensitive): Lender, Program, MinScore, MaxScore,
#   MaxRepos, MinJobMonths, MinIncome, MinDown, AllowGig, AllowNoDL, MinMiles, MaxMiles,
#   LTVCap (e.g., 1.35 for 135%), FeeBands, FeeFinancedDefault
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_RULES = pd.DataFrame([
    # Gateway
    {"Lender":"Gateway Financial Solutions","Program":"Select","MinScore":560,"MaxScore":800,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2000,"MinDown":500,"AllowGig":True,"AllowNoDL":False,"MinMiles":0,"MaxMiles":150000,"LTVCap":1.35,"FeeBands":"","FeeFinancedDefault":False},
    {"Lender":"Gateway Financial Solutions","Program":"Select Plus","MinScore":620,"MaxScore":800,"MaxRepos":1,"MinJobMonths":12,"MinIncome":2500,"MinDown":1000,"AllowGig":True,"AllowNoDL":False,"MinMiles":0,"MaxMiles":150000,"LTVCap":1.35,"FeeBands":"","FeeFinancedDefault":False},
    # Westlake sample
    {"Lender":"Westlake Financial","Program":"Standard","MinScore":520,"MaxScore":800,"MaxRepos":3,"MinJobMonths":3,"MinIncome":1800,"MinDown":0,"AllowGig":True,"AllowNoDL":True,"MinMiles":0,"MaxMiles":180000,"LTVCap":1.25,"FeeBands":"0-559:995;560-599:795;600-639:595;640+:0","FeeFinancedDefault":True},
    # GLS sample
    {"Lender":"Global Lending Services","Program":"2","MinScore":540,"MaxScore":800,"MaxRepos":2,"MinJobMonths":6,"MinIncome":2200,"MinDown":500,"AllowGig":True,"AllowNoDL":False,"MinMiles":0,"MaxMiles":150000,"LTVCap":1.30,"FeeBands":"0-559:795;560-599:595;600-639:395;640+:0","FeeFinancedDefault":False},
    # Exeter sample
    {"Lender":"Exeter Finance","Program":"+Bronze","MinScore":520,"MaxScore":800,"MaxRepos":99,"MinJobMonths":3,"MinIncome":1800,"MinDown":0,"AllowGig":True,"AllowNoDL":True,"MinMiles":0,"MaxMiles":200000,"LTVCap":1.24,"FeeBands":"0-559:995;560-599:795;600-639:495;640+:0","FeeFinancedDefault":False},
])

if "rate_rules" not in st.session_state:
    st.session_state["rate_rules"] = DEFAULT_RULES.copy()


# ──────────────────────────────────────────────────────────────────────────────
# Inventory (HARD), filters: total cost >= 4000; exclude stock starting with W or T
# ──────────────────────────────────────────────────────────────────────────────
HARD_INVENTORY = pd.DataFrame([
    {"Stock":"A001","Year":2016,"Make":"Chevrolet","Model":"Equinox","Trim":"LT","Miles":93500,"Price":9990,"BookValue":9990},
    {"Stock":"A002","Year":2017,"Make":"Ford","Model":"Edge","Trim":"SEL","Miles":102300,"Price":10450,"BookValue":12200},
    {"Stock":"A007","Year":2018,"Make":"Hyundai","Model":"Elantra","Trim":"SEL","Miles":84500,"Price":10490,"BookValue":10990},
    {"Stock":"A008","Year":2019,"Make":"Nissan","Model":"Versa","Trim":"SV","Miles":61200,"Price":8990,"BookValue":11200},
    {"Stock":"X005","Year":2010,"Make":"Dodge","Model":"Journey","Trim":"SXT","Miles":111200,"Price":5390,"BookValue":10600},
])

def normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Stock"] = df["Stock"].astype(str)
    # total "cost" proxy—use Price as retail, BookValue acts as base for LTV
    df = df[df["Price"] >= 4000]
    df = df[~df["Stock"].str.upper().str.startswith(("W","T"))]
    return df.reset_index(drop=True)

if "inventory" not in st.session_state:
    st.session_state["inventory"] = normalize_inventory(HARD_INVENTORY)


# ──────────────────────────────────────────────────────────────────────────────
# Parsing helpers: deal recap text → features/lenders table
# Note: These regexes are intentionally lenient and easy to extend on real samples.
# ──────────────────────────────────────────────────────────────────────────────
def extract_text_from_upload(file) -> str:
    name = file.name.lower()
    if name.endswith(".pdf") and pdfplumber:
        try:
            with pdfplumber.open(io.BytesIO(file.read())) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
            return "\n".join(pages)
        except Exception:
            return ""
    # image OCR
    if Image and pytesseract:
        try:
            img = Image.open(file)
            return pytesseract.image_to_string(img)
        except Exception:
            return ""
    # No parser available
    return ""

NUM = r"([0-9][0-9,\.]*)"
def _to_float(x, default=0.0):
    try:
        if isinstance(x,(int,float)): return float(x)
        s = str(x).replace(",","").strip()
        if s == "": return default
        return float(s)
    except Exception:
        return default

def parse_recap_text(txt: str) -> Dict[str, Any]:
    out = {
        "credit": None, "income": None, "down": None, "term": None,
        "job_years": None, "job_months": None, "gig": False, "repos": None,
        "has_dl": "Yes",
        "lenders": pd.DataFrame(columns=["Lender","Decision","Tier","Term","Amount","BuyRate","Payment","Notes"]),
    }
    t = txt.lower()

    # crude score
    m = re.search(r"(score|cb|tu)\D{0,10}(\d{3})", t)
    if m: out["credit"] = int(m.group(2))

    # income per month
    m = re.search(r"(gross|mo\.?\s*income|monthly income)\D{0,10}"+NUM, t)
    if m: out["income"] = _to_float(m.group(2))

    # down
    m = re.search(r"(cash down|down\s*payment)\D{0,10}"+NUM, t)
    if m: out["down"] = _to_float(m.group(2))

    # term
    m = re.search(r"(term)\D{0,10}(\d{2,3})", t)
    if m: out["term"] = int(m.group(2))

    # job time (years / months)
    m = re.search(r"(emp time years|emp\.?\s*yrs|emp years)\D{0,10}(\d+)", t)
    if m: out["job_years"] = int(m.group(2))
    m = re.search(r"(emp time mos|emp\.?\s*months)\D{0,10}(\d+)", t)
    if m: out["job_months"] = int(m.group(2))

    # repos (approx)
    m = re.search(r"(repo[s]?|repossessions?)\D{0,10}(\d+)", t)
    if m: out["repos"] = int(m.group(2))

    # DL (presence of "valid dl" → yes; if "no dl" → No)
    if re.search(r"no\s+dl", t): out["has_dl"] = "No"

    # lender rows: try to pick common table fields
    rows = []
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    for ln in lines:
        # e.g. "Westlake Financial Approved Standard 54 10,339.00 24.9 321.03 ..."
        if re.search(r"(approved|declined|conditioned|booked|funded)", ln, re.I):
            lender = ln.split()[0:3]  # first few words
            lender = " ".join(lender)
            decision = re.search(r"(Approved|Declined|Conditioned|Booked|Funded)", ln, re.I)
            tier = re.search(r"Tier\s*:?[\s]*([A-Za-z0-9\+\-]+)", ln, re.I)
            term = re.search(r"\s(\d{2,3})\s", ln)
            amt = re.search(r"(\$|\s)"+NUM, ln)
            rate = re.search(r"(\d{1,2}\.?\d*)\s*%|\s(\d{1,2}\.?\d*)\s*$", ln)
            pmt = re.search(r"(\$"+NUM+r")\s*$", ln)

            rows.append({
                "Lender": lender.strip(),
                "Decision": decision.group(1).title() if decision else "",
                "Tier": tier.group(1) if tier else "",
                "Term": int(term.group(1)) if term else None,
                "Amount": _to_float(amt.group(2)) if amt else None,
                "BuyRate": _to_float((rate.group(1) or rate.group(2)) if rate else None),
                "Payment": _to_float(pmt.group(2)) if pmt else None,
                "Notes": ln
            })
    if rows:
        out["lenders"] = pd.DataFrame(rows).drop_duplicates(subset=["Lender","Decision"], keep="first")
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Decision logic
# ──────────────────────────────────────────────────────────────────────────────
def eligible(row, F):
    if not (row.MinScore <= F["credit"] <= row.MaxScore): return (False, "Score window")
    if F["repos"] is not None and F["repos"] > row.MaxRepos: return (False, "Too many repos")
    job_total = (F.get("job_years") or 0)*12 + (F.get("job_months") or 0)
    if job_total < row.MinJobMonths: return (False, "Job time")
    if F["income"] < row.MinIncome: return (False, "Income")
    if F["down"] < row.MinDown: return (False, "Down")
    if (not row.AllowNoDL) and F["has_dl"] == "No": return (False, "DL required")
    if F["gig"] and (not row.AllowGig): return (False, "No gig")
    return (True, "")

def score_fit(row, F, unit):
    # Basic fit score: closer to window mid score + LTV headroom + lower miles
    window_mid = (row.MinScore + row.MaxScore)/2
    s = 100 - abs(F["credit"] - window_mid)*0.5
    s += min(1000, F["down"])/40.0
    s += max(0, (row.MaxMiles - unit["Miles"]) / 5000.0)
    return s

def cap_price(book, ltv_cap):
    return round(book * float(ltv_cap), 0)

def build_calls(lender:str, program:str, cap:int):
    # Simple "call" text; Gateway shows Select vs Select Plus when applicable
    if lender == "Gateway Financial Solutions":
        left = f"Select: CAP @ ${cap:,} • Dealer Fee $395 (not financed)"
        right = f"Select Plus: CAP @ ${cap:,} • Dealer Fee $0"
        return left, right
    return (f"{program or 'Program'}: CAP @ ${cap:,}", "")

def recommend(rules: pd.DataFrame, F:dict, inv:pd.DataFrame, topn=5):
    rows = []
    for _, rr in rules.iterrows():
        ok, why = eligible(rr, F)
        if not ok: 
            rows.append({"Lender":rr.Lender,"Program":rr.Program,"Eligible":False,"Reason":why})
            continue
        for _, u in inv.iterrows():
            if not (rr.MinMiles <= u.Miles <= rr.MaxMiles):
                continue
            ltv_cap = rr.get("LTVCap", 1.25)
            cap = cap_price(u.BookValue, ltv_cap)
            dealer_fee, fee_financed = resolve_fee(rr.Lender, rr.Program, rr, F)
            price = min(u.Price, cap)  # set to cap if price higher
            headroom = cap - price
            s = score_fit(rr, F, u) + headroom/200.0
            rows.append({
                "Lender": rr.Lender,
                "Program": rr.Program,
                "Eligible": True,
                "Unit": f"{u.Year} {u.Make} {u.Model} {u.Trim}",
                "Stock": u.Stock,
                "Miles": int(u.Miles),
                "Book": int(u.BookValue),
                "Price": int(price),
                "Cap": int(cap),
                "Headroom": int(headroom),
                "DealerFee": float(dealer_fee),
                "FeeFinanced": fee_financed,
                "Score": round(s,1)
            })
    df = pd.DataFrame(rows)
    best = df[df["Eligible"]].sort_values(["Score","Headroom"], ascending=[False,False]).head(topn)
    return best, df


# ──────────────────────────────────────────────────────────────────────────────
# App UI
# ──────────────────────────────────────────────────────────────────────────────
tabs = st.tabs(["🔁 Rehash", "📦 Inventory", "📑 Rules"])
with tabs[0]:
    st.subheader("Rehash a deal recap")
    left, right = st.columns([1.2, 1])

    with left:
        up = st.file_uploader("Upload a **PDF** or **image** of the recap", type=["pdf","png","jpg","jpeg"])
        manual_txt = ""
        parsed = None
        if up is not None:
            raw_txt = extract_text_from_upload(up)
            if not raw_txt.strip():
                st.warning("Couldn’t read text. If this was an image and OCR isn’t available, paste the visible text below.")
                manual_txt = st.text_area("Paste recap text", height=220)
                raw_txt = manual_txt
            if raw_txt.strip():
                st.caption("Parsed text (first 1200 chars shown)")
                st.code(raw_txt[:1200] + ("..." if len(raw_txt)>1200 else ""), language="text")
                parsed = parse_recap_text(raw_txt)

        st.markdown("---")
        st.subheader("Applicant override (optional)")
        with st.form("rehash_form"):
            col1, col2, col3 = st.columns(3)
            def preset(k, d):
                return parsed.get(k) if (parsed and parsed.get(k) is not None) else d
            credit = col1.number_input("Credit Score", 300, 850, int(preset("credit", 620)))
            income = col2.number_input("Monthly Income ($)", 0, 20000, int(preset("income", 3000)))
            down   = col3.number_input("Down Payment ($)", 0, 20000, int(preset("down", 1000)))

            col4, col5, col6 = st.columns(3)
            job_years = col4.number_input("Job Time (years)", 0, 50, int(preset("job_years", 0)))
            job_months = col5.number_input("Job Time (months)", 0, 360, int(preset("job_months", 6)))
            has_dl = col6.selectbox("Driver's License?", ["Yes","No"], index=0 if preset("has_dl","Yes")=="Yes" else 1)

            include_gig = st.checkbox("Gig / DoorDash income?", value=False)
            repos = st.number_input("# of Repos (reported)", 0, 10, int(preset("repos", 0)))

            submitted = st.form_submit_button("Suggest next bank + car", type="primary")

        F = {
            "credit": credit, "income": income, "down": down, "gig": include_gig,
            "job_years": job_years, "job_months": job_months, "has_dl": has_dl,
            "repos": repos
        }

    with right:
        st.subheader("Lenders found in the recap (if any)")
        if parsed and isinstance(parsed.get("lenders"), pd.DataFrame) and len(parsed["lenders"]):
            st.dataframe(parsed["lenders"], use_container_width=True, height=240)
        else:
            st.caption("None detected yet.")

    if submitted:
        rules = st.session_state["rate_rules"].copy()
        inv = st.session_state["inventory"].copy()
        best, audit = recommend(rules, F, inv, topn=5)

        st.markdown("### Recommendation")
        if len(best)==0:
            st.error("No eligible lender/unit with current inputs.")
        else:
            pick = best.iloc[0]
            with st.container():
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown('<div class="metric">✅ Best path</div>', unsafe_allow_html=True)
                st.write(f"**{pick.Lender} — {pick.Program}**")
                st.write(f"**Unit:** {pick.Unit}  •  **Stock:** `{pick.Stock}`  •  **Miles:** {pick.Miles:,}")
                st.write(f"**Book:** ${pick.Book:,}  •  **Price (set to cap if higher):** ${pick.Price:,}  •  **Cap (LTV):** ${pick.Cap:,}")
                st.write(f"**Dealer Fee:** ${pick.DealerFee:,.0f}  •  **Financed?** {'Yes' if pick.FeeFinanced else 'No'}")
                # “Calls”
                left_call, right_call = build_calls(str(pick.Lender), str(pick.Program), int(pick.Cap))
                st.write("**Calls:**")
                if right_call:
                    c1, c2 = st.columns(2)
                    c1.markdown(f"<div class='call'>{left_call}</div>", unsafe_allow_html=True)
                    c2.markdown(f"<div class='call'>{right_call}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='call'>{left_call}</div>", unsafe_allow_html=True)
                st.write(f"**Why:** Score window + job/income/down fit; miles within program; LTV cap met.")
                st.write(f"**Proofs:** POI, POR, DL (add others per lender’s notes).")
                st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("### Top alternatives (bank + unit)")
            st.dataframe(
                best[["Lender","Program","Unit","Stock","Price","Book","Cap","DealerFee","Score"]]
                .rename(columns={"Cap":"Cap(LTV)"}),
                use_container_width=True, height=220
            )

            with st.expander("Audit (all pairs)"):
                st.dataframe(audit, use_container_width=True, height=320)


with tabs[1]:
    st.subheader("Inventory")
    st.dataframe(st.session_state["inventory"], use_container_width=True, height=320)
    st.caption("Filters: price ≥ $4,000; exclude stock starting with W or T.")

with tabs[2]:
    st.subheader("Current rules (first 30 rows)")
    st.dataframe(st.session_state["rate_rules"].head(30), use_container_width=True, height=360)
    st.caption("Upload an updated CSV/XLSX next iteration to override these.")
