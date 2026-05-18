"""
Static option lists, education-plan presets, cust_id validation, and
input-warning collection for Page 1.

Pulled out of 01_User_Information.py to keep the page file focused on
layout/rendering.
"""
import re
import pandas as pd

from strings import (
    S,
    edu_level_label, school_type_label,
)
from state import draft_get, set_field_value
from school_fees import schools_for_level, lookup as lookup_school_fee, CUSTOM_SCHOOL_SENTINEL


# ============================================================
# OPTION LISTS / LABEL MAPS
# ============================================================
EDU_LEVEL_OPTIONS = [
    "kindergarten",
    "elementary",
    "middle_school",
    "high_school",
    "bachelor",
    "master",
    "doctor",
    "other",
]

EDU_LEVEL_LABELS = {k: edu_level_label(k) for k in [
    "kindergarten", "elementary", "middle_school", "high_school",
    "bachelor", "master", "doctor", "other",
]}

SCHOOL_TYPE_OPTIONS = [
    "international",
    "government",
    "private",
    "foreign_university",
    "other",
]

SCHOOL_TYPE_LABELS = {k: school_type_label(k) for k in [
    "international", "government", "private", "foreign_university", "other",
]}

COUNTRY_OPTIONS = ["", "TH", "US", "UK", "AU", "JP", "SG", "CN", "DE", "Other"]


# ============================================================
# EDUCATION PRESETS
# ============================================================
EDU_DEFAULT_PRESETS = {
    "kindergarten": {
        "country": "TH",
        "school_type": "international",
        "school_name": "",
        "start_age": 4,
        "end_age": 6,
        "annual_cost": 200_000.0,
        "cost_growth_rate": 0.03,
        "cost_basis_year": 2026,
        "note": "",
    },
    "elementary": {
        "country": "TH",
        "school_type": "international",
        "school_name": "",
        "start_age": 7,
        "end_age": 12,
        "annual_cost": 500_000.0,
        "cost_growth_rate": 0.03,
        "cost_basis_year": 2026,
        "note": "",
    },
    "middle_school": {
        "country": "TH",
        "school_type": "international",
        "school_name": "",
        "start_age": 13,
        "end_age": 15,
        "annual_cost": 800_000.0,
        "cost_growth_rate": 0.03,
        "cost_basis_year": 2026,
        "note": "",
    },
    "high_school": {
        "country": "TH",
        "school_type": "international",
        "school_name": "",
        "start_age": 16,
        "end_age": 18,
        "annual_cost": 1_000_000.0,
        "cost_growth_rate": 0.03,
        "cost_basis_year": 2026,
        "note": "",
    },
    "bachelor": {
        "country": "US",
        "school_type": "foreign_university",
        "school_name": "",
        "start_age": 19,
        "end_age": 22,
        "annual_cost": 3_000_000.0,
        "cost_growth_rate": 0.03,
        "cost_basis_year": 2026,
        "note": "",
    },
    "master": {
        "country": "US",
        "school_type": "foreign_university",
        "school_name": "",
        "start_age": 23,
        "end_age": 24,
        "annual_cost": 3_000_000.0,
        "cost_growth_rate": 0.03,
        "cost_basis_year": 2026,
        "note": "",
    },
    "doctor": {
        "country": "US",
        "school_type": "international",
        "school_name": "",
        "start_age": 25,
        "end_age": 27,
        "annual_cost": 3_000_000,
        "cost_growth_rate": 0.03,
        "cost_basis_year": 2026,
        "note": "",
    },
    "other": {
        "country": "TH",
        "school_type": "international",
        "school_name": "",
        "start_age": 4,
        "end_age": 6,
        "annual_cost": 200_000.0,
        "cost_growth_rate": 0.03,
        "cost_basis_year": 2026,
        "note": "",
    },
}

DEFAULT_EDU_ROW_ORDER = [
    "kindergarten",
    "elementary",
    "middle_school",
    "high_school",
    "bachelor",
    "master",
    "doctor",
]


def get_default_level_for_row(row_idx: int) -> str:
    if row_idx < len(DEFAULT_EDU_ROW_ORDER):
        return DEFAULT_EDU_ROW_ORDER[row_idx]
    return "other"


def apply_edu_preset_to_draft(child_idx: int, edu_idx: int, level: str):
    preset = EDU_DEFAULT_PRESETS.get(level, EDU_DEFAULT_PRESETS["other"])

    field_map = {
        f"child.{child_idx}.edu.{edu_idx}.level": level,
        f"child.{child_idx}.edu.{edu_idx}.country": preset["country"],
        f"child.{child_idx}.edu.{edu_idx}.school_type": preset["school_type"],
        f"child.{child_idx}.edu.{edu_idx}.school_name": preset["school_name"],
        f"child.{child_idx}.edu.{edu_idx}.start_age": preset["start_age"],
        f"child.{child_idx}.edu.{edu_idx}.end_age": preset["end_age"],
        f"child.{child_idx}.edu.{edu_idx}.annual_cost": preset["annual_cost"],
        f"child.{child_idx}.edu.{edu_idx}.show_advanced": False,
        f"child.{child_idx}.edu.{edu_idx}.cost_growth_rate": preset["cost_growth_rate"],
        f"child.{child_idx}.edu.{edu_idx}.cost_basis_year": preset["cost_basis_year"],
        f"child.{child_idx}.edu.{edu_idx}.note": preset["note"],
    }

    for field, value in field_map.items():
        set_field_value(field, value)


def _on_edu_level_change(child_idx: int, edu_idx: int, level_field: str):
    """When education level changes: refresh start/end age from the preset and
    reset the school selection (schools list is per-level)."""
    new_level = draft_get(level_field, "")
    preset = EDU_DEFAULT_PRESETS.get(new_level, EDU_DEFAULT_PRESETS["other"])
    set_field_value(f"child.{child_idx}.edu.{edu_idx}.start_age", preset["start_age"])
    set_field_value(f"child.{child_idx}.edu.{edu_idx}.end_age", preset["end_age"])
    set_field_value(f"child.{child_idx}.edu.{edu_idx}.school_name", "")


def _on_school_select(child_idx: int, edu_idx: int, sb_key: str, level_field: str):
    """Selectbox callback: when a known school is picked, autofill country,
    school_type and annual_cost from the CSV. (custom) leaves user to type."""
    import streamlit as st
    chosen = st.session_state.get(sb_key, CUSTOM_SCHOOL_SENTINEL)
    sn_field = f"child.{child_idx}.edu.{edu_idx}.school_name"
    level = draft_get(level_field, "")

    if chosen == CUSTOM_SCHOOL_SENTINEL:
        prev = draft_get(sn_field, "") or ""
        if prev in schools_for_level(level):
            set_field_value(sn_field, "")
        return

    set_field_value(sn_field, chosen)
    row = lookup_school_fee(level, chosen)
    if row is None:
        return

    country = row.get("country") or ""
    school_type = row.get("school_type") or ""
    if country:
        set_field_value(f"child.{child_idx}.edu.{edu_idx}.country", country)
    if school_type:
        set_field_value(f"child.{child_idx}.edu.{edu_idx}.school_type", school_type)
    ac = row.get("annual_cost")
    try:
        if ac is not None and not pd.isna(ac):
            set_field_value(f"child.{child_idx}.edu.{edu_idx}.annual_cost", float(ac))
    except (TypeError, ValueError):
        pass


def load_standard_education_template(child_idx: int, n_rows: int):
    set_field_value(f"child.{child_idx}.n_edu", int(n_rows))
    for row_idx in range(int(n_rows)):
        apply_edu_preset_to_draft(
            child_idx=child_idx,
            edu_idx=row_idx,
            level=get_default_level_for_row(row_idx),
        )


# ============================================================
# CUST_ID VALIDATION
# ============================================================
CUST_ID_REQUIRED_LEN = 10
CUST_ID_MAX_LEN = 10  # kept for backward-compat with code referencing the cap
CUST_ID_PATTERN = re.compile(r"^\d+$")


def normalize_cust_id(raw: str) -> str:
    """Strip whitespace from a raw cust_id input."""
    return str(raw or "").strip()


def cust_id_validation_error(cust_id: str):
    """
    Returns an error message string if invalid, else None.
    Rule: numeric only, length must be exactly 30 digits.
    """
    if not cust_id:
        return S("p1", "cid_err_empty")
    if not CUST_ID_PATTERN.match(cust_id):
        return S("p1", "cid_err_digits")
    if len(cust_id) != CUST_ID_REQUIRED_LEN:
        return S("p1", "cid_err_exact", required=CUST_ID_REQUIRED_LEN, got=len(cust_id))
    return None


# ============================================================
# INPUT VALIDATION
# ============================================================
# Errors block the Run button (would otherwise feed garbage to the simulator
# or trip ValueError mid-run). Warnings inform the user but allow Run.
def collect_input_errors(children, parent_expenses, saving_plan, assumptions):
    errors = []

    for child in children:
        for plan in child.education_plan:
            if plan.start_age > plan.end_age:
                errors.append(S("warn", "edu_age_range", child=child.name, level=edu_level_label(plan.level)))

        for ex in child.extra_expenses:
            if ex.year is not None and ex.end_year is not None and ex.year > ex.end_year:
                errors.append(S("warn", "child_extra_year_range", name=ex.name, child=child.name))
            if ex.start_age is not None and ex.end_age is not None and ex.start_age > ex.end_age:
                errors.append(S("warn", "child_extra_age_range", name=ex.name, child=child.name))

    for ex in parent_expenses:
        if ex.year is not None and ex.end_year is not None and ex.year > ex.end_year:
            errors.append(S("warn", "parent_year_range", name=ex.name))

    if assumptions.default_highschool_start_age > assumptions.default_highschool_end_age:
        errors.append(S("warn", "hs_age_range"))

    if saving_plan.monthly_contribution < 0:
        errors.append(S("warn", "negative_contribution"))

    return errors


def collect_input_warnings(children, parent_expenses, saving_plan, assumptions):
    warnings = []

    for child in children:
        if not str(child.name).strip():
            warnings.append(S("warn", "child_name_empty"))

    return warnings
