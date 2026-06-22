"""
Per-section render functions for Page 1 (01_User_Information.py).

Each function renders one logical section of the page and returns whatever
downstream state the orchestrator needs to build the simulation inputs.
All widget keys, draft field names, and session_state interactions are
preserved exactly as they were when this code lived in 01_User_Information.py.
"""
import streamlit as st
import pandas as pd
from datetime import date

from strings import (
    S, SC,
    edu_level_label, school_type_label, country_label,
    expense_type_label, trigger_label, inflation_label,
    gender_label, compound_mode_label, expense_timing_label,
)
from simulation_core import (
    Child,
    EducationPlan,
    ExtraExpense,
    ParentExpense,
    AnnualTopup,
    SavingPlan,
    Assumptions,
    simulate_education_plan,
)
from database import (
    save_draft as db_save_draft,
    load_latest_draft as db_load_latest_draft,
    has_previous_data as db_has_previous_data,
    get_latest_meta as db_get_latest_meta,
)
from school_fees import schools_for_level, lookup as lookup_school_fee, CUSTOM_SCHOOL_SENTINEL
from cost_of_living import load_cost_of_living
from financial_aid import load_financial_aid, AID_LABELS
from fx import load_fx_rates, to_thb


def _ccy_options():
    """Currency dropdown options, THB first then the rest (from fx_rate.csv)."""
    return ["THB"] + sorted(c for c in load_fx_rates() if c != "THB")

from state import (
    _none_if_blank, _to_optional_int,
    draft_get, draft_set,
    persist_all_widget_buffers, switch_page_with_persist,
    apply_loaded_draft_to_state,
    reset_draft_for_new_customer, draft_owner_error,
)
from widgets import (
    p_text_input, p_number_input, p_selectbox,
    p_date_input, p_percent_input,
)
from presets import (
    EDU_LEVEL_OPTIONS, EDU_LEVEL_LABELS,
    SCHOOL_TYPE_OPTIONS, COUNTRY_OPTIONS,
    EDU_DEFAULT_PRESETS,
    get_default_level_for_row,
    _on_edu_level_change, _on_school_select,
    CUST_ID_MAX_LEN,
    normalize_cust_id, cust_id_validation_error,
    collect_input_warnings,
    collect_input_errors,
)


# ============================================================
# UI UTILITIES
# ============================================================
# Year-range constants used by all "year" inputs (parent extras, top-ups,
# child extras, etc). ปีต่ำสุดผูกกับปีปัจจุบัน (กันคนกรอกปีย้อนหลังมั่ว);
# ปีสูงสุดเผื่อ horizon ระดับมหาวิทยาลัย/ปริญญาเอกของลูกแรกเกิด
YEAR_MIN_DEFAULT = date.today().year
YEAR_MAX_DEFAULT = 2100

# Caps for repeatable sections (children / edu / extras / parent / topups)
MAX_N_CHILDREN = 10
MIN_N_CHILDREN = 1          # ลูก ≥ 1 คน — น้อยกว่านี้ไม่มีอะไรให้ simulate
MAX_N_EDU = 20
MAX_N_EXTRA = 20
MAX_N_PARENT_EXPENSES = 20
MAX_N_TOPUPS = 20

# Cap ทุก rate input (inflation / return / growth) ที่ 20% — เกินกว่านี้
# มักหมายถึงผู้ใช้กรอกผิดหน่วย (%ต่อปี vs ต่อเดือน)
RATE_MAX_PCT = 20.0


def _btn_spacer(margin_top_px: int = 28):
    """Vertical spacer to push a button's top down so it aligns with the
    baseline of a `st.metric` in a neighbouring column. ใช้แทน <div> hack
    ที่กระจัดกระจายไปทั้งไฟล์เดิม."""
    st.markdown(
        f"<div style='margin-top:{margin_top_px}px'></div>",
        unsafe_allow_html=True,
    )


# ============================================================
# AUTO-FILL HELPER: build extra-expense rows from education plans
# ============================================================
# Marker prefix in the `note` field that identifies an auto-generated row.
# ใช้สำหรับลบของเก่าทิ้งตอนกด Auto-fill ซ้ำ (replace mode) แต่ไม่แตะ row
# ที่ user กรอกเอง
AUTO_EXTRA_MARKER = "[AUTO]"

# Mapping: cost-of-living LOCAL-currency column → (Thai display name).
# Auto-fill stores the local amount + the city's currency; THB is derived at
# sim time via fx (consistent with education-plan auto-derive).
_COL_COMPONENTS = [
    ("accom_local_year",     "ค่าที่พัก"),
    ("food_local_year",      "ค่าอาหาร"),
    ("transport_local_year", "ค่าเดินทาง"),
    ("utilities_local_year", "ค่าน้ำ-ไฟ-เน็ต"),
]


# Education levels that "count" for Thai-domestic auto-fill: extras only
# kick in for higher-ed (when the student typically moves out / lives near
# uni). For lower levels in TH, students live with parents → no extras.
# For NON-TH plans every level contributes (student is abroad regardless).
_TH_AUTO_FILL_LEVELS = {"bachelor", "master", "doctor"}


def _auto_extras_from_edu_plans(edu_plans, col_df):
    """Build auto-generated extra-expense rows from a child's education plans.

    Filtering:
      - TH plans: only `bachelor` / `master` / `doctor` contribute (student
        is assumed to live with parents during lower levels in Thailand).
      - Non-TH plans: every level contributes (student is abroad regardless).

    City resolution:
      - Looks up `school_fees` by (level, school_name) to get the school's
        city, then keys cost-of-living rows by (country, city).
      - Falls back to the first available city for that country when the
        school is custom or not found (with a warning).

    Groups remaining plans by (country, city), merges the age range across
    plans (min start_age → max end_age), then emits 4 recurring rows per
    (country, city) key (accommodation / food / transport / utilities)
    using the annual values from cost_of_living.csv.

    Returns (rows, warnings):
        rows: list of dicts ready to write back to draft state.
        warnings: list of Thai-language warning strings.
    """
    rows = []
    warnings = []

    if not edu_plans:
        return rows, warnings

    # Index cost-of-living CSV by (country, city) for exact lookup, and
    # keep "first city seen" per country as a fallback.
    cost_by_city: dict = {}
    first_city_for_country: dict = {}
    if col_df is not None and not col_df.empty:
        for r in col_df.to_dict("records"):
            _c = str(r.get("country", "")).strip()
            _city = str(r.get("city", "")).strip()
            if not _c:
                continue
            cost_by_city[(_c, _city)] = r
            if _c not in first_city_for_country:
                first_city_for_country[_c] = _city

    # Filter + resolve city + group by (country, city)
    by_country_city: dict = {}
    for plan in edu_plans:
        country = (plan.country or "").strip()
        level = (plan.level or "").strip()
        if not country:
            continue
        # TH rule: skip non-higher-ed in Thailand
        if country == "TH" and level not in _TH_AUTO_FILL_LEVELS:
            continue

        # Try resolving the school's city via school_fees lookup
        city = None
        if plan.school_name and plan.school_name != CUSTOM_SCHOOL_SENTINEL:
            try:
                school_row = lookup_school_fee(level, plan.school_name)
                if school_row:
                    _city_raw = str(school_row.get("city", "") or "").strip()
                    if _city_raw:
                        city = _city_raw
            except Exception:
                city = None

        if not city:
            # Fallback: first known city for that country
            city = first_city_for_country.get(country)
            if city:
                warnings.append(
                    f"ℹ️ {edu_level_label(level)} ({country_label(country)}): "
                    f"ไม่พบเมืองของโรงเรียน — ใช้ค่าครองชีพของ {city} เป็นค่าเริ่มต้น"
                )
            else:
                warnings.append(
                    f"⚠️ ไม่พบข้อมูลค่าครองชีพของ {country_label(country)} ใน CSV — ข้ามไป"
                )
                continue

        # Track which schools contributed to this (country, city) group so
        # the auto-generated note can list them (e.g. when 2 schools share
        # the same city → "[AUTO] US - Cambridge, MA - MIT / Harvard").
        plan_school_name = (plan.school_name or "").strip()

        key = (country, city)
        if key not in by_country_city:
            by_country_city[key] = {
                "start_age": int(plan.start_age),
                "end_age": int(plan.end_age),
                "schools": [],
            }
        else:
            by_country_city[key]["start_age"] = min(
                by_country_city[key]["start_age"], int(plan.start_age)
            )
            by_country_city[key]["end_age"] = max(
                by_country_city[key]["end_age"], int(plan.end_age)
            )
        if plan_school_name and plan_school_name != CUSTOM_SCHOOL_SENTINEL:
            if plan_school_name not in by_country_city[key]["schools"]:
                by_country_city[key]["schools"].append(plan_school_name)

    if not by_country_city:
        return rows, warnings

    for (country, city), group in by_country_city.items():
        csv_row = cost_by_city.get((country, city))
        if csv_row is None:
            warnings.append(
                f"⚠️ ไม่พบข้อมูลค่าครองชีพของ {country_label(country)} เมือง {city} — ข้ามไป"
            )
            continue

        country_name = country_label(country)
        start_age = group["start_age"]
        end_age = group["end_age"]
        schools_str = " / ".join(group["schools"]) if group["schools"] else "-"

        # Pull the ORIGINAL local amount + the city's currency; THB is derived
        # at sim time via fx (re-prices if fx_rate.csv changes).
        _ccy = str(csv_row.get("currency", "THB")).strip() or "THB"

        for col_key, kind_label in _COL_COMPONENTS:
            local_amt = float(int(csv_row.get(col_key, 0) or 0))
            if local_amt <= 0:
                continue
            rows.append({
                "name": f"{kind_label} - {country_name} - {city}",
                "amount": local_amt,
                "currency": _ccy,
                "type": "recurring",
                "trigger_mode": "by_child_age",
                "inflation_type": "general",
                "year": date.today().year,
                "end_year": date.today().year + 2,
                "child_age": 10,
                "start_year": date.today().year,
                "start_age": int(start_age),
                "end_age": int(end_age),
                "note": f"{AUTO_EXTRA_MARKER} {country_name} - {city} - {schools_str}",
            })

    return rows, warnings


# Field names used inside each child.{i}.extra.{j}.* sub-record. Centralised
# so _delete_indexed_row และ _apply_auto_extras_to_draft อ้างถึงชุดเดียวกัน
_EXTRA_FIELDS = (
    "name", "amount", "currency", "type", "trigger_mode", "inflation_type",
    "year", "end_year", "child_age", "start_year",
    "start_age", "end_age", "note",
)

# Field tuples สำหรับ list อื่น ๆ ที่ใช้กับ _delete_indexed_row
_EDU_FIELDS = (
    "level", "country", "school_type", "school_name",
    "start_age", "end_age", "annual_cost", "annual_currency",
    "show_advanced", "cost_growth_rate", "cost_basis_year", "note",
)
_PARENT_FIELDS = (
    "name", "amount", "type", "year", "end_year", "inflation_type", "note",
)
_TOPUP_FIELDS = (
    "year", "amount", "note", "mode", "year_start", "year_end",
)


def _delete_indexed_row(
    draft,
    key_prefix: str,
    fields,
    del_idx: int,
    n_rows: int,
    count_field: str,
    extra_widget_keys=None,
):
    """Generic shift-and-delete สำหรับ list ที่ index ด้วย key_prefix.{idx}.{field}.

    - shift row k+1 → k สำหรับ k จาก del_idx ถึง n_rows-2 (draft + session_state)
    - ลบ orphan keys ของแถวสุดท้ายทั้ง draft + session_state
    - extra_widget_keys(idx) → iterable ของ widget keys เพิ่มเติม (เช่น
      sb_school_{i}_{j} ที่ใช้ key prefix ต่างจาก draft) — กันค่าตกค้าง
    - decrement count_field
    """
    # Shift values down
    for k in range(del_idx, n_rows - 1):
        for f in fields:
            src_key = f"{key_prefix}.{k+1}.{f}"
            dst_key = f"{key_prefix}.{k}.{f}"
            if src_key in draft:
                draft[dst_key] = draft[src_key]

    # ลบ orphan keys ของแถวสุดท้ายทั้ง draft และ widget state
    for f in fields:
        orphan_key = f"{key_prefix}.{n_rows-1}.{f}"
        if orphan_key in draft:
            del draft[orphan_key]
        if orphan_key in st.session_state:
            del st.session_state[orphan_key]

    # ล้าง widget state ของแถวที่ถูก shift เพื่อให้ widget อ่านค่าใหม่จาก draft
    for k in range(del_idx, n_rows - 1):
        for f in fields:
            wkey = f"{key_prefix}.{k}.{f}"
            if wkey in st.session_state:
                del st.session_state[wkey]

    # Extra widget keys (key ที่ prefix ต่างจาก draft เช่น sb_school_{i}_{j})
    if extra_widget_keys is not None:
        for ek in extra_widget_keys(n_rows - 1):
            if ek in st.session_state:
                del st.session_state[ek]
        for k in range(del_idx, n_rows - 1):
            for ek in extra_widget_keys(k):
                if ek in st.session_state:
                    del st.session_state[ek]

    draft_set(count_field, n_rows - 1)


def _delete_all_rows(
    draft,
    key_prefix: str,
    fields,
    n_rows: int,
    count_field: str,
    extra_widget_keys=None,
):
    """ลบทุก row ใน list ที่ index ด้วย key_prefix.{idx}.{field}.

    เคลียร์ทั้ง draft และ session_state ของทุก index ตั้งแต่ 0 ถึง n_rows-1
    รวมถึง extra widget keys (เช่น sb_school_{i}_{j}) แล้ว reset count_field
    เป็น 0
    """
    for k in range(n_rows):
        for f in fields:
            key = f"{key_prefix}.{k}.{f}"
            if key in draft:
                del draft[key]
            if key in st.session_state:
                del st.session_state[key]
        if extra_widget_keys is not None:
            for ek in extra_widget_keys(k):
                if ek in st.session_state:
                    del st.session_state[ek]

    draft_set(count_field, 0)


def _apply_auto_extras_to_draft(draft, child_idx: int, field_n_extra: str, new_auto_rows):
    """Replace mode: keep manual rows, drop existing [AUTO] rows, append new ones.

    Reads the current child.{i}.extra.{j}.* state, filters out rows whose
    `note` starts with AUTO_EXTRA_MARKER, appends `new_auto_rows`, then writes
    back to draft state. Caps at MAX_N_EXTRA. Returns the final row count.
    """
    current_n = int(draft_get(field_n_extra, 0))

    # Collect manual (non-AUTO) rows by snapshotting all per-field draft values
    manual_rows = []
    for j in range(current_n):
        note_val = str(draft_get(f"child.{child_idx}.extra.{j}.note", "") or "")
        if note_val.startswith(AUTO_EXTRA_MARKER):
            continue
        manual_rows.append({
            "name": draft_get(f"child.{child_idx}.extra.{j}.name", f"Expense {j+1}"),
            "amount": float(draft_get(f"child.{child_idx}.extra.{j}.amount", 100000.0)),
            "currency": draft_get(f"child.{child_idx}.extra.{j}.currency", "THB"),
            "type": draft_get(f"child.{child_idx}.extra.{j}.type", "one_time"),
            "trigger_mode": draft_get(f"child.{child_idx}.extra.{j}.trigger_mode", "by_year"),
            "inflation_type": draft_get(f"child.{child_idx}.extra.{j}.inflation_type", "general"),
            "year": draft_get(f"child.{child_idx}.extra.{j}.year", date.today().year),
            "end_year": draft_get(f"child.{child_idx}.extra.{j}.end_year", date.today().year + 2),
            "child_age": draft_get(f"child.{child_idx}.extra.{j}.child_age", 10),
            "start_year": draft_get(f"child.{child_idx}.extra.{j}.start_year", date.today().year),
            "start_age": draft_get(f"child.{child_idx}.extra.{j}.start_age", 8),
            "end_age": draft_get(f"child.{child_idx}.extra.{j}.end_age", 12),
            "note": note_val,
        })

    # Merge manual + new auto rows, cap at MAX_N_EXTRA
    merged = manual_rows + new_auto_rows
    if len(merged) > MAX_N_EXTRA:
        merged = merged[:MAX_N_EXTRA]

    # Write back to draft state
    for j, row in enumerate(merged):
        draft_set(f"child.{child_idx}.extra.{j}.name", row["name"])
        draft_set(f"child.{child_idx}.extra.{j}.amount", float(row["amount"]))
        draft_set(f"child.{child_idx}.extra.{j}.currency", row.get("currency", "THB"))
        draft_set(f"child.{child_idx}.extra.{j}.type", row["type"])
        draft_set(f"child.{child_idx}.extra.{j}.trigger_mode", row["trigger_mode"])
        draft_set(f"child.{child_idx}.extra.{j}.inflation_type", row["inflation_type"])
        draft_set(f"child.{child_idx}.extra.{j}.year", int(row["year"]))
        draft_set(f"child.{child_idx}.extra.{j}.end_year", int(row["end_year"]))
        draft_set(f"child.{child_idx}.extra.{j}.child_age", int(row["child_age"]))
        draft_set(f"child.{child_idx}.extra.{j}.start_year", int(row["start_year"]))
        draft_set(f"child.{child_idx}.extra.{j}.start_age", int(row["start_age"]))
        draft_set(f"child.{child_idx}.extra.{j}.end_age", int(row["end_age"]))
        draft_set(f"child.{child_idx}.extra.{j}.note", row["note"])

    draft_set(field_n_extra, len(merged))
    return len(merged)


# ============================================================
# DEFAULT EDUCATION PRESET (one-click standard plan)
# ============================================================
# K-12 → Shrewsbury (อินเตอร์ไทย), ปริญญาตรี → MIT, ปริญญาโท → Harvard.
# ชื่อโรงเรียนต้องตรงกับที่มีใน data/school_fees.csv "เป๊ะ ๆ" — ถ้าไม่ตรง
# selectbox จะ fallback เป็น "(พิมพ์เอง / custom)" และผู้ใช้จะเห็นชื่อใน
# ช่อง custom-text แทนที่จะถูกเลือกจาก dropdown โดยตรง
DEFAULT_EDU_PRESET_PLANS = [
    ("kindergarten",  "Shrewsbury International School Bangkok"),
    ("elementary",    "Shrewsbury International School Bangkok"),
    ("middle_school", "Shrewsbury International School Bangkok"),
    ("high_school",   "Shrewsbury International School Bangkok"),
    ("bachelor",      "Massachusetts Institute of Technology (MIT)"),
    ("master",        "Harvard University"),
]


def _apply_default_edu_preset(draft, child_idx: int, current_n_edu: int, field_n_edu: str):
    """Wipe this child's education plans and load DEFAULT_EDU_PRESET_PLANS.

    สำหรับแต่ละแถวจะใช้ EDU_DEFAULT_PRESETS เป็นค่าเริ่มต้น (country, age,
    growth rate, ...) แล้ว overlay ทับด้วยข้อมูลโรงเรียนจริงจาก
    school_fees.lookup() ถ้ามี (country/school_type/annual_cost/age range).
    Sync ค่า sb_school_{i}_{j} widget state ด้วยเพื่อให้ selectbox โชว์
    โรงเรียนที่เลือกหลัง rerun
    """
    # Step 1: clear existing rows (รวม widget state ของ sb_school_*)
    _delete_all_rows(
        draft,
        key_prefix=f"child.{child_idx}.edu",
        fields=_EDU_FIELDS,
        n_rows=current_n_edu,
        count_field=field_n_edu,
        extra_widget_keys=lambda k: (f"sb_school_{child_idx}_{k}",),
    )

    # Step 2: เขียนแถวใหม่ตามลำดับใน DEFAULT_EDU_PRESET_PLANS
    for j, (level, school_name) in enumerate(DEFAULT_EDU_PRESET_PLANS):
        base = EDU_DEFAULT_PRESETS.get(level, EDU_DEFAULT_PRESETS["other"])

        country = base["country"]
        school_type = base["school_type"]
        annual_cost = float(base["annual_cost"])
        annual_currency = "THB"
        start_age = int(base["start_age"])
        end_age = int(base["end_age"])

        row = lookup_school_fee(level, school_name)
        if row is not None:
            _c = row.get("country")
            if _c:
                country = str(_c)
            _st = row.get("school_type")
            if _st:
                school_type = str(_st)
            # Use ORIGINAL amount + currency; THB derived at sim time via fx.
            _oamt = row.get("original_amount")
            try:
                if _oamt is not None and not pd.isna(_oamt):
                    annual_cost = float(_oamt)
                    annual_currency = str(row.get("original_currency") or "THB").strip() or "THB"
            except (TypeError, ValueError):
                pass
            _amin = row.get("age_min")
            _amax = row.get("age_max")
            try:
                if _amin is not None and not pd.isna(_amin):
                    start_age = int(_amin)
                if _amax is not None and not pd.isna(_amax):
                    end_age = int(_amax)
            except (TypeError, ValueError):
                pass

        draft_set(f"child.{child_idx}.edu.{j}.level", level)
        draft_set(f"child.{child_idx}.edu.{j}.country", country)
        draft_set(f"child.{child_idx}.edu.{j}.school_type", school_type)
        draft_set(f"child.{child_idx}.edu.{j}.school_name", school_name)
        draft_set(f"child.{child_idx}.edu.{j}.start_age", int(start_age))
        draft_set(f"child.{child_idx}.edu.{j}.end_age", int(end_age))
        draft_set(f"child.{child_idx}.edu.{j}.annual_cost", float(annual_cost))
        draft_set(f"child.{child_idx}.edu.{j}.annual_currency", annual_currency)
        draft_set(f"child.{child_idx}.edu.{j}.show_advanced", False)
        draft_set(f"child.{child_idx}.edu.{j}.cost_growth_rate", float(base["cost_growth_rate"]))
        draft_set(f"child.{child_idx}.edu.{j}.cost_basis_year", int(base["cost_basis_year"]))
        draft_set(f"child.{child_idx}.edu.{j}.note", base.get("note", ""))

        # Sync selectbox widget state ให้โชว์โรงเรียนที่เลือกหลัง rerun
        st.session_state[f"sb_school_{child_idx}_{j}"] = school_name

    draft_set(field_n_edu, len(DEFAULT_EDU_PRESET_PLANS))
    return len(DEFAULT_EDU_PRESET_PLANS)


# ============================================================
# CHILD-ROW DELETION (snapshot + wipe + restore at new index)
# ============================================================
# Top-level (non-list) fields stored per child. Nested edu/extra rows use
# _EDU_FIELDS and _EXTRA_FIELDS keyed under child.{i}.edu.{j}.* / .extra.{j}.*
_CHILD_TOP_FIELDS = ("name", "gender", "birth_date", "n_edu", "n_extra")


def _snapshot_child(draft, child_idx: int) -> dict:
    """Capture ALL state for one child (top fields + nested edu + nested extra).

    เก็บ sb_school_{i}_{j} widget state ไว้ด้วยใต้ key "__sb_school" ของ
    แต่ละ edu row เพื่อให้ selectbox โชว์โรงเรียนเดิมหลัง shift index
    """
    snap = {"top": {}, "edu": [], "extra": []}

    for f in _CHILD_TOP_FIELDS:
        key = f"child.{child_idx}.{f}"
        if key in draft:
            snap["top"][f] = draft[key]

    n_edu = int(draft.get(f"child.{child_idx}.n_edu", 0) or 0)
    for j in range(n_edu):
        row = {}
        for f in _EDU_FIELDS:
            key = f"child.{child_idx}.edu.{j}.{f}"
            if key in draft:
                row[f] = draft[key]
        sb_key = f"sb_school_{child_idx}_{j}"
        if sb_key in st.session_state:
            row["__sb_school"] = st.session_state[sb_key]
        snap["edu"].append(row)

    n_extra = int(draft.get(f"child.{child_idx}.n_extra", 0) or 0)
    for j in range(n_extra):
        row = {}
        for f in _EXTRA_FIELDS:
            key = f"child.{child_idx}.extra.{j}.{f}"
            if key in draft:
                row[f] = draft[key]
        snap["extra"].append(row)

    return snap


def _wipe_child(draft, child_idx: int):
    """Delete every draft + widget-state key belonging to one child slot.

    ใช้ MAX_N_EDU / MAX_N_EXTRA เป็น upper bound เผื่อมี orphan key
    หลงเหลือจาก list ขนาดเดิมที่ใหญ่กว่า n_edu/n_extra ปัจจุบัน
    """
    for f in _CHILD_TOP_FIELDS:
        key = f"child.{child_idx}.{f}"
        if key in draft:
            del draft[key]
        if key in st.session_state:
            del st.session_state[key]

    disp_key = f"child_name_display_{child_idx}"
    if disp_key in st.session_state:
        del st.session_state[disp_key]

    for j in range(MAX_N_EDU):
        for f in _EDU_FIELDS:
            key = f"child.{child_idx}.edu.{j}.{f}"
            if key in draft:
                del draft[key]
            if key in st.session_state:
                del st.session_state[key]
        sb_key = f"sb_school_{child_idx}_{j}"
        if sb_key in st.session_state:
            del st.session_state[sb_key]

    for j in range(MAX_N_EXTRA):
        for f in _EXTRA_FIELDS:
            key = f"child.{child_idx}.extra.{j}.{f}"
            if key in draft:
                del draft[key]
            if key in st.session_state:
                del st.session_state[key]


def _restore_child(draft, child_idx: int, snap: dict):
    """Write a snapshot back at the given (possibly different) child index."""
    for f, v in snap["top"].items():
        draft_set(f"child.{child_idx}.{f}", v)

    for j, row in enumerate(snap["edu"]):
        for f in _EDU_FIELDS:
            if f in row:
                draft_set(f"child.{child_idx}.edu.{j}.{f}", row[f])
        sb_val = row.get("__sb_school")
        if sb_val is not None:
            st.session_state[f"sb_school_{child_idx}_{j}"] = sb_val

    for j, row in enumerate(snap["extra"]):
        for f in _EXTRA_FIELDS:
            if f in row:
                draft_set(f"child.{child_idx}.extra.{j}.{f}", row[f])


def _delete_child_row(draft, del_idx: int, n_children: int):
    """Remove child at del_idx; shift later children up by 1.

    ใช้วิธี snapshot-wipe-restore เพราะแต่ละลูกมี nested list (edu/extra)
    ขนาดต่างกัน — generic shift-and-delete ที่ใช้กับ flat list จะคำนวณ
    boundary ผิด
    """
    if n_children <= 0:
        return

    surviving = []
    for k in range(n_children):
        if k == del_idx:
            continue
        surviving.append(_snapshot_child(draft, k))

    for k in range(n_children):
        _wipe_child(draft, k)

    for new_idx, snap in enumerate(surviving):
        _restore_child(draft, new_idx, snap)

    draft_set("n_children", len(surviving))


# ============================================================
# SECTION 0: CUSTOMER ID
# ============================================================
def render_section_cust_id():
    """Render the Customer ID section that gates the run button and DB import."""
    with st.container(border=True):
        st.subheader(S("p1", "cid_header"))
        st.caption(S("p1", "cid_caption"))

        cust_id_value = p_text_input(
            "cust_id",
            field="cust_id",
            default="",
            label_visibility="collapsed",
            placeholder=S("p1", "cid_placeholder"),
            max_chars=CUST_ID_MAX_LEN,
        )
        cust_id_clean = normalize_cust_id(cust_id_value)
        cust_id_error = cust_id_validation_error(cust_id_clean)

        # A complete, valid id that differs from the draft's owner means the
        # on-screen data belongs to a previous customer → start fresh so it
        # can't be saved under the new id. (Import below re-loads their history.)
        if cust_id_clean and cust_id_error is None:
            _owner = draft_get("_owner_cust_id", "")
            if not _owner:
                draft_set("_owner_cust_id", cust_id_clean)
            elif _owner != cust_id_clean:
                reset_draft_for_new_customer(cust_id_clean)
                st.rerun()

        if cust_id_clean and cust_id_error:
            st.warning(cust_id_error)

        if cust_id_clean and cust_id_error is None:
            try:
                has_prev = db_has_previous_data(cust_id_clean)
            except Exception as e:
                has_prev = False
                st.error(S("p1", "cid_check_failed", error=e))

            if has_prev:
                meta = db_get_latest_meta(cust_id_clean) or {}
                last_saved = meta.get("created_at", "")
                info_msg = S("p1", "cid_prev_found")
                if last_saved:
                    info_msg += S("p1", "cid_last_saved", ts=last_saved)
                st.info(info_msg)

                if st.button(
                    S("p1", "cid_btn_import"),
                    key="btn_import_prev_data",
                    width="stretch",
                ):
                    try:
                        loaded = db_load_latest_draft(cust_id_clean)
                        if loaded:
                            loaded["cust_id"] = cust_id_clean
                            n_loaded = apply_loaded_draft_to_state(loaded)
                            st.success(S("p1", "cid_imported", n=n_loaded))
                            st.rerun()
                        else:
                            st.warning(S("p1", "cid_no_prev"))
                    except Exception as e:
                        st.error(S("p1", "cid_import_failed", error=e))


# ============================================================
# SECTION 1: CHILD EXPENSES
# ============================================================
def render_section_children(draft):
    """
    Render the Child Expenses section.

    Returns (children, n_children, total_edu_plans, total_child_extra).
    """
    st.header(S("p1", "sec1_header"))
    st.caption(S("p1", "sec1_caption"))

    n_children = int(draft_get("n_children", 1))

    # ── Fee Reference link button ──
    _fee_ref_col, _fee_space = st.columns([2, 4])
    with _fee_ref_col:
        if st.button(S("p1", "btn_fee_reference"), key="btn_fee_reference", width="stretch"):
            switch_page_with_persist("pages/04_School_Fees_Reference.py")

    _c_label, _c_space = st.columns([1, 4])
    with _c_label:
        st.metric(S("p1", "metric_n_children"), n_children)

    children = []

    for i in range(n_children):
        field_name = f"child.{i}.name"
        field_gender = f"child.{i}.gender"
        field_birth = f"child.{i}.birth_date"
        field_n_edu = f"child.{i}.n_edu"
        field_n_extra = f"child.{i}.n_extra"

        draft.setdefault(field_name, f"Child {i+1}")
        draft.setdefault(field_gender, "M")
        draft.setdefault(field_birth, date(2022, 1, 1))
        draft.setdefault(field_n_edu, 5)
        draft.setdefault(field_n_extra, 0)

        child_name_preview = draft_get(field_name, f"Child {i+1}")

        with st.expander(S("p1", "child_expander", n=i+1, name=child_name_preview), expanded=(i == 0)):
            # ── Per-child delete (กลับมาอยู่ใน expander, ชิดซ้ายสุดของ box) ──
            # disabled เมื่อเหลือลูกคนเดียว (MIN_N_CHILDREN=1) — น้อยกว่านี้
            # ไม่มีอะไรให้ simulate
            _cd_del, _cd_space = st.columns([1, 5])
            with _cd_del:
                if st.button(
                    "🗑 ลบข้อมูลลูก",
                    key=f"btn_del_child_{i}",
                    width="stretch",
                    disabled=n_children <= MIN_N_CHILDREN,
                    help="ลบข้อมูลลูกคนนี้ทั้งหมด (รวมแผนการศึกษาและรายจ่ายเพิ่มเติม) "
                         "— ลูกคนถัดไปจะเลื่อนขึ้นมาแทน",
                ):
                    _delete_child_row(draft, i, n_children)
                    st.rerun()

            tab_basic, tab_edu, tab_extra = st.tabs([
                S("p1", "tab_basic"),
                S("p1", "tab_edu"),
                S("p1", "tab_extra"),
            ])

            # ----------------------------------------------------
            # TAB 1: BASIC INFO
            # ----------------------------------------------------
            with tab_basic:
                st.caption(S("p1", "basic_caption"))

                c1, c2, c3 = st.columns([1.5, 1, 1])

                with c1:
                    # Auto-assigned child name (read-only)
                    fixed_name = f"Child {i+1}"
                    draft_set(field_name, fixed_name)  # always overwrite, ignore any prior edits
                    st.text_input(
                        S("p1", "label_child_name"),
                        value=fixed_name,
                        key=f"child_name_display_{i}",
                        disabled=True,
                    )

                with c2:
                    p_selectbox(
                        S("p1", "label_gender"),
                        field=field_gender,
                        options=["M", "F", "Other"],
                        default="M",
                        format_func=gender_label,
                    )

                with c3:
                    p_date_input(
                        S("p1", "label_birth_date"),
                        field=field_birth,
                        default=date(2022, 1, 1),
                        min_value=date(2004, 1, 1),
                        max_value=date.today().replace(year=date.today().year + 2),
                    )

            # ----------------------------------------------------
            # TAB 2: EDUCATION PLANS
            # ----------------------------------------------------
            with tab_edu:
                st.caption(S("p1", "edu_caption"))

                n_edu = int(draft_get(field_n_edu, 5))
                _e_label, _e_default, _e_clear, _e_space = st.columns([1.3, 2, 1.7, 2.5])
                with _e_label:
                    st.metric(S("p1", "metric_n_edu"), n_edu)
                with _e_default:
                    _btn_spacer()
                    if st.button(
                        "📋 ใช้ค่าเริ่มต้น",
                        key=f"btn_default_edu_{i}",
                        width="stretch",
                        help="โหลดแผนการศึกษาเริ่มต้น: อนุบาล–มัธยมปลาย Shrewsbury, "
                             "ปริญญาตรี Top US, ปริญญาโท Top US MBA "
                             "(จะลบแผนเดิมทั้งหมดก่อน)",
                    ):
                        _n_new = _apply_default_edu_preset(draft, i, n_edu, field_n_edu)
                        st.success(
                            f"✅ โหลดแผนการศึกษาเริ่มต้น {_n_new} รายการแล้ว "
                            "— ปรับแก้ในแต่ละการ์ดได้"
                        )
                        st.rerun()
                with _e_clear:
                    _btn_spacer()
                    if st.button(
                        "🗑 ลบทั้งหมด",
                        key=f"btn_clear_edu_{i}",
                        width="stretch",
                        disabled=n_edu <= 0,
                        help="ลบแผนการศึกษาทุกรายการของลูกคนนี้",
                    ):
                        _delete_all_rows(
                            draft,
                            key_prefix=f"child.{i}.edu",
                            fields=_EDU_FIELDS,
                            n_rows=n_edu,
                            count_field=field_n_edu,
                            extra_widget_keys=lambda k: (f"sb_school_{i}_{k}",),
                        )
                        st.rerun()

                edu_plans = []

                for j in range(n_edu):
                    default_level = get_default_level_for_row(j)
                    default_preset = EDU_DEFAULT_PRESETS.get(
                        default_level, EDU_DEFAULT_PRESETS["other"]
                    )

                    f_level = f"child.{i}.edu.{j}.level"
                    f_country = f"child.{i}.edu.{j}.country"
                    f_school_type = f"child.{i}.edu.{j}.school_type"
                    f_school_name = f"child.{i}.edu.{j}.school_name"
                    f_start_age = f"child.{i}.edu.{j}.start_age"
                    f_end_age = f"child.{i}.edu.{j}.end_age"
                    f_annual_cost = f"child.{i}.edu.{j}.annual_cost"
                    f_annual_currency = f"child.{i}.edu.{j}.annual_currency"
                    f_show_advanced = f"child.{i}.edu.{j}.show_advanced"
                    f_cost_growth = f"child.{i}.edu.{j}.cost_growth_rate"
                    f_cost_basis = f"child.{i}.edu.{j}.cost_basis_year"
                    f_note = f"child.{i}.edu.{j}.note"

                    draft.setdefault(f_level, default_level)
                    draft.setdefault(f_country, default_preset["country"])
                    draft.setdefault(f_school_type, default_preset["school_type"])
                    draft.setdefault(f_school_name, default_preset["school_name"])
                    draft.setdefault(f_start_age, default_preset["start_age"])
                    draft.setdefault(f_end_age, default_preset["end_age"])
                    draft.setdefault(f_annual_cost, float(default_preset["annual_cost"]))
                    draft.setdefault(f_annual_currency, "THB")
                    draft.setdefault(f_show_advanced, False)
                    draft.setdefault(f_cost_growth, float(default_preset["cost_growth_rate"]))
                    draft.setdefault(f_cost_basis, int(default_preset["cost_basis_year"]))
                    draft.setdefault(f_note, default_preset["note"])

                    with st.container(border=True):
                        top1, top2 = st.columns([3, 1])
                        with top1:
                            _edu_level_label = EDU_LEVEL_LABELS.get(draft_get(f_level, default_level), default_level)
                            st.markdown(f"**{S('p1', 'edu_plan_header', n=j+1, level=_edu_level_label)}**")
                        with top2:
                            if st.button(
                                "🗑 ลบ",
                                key=f"btn_del_edu_{i}_{j}",
                                width="stretch",
                                help="ลบแผนการศึกษานี้ (แผนด้านล่างจะเลื่อนขึ้นมาแทน)",
                            ):
                                _delete_indexed_row(
                                    draft,
                                    key_prefix=f"child.{i}.edu",
                                    fields=_EDU_FIELDS,
                                    del_idx=j,
                                    n_rows=n_edu,
                                    count_field=field_n_edu,
                                    extra_widget_keys=lambda k: (f"sb_school_{i}_{k}",),
                                )
                                st.rerun()

                        # ── Row 1: Primary fields (always visible) ──
                        # min+max age รวมกัน = 1 unit (เท่า min age เดิม),
                        # school name = 2 units (สองเท่าของเดิม)
                        e1, e2, e3, e4 = st.columns([1, 0.5, 0.5, 2])

                        with e1:
                            p_selectbox(
                                S("p1", "label_edu_level"),
                                field=f_level,
                                options=EDU_LEVEL_OPTIONS,
                                default=default_level,
                                format_func=edu_level_label,
                                on_change_extra=_on_edu_level_change,
                                on_change_extra_args=(i, j, f_level),
                            )

                        with e2:
                            p_number_input(
                                S("p1", "label_start_age"),
                                field=f_start_age,
                                default=default_preset["start_age"],
                                min_value=0,
                                max_value=40,
                                step=1,
                                format="%d",
                                cast=int,
                                help=SC("inclusive_help"),
                            )

                        with e3:
                            p_number_input(
                                S("p1", "label_end_age"),
                                field=f_end_age,
                                default=default_preset["end_age"],
                                min_value=0,
                                max_value=40,
                                step=1,
                                format="%d",
                                cast=int,
                                help=SC("inclusive_help"),
                            )

                        with e4:
                            _current_level = draft_get(f_level, default_level)
                            _known_schools = schools_for_level(_current_level)
                            _sb_options = [CUSTOM_SCHOOL_SENTINEL] + _known_schools
                            _sb_key = f"sb_school_{i}_{j}"
                            _current_sn = draft_get(f_school_name, "") or ""
                            _desired_sb = _current_sn if _current_sn in _known_schools else CUSTOM_SCHOOL_SENTINEL
                            if _sb_key not in st.session_state or st.session_state[_sb_key] not in _sb_options:
                                st.session_state[_sb_key] = _desired_sb
                            st.selectbox(
                                S("p1", "label_school_name"),
                                options=_sb_options,
                                key=_sb_key,
                                on_change=_on_school_select,
                                args=(i, j, _sb_key, f_level),
                            )
                            if st.session_state[_sb_key] == CUSTOM_SCHOOL_SENTINEL:
                                p_text_input(
                                    S("p1", "label_school_name_custom"),
                                    field=f_school_name,
                                    default="",
                                    label_visibility="collapsed",
                                    placeholder=S("p1", "placeholder_school_name_custom"),
                                )

                        # ── Row 2: School details (always visible) ──
                        _country_default = default_preset.get("country", "")
                        if _country_default not in COUNTRY_OPTIONS:
                            _country_default = ""

                        # country/type = ซ้ายครึ่งแถว | cost/currency/note เท่ากัน = ขวาครึ่งแถว
                        # (รวม cost+currency+note = 3 = ครึ่งหนึ่งของ 6 เท่ากับชื่อโรงเรียนแถวบน)
                        s1, s2, s3, s_ccy, s4 = st.columns([1.5, 1.5, 1, 1, 1])

                        with s1:
                            p_selectbox(
                                S("p1", "label_country"),
                                field=f_country,
                                options=COUNTRY_OPTIONS,
                                default=_country_default,
                                format_func=country_label,
                            )

                        with s2:
                            p_selectbox(
                                S("p1", "label_school_type"),
                                field=f_school_type,
                                options=SCHOOL_TYPE_OPTIONS,
                                default=default_preset["school_type"],
                                format_func=school_type_label,
                            )

                        with s3:
                            p_number_input(
                                S("p1", "label_annual_cost"),
                                field=f_annual_cost,
                                default=float(default_preset["annual_cost"]),
                                min_value=0.0,
                                step=10_000.0,
                                format="%.0f",
                                cast=float,
                            )

                        with s_ccy:
                            p_selectbox(
                                "สกุลเงิน",
                                field=f_annual_currency,
                                options=_ccy_options(),
                                default="THB",
                            )

                        with s4:
                            p_text_input(S("p1", "label_note"), field=f_note, default=default_preset["note"])

                        # ── Toggle: override education inflation per-plan ──
                        # OFF (default) → ใช้ค่า education_inflation จากหัวข้อ "สมมติฐาน"
                        # ON            → ผู้ใช้ตั้งอัตราเงินเฟ้อ + ปีฐานเฉพาะแผนนี้
                        # draft state ของ override (f_cost_growth / f_cost_basis)
                        # ยังเก็บไว้อยู่แม้ toggle ถูกปิด — เปิดใหม่จะได้ค่าเดิมกลับมา
                        _override_toggle_key = f"toggle_growth_override_{i}_{j}"
                        if _override_toggle_key not in st.session_state:
                            st.session_state[_override_toggle_key] = bool(
                                draft_get(f_show_advanced, False)
                            )

                        _use_override = st.toggle(
                            "ปรับอัตราเงินเฟ้อค่าเล่าเรียนและปีฐานเอง",
                            key=_override_toggle_key,
                            help="ปิด: ใช้อัตราเงินเฟ้อค่าเล่าเรียนจากหัวข้อ ‘สมมติฐาน’ ด้านล่าง | "
                                 "เปิด: กำหนดอัตราเงินเฟ้อและปีฐานเฉพาะแผนนี้",
                        )
                        draft_set(f_show_advanced, _use_override)

                        if _use_override:
                            e9, e10 = st.columns(2)

                            with e9:
                                cost_growth_rate = p_percent_input(
                                    S("p1", "label_cost_growth_rate"),
                                    field=f_cost_growth,
                                    default_decimal=float(default_preset["cost_growth_rate"]),
                                    min_value=0.0,
                                    max_value=RATE_MAX_PCT,
                                    step=0.5,
                                    format="%.1f",
                                )

                            with e10:
                                cost_basis_year = int(
                                    p_number_input(
                                        S("p1", "label_cost_basis_year"),
                                        field=f_cost_basis,
                                        default=date.today().year,
                                        min_value=date.today().year,
                                        max_value=2100,
                                        step=1,
                                        format="%d",
                                        cast=int,
                                    )
                                )
                        else:
                            # None ส่งต่อ EducationPlan → simulation_core fallback
                            # ไปใช้ assumptions.education_inflation_rate + base year
                            # ของ assumption section (ดู simulation_core.py:649-658)
                            cost_growth_rate = None
                            cost_basis_year = None

                        # 🎓 Scholarships matching THIS plan's school — pinned
                        # to the very bottom of the card.
                        _aid_sn = (draft_get(f_school_name) or "").strip()
                        if _aid_sn:
                            _aid_m = load_financial_aid()
                            _aid_m = _aid_m[_aid_m["University"] == _aid_sn]
                            if not _aid_m.empty:
                                with st.expander(
                                    f"🎓 ทุนการศึกษาที่เกี่ยวข้อง ({len(_aid_m)} รายการ)",
                                    expanded=False,
                                ):
                                    for _i, (_, _aid_r) in enumerate(_aid_m.iterrows()):
                                        _src = str(_aid_r["Source"]).strip()
                                        _src_md = (
                                            f"[🔗 เปิดลิงก์]({_src})"
                                            if _src.startswith("http") else (_src or "-")
                                        )
                                        st.markdown(
                                            f"**🎓 {_aid_r['Scholarship']}**\n\n"
                                            f"- **ประเภททุน:** {_aid_r['Scholarship_Type']}\n"
                                            f"- **มูลค่าทุน:** {_aid_r['Scholarship_Value']}\n"
                                            f"- **เงื่อนไข:** {_aid_r['Conditions']}\n"
                                            f"- **ที่มา:** {_src_md}"
                                        )
                                        if _i < len(_aid_m) - 1:
                                            st.divider()

                        edu_plans.append(
                            EducationPlan(
                                level=draft_get(f_level),
                                country=draft_get(f_country),
                                school_type=draft_get(f_school_type),
                                school_name=_none_if_blank(draft_get(f_school_name)),
                                start_age=int(draft_get(f_start_age)),
                                end_age=int(draft_get(f_end_age)),
                                annual_cost=to_thb(
                                    float(draft_get(f_annual_cost)),
                                    draft_get(f_annual_currency, "THB"),
                                ),
                                cost_growth_rate=cost_growth_rate,
                                cost_basis_year=cost_basis_year,
                                note=_none_if_blank(draft_get(f_note)),
                            )
                        )

                # Add button ที่ท้ายลิสต์ (ใช้แทนปุ่ม ➕ ที่เคยอยู่ header)
                if st.button(
                    "➕ เพิ่มแผนการศึกษา",
                    key=f"btn_add_edu_bottom_{i}",
                    width="stretch",
                    disabled=n_edu >= MAX_N_EDU,
                ):
                    draft_set(field_n_edu, n_edu + 1)
                    st.rerun()

            # ----------------------------------------------------
            # TAB 3: CHILD EXTRA EXPENSES
            # ----------------------------------------------------
            with tab_extra:
                st.caption(S("p1", "extra_caption"))

                n_extra = int(draft_get(field_n_extra, 0))

                # ปุ่ม Auto-fill เปิดใช้ได้ก็ต่อเมื่อมี edu plan ที่ระบุประเทศแล้ว
                _has_country_in_edu = any(
                    (getattr(p, "country", None) or "").strip()
                    for p in edu_plans
                )

                _x_label, _x_auto, _x_clear, _x_space = st.columns([1, 1.5, 1.5, 2])
                with _x_label:
                    st.metric(S("p1", "metric_n_extra"), n_extra)
                with _x_auto:
                    _btn_spacer()
                    if st.button(
                        "🪄 Auto-fill จาก Education Plan",
                        key=f"btn_auto_extra_{i}",
                        width="stretch",
                        disabled=not _has_country_in_edu,
                        help="สร้างรายการค่าครองชีพ (ที่พัก/อาหาร/เดินทาง/น้ำ-ไฟ) อัตโนมัติ "
                             "ตามประเทศและช่วงอายุของแผนการศึกษา — แก้ไขได้ภายหลัง "
                             "(รายการที่กรอกเองจะไม่ถูกแตะ)",
                    ):
                        _col_df = load_cost_of_living()
                        _auto_rows, _auto_warnings = _auto_extras_from_edu_plans(edu_plans, _col_df)
                        if not _auto_rows:
                            # Toast survives st.rerun(); inline st.warning() does not.
                            st.toast(
                                "ไม่สามารถสร้างรายการอัตโนมัติได้ — "
                                "ตรวจสอบว่าแผนการศึกษาระบุประเทศที่มีในฐานข้อมูลค่าครองชีพ",
                                icon="⚠️",
                            )
                        else:
                            _n_final = _apply_auto_extras_to_draft(
                                draft, i, field_n_extra, _auto_rows
                            )
                            st.toast(
                                f"สร้างรายการอัตโนมัติ {len(_auto_rows)} รายการ "
                                f"(รวม {_n_final} รายการ) — ปรับแก้ได้ในการ์ดด้านล่าง",
                                icon="✅",
                            )
                            for _w in _auto_warnings:
                                st.toast(_w, icon="ℹ️")
                            st.rerun()
                with _x_clear:
                    _btn_spacer()
                    if st.button(
                        "🗑 ลบทั้งหมด",
                        key=f"btn_clear_extra_{i}",
                        width="stretch",
                        disabled=n_extra <= 0,
                        help="ลบรายจ่ายเพิ่มเติมทุกรายการของลูกคนนี้",
                    ):
                        _delete_all_rows(
                            draft,
                            key_prefix=f"child.{i}.extra",
                            fields=_EXTRA_FIELDS,
                            n_rows=n_extra,
                            count_field=field_n_extra,
                        )
                        st.rerun()

                extra_expenses = []

                for j in range(n_extra):
                    f_name = f"child.{i}.extra.{j}.name"
                    f_amount = f"child.{i}.extra.{j}.amount"
                    f_currency = f"child.{i}.extra.{j}.currency"
                    f_type = f"child.{i}.extra.{j}.type"
                    f_trigger = f"child.{i}.extra.{j}.trigger_mode"
                    f_infl = f"child.{i}.extra.{j}.inflation_type"
                    f_year = f"child.{i}.extra.{j}.year"
                    f_child_age = f"child.{i}.extra.{j}.child_age"
                    f_start_year = f"child.{i}.extra.{j}.start_year"
                    f_end_year = f"child.{i}.extra.{j}.end_year"
                    f_start_age = f"child.{i}.extra.{j}.start_age"
                    f_end_age = f"child.{i}.extra.{j}.end_age"
                    f_note = f"child.{i}.extra.{j}.note"

                    draft.setdefault(f_name, f"Expense {j+1}")
                    draft.setdefault(f_amount, 100000.0)
                    draft.setdefault(f_currency, "THB")
                    draft.setdefault(f_type, "one_time")
                    draft.setdefault(f_trigger, "by_year")
                    draft.setdefault(f_infl, "general")
                    draft.setdefault(f_year, date.today().year)
                    draft.setdefault(f_child_age, 10)
                    draft.setdefault(f_start_year, date.today().year)
                    draft.setdefault(f_end_year, date.today().year + 2)
                    draft.setdefault(f_start_age, 8)
                    draft.setdefault(f_end_age, 12)
                    draft.setdefault(f_note, "")

                    with st.container(border=True):
                        _hdr_col, _del_col = st.columns([5, 1])
                        with _hdr_col:
                            st.markdown(f"**{S('p1', 'extra_card_header', n=j+1)}**")
                        with _del_col:
                            if st.button(
                                "🗑 ลบ",
                                key=f"btn_del_extra_{i}_{j}",
                                width="stretch",
                                help="ลบรายการนี้ออก (รายการที่อยู่ด้านล่างจะเลื่อนขึ้นมาแทน)",
                            ):
                                _delete_indexed_row(
                                    draft,
                                    key_prefix=f"child.{i}.extra",
                                    fields=_EXTRA_FIELDS,
                                    del_idx=j,
                                    n_rows=n_extra,
                                    count_field=field_n_extra,
                                )
                                st.rerun()

                        # name+amount = ครึ่งซ้าย (amount ยาวถึงกลางหน้า) | currency+type = ครึ่งขวา เท่าๆ กัน
                        x1, x2, x_ccy, x3 = st.columns([2.5, 1.5, 2, 2])
                        with x1:
                            p_text_input(SC("name"), field=f_name, default=f"Expense {j+1}")
                        with x2:
                            p_number_input(
                                SC("amount"),
                                field=f_amount,
                                default=100000.0,
                                min_value=0.0,
                                step=1000.0,
                                format="%.0f",
                                cast=float,
                            )
                        with x_ccy:
                            p_selectbox(
                                "สกุลเงิน",
                                field=f_currency,
                                options=_ccy_options(),
                                default="THB",
                            )
                        with x3:
                            ex_type = p_selectbox(
                                SC("type"),
                                field=f_type,
                                options=["one_time", "recurring"],
                                default="one_time",
                                format_func=expense_type_label,
                            )

                        x4, x5 = st.columns(2)
                        with x4:
                            trigger_mode = p_selectbox(
                                S("p1", "label_trigger"),
                                field=f_trigger,
                                options=["by_year", "by_child_age"],
                                default="by_year",
                                format_func=trigger_label,
                            )
                        with x5:
                            p_selectbox(
                                S("p1", "label_infl_type"),
                                field=f_infl,
                                options=["general", "education", "none"],
                                default="general",
                                format_func=inflation_label,
                            )

                        year = None
                        end_year = None
                        child_age = None
                        start_age_ex = None
                        end_age_ex = None

                        if ex_type == "one_time":
                            if trigger_mode == "by_year":
                                year = int(
                                    p_number_input(
                                        SC("year"),
                                        field=f_year,
                                        default=date.today().year,
                                        min_value=YEAR_MIN_DEFAULT,
                                        max_value=YEAR_MAX_DEFAULT,
                                        step=1,
                                        format="%d",
                                        cast=int,
                                    )
                                )
                            else:
                                child_age = int(
                                    p_number_input(
                                        SC("child_age"),
                                        field=f_child_age,
                                        default=10,
                                        min_value=1,
                                        max_value=35,
                                        step=1,
                                        format="%d",
                                        cast=int,
                                    )
                                )
                        else:
                            if trigger_mode == "by_year":
                                y1, y2 = st.columns(2)

                                with y1:
                                    year = int(
                                        p_number_input(
                                            SC("start_year"),
                                            field=f_start_year,
                                            default=date.today().year,
                                            min_value=YEAR_MIN_DEFAULT,
                                            max_value=YEAR_MAX_DEFAULT,
                                            step=1,
                                            format="%d",
                                            cast=int,
                                        )
                                    )

                                with y2:
                                    end_year = int(
                                        p_number_input(
                                            SC("end_year"),
                                            field=f_end_year,
                                            default=date.today().year + 2,
                                            min_value=YEAR_MIN_DEFAULT,
                                            max_value=YEAR_MAX_DEFAULT,
                                            step=1,
                                            format="%d",
                                            cast=int,
                                        )
                                    )
                            else:
                                a1, a2 = st.columns(2)

                                with a1:
                                    start_age_ex = int(
                                        p_number_input(
                                            SC("start_age"),
                                            field=f_start_age,
                                            default=8,
                                            min_value=1,
                                            max_value=50,
                                            step=1,
                                            format="%d",
                                            cast=int,
                                            help=SC("inclusive_help"),
                                        )
                                    )

                                with a2:
                                    end_age_ex = int(
                                        p_number_input(
                                            SC("end_age"),
                                            field=f_end_age,
                                            default=12,
                                            min_value=1,
                                            max_value=50,
                                            step=1,
                                            format="%d",
                                            cast=int,
                                            help=SC("inclusive_help"),
                                        )
                                    )

                        p_text_input(SC("note_optional"), field=f_note, default="")

                        extra_expenses.append(
                            ExtraExpense(  # amount → THB via fx (default THB = no-op)
                                name=draft_get(f_name),
                                amount=to_thb(
                                    float(draft_get(f_amount)),
                                    draft_get(f_currency, "THB"),
                                ),
                                type=draft_get(f_type),
                                year=year,
                                end_year=end_year,
                                child_age=child_age,
                                start_age=start_age_ex,
                                end_age=end_age_ex,
                                inflation_type=draft_get(f_infl),
                                note=_none_if_blank(draft_get(f_note)),
                            )
                        )

                # Add button ที่ท้ายลิสต์ (ใช้แทนปุ่ม ➕ ที่เคยอยู่ header)
                if st.button(
                    "➕ เพิ่มรายการ",
                    key=f"btn_add_extra_bottom_{i}",
                    width="stretch",
                    disabled=n_extra >= MAX_N_EXTRA,
                ):
                    draft_set(field_n_extra, n_extra + 1)
                    st.rerun()

            children.append(
                Child(
                    name=draft_get(field_name),
                    gender=draft_get(field_gender),
                    birth_date=draft_get(field_birth).strftime("%Y-%m-%d"),
                    education_plan=edu_plans,
                    extra_expenses=extra_expenses,
                )
            )

    # Add button ที่ท้ายลิสต์ (ใช้แทนปุ่ม ➕ ที่เคยอยู่ header)
    if st.button(
        "➕ เพิ่มข้อมูลลูก",
        key="btn_add_child_bottom",
        width="stretch",
        disabled=n_children >= MAX_N_CHILDREN,
    ):
        draft_set("n_children", n_children + 1)
        st.rerun()

    total_edu_plans = sum(len(c.education_plan) for c in children)
    total_child_extra = sum(len(c.extra_expenses) for c in children)
    return children, n_children, total_edu_plans, total_child_extra


# ============================================================
# SECTION 2: PARENT EXPENSES
# ============================================================
def render_section_parent_expenses(draft, assumptions_start_year: int = None):
    """Render the Parent Expenses section. Returns (parent_expenses, n_parent_expenses).

    `assumptions_start_year` ถ้าส่งมาจะใช้เป็น min_value ของปีรายจ่ายผู้ปกครอง
    (ตามที่ user ต้องการ #17). ถ้าไม่ส่งมาจะ fallback เป็นปีปัจจุบัน."""
    st.header(S("p1", "sec2_header"))
    st.caption(S("p1", "sec2_caption"))

    # ใช้ assumptions.start_year ถ้ามี — กันคนใส่ปีเก่ากว่าจุดเริ่ม simulate
    year_min = int(assumptions_start_year) if assumptions_start_year else YEAR_MIN_DEFAULT

    n_parent_expenses = int(draft_get("n_parent_expenses", 0))
    _pe_label, _pe_space = st.columns([1, 4])
    with _pe_label:
        st.metric(S("p1", "metric_n_parent"), n_parent_expenses)

    parent_expenses = []

    for i in range(n_parent_expenses):
        f_name = f"parent.{i}.name"
        f_amount = f"parent.{i}.amount"
        f_type = f"parent.{i}.type"
        f_year = f"parent.{i}.year"
        f_end_year = f"parent.{i}.end_year"
        f_infl = f"parent.{i}.inflation_type"
        f_note = f"parent.{i}.note"

        draft.setdefault(f_name, f"Parent Expense {i+1}")
        draft.setdefault(f_amount, 100000.0)
        draft.setdefault(f_type, "one_time")
        draft.setdefault(f_year, date.today().year)
        draft.setdefault(f_end_year, date.today().year + 2)
        draft.setdefault(f_infl, "general")
        draft.setdefault(f_note, "")

        with st.container(border=True):
            _pe_hdr, _pe_del = st.columns([5, 1])
            with _pe_hdr:
                st.markdown(f"**{S('p1', 'parent_card_header', n=i+1)}**")
            with _pe_del:
                if st.button(
                    "🗑 ลบ",
                    key=f"btn_del_pe_{i}",
                    width="stretch",
                    help="ลบรายการนี้ (รายการด้านล่างจะเลื่อนขึ้นมาแทน)",
                ):
                    _delete_indexed_row(
                        draft,
                        key_prefix="parent",
                        fields=_PARENT_FIELDS,
                        del_idx=i,
                        n_rows=n_parent_expenses,
                        count_field="n_parent_expenses",
                    )
                    st.rerun()

            p1, p2, p3 = st.columns(3)

            with p1:
                p_text_input(SC("name"), field=f_name, default=f"Parent Expense {i+1}")

            with p2:
                p_number_input(
                    SC("amount"),
                    field=f_amount,
                    default=100000.0,
                    min_value=0.0,
                    step=1000.0,
                    format="%.0f",
                    cast=float,
                )

            with p3:
                current_type = p_selectbox(
                    SC("type"),
                    field=f_type,
                    options=["one_time", "recurring"],
                    default="one_time",
                    format_func=expense_type_label,
                )

            end_year = None

            if current_type == "one_time":
                p4, p5, p6 = st.columns(3)

                with p4:
                    p_number_input(
                        SC("year"),
                        field=f_year,
                        default=date.today().year,
                        min_value=year_min,
                        max_value=YEAR_MAX_DEFAULT,
                        step=1,
                        format="%d",
                        cast=int,
                    )

                with p5:
                    p_selectbox(
                        S("p1", "label_infl_type"),
                        field=f_infl,
                        options=["general", "education", "none"],
                        default="general",
                        format_func=inflation_label,
                    )

                with p6:
                    p_text_input(SC("note_optional"), field=f_note, default="")

            else:
                p4, p5, p6, p7 = st.columns([0.5, 0.5, 1, 1])

                with p4:
                    p_number_input(
                        SC("start_year"),
                        field=f_year,
                        default=date.today().year,
                        min_value=year_min,
                        max_value=YEAR_MAX_DEFAULT,
                        step=1,
                        format="%d",
                        cast=int,
                    )

                with p5:
                    end_year = int(
                        p_number_input(
                            SC("end_year"),
                            field=f_end_year,
                            default=date.today().year + 2,
                            min_value=year_min,
                            max_value=YEAR_MAX_DEFAULT,
                            step=1,
                            format="%d",
                            cast=int,
                        )
                    )

                with p6:
                    p_selectbox(
                        S("p1", "label_infl_type"),
                        field=f_infl,
                        options=["general", "education", "none"],
                        default="general",
                        format_func=inflation_label,
                    )

                with p7:
                    p_text_input(SC("note_optional"), field=f_note, default="")

            parent_expenses.append(
                ParentExpense(
                    name=draft_get(f_name),
                    amount=float(draft_get(f_amount)),
                    type=draft_get(f_type),
                    year=int(draft_get(f_year)),
                    end_year=end_year,
                    inflation_type=draft_get(f_infl),
                    note=_none_if_blank(draft_get(f_note)),
                )
            )

    # Add button ที่ท้ายลิสต์ (ใช้แทนปุ่ม ➕/➖ ที่เคยอยู่ header)
    if st.button(
        "➕ เพิ่มค่าใช้จ่ายครอบครัว",
        key="btn_add_pe_bottom",
        width="stretch",
        disabled=n_parent_expenses >= MAX_N_PARENT_EXPENSES,
    ):
        draft_set("n_parent_expenses", n_parent_expenses + 1)
        st.rerun()

    return parent_expenses, n_parent_expenses


# ============================================================
# SECTION 3: SAVING PLAN
# ============================================================
def render_section_saving_plan(draft):
    """
    Render the Saving Plan section.

    Returns (saving_plan, initial_savings, monthly_contribution, n_topups).
    """
    st.header(S("p1", "sec3_header"))
    st.caption(S("p1", "sec3_caption"))

    s1, s2 = st.columns(2)

    with s1:
        initial_savings = float(
            p_number_input(
                S("p1", "label_initial_savings"),
                field="initial_savings",
                default=2_000_000.0,
                min_value=0.0,
                step=10_000.0,
                format="%.0f",
                cast=float,
            )
        )

    with s2:
        monthly_contribution = float(
            p_number_input(
                S("p1", "label_monthly_contrib"),
                field="monthly_contribution",
                default=50_000.0,
                min_value=0.0,
                step=1000.0,
                format="%.0f",
                cast=float,
            )
        )

    saving_start_year = int(draft_get("saving_start_year"))

    n_topups = int(draft_get("n_topups", 0))
    _tp_label, _tp_space = st.columns([1, 4])
    with _tp_label:
        st.metric(S("p1", "metric_n_topups"), n_topups)

    _topup_amt_by_year: dict = {}
    _topup_note_by_year: dict = {}
    _topup_raw_count = 0
    for i in range(n_topups):
        f_year = f"topup.{i}.year"
        f_amount = f"topup.{i}.amount"
        f_note = f"topup.{i}.note"
        f_mode = f"topup.{i}.mode"
        f_year_start = f"topup.{i}.year_start"
        f_year_end = f"topup.{i}.year_end"

        draft.setdefault(f_year, date.today().year)
        draft.setdefault(f_amount, 300000.0)
        draft.setdefault(f_note, "")
        draft.setdefault(f_mode, "once")
        draft.setdefault(f_year_start, date.today().year)
        draft.setdefault(f_year_end, date.today().year)

        with st.container(border=True):
            _tp_hdr, _tp_del = st.columns([5, 1])
            with _tp_hdr:
                st.markdown(f"**{S('p1', 'topup_card_header', n=i+1)}**")
            with _tp_del:
                if st.button(
                    "🗑 ลบ",
                    key=f"btn_del_topup_{i}",
                    width="stretch",
                    help="ลบรายการนี้ (รายการด้านล่างจะเลื่อนขึ้นมาแทน)",
                ):
                    _delete_indexed_row(
                        draft,
                        key_prefix="topup",
                        fields=_TOPUP_FIELDS,
                        del_idx=i,
                        n_rows=n_topups,
                        count_field="n_topups",
                    )
                    st.rerun()

            # ความถี่ + ช่องกรอกอยู่แถวเดียวกัน. จัด layout ตามโหมดปัจจุบันที่
            # อ่านจาก draft ก่อน (p_selectbox on_change รีรันสคริปต์ ค่าจึงตรงกัน
            # เสมอภายในรอบที่นิ่งแล้ว). scale: once [1,1,1,1] / multi [1,.5,.5,1,1].
            _mode_pre = draft_get(f_mode, "once")

            if _mode_pre == "multi":
                cc1, cc2, cc3, cc4, cc5 = st.columns([1, 0.5, 0.5, 1, 1])
                with cc1:
                    _tp_mode = p_selectbox(
                        "ความถี่",
                        field=f_mode,
                        options=["once", "multi"],
                        default="once",
                        format_func=lambda m: "ครั้งเดียว" if m == "once" else "หลายปี",
                    )
                with cc2:
                    p_number_input(
                        "ปีแรก",
                        field=f_year_start,
                        default=date.today().year,
                        min_value=YEAR_MIN_DEFAULT,
                        max_value=YEAR_MAX_DEFAULT,
                        step=1,
                        format="%d",
                        cast=int,
                    )
                with cc3:
                    p_number_input(
                        "ปีสุดท้าย",
                        field=f_year_end,
                        default=date.today().year,
                        min_value=YEAR_MIN_DEFAULT,
                        max_value=YEAR_MAX_DEFAULT,
                        step=1,
                        format="%d",
                        cast=int,
                    )
                with cc4:
                    p_number_input(
                        SC("amount"),
                        field=f_amount,
                        default=300000.0,
                        min_value=0.0,
                        step=1000.0,
                        format="%.0f",
                        cast=float,
                    )
                with cc5:
                    p_text_input(SC("note_optional"), field=f_note, default="")

                _ys = int(draft_get(f_year_start))
                _ye = int(draft_get(f_year_end))
                if _ye < _ys:
                    _ys, _ye = _ye, _ys
                    st.caption("⚠️ ปีสุดท้ายน้อยกว่าปีแรก — ระบบสลับให้อัตโนมัติ")
                _amt = float(draft_get(f_amount))
                _nt = _none_if_blank(draft_get(f_note))
                for _y in range(_ys, _ye + 1):
                    _topup_amt_by_year[_y] = _topup_amt_by_year.get(_y, 0.0) + _amt
                    if _nt and _y not in _topup_note_by_year:
                        _topup_note_by_year[_y] = _nt
                    _topup_raw_count += 1
            else:
                cc1, cc2, cc3, cc4 = st.columns([1, 1, 1, 1])
                with cc1:
                    _tp_mode = p_selectbox(
                        "ความถี่",
                        field=f_mode,
                        options=["once", "multi"],
                        default="once",
                        format_func=lambda m: "ครั้งเดียว" if m == "once" else "หลายปี",
                    )
                with cc2:
                    p_number_input(
                        SC("year"),
                        field=f_year,
                        default=date.today().year,
                        min_value=YEAR_MIN_DEFAULT,
                        max_value=YEAR_MAX_DEFAULT,
                        step=1,
                        format="%d",
                        cast=int,
                    )
                with cc3:
                    p_number_input(
                        SC("amount"),
                        field=f_amount,
                        default=300000.0,
                        min_value=0.0,
                        step=1000.0,
                        format="%.0f",
                        cast=float,
                    )
                with cc4:
                    p_text_input(SC("note_optional"), field=f_note, default="")

                _oy = int(draft_get(f_year))
                _oamt = float(draft_get(f_amount))
                _onote = _none_if_blank(draft_get(f_note))
                _topup_amt_by_year[_oy] = _topup_amt_by_year.get(_oy, 0.0) + _oamt
                if _onote and _oy not in _topup_note_by_year:
                    _topup_note_by_year[_oy] = _onote
                _topup_raw_count += 1

    # รวม top-up ที่ปีทับซ้อนกันให้เป็นปีละ 1 รายการ (ยอดรวม) — กัน
    # duplicate-year error และให้ปีเดียวกันบวกยอดกันตามที่ผู้ใช้คาดหวัง.
    annual_topups = [
        AnnualTopup(
            year=_y,
            amount=_topup_amt_by_year[_y],
            note=_topup_note_by_year.get(_y),
        )
        for _y in sorted(_topup_amt_by_year)
    ]
    if len(annual_topups) < _topup_raw_count:
        st.caption(
            "ℹ️ มีปีที่ทับซ้อนกัน — ระบบรวมยอดเงินก้อนพิเศษของปีนั้นให้อัตโนมัติแล้ว"
        )

    # Add button ที่ท้ายลิสต์ (ใช้แทนปุ่ม ➕/➖ ที่เคยอยู่ header)
    if st.button(
        "➕ เพิ่มเงินก้อนพิเศษ",
        key="btn_add_topup_bottom",
        width="stretch",
        disabled=n_topups >= MAX_N_TOPUPS,
    ):
        draft_set("n_topups", n_topups + 1)
        st.rerun()

    saving_plan = SavingPlan(
        initial_savings=initial_savings,
        monthly_contribution=monthly_contribution,
        saving_start_year=saving_start_year,
        annual_topups=annual_topups,
    )
    return saving_plan, initial_savings, monthly_contribution, n_topups


# ============================================================
# SECTION 4: ASSUMPTIONS
# ============================================================
def render_section_assumptions():
    """Render the Assumptions section. Returns the Assumptions dataclass."""
    st.header(S("p1", "sec4_header"))

    basic_a0, basic_a1 = st.columns(2)

    with basic_a0:
        p_percent_input(
            S("p1", "label_general_infl"),
            field="general_inflation_rate",
            default_decimal=0.03,
            min_value=0.0,
            max_value=RATE_MAX_PCT,
            step=0.5,
            format="%.1f",
            help=S("p1", "label_general_infl_help"),
        )

    with basic_a1:
        p_percent_input(
            S("p1", "label_edu_infl"),
            field="education_inflation_rate",
            default_decimal=0.05,
            min_value=0.0,
            max_value=RATE_MAX_PCT,
            step=0.5,
            format="%.1f",
            help=S("p1", "label_edu_infl_help"),
        )

    # Investment return input hidden — forced to 0% by default.
    # Users can override via Page 2 re-simulation expander if needed.
    draft_set("investment_return_rate", 0.0)

    with st.expander(S("p1", "advanced_assump"), expanded=False):
        a1, a2 = st.columns(2)

        with a1:
            p_selectbox(
                S("p1", "label_compound_mode"),
                field="return_compound_mode",
                options=["yearly", "monthly"],
                default="yearly",
                format_func=compound_mode_label,
            )

        with a2:
            p_selectbox(
                S("p1", "label_expense_timing"),
                field="expense_timing",
                options=["start_of_year", "midyear", "end_of_year"],
                default="end_of_year",
                format_func=expense_timing_label,
            )

    assumptions = Assumptions(
        start_year=int(draft_get("assump_start_year")),
        general_inflation_rate=float(draft_get("general_inflation_rate")),
        education_inflation_rate=float(draft_get("education_inflation_rate")),
        investment_return_rate=float(draft_get("investment_return_rate")),
        return_compound_mode=draft_get("return_compound_mode"),
        expense_timing=draft_get("expense_timing"),
        open_recurring_default_years=int(draft_get("open_recurring_default_years")),
        inflation_base_year=_to_optional_int(draft_get("inflation_base_year")),
        auto_add_th_international_highschool_before_university=bool(draft_get("auto_add_hs")),
        default_highschool_start_age=int(draft_get("default_highschool_start_age")),
        default_highschool_end_age=int(draft_get("default_highschool_end_age")),
    )
    return assumptions


# ============================================================
# SECTION 5: REVIEW & RUN
# ============================================================
def render_section_review_and_run(
    *,
    children,
    parent_expenses,
    saving_plan,
    assumptions,
    n_children,
    total_edu_plans,
    total_child_extra,
    n_parent_expenses,
    n_topups,
    initial_savings,
    monthly_contribution,
):
    """Render the Review & Run section and execute the simulation on click."""
    input_errors = collect_input_errors(
        children=children,
        parent_expenses=parent_expenses,
        saving_plan=saving_plan,
        assumptions=assumptions,
    )
    input_warnings = collect_input_warnings(
        children=children,
        parent_expenses=parent_expenses,
        saving_plan=saving_plan,
        assumptions=assumptions,
    )

    with st.sidebar:
        st.markdown(S("sidebar", "snapshot_header"))
        st.metric(S("sidebar", "metric_children"), int(n_children))
        st.metric(S("sidebar", "metric_edu_plans"), int(total_edu_plans))
        st.metric(S("sidebar", "metric_parent_exp"), int(n_parent_expenses))
        st.metric(S("sidebar", "metric_monthly"), f"{float(monthly_contribution):,.0f}")
        st.metric(S("sidebar", "metric_initial"), f"{float(initial_savings):,.0f}")

    st.header(S("p1", "sec5_header"))

    if input_errors:
        for msg in input_errors:
            st.error(msg)

    if input_warnings:
        for msg in input_warnings:
            st.warning(msg)

    _ri = S("p1", "review_col_item")
    _rv = S("p1", "review_col_value")
    with st.expander(S("p1", "review_expander"), expanded=False):
        # ── Overall summary table ──
        st.markdown("**ภาพรวม**")
        review_df = pd.DataFrame([
            {_ri: S("p1", "review_children"),        _rv: f"{int(n_children):,}"},
            {_ri: S("p1", "review_edu_plans"),       _rv: f"{int(total_edu_plans):,}"},
            {_ri: S("p1", "review_child_extra"),     _rv: f"{int(total_child_extra):,}"},
            {_ri: S("p1", "review_parent_exp"),      _rv: f"{int(n_parent_expenses):,}"},
            {_ri: S("p1", "review_topups"),          _rv: f"{int(n_topups):,}"},
            {_ri: S("p1", "review_initial_savings"), _rv: f"{float(initial_savings):,.0f}"},
            {_ri: S("p1", "review_monthly"),         _rv: f"{float(monthly_contribution):,.0f}"},
            {_ri: S("p1", "review_general_infl"),    _rv: f"{float(draft_get('general_inflation_rate'))*100:.1f}%"},
            {_ri: S("p1", "review_edu_infl"),        _rv: f"{float(draft_get('education_inflation_rate'))*100:.1f}%"},
            {_ri: S("p1", "review_invest_return"),   _rv: f"{float(draft_get('investment_return_rate'))*100:.1f}%"},
        ])
        st.dataframe(review_df, width="stretch", hide_index=True)

        # ── Per-child breakdown ──
        if children:
            st.markdown("**รายละเอียดรายลูก**")
            per_child_rows = []
            for idx, c in enumerate(children, start=1):
                # อ้างถึง EducationPlan / ExtraExpense จาก simulation_core
                edu_summary = ", ".join(
                    f"{edu_level_label(p.level)} ({p.start_age}-{p.end_age})"
                    for p in c.education_plan
                ) or "—"
                total_edu_cost_today = sum(float(p.annual_cost) for p in c.education_plan)
                per_child_rows.append({
                    "ลูก": c.name,
                    "วันเกิด": c.birth_date,
                    "เพศ": gender_label(c.gender),
                    "จำนวนระดับการศึกษา": f"{len(c.education_plan):,}",
                    "ช่วงการศึกษา": edu_summary,
                    "รวมค่าเล่าเรียน/ปี (ปีฐาน)": f"{total_edu_cost_today:,.0f}",
                    "รายจ่ายเพิ่มเติม": f"{len(c.extra_expenses):,}",
                })
            child_df = pd.DataFrame(per_child_rows)
            # cast object columns to str (Arrow consistency, เหมือนตอน footer)
            for _col in child_df.columns:
                if child_df[_col].dtype == object:
                    child_df[_col] = child_df[_col].astype(str)
            st.dataframe(child_df, width="stretch", hide_index=True)

        # ── Per-child education plan detail ──
        if children and any(c.education_plan for c in children):
            st.markdown("**แผนการศึกษารายลูก**")
            edu_rows = []
            for c in children:
                for plan in c.education_plan:
                    edu_rows.append({
                        "ลูก": c.name,
                        "ระดับ": edu_level_label(plan.level),
                        "ประเทศ": plan.country or "—",
                        "ประเภท": school_type_label(plan.school_type) if plan.school_type else "—",
                        "โรงเรียน": plan.school_name or "—",
                        "อายุเริ่ม-จบ": f"{plan.start_age}-{plan.end_age}",
                        "ค่าเล่าเรียน/ปี (ปีฐาน)": f"{float(plan.annual_cost):,.0f}",
                        "ปีฐาน": (
                            f"{int(plan.cost_basis_year)}"
                            if plan.cost_basis_year is not None
                            else "ใช้ค่าจากสมมติฐาน"
                        ),
                        "อัตราเพิ่ม/ปี": (
                            f"{float(plan.cost_growth_rate)*100:.1f}%"
                            if plan.cost_growth_rate is not None
                            else "ใช้ค่าจากสมมติฐาน"
                        ),
                    })
            edu_df = pd.DataFrame(edu_rows)
            for _col in edu_df.columns:
                if edu_df[_col].dtype == object:
                    edu_df[_col] = edu_df[_col].astype(str)
            st.dataframe(edu_df, width="stretch", hide_index=True)

    _run_cust_id = normalize_cust_id(draft_get("cust_id", ""))
    _run_cust_id_error = cust_id_validation_error(_run_cust_id)
    _can_run = (_run_cust_id_error is None) and (not input_errors)

    if _run_cust_id_error:
        st.info(S("p1", "cid_gate_info", error=_run_cust_id_error))

    run_clicked = st.button(
        S("p1", "btn_run"),
        type="primary",
        width="stretch",
        disabled=not _can_run,
    )

    # ============================================================
    # EXECUTE SIMULATION
    # ============================================================
    if run_clicked:
        persist_all_widget_buffers()
        _final_cust_id = normalize_cust_id(draft_get("cust_id", ""))
        _final_cust_id_error = cust_id_validation_error(_final_cust_id)
        if _final_cust_id_error:
            st.error(_final_cust_id_error)
            st.stop()
        if input_errors:
            for msg in input_errors:
                st.error(msg)
            st.stop()
        _owner_err = draft_owner_error(_final_cust_id)
        if _owner_err:
            st.error(_owner_err)
            st.stop()
        try:
            expense_df, saving_df, summary_df = simulate_education_plan(
                children=children,
                saving_plan=saving_plan,
                assumptions=assumptions,
                parent_expenses=parent_expenses,
            )

            st.session_state["expense_df"] = expense_df
            st.session_state["saving_df"] = saving_df
            st.session_state["summary_df"] = summary_df
            st.session_state["simulation_ran"] = True

            st.session_state["saving_plan_obj"] = saving_plan
            st.session_state["assumptions_obj"] = assumptions
            st.session_state["children_obj"] = children
            st.session_state["parent_expenses_obj"] = parent_expenses

            st.session_state["input_snapshot"] = {
                "n_children": int(n_children),
                "education_plans": int(total_edu_plans),
                "child_extra_expenses": int(total_child_extra),
                "parent_expenses": int(n_parent_expenses),
                "annual_topups": int(n_topups),
            }

            try:
                db_save_draft(
                    _final_cust_id,
                    dict(st.session_state["draft"]),
                    staff_id=st.session_state.get("staff_id", ""),
                )
            except Exception as save_err:
                st.warning(S("p1", "save_warn", error=save_err))

            st.success(S("p1", "sim_success"))

            switch_page_with_persist("pages/02_Expense_Simulation.py")

        except Exception as e:
            st.error(S("p1", "sim_failed", error=e))

    # ============================================================
    # FOOTER PREVIEW
    # ============================================================
    if st.session_state.get("simulation_ran"):
        with st.expander(S("p1", "footer_expander"), expanded=False):
            latest_summary_df = st.session_state.get("summary_df")
            if isinstance(latest_summary_df, pd.DataFrame) and not latest_summary_df.empty:
                _disp = latest_summary_df.copy()
                # Arrow ต้องการ column ที่ type เดียวกัน — cast object columns เป็น str
                # กัน error เดียวกับ Page 2 (column "ค่า" ผสม '2,000,000' str กับ int)
                for _col in _disp.columns:
                    if _disp[_col].dtype == object:
                        _disp[_col] = _disp[_col].astype(str)
                st.dataframe(_disp, width="stretch")
