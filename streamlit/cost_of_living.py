import os
import pandas as pd
import streamlit as st

_CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "cost_of_living.csv")

_NUMERIC_COLS = ("accom_thb", "food_thb", "transport_thb", "utilities_thb")
_STRING_COLS = ("country", "city", "note", "source")


@st.cache_data(show_spinner=False)
def load_cost_of_living() -> pd.DataFrame:
    """โหลดข้อมูลค่าครองชีพ + ค่าที่พักรายประเทศจาก CSV (แก้ไขได้ที่ data/cost_of_living.csv)"""
    if not os.path.exists(_CSV_PATH):
        return pd.DataFrame(columns=list(_STRING_COLS) + list(_NUMERIC_COLS))

    df = pd.read_csv(_CSV_PATH)

    for col in _NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    for col in _STRING_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df
