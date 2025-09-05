import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

st.set_page_config(page_title="AI Desking Assist", layout="wide")
st.title("🚗 AI Desking Assist")

def monthly_payment(af, apr, term):
    r = (apr/100)/12
    if term <= 0: return 0.0
    if r <= 0: return af/term
    return (af*r)/(1-(1+r)**(-term))

def is_frame(stock, prefix="X"):
    return isinstance(stock,str) and stock.strip().upper().startswith(prefix)

THIS_YEAR = datetime.now().year

def build_pdf(info):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 750, "AI Desking Assist — Recap")
    c.setFont("Helvetica", 10)
    y = 730
    for k,v in info.items():
        c.drawString(50, y, f"{k}: {v}")
        y -= 15
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

tabs = st.tabs(["Desk a Deal", "Rate Sheets", "Settings"])

with tabs[2]:
    st.subheader("Settings")
    min_cost = st.number_input("Min cost", 0, 20000, 2000, 100)
    frame_prefix = st.text_input("Frame stock prefix", "X")
    st.session_state["SET"] = {"min_cost":min_cost, "frame_prefix":frame_prefix}

def normalize_rates(df):
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    return df

def normalize_inv(df):
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    return df

with tabs[1]:
    st.subheader("Upload Rate Sheets")
    rs = st.file_uploader("Rate sheet (CSV/XLSX)", type=["csv","xlsx"], key="rs")
    if rs:
        df = pd.read_csv(rs) if rs.name.endswith(".csv") else pd.read_excel(rs)
        df = normalize_rates(df)
        st.session_state["RATES"] = df
        st.success(f"Loaded {len(df)} lenders")
        st.dataframe(df)

with tabs[0]:
    st.subheader("Upload Inventory")
    inv_up = st.file_uploader("Inventory (CSV/XLSX)", type=["csv","xlsx"], key="inv")
    if inv_up:
        inv = pd.read_csv(inv_up) if inv_up.name.endswith(".csv") else pd.read_excel(inv_up)
        inv = normalize_inv(inv)
        st.session_state["INV"] = inv
        st.success(f"Loaded {len(inv)} vehicles")
        st.dataframe(inv.head())

    st.subheader("Customer Profile")
    score = st.number_input("Score",300,850,600)
    repos = st.number_input("Repos",0,10,0)
    down = st.number_input("Down",0,20000,1000)
    dl = st.selectbox("DL?",["Yes","No"])
    if st.button("Recommend"):
        rates = st.session_state.get("RATES")
        inv = st.session_state.get("INV")
        if rates is None or inv is None:
            st.error("Upload both rate sheets and inventory")
        else:
            st.success("Demo: picking first lender and first car")
            lender = rates.iloc[0].to_dict()
            car = inv.iloc[0].to_dict()
            recap = {"Score":score,"Repos":repos,"Down":down,"DL":dl,
                     "Lender":lender.get("name",""),"Car":f"{car.get('year','')} {car.get('make','')} {car.get('model','')}"}
            pdf = build_pdf(recap)
            st.download_button("Download Recap PDF", data=pdf, file_name="recap.pdf")
