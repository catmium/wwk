import os
import pandas as pd
import streamlit as st

_CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "financial_aid.csv")

_COLS = ("University", "Scholarship", "Scholarship_Type",
         "Conditions", "Scholarship_Value", "Source")

# Thai display labels (English CSV headers → table headers). Shared by page 1
# (matched table) and page 4 (full reference table).
AID_LABELS = {
    "University": "สถาบัน",
    "Scholarship": "ทุนการศึกษา",
    "Scholarship_Type": "ประเภททุน",
    "Conditions": "เงื่อนไข",
    "Scholarship_Value": "มูลค่าทุน",
    "Source": "ที่มา",
}


@st.cache_data(show_spinner=False)
def load_financial_aid() -> pd.DataFrame:
    """โหลดข้อมูลทุนการศึกษา/ความช่วยเหลือทางการเงินจาก CSV (แก้ไขได้ที่ data/financial_aid.csv).

    คอลัมน์ University ตรงกับ school_name ใน school_fees แบบ exact match —
    ใช้จับคู่กับแผนการศึกษาในหน้า 1.
    """
    if not os.path.exists(_CSV_PATH):
        return pd.DataFrame(columns=list(_COLS))

    df = pd.read_csv(_CSV_PATH, encoding="utf-8-sig")  # utf-8-sig strips the BOM
    for col in _COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df
