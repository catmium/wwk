import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd

from strings import S, edu_level_label, school_type_label, country_label
from school_fees import load_school_fees
from cost_of_living import load_cost_of_living
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
#   school_name, level, country, city, school_type,
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
    df_all["เมือง"] = df_all["city"].fillna("").astype(str) if "city" in df_all.columns else ""
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

# Row 1: education level + school type
level_order = ["อนุบาล", "ประถมศึกษา", "มัธยมต้น", "มัธยมปลาย", "ปริญญาตรี", "ปริญญาโท", "ปริญญาเอก"]
f_r1c1, f_r1c2 = st.columns(2)

with f_r1c1:
    available_levels = [l for l in level_order if l in df_all["ระดับ"].unique()]
    level_opts = [S("p4", "filter_all")] + available_levels
    selected_level = st.selectbox(S("p4", "filter_level"), level_opts, key="ref_level")

with f_r1c2:
    type_opts = [S("p4", "filter_all")] + sorted(df_all["ประเภท"].unique().tolist())
    selected_type = st.selectbox(S("p4", "filter_type"), type_opts, key="ref_type")

# Row 2: country + city (cascade) + school name search
f_r2c1, f_r2c2, f_r2c3 = st.columns([1, 1, 2])

with f_r2c1:
    country_opts = [S("p4", "filter_all")] + sorted(df_all["ประเทศ"].unique().tolist())
    selected_country = st.selectbox(S("p4", "filter_country"), country_opts, key="ref_country")

with f_r2c2:
    # Cascade: only show cities for the selected country (or all cities if no country filter)
    if selected_country != S("p4", "filter_all"):
        _city_pool = df_all.loc[df_all["ประเทศ"] == selected_country, "เมือง"]
    else:
        _city_pool = df_all["เมือง"]
    _city_pool = [c for c in _city_pool.dropna().unique().tolist() if c]
    _city_pool.sort()
    city_opts = [S("p4", "filter_all")] + _city_pool
    selected_city = st.selectbox("เมือง", city_opts, key="ref_city")

with f_r2c3:
    search_text = st.text_input(
        "ชื่อสถาบัน",
        placeholder="เช่น ISB, Harrow, จุฬา, MIT, Shrewsbury...",
        key="ref_search",
    )

# ============================================================
# FILTERING
# ============================================================
df_filtered = df_all.copy()

if search_text.strip():
    _q = search_text.strip()
    df_filtered = df_filtered[
        df_filtered["ชื่อสถาบัน"].str.contains(_q, case=False, na=False)
    ]

if selected_country != S("p4", "filter_all"):
    df_filtered = df_filtered[df_filtered["ประเทศ"] == selected_country]

if selected_city != S("p4", "filter_all"):
    df_filtered = df_filtered[df_filtered["เมือง"] == selected_city]

if selected_type != S("p4", "filter_all"):
    df_filtered = df_filtered[df_filtered["ประเภท"] == selected_type]

if selected_level != S("p4", "filter_all"):
    df_filtered = df_filtered[df_filtered["ระดับ"] == selected_level]

# Sort: level order → country → city → name
level_order_map = {l: i for i, l in enumerate(level_order)}
df_filtered = df_filtered.copy()
df_filtered["_level_sort"] = df_filtered["ระดับ"].map(level_order_map).fillna(99)
df_filtered = df_filtered.sort_values(
    ["_level_sort", "ประเทศ", "เมือง", "ชื่อสถาบัน"]
).drop(columns=["_level_sort"])

# ============================================================
# RESULTS
# ============================================================
st.markdown(f"**{S('p4', 'result_count', n=len(df_filtered))}**")

if df_filtered.empty:
    st.info(S("p4", "no_results"))
else:
    display_cols = [
        "ชื่อสถาบัน", "ประเทศ", "เมือง", "ประเภท", "ระดับ",
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

# ============================================================
# COST OF LIVING + ACCOMMODATION REFERENCE (per city)
# ============================================================
# ประมาณการค่าใช้จ่ายต่อเดือนสำหรับนักเรียน/นักศึกษาแต่ละเมือง
# (ตัวเลขโดยประมาณปี 2024 — link source ในคอลัมน์ "ที่มา" สำหรับเช็คเรทล่าสุด)
st.markdown("---")
st.subheader("🏠 ค่าครองชีพและค่าที่พักโดยประมาณ (ต่อเดือน)")
st.caption(
    "ประมาณการค่าใช้จ่ายต่อเดือนสำหรับนักเรียน/นักศึกษาในแต่ละเมือง "
    "เพื่อใช้วางแผนงบประมาณการศึกษาที่ครอบคลุมมากกว่าค่าเล่าเรียน — "
    "ตัวเลขอ้างอิง Numbeo (cost-of-living index) และอาจแตกต่างกันตามรูปแบบที่พักและไลฟ์สไตล์"
)

df_living_raw = load_cost_of_living()

# ---------- Cost of living filters: country, city, search ----------
_col_countries = sorted(df_living_raw["country"].dropna().unique().tolist())
_clf_col1, _clf_col2, _clf_col3 = st.columns([1, 1, 2])

with _clf_col1:
    _col_country_opts = [S("p4", "filter_all")] + [country_label(c) for c in _col_countries]
    selected_col_country = st.selectbox(
        "ประเทศ",
        _col_country_opts,
        key="col_country_filter",
    )

# Resolve country code (used by both city cascade and the filter step)
if selected_col_country != S("p4", "filter_all"):
    _selected_col_country_code = next(
        (c for c in _col_countries if country_label(c) == selected_col_country),
        None,
    )
else:
    _selected_col_country_code = None

with _clf_col2:
    # Cascade: only show cities for the selected country (or all if no country filter)
    if _selected_col_country_code:
        _col_city_pool = df_living_raw.loc[
            df_living_raw["country"] == _selected_col_country_code, "city"
        ]
    else:
        _col_city_pool = df_living_raw["city"]
    _col_city_pool = [c for c in _col_city_pool.dropna().unique().tolist() if c]
    _col_city_pool.sort()
    _col_city_opts = [S("p4", "filter_all")] + _col_city_pool
    selected_col_city = st.selectbox(
        "เมือง",
        _col_city_opts,
        key="col_city_filter",
    )

with _clf_col3:
    _col_search = st.text_input(
        "ค้นหาเมือง / โน้ต",
        placeholder="เช่น Cambridge, Boston, เชียงใหม่, MIT, จุฬา...",
        key="col_search",
    )

# ---------- Apply filters (no sort — preserve CSV ordering) ----------
df_living = df_living_raw.copy()
if not df_living.empty:
    df_living["_living"] = (
        df_living["food_thb"] + df_living["transport_thb"] + df_living["utilities_thb"]
    )
    df_living["_total_month"] = df_living["accom_thb"] + df_living["_living"]
    df_living["_total_year"] = df_living["_total_month"] * 12

    if _selected_col_country_code:
        df_living = df_living[df_living["country"] == _selected_col_country_code]

    if selected_col_city != S("p4", "filter_all"):
        df_living = df_living[df_living["city"] == selected_col_city]

    if _col_search.strip():
        _q = _col_search.strip()
        df_living = df_living[
            df_living["city"].str.contains(_q, case=False, na=False)
            | df_living["note"].str.contains(_q, case=False, na=False)
        ]

# ---------- Build display DataFrame ----------
_col_data = []
for _, r in df_living.iterrows():
    _col_data.append({
        "ประเทศ": country_label(r["country"]),
        "เมือง": r["city"],
        "ค่าที่พัก/เดือน (฿)": int(r["accom_thb"]),
        "ค่าอาหาร/เดือน (฿)": int(r["food_thb"]),
        "ค่าเดินทาง/เดือน (฿)": int(r["transport_thb"]),
        "ค่าน้ำ-ไฟ-เน็ต/เดือน (฿)": int(r["utilities_thb"]),
        "รวม/เดือน (฿)": int(r["_total_month"]),
        "รวม/ปี (฿)": int(r["_total_year"]),
        "หมายเหตุ": r.get("note", ""),
        "ที่มา": r.get("source", ""),
    })

df_living_display = pd.DataFrame(_col_data)

st.markdown(f"**พบ {len(df_living_display)} เมือง**")

if df_living_display.empty:
    st.info("ไม่พบข้อมูลค่าครองชีพตรงเงื่อนไขที่เลือก")
else:
    st.dataframe(
        df_living_display,
        width="stretch",
        hide_index=True,
        column_config={
            "ค่าที่พัก/เดือน (฿)": st.column_config.NumberColumn(
                "ค่าที่พัก/เดือน (฿)",
                format="฿%,.0f",
                help="หอพักนักศึกษา / shared apartment / homestay",
            ),
            "ค่าอาหาร/เดือน (฿)": st.column_config.NumberColumn(
                "ค่าอาหาร/เดือน (฿)",
                format="฿%,.0f",
            ),
            "ค่าเดินทาง/เดือน (฿)": st.column_config.NumberColumn(
                "ค่าเดินทาง/เดือน (฿)",
                format="฿%,.0f",
                help="ค่ารถสาธารณะ / student pass",
            ),
            "ค่าน้ำ-ไฟ-เน็ต/เดือน (฿)": st.column_config.NumberColumn(
                "ค่าน้ำ-ไฟ-เน็ต/เดือน (฿)",
                format="฿%,.0f",
            ),
            "รวม/เดือน (฿)": st.column_config.NumberColumn(
                "รวม/เดือน (฿)",
                format="฿%,.0f",
                help="รวมค่าที่พัก + ค่าครองชีพต่อเดือน",
            ),
            "รวม/ปี (฿)": st.column_config.NumberColumn(
                "รวม/ปี (฿)",
                format="฿%,.0f",
                help="ประมาณการรวมต่อปี (รวม/เดือน × 12) — ยังไม่รวมค่าเล่าเรียน",
            ),
            "ที่มา": st.column_config.LinkColumn(
                "ที่มา",
                display_text="🔗 ดู",
                help="Numbeo cost-of-living reference",
            ),
        },
    )

    # Download
    _col_csv = df_living_display.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="⬇ ดาวน์โหลด CSV (ค่าครองชีพ)",
        data=_col_csv,
        file_name="cost_of_living_reference.csv",
        mime="text/csv",
    )

st.caption(
    "⚠️ ตัวเลขเป็นการประมาณการสำหรับนักศึกษา/นักเรียนที่อยู่หอพักหรือเช่าห้องร่วม "
    "อ้างอิงค่าครองชีพในเมืองมหาวิทยาลัยช่วงปี 2024 (Numbeo) "
    "ค่าใช้จ่ายจริงอาจสูง/ต่ำกว่านี้ขึ้นอยู่กับเมือง ประเภทที่พัก และไลฟ์สไตล์ — "
    "ไม่รวมค่าประกันสุขภาพ ค่าวีซ่า ค่าตั๋วเครื่องบินกลับบ้าน และค่าใช้จ่ายส่วนตัวอื่นๆ"
)
