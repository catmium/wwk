import os
import pandas as pd
import streamlit as st

_CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "cost_of_living.csv")

# Source of truth is ANNUAL (per-year) THB. The *_local_year + total_local_year
# columns carry the local-currency figures for the upcoming multi-currency
# feature (loaded and typed here; not consumed yet).
_NUMERIC_COLS = (
    "accom_thb_year", "accom_local_year",
    "food_thb_year", "food_local_year",
    "transport_thb_year", "transport_local_year",
    "utilities_thb_year", "utilities_local_year",
    "total_thb_year", "total_local_year",
)
_STRING_COLS = ("country", "city", "currency", "note", "source")


@st.cache_data(show_spinner=False)
def load_cost_of_living() -> pd.DataFrame:
    """โหลดข้อมูลค่าครองชีพรายปี (THB + สกุลท้องถิ่น) จาก CSV (แก้ไขได้ที่ data/cost_of_living.csv)"""
    if not os.path.exists(_CSV_PATH):
        return pd.DataFrame(columns=list(_STRING_COLS) + list(_NUMERIC_COLS))

    df = pd.read_csv(_CSV_PATH, encoding="utf-8-sig")  # utf-8-sig strips the BOM

    for col in _NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    for col in _STRING_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df
