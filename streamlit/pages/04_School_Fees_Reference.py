import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd

from strings import S, edu_level_label, school_type_label, country_label
from school_fees import load_school_fees
from state import require_login

require_login()

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title=S("p4", "page_title"),
    page_icon="📚",
    layout="wide",
)

# ============================================================
# LOAD DATA (CSV-backed)
# ============================================================
# Columns (internal keys):
#   school_name, level, country, school_type,
#   age_min, age_max, annual_cost,
#   original_amount, original_currency,
#   notes, source_year, ref_url

df_raw = load_school_fees()

# Build a display-friendly DataFrame: translate internal keys to Thai labels
# but keep the underlying internal columns for filtering/sorting.
df_all = df_raw.copy()
if not df_all.empty:
    df_all["ระดับ"] = df_all["level"].apply(edu_level_label)
    df_all["ประเภท"] = df_all["school_type"].apply(school_type_label)
    df_all["ประเทศ"] = df_all["country"].apply(country_label)
    df_all["ชื่อสถาบัน"] = df_all["school_name"]
    df_all["ค่าเล่าเรียน/ปี (฿)"] = pd.to_numeric(df_all["annual_cost"], errors="coerce")
    df_all["ช่วงอายุ"] = df_all.apply(
        lambda r: f"{int(r['age_min'])}–{int(r['age_max'])} ปี"
        if pd.notna(r["age_min"]) and pd.notna(r["age_max"]) else "",
        axis=1,
    )
    df_all["ต้นฉบับ"] = df_all.apply(
        lambda r: f"{r['original_amount']:,.0f} {r['original_currency']}"
        if pd.notna(r["original_amount"]) else "",
        axis=1,
    )
    df_all["หมายเหตุ"] = df_all["notes"].fillna("").astype(str)
    df_all["ปีอ้างอิง"] = pd.to_numeric(df_all["source_year"], errors="coerce").astype("Int64")
    df_all["เว็บไซต์"] = df_all["ref_url"].fillna("").astype(str)

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("## 📚 School Fees Reference")
    if st.button(S("p4", "back_btn"), width="stretch"):
        st.switch_page("01_User_Information.py")

# ============================================================
# PAGE HEADER
# ============================================================
st.title(S("p4", "title"))
st.caption(S("p4", "caption"))
st.warning(S("p4", "disclaimer"))
st.markdown("---")

if df_raw.empty:
    st.error("School fees reference CSV is missing or empty (data/school_fees.csv).")
    st.stop()

# ============================================================
# FILTERS
# ============================================================
st.subheader(S("p4", "filter_header"))

f_col1, f_col2, f_col3, f_col4 = st.columns([2, 1, 1, 1])

with f_col1:
    search_text = st.text_input(
        S("p4", "filter_search"),
        placeholder="เช่น ISB, Harrow, จุฬา, MIT...",
        key="ref_search",
    )

with f_col2:
    country_opts = [S("p4", "filter_all")] + sorted(df_all["ประเทศ"].unique().tolist())
    selected_country = st.selectbox(S("p4", "filter_country"), country_opts, key="ref_country")

with f_col3:
    type_opts = [S("p4", "filter_all")] + sorted(df_all["ประเภท"].unique().tolist())
    selected_type = st.selectbox(S("p4", "filter_type"), type_opts, key="ref_type")

with f_col4:
    level_order = ["อนุบาล", "ประถมศึกษา", "มัธยมต้น", "มัธยมปลาย", "ปริญญาตรี", "ปริญญาโท", "ปริญญาเอก"]
    available_levels = [l for l in level_order if l in df_all["ระดับ"].unique()]
    level_opts = [S("p4", "filter_all")] + available_levels
    selected_level = st.selectbox(S("p4", "filter_level"), level_opts, key="ref_level")

# ============================================================
# FILTERING
# ============================================================
df_filtered = df_all.copy()

if search_text.strip():
    mask = df_filtered["ชื่อสถาบัน"].str.contains(search_text.strip(), case=False, na=False)
    df_filtered = df_filtered[mask]

if selected_country != S("p4", "filter_all"):
    df_filtered = df_filtered[df_filtered["ประเทศ"] == selected_country]

if selected_type != S("p4", "filter_all"):
    df_filtered = df_filtered[df_filtered["ประเภท"] == selected_type]

if selected_level != S("p4", "filter_all"):
    df_filtered = df_filtered[df_filtered["ระดับ"] == selected_level]

# Sort: level order → country → name
level_order_map = {l: i for i, l in enumerate(level_order)}
df_filtered = df_filtered.copy()
df_filtered["_level_sort"] = df_filtered["ระดับ"].map(level_order_map).fillna(99)
df_filtered = df_filtered.sort_values(["_level_sort", "ประเทศ", "ชื่อสถาบัน"]).drop(columns=["_level_sort"])

# ============================================================
# RESULTS
# ============================================================
st.markdown(f"**{S('p4', 'result_count', n=len(df_filtered))}**")

if df_filtered.empty:
    st.info(S("p4", "no_results"))
else:
    display_cols = [
        "ชื่อสถาบัน", "ประเทศ", "ประเภท", "ระดับ",
        "ช่วงอายุ", "ค่าเล่าเรียน/ปี (฿)", "ต้นฉบับ",
        "หมายเหตุ", "ปีอ้างอิง", "เว็บไซต์",
    ]

    st.dataframe(
        df_filtered[display_cols].reset_index(drop=True),
        width="stretch",
        hide_index=True,
        column_config={
            "ค่าเล่าเรียน/ปี (฿)": st.column_config.NumberColumn(
                "ค่าเล่าเรียน/ปี (฿)",
                format="฿%,.0f",
            ),
            "ปีอ้างอิง": st.column_config.NumberColumn(
                "ปีอ้างอิง",
                format="%d",
            ),
            "เว็บไซต์": st.column_config.LinkColumn(
                "เว็บไซต์",
                display_text="🔗 เปิด",
            ),
        },
    )

    csv_cols = [c for c in display_cols if c != "เว็บไซต์"] + ["เว็บไซต์"]
    csv_bytes = df_filtered[csv_cols].to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=S("p4", "dl_btn"),
        data=csv_bytes,
        file_name="school_fees_reference.csv",
        mime="text/csv",
    )
