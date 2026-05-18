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
from school_fees import schools_for_level, CUSTOM_SCHOOL_SENTINEL

from state import (
    _none_if_blank, _to_optional_int,
    draft_get, draft_set, set_field_value,
    persist_all_widget_buffers, switch_page_with_persist,
    apply_loaded_draft_to_state,
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

    _c_label, _c_add, _c_rem, _c_space = st.columns([1, 1, 1, 2])
    with _c_label:
        st.metric(S("p1", "metric_n_children"), n_children)
    with _c_add:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        if st.button(S("p1", "btn_add_child"), key="btn_add_child", width="stretch", disabled=n_children >= 10):
            draft_set("n_children", n_children + 1)
            st.rerun()
    with _c_rem:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        if st.button(S("p1", "btn_rem_child"), key="btn_rem_child", width="stretch", disabled=n_children <= 0):
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

                # with c1:
                #     p_text_input(S("p1", "label_child_name"), field=field_name, default=f"Child {i+1}")

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
                _e_label, _e_add, _e_rem, _e_space = st.columns([2, 1, 1, 3.5])
                with _e_label:
                    st.metric(S("p1", "metric_n_edu"), n_edu)
                with _e_add:
                    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                    if st.button("➕", key=f"btn_add_edu_{i}", width="stretch", disabled=n_edu >= 20):
                        draft_set(field_n_edu, n_edu + 1)
                        st.rerun()
                with _e_rem:
                    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                    if st.button("🗑", key=f"btn_rem_edu_{i}", width="stretch", disabled=n_edu <= 0):
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

                        # ── Row 1: Primary fields (always visible) ──
                        e1, e2, e3, e4 = st.columns(4)

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
                            p_number_input(
                                S("p1", "label_annual_cost"),
                                field=f_annual_cost,
                                default=float(default_preset["annual_cost"]),
                                min_value=0.0,
                                step=10_000.0,
                                format="%.0f",
                                cast=float,
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
                    if st.button("➕ เพิ่มรายการ", key=f"btn_add_extra_{i}", width="stretch", disabled=n_extra >= 30):
                        draft_set(field_n_extra, n_extra + 1)
                        st.rerun()
                with _x_rem:
                    st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                    if st.button("🗑 ลบรายการล่าสุด", key=f"btn_rem_extra_{i}", width="stretch", disabled=n_extra <= 0):
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

    total_edu_plans = sum(len(c.education_plan) for c in children)
    total_child_extra = sum(len(c.extra_expenses) for c in children)
    return children, n_children, total_edu_plans, total_child_extra


# ============================================================
# SECTION 2: PARENT EXPENSES
# ============================================================
def render_section_parent_expenses(draft):
    """Render the Parent Expenses section. Returns (parent_expenses, n_parent_expenses)."""
    st.header(S("p1", "sec2_header"))
    st.caption(S("p1", "sec2_caption"))

    n_parent_expenses = int(draft_get("n_parent_expenses", 0))
    _pe_label, _pe_add, _pe_rem, _pe_space = st.columns([1, 1, 1, 2])
    with _pe_label:
        st.metric(S("p1", "metric_n_parent"), n_parent_expenses)
    with _pe_add:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        if st.button(S("p1", "btn_add_parent"), key="btn_add_pe", width="stretch", disabled=n_parent_expenses >= 30):
            draft_set("n_parent_expenses", n_parent_expenses + 1)
            st.rerun()
    with _pe_rem:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        if st.button(S("p1", "btn_rem_child"), key="btn_rem_pe", width="stretch", disabled=n_parent_expenses <= 0):
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
    _tp_label, _tp_add, _tp_rem, _tp_space = st.columns([1, 1, 1, 2])
    with _tp_label:
        st.metric(S("p1", "metric_n_topups"), n_topups)
    with _tp_add:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        if st.button(S("p1", "btn_add_topup"), key="btn_add_topup", width="stretch", disabled=n_topups >= 20):
            draft_set("n_topups", n_topups + 1)
            st.rerun()
    with _tp_rem:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        if st.button(S("p1", "btn_rem_child"), key="btn_rem_topup", width="stretch", disabled=n_topups <= 0):
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
    return saving_plan, initial_savings, monthly_contribution, n_topups


# ============================================================
# SECTION 4: ASSUMPTIONS
# ============================================================
def render_section_assumptions():
    """Render the Assumptions section. Returns the Assumptions dataclass."""
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
            
            
