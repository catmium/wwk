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

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title=S("p1", "page_title"),
    page_icon="📘",
    layout="wide",
)

# ============================================================
# HELPERS
# ============================================================
def _none_if_blank(text):
    if text is None:
        return None
    text = str(text).strip()
    return None if text == "" else text


def _to_optional_int(text):
    text = _none_if_blank(text)
    if text is None:
        return None
    return int(text)


def _widget_key(field: str) -> str:
    return f"w__{field}"


def _ensure_state(key, default):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


def init_app_state():
    """
    Single source of truth:
    - st.session_state["draft"] : all user inputs
    - st.session_state["expense_df"], saving_df, summary_df : simulation outputs
    """
    _ensure_state("draft", {})
    _ensure_state("simulation_ran", False)
    _ensure_state("expense_df", None)
    _ensure_state("saving_df", None)
    _ensure_state("summary_df", None)
    _ensure_state("input_snapshot", None)

    draft = st.session_state["draft"]
    today_year = date.today().year

    defaults = {
        "n_children": 1,
        "n_parent_expenses": 0,
        "n_topups": 0,
        "initial_savings": 2_000_000.0,
        "monthly_contribution": 50_000.0,
        "saving_start_year": today_year,
        "assump_start_year": today_year,
        "general_inflation_rate": 0.02,
        "education_inflation_rate": 0.03,
        "investment_return_rate": 0.04,
        "return_compound_mode": "yearly",
        "expense_timing": "end_of_year",
        "open_recurring_default_years": 5,
        "inflation_base_year": str(today_year),
        "auto_add_hs": False,
        "default_highschool_start_age": 16,
        "default_highschool_end_age": 18,
    }

    for k, v in defaults.items():
        draft.setdefault(k, v)


def draft_get(field, default=None):
    return st.session_state["draft"].get(field, default)


def draft_set(field, value):
    st.session_state["draft"][field] = value


def set_field_value(field, value):
    """
    Update both source-of-truth and current widget buffer.
    Useful for template loading / programmatic preset.
    """
    draft_set(field, value)
    st.session_state[_widget_key(field)] = value


def ensure_widget_buffer(field, default):
    """
    Make widget buffer reflect draft on first render only.
    """
    if field not in st.session_state["draft"]:
        st.session_state["draft"][field] = default

    wkey = _widget_key(field)
    if wkey not in st.session_state:
        st.session_state[wkey] = st.session_state["draft"][field]


def on_widget_change(field, cast=None):
    val = st.session_state[_widget_key(field)]
    if cast is not None and val is not None:
        try:
            val = cast(val)
        except Exception:
            pass
    draft_set(field, val)


def persist_all_widget_buffers():
    """
    Force copy all current widget buffers into draft.
    This is the critical commit step before navigation.
    """
    for key, value in st.session_state.items():
        if key.startswith("w__"):
            field = key[3:]
            st.session_state["draft"][field] = value


def switch_page_with_persist(page_path: str):
    persist_all_widget_buffers()
    st.switch_page(page_path)


# ============================================================
# PERSISTENT WIDGETS
# ============================================================
def p_text_input(label, field, default="", **kwargs):
    ensure_widget_buffer(field, default)
    st.text_input(
        label,
        key=_widget_key(field),
        on_change=on_widget_change,
        args=(field, str),
        **kwargs,
    )
    return draft_get(field, default)


def p_text_area(label, field, default="", **kwargs):
    ensure_widget_buffer(field, default)
    st.text_area(
        label,
        key=_widget_key(field),
        on_change=on_widget_change,
        args=(field, str),
        **kwargs,
    )
    return draft_get(field, default)


def p_number_input(label, field, default, cast=None, **kwargs):
    ensure_widget_buffer(field, default)
    st.number_input(
        label,
        key=_widget_key(field),
        on_change=on_widget_change,
        args=(field, cast),
        **kwargs,
    )
    return draft_get(field, default)


def p_selectbox(label, field, options, default, format_func=None, **kwargs):
    if draft_get(field, default) not in options:
        draft_set(field, default)

    ensure_widget_buffer(field, default)

    current_value = draft_get(field, default)
    if current_value not in options:
        current_value = default
        set_field_value(field, default)

    index = options.index(current_value)

    selectbox_kwargs = dict(
        label=label,
        options=options,
        index=index,
        key=_widget_key(field),
        on_change=on_widget_change,
        args=(field, None),
        **kwargs,
    )
    if format_func is not None:
        selectbox_kwargs["format_func"] = format_func

    st.selectbox(**selectbox_kwargs)
    return draft_get(field, default)


def p_checkbox(label, field, default=False, **kwargs):
    ensure_widget_buffer(field, default)
    st.checkbox(
        label,
        key=_widget_key(field),
        on_change=on_widget_change,
        args=(field, bool),
        **kwargs,
    )
    return draft_get(field, default)


def p_date_input(label, field, default, **kwargs):
    ensure_widget_buffer(field, default)
    st.date_input(
        label,
        key=_widget_key(field),
        on_change=on_widget_change,
        args=(field, None),
        **kwargs,
    )
    return draft_get(field, default)


def p_percent_input(label, field, default_decimal, **kwargs):
    """
    Display a decimal rate (e.g. 0.03) as a percentage (3.0) in the widget.
    Draft stores decimal; widget shows percent. Converts on change.
    """
    pct_field = f"{field}__pct_display"
    wkey = _widget_key(pct_field)

    decimal_val = draft_get(field, default_decimal)
    if wkey not in st.session_state:
        st.session_state[wkey] = round(float(decimal_val) * 100, 4)

    def _on_pct_change():
        pct_val = st.session_state[wkey]
        draft_set(field, round(float(pct_val) / 100, 8))

    st.number_input(label, key=wkey, on_change=_on_pct_change, **kwargs)
    return draft_get(field, default_decimal)


# ============================================================
# PRESETS / LOOKUPS
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


def load_standard_education_template(child_idx: int, n_rows: int):
    set_field_value(f"child.{child_idx}.n_edu", int(n_rows))
    for row_idx in range(int(n_rows)):
        apply_edu_preset_to_draft(
            child_idx=child_idx,
            edu_idx=row_idx,
            level=get_default_level_for_row(row_idx),
        )


# ============================================================
# VALIDATION
# ============================================================
def collect_input_warnings(children, parent_expenses, saving_plan, assumptions):
    warnings = []

    for child in children:
        if not str(child.name).strip():
            warnings.append(S("warn", "child_name_empty"))

        for plan in child.education_plan:
            if plan.start_age > plan.end_age:
                warnings.append(S("warn", "edu_age_range", child=child.name, level=edu_level_label(plan.level)))

        for ex in child.extra_expenses:
            if ex.year is not None and ex.end_year is not None and ex.year > ex.end_year:
                warnings.append(S("warn", "child_extra_year_range", name=ex.name, child=child.name))
            if ex.start_age is not None and ex.end_age is not None and ex.start_age > ex.end_age:
                warnings.append(S("warn", "child_extra_age_range", name=ex.name, child=child.name))

    for ex in parent_expenses:
        if ex.year is not None and ex.end_year is not None and ex.year > ex.end_year:
            warnings.append(S("warn", "parent_year_range", name=ex.name))

    if assumptions.default_highschool_start_age > assumptions.default_highschool_end_age:
        warnings.append(S("warn", "hs_age_range"))

    if saving_plan.monthly_contribution < 0:
        warnings.append(S("warn", "negative_contribution"))

    return warnings


# ============================================================
# INIT
# ============================================================
init_app_state()
draft = st.session_state["draft"]

# ============================================================
# SIDEBAR: WORKFLOW PROGRESS
# ============================================================
with st.sidebar:
    st.markdown(S("sidebar", "workflow_header"))
    sim_ran = st.session_state.get("simulation_ran", False)

    st.markdown(S("sidebar", "step1_active") if not sim_ran else S("sidebar", "step1_done"))
    st.markdown(S("sidebar", "step2_done") if sim_ran else S("sidebar", "step2"))
    st.markdown(S("sidebar", "step3"))
    st.markdown("---")


# ============================================================
# PAGE TITLE
# ============================================================
st.title(S("p1", "title"))
st.caption(S("p1", "caption"))

st.markdown("---")

# ============================================================
# SECTION 1: CHILD EXPENSES
# ============================================================
# with st.container(border=True):
st.header(S("p1", "sec1_header"))
st.caption(S("p1", "sec1_caption"))

n_children = int(draft_get("n_children", 1))

# ── Fee Reference link button ──
_fee_ref_col, _fee_space = st.columns([2, 4])
with _fee_ref_col:
    if st.button(S("p1", "btn_fee_reference"), key="btn_fee_reference", use_container_width=True):
        switch_page_with_persist("pages/04_School_Fees_Reference.py")

_c_label, _c_add, _c_rem, _c_space = st.columns([1, 1, 1, 2])
with _c_label:
    st.metric(S("p1", "metric_n_children"), n_children)
with _c_add:
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    if st.button(S("p1", "btn_add_child"), key="btn_add_child", use_container_width=True, disabled=n_children >= 10):
        draft_set("n_children", n_children + 1)
        st.rerun()
with _c_rem:
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    if st.button(S("p1", "btn_rem_child"), key="btn_rem_child", use_container_width=True, disabled=n_children <= 0):
        draft_set("n_children", n_children - 1)
        st.rerun()

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
                p_text_input(S("p1", "label_child_name"), field=field_name, default=f"Child {i+1}")

            with c2:
                p_selectbox(
                    S("p1", "label_gender"),
                    field=field_gender,
                    options=["M", "F", "Other"],
                    default="M",
                    format_func=gender_label,
                )

            with c3:
                p_date_input(S("p1", "label_birth_date"), field=field_birth, default=date(2022, 1, 1))

        # ----------------------------------------------------
        # TAB 2: EDUCATION PLANS
        # ----------------------------------------------------
        with tab_edu:
            st.caption(S("p1", "edu_caption"))

            n_edu = int(draft_get(field_n_edu, 5))
            _e_label, _e_add, _e_rem, _e_space = st.columns([2, 1, 1, 3.5])
            with _e_label:
                st.metric(S("p1", "metric_n_edu"), n_edu)
            with _e_add:
                st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                if st.button("➕", key=f"btn_add_edu_{i}", use_container_width=True, disabled=n_edu >= 20):
                    draft_set(field_n_edu, n_edu + 1)
                    st.rerun()
            with _e_rem:
                st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                if st.button("🗑", key=f"btn_rem_edu_{i}", use_container_width=True, disabled=n_edu <= 0):
                    draft_set(field_n_edu, n_edu - 1)
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
                f_show_advanced = f"child.{i}.edu.{j}.show_advanced"
                f_cost_growth = f"child.{i}.edu.{j}.cost_growth_rate"
                f_cost_basis = f"child.{i}.edu.{j}.cost_basis_year"
                f_note = f"child.{i}.edu.{j}.note"

                # init defaults in single source of truth
                draft.setdefault(f_level, default_level)
                draft.setdefault(f_country, default_preset["country"])
                draft.setdefault(f_school_type, default_preset["school_type"])
                draft.setdefault(f_school_name, default_preset["school_name"])
                draft.setdefault(f_start_age, default_preset["start_age"])
                draft.setdefault(f_end_age, default_preset["end_age"])
                draft.setdefault(f_annual_cost, float(default_preset["annual_cost"]))
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
                        st.empty()
                        # if st.button(
                        #     S("p1", "btn_reset_preset"),
                        #     key=f"use_default_{i}_{j}",
                        #     use_container_width=True,
                        # ):
                        #     apply_edu_preset_to_draft(
                        #         child_idx=i,
                        #         edu_idx=j,
                        #         level=draft_get(f_level, default_level),
                        #     )
                        #     st.rerun()

                    # ── Row 1: Primary fields (always visible) ──
                    e1, e2, e3, e4 = st.columns(4)

                    with e1:
                        p_selectbox(
                            S("p1", "label_edu_level"),
                            field=f_level,
                            options=EDU_LEVEL_OPTIONS,
                            default=default_level,
                            format_func=edu_level_label,
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
                        p_number_input(
                            S("p1", "label_annual_cost"),
                            field=f_annual_cost,
                            default=float(default_preset["annual_cost"]),
                            min_value=0.0,
                            step=10_000.0,
                            format="%.0f",
                            cast=float,
                        )

                    # ── Row 2: School details (always visible) ──
                    _country_default = default_preset.get("country", "")
                    if _country_default not in COUNTRY_OPTIONS:
                        _country_default = ""

                    s1, s2, s3, s4 = st.columns(4)

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
                        p_text_input(
                            S("p1", "label_school_name"),
                            field=f_school_name,
                            default=default_preset["school_name"],
                        )

                    with s4:
                        p_text_input(S("p1", "label_note"), field=f_note, default=default_preset["note"])

                    # ── Slim expander: growth rate override ──
                    with st.expander(S("p1", "edu_advanced_expander"), expanded=False):
                        e9, e10 = st.columns(2)

                        with e9:
                            cost_growth_rate = p_percent_input(
                                S("p1", "label_cost_growth_rate"),
                                field=f_cost_growth,
                                default_decimal=float(default_preset["cost_growth_rate"]),
                                min_value=0.0,
                                max_value=30.0,
                                step=0.5,
                                format="%.1f",
                            )

                        with e10:
                            cost_basis_year = int(
                                p_number_input(
                                    S("p1", "label_cost_basis_year"),
                                    field=f_cost_basis,
                                    default=2026,
                                    min_value=2026,
                                    max_value=2100,
                                    step=1,
                                    format="%d",
                                    cast=int,
                                )
                            )

                    edu_plans.append(
                        EducationPlan(
                            level=draft_get(f_level),
                            country=draft_get(f_country),
                            school_type=draft_get(f_school_type),
                            school_name=_none_if_blank(draft_get(f_school_name)),
                            start_age=int(draft_get(f_start_age)),
                            end_age=int(draft_get(f_end_age)),
                            annual_cost=float(draft_get(f_annual_cost)),
                            cost_growth_rate=cost_growth_rate,
                            cost_basis_year=cost_basis_year,
                            note=_none_if_blank(draft_get(f_note)),
                        )
                    )

        # ----------------------------------------------------
        # TAB 3: CHILD EXTRA EXPENSES
        # ----------------------------------------------------
        with tab_extra:
            st.caption(S("p1", "extra_caption"))

            n_extra = int(draft_get(field_n_extra, 0))
            _x_label, _x_add, _x_rem, _x_space = st.columns([1, 1, 1, 2])
            with _x_label:
                st.metric(S("p1", "metric_n_extra"), n_extra)
            with _x_add:
                st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                if st.button("➕ เพิ่มรายการ", key=f"btn_add_extra_{i}", use_container_width=True, disabled=n_extra >= 30):
                    draft_set(field_n_extra, n_extra + 1)
                    st.rerun()
            with _x_rem:
                st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                if st.button("🗑 ลบรายการล่าสุด", key=f"btn_rem_extra_{i}", use_container_width=True, disabled=n_extra <= 0):
                    draft_set(field_n_extra, n_extra - 1)
                    st.rerun()

            extra_expenses = []

            for j in range(n_extra):
                f_name = f"child.{i}.extra.{j}.name"
                f_amount = f"child.{i}.extra.{j}.amount"
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
                    st.markdown(f"**{S('p1', 'extra_card_header', n=j+1)}**")

                    x1, x2, x3 = st.columns(3)
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
                                    min_value=2020,
                                    max_value=2100,
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
                                        min_value=2020,
                                        max_value=2100,
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
                                        min_value=2020,
                                        max_value=2100,
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
                        ExtraExpense(
                            name=draft_get(f_name),
                            amount=float(draft_get(f_amount)),
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

        children.append(
            Child(
                name=draft_get(field_name),
                gender=draft_get(field_gender),
                birth_date=draft_get(field_birth).strftime("%Y-%m-%d"),
                education_plan=edu_plans,
                extra_expenses=extra_expenses,
            )
        )
st.markdown("---")

# ============================================================
# SECTION 2: PARENT EXPENSES
# ============================================================

st.header(S("p1", "sec2_header"))
st.caption(S("p1", "sec2_caption"))

n_parent_expenses = int(draft_get("n_parent_expenses", 0))
_pe_label, _pe_add, _pe_rem, _pe_space = st.columns([1, 1, 1, 2])
with _pe_label:
    st.metric(S("p1", "metric_n_parent"), n_parent_expenses)
with _pe_add:
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    if st.button(S("p1", "btn_add_parent"), key="btn_add_pe", use_container_width=True, disabled=n_parent_expenses >= 30):
        draft_set("n_parent_expenses", n_parent_expenses + 1)
        st.rerun()
with _pe_rem:
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    if st.button(S("p1", "btn_rem_child"), key="btn_rem_pe", use_container_width=True, disabled=n_parent_expenses <= 0):
        draft_set("n_parent_expenses", n_parent_expenses - 1)
        st.rerun()

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
        st.markdown(f"**{S('p1', 'parent_card_header', n=i+1)}**")

        # ── Row 1: name | amount | type ──
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

        # ── Row 2: ปี | เงินเฟ้อ | หมายเหตุ
        # one_time  : [1]ปี          [1]เงินเฟ้อ [1]หมายเหตุ
        # recurring : [.5]ต้น [.5]จบ [1]เงินเฟ้อ [1]หมายเหตุ  ← ปีต้น+ปีจบ กว้างเท่า ปีครั้งเดียว
        end_year = None

        if current_type == "one_time":
            p4, p5, p6 = st.columns(3)

            with p4:
                p_number_input(
                    SC("year"),
                    field=f_year,
                    default=date.today().year,
                    min_value=1900,
                    max_value=2200,
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
                    min_value=1900,
                    max_value=2200,
                    step=1,
                    format="%d",
                    cast=int,
                )

            with p5:
                end_year = int(
                    p_number_input(
                        SC("end_year"),
                        field=f_end_year,
                        default=2030,
                        min_value=1900,
                        max_value=2200,
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
st.markdown("---")

# ============================================================
# SECTION 3: SAVING PLAN
# ============================================================

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
_tp_label, _tp_add, _tp_rem, _tp_space = st.columns([1, 1, 1, 2])
with _tp_label:
    st.metric(S("p1", "metric_n_topups"), n_topups)
with _tp_add:
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    if st.button(S("p1", "btn_add_topup"), key="btn_add_topup", use_container_width=True, disabled=n_topups >= 20):
        draft_set("n_topups", n_topups + 1)
        st.rerun()
with _tp_rem:
    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
    if st.button(S("p1", "btn_rem_child"), key="btn_rem_topup", use_container_width=True, disabled=n_topups <= 0):
        draft_set("n_topups", n_topups - 1)
        st.rerun()

annual_topups = []
for i in range(n_topups):
    f_year = f"topup.{i}.year"
    f_amount = f"topup.{i}.amount"
    f_note = f"topup.{i}.note"

    draft.setdefault(f_year, date.today().year)
    draft.setdefault(f_amount, 300000.0)
    draft.setdefault(f_note, "")

    with st.container(border=True):
        st.markdown(f"**{S('p1', 'topup_card_header', n=i+1)}**")

        t1, t2, t3 = st.columns(3)

        with t1:
            p_number_input(
                SC("year"),
                field=f_year,
                default=date.today().year,
                min_value=1900,
                max_value=2200,
                step=1,
                format="%d",
                cast=int,
            )

        with t2:
            p_number_input(
                SC("amount"),
                field=f_amount,
                default=300000.0,
                min_value=0.0,
                step=1000.0,
                format="%.0f",
                cast=float,
            )

        with t3:
            p_text_input(SC("note_optional"), field=f_note, default="")

        annual_topups.append(
            AnnualTopup(
                year=int(draft_get(f_year)),
                amount=float(draft_get(f_amount)),
                note=_none_if_blank(draft_get(f_note)),
            )
        )

saving_plan = SavingPlan(
    initial_savings=initial_savings,
    monthly_contribution=monthly_contribution,
    saving_start_year=saving_start_year,
    annual_topups=annual_topups,
)
st.markdown("---")

# ============================================================
# SECTION 4: ASSUMPTIONS
# ============================================================

st.header(S("p1", "sec4_header"))

basic_a0, basic_a1, basic_a2 = st.columns(3)

with basic_a0:
    p_percent_input(
        S("p1", "label_general_infl"),
        field="general_inflation_rate",
        default_decimal=0.03,
        min_value=0.0,
        max_value=30.0,
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
        max_value=30.0,
        step=0.5,
        format="%.1f",
        help=S("p1", "label_edu_infl_help"),
    )

with basic_a2:
    p_percent_input(
        S("p1", "label_invest_return"),
        field="investment_return_rate",
        default_decimal=0.06,
        min_value=0.0,
        max_value=50.0,
        step=0.5,
        format="%.1f",
        help=S("p1", "label_invest_return_help"),
    )

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

    # b1, b2 = st.columns(2)

    # with b1:
    #     p_number_input(
    #         "Open recurring default years",
    #         field="open_recurring_default_years",
    #         default=5,
    #         min_value=1,
    #         max_value=100,
    #         step=1,
    #         format="%d",
    #         cast=int,
    #     )

    # with b2:
    #     p_text_input(
    #         "Inflation base year (optional)",
    #         field="inflation_base_year",
    #         default=str(date.today().year),
    #     )

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
st.markdown("---")

# ============================================================
# SECTION 5: REVIEW & RUN
# ============================================================

total_edu_plans = sum(len(c.education_plan) for c in children)
total_child_extra = sum(len(c.extra_expenses) for c in children)

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

if input_warnings:
    for msg in input_warnings:
        st.warning(msg)

_ri = S("p1", "review_col_item")
_rv = S("p1", "review_col_value")
with st.expander(S("p1", "review_expander"), expanded=False):
    review_df = pd.DataFrame([
        {_ri: S("p1", "review_children"),        _rv: int(n_children)},
        {_ri: S("p1", "review_edu_plans"),        _rv: int(total_edu_plans)},
        {_ri: S("p1", "review_child_extra"),      _rv: int(total_child_extra)},
        {_ri: S("p1", "review_parent_exp"),       _rv: int(n_parent_expenses)},
        {_ri: S("p1", "review_topups"),           _rv: int(n_topups)},
        {_ri: S("p1", "review_initial_savings"),  _rv: f"{float(initial_savings):,.0f}"},
        {_ri: S("p1", "review_monthly"),          _rv: f"{float(monthly_contribution):,.0f}"},
        {_ri: S("p1", "review_general_infl"),     _rv: f"{float(draft_get('general_inflation_rate'))*100:.1f}%"},
        {_ri: S("p1", "review_edu_infl"),         _rv: f"{float(draft_get('education_inflation_rate'))*100:.1f}%"},
        {_ri: S("p1", "review_invest_return"),    _rv: f"{float(draft_get('investment_return_rate'))*100:.1f}%"},
    ])
    st.dataframe(review_df, use_container_width=True, hide_index=True)

run_clicked = st.button(
    S("p1", "btn_run"),
    type="primary",
    use_container_width=True,
)

# ============================================================
# EXECUTE SIMULATION
# ============================================================
if run_clicked:
    persist_all_widget_buffers()
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

        ### add
        st.session_state["saving_plan_obj"] = saving_plan
        st.session_state["assumptions_obj"] = assumptions

        st.session_state["input_snapshot"] = {
            "n_children": int(n_children),
            "education_plans": int(total_edu_plans),
            "child_extra_expenses": int(total_child_extra),
            "parent_expenses": int(n_parent_expenses),
            "annual_topups": int(n_topups),
        }

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
            st.dataframe(latest_summary_df, use_container_width=True)
