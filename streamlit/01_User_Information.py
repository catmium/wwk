import re
import streamlit as st

from strings import S
from state import init_app_state, ADMIN_STAFF_IDS, hide_admin_pages_from_sidebar
from sections import (
    render_section_cust_id,
    render_section_children,
    render_section_parent_expenses,
    render_section_saving_plan,
    render_section_assumptions,
    render_section_review_and_run,
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
# INIT
# ============================================================
init_app_state()
draft = st.session_state["draft"]

# ซ่อน Page 5 จาก sidebar ถ้าไม่ใช่ admin (ต้องเรียกทุกครั้งที่ render)
hide_admin_pages_from_sidebar()

# ============================================================
# PHASE 1 — WELCOME GATE (Staff ID tracking, ไม่ได้ authenticate)
# ============================================================
if not st.session_state.get("staff_id_verified"):
    st.title("👋 ยินดีต้อนรับสู่ Wealth with Kids Planner")
    st.caption("เครื่องมือวางแผนการเงินสำหรับครอบครัวที่มีลูก — กรุณาระบุ Staff ID เพื่อเข้าใช้งาน")

    with st.container(border=True):
        _sid = st.text_input(
            "Staff ID (ตัวเลข 5 หลัก)",
            max_chars=5,
            key="welcome_staff_id_input",
            placeholder="เช่น 12345",
            help="Staff ID ใช้สำหรับติดตามผู้ใช้งานเท่านั้น ไม่ได้ใช้ในการตรวจสอบสิทธิ์",
        )
        _ok = st.button("🔓 เข้าสู่ระบบ", type="primary", use_container_width="stretch")

        if _ok:
            _sid_clean = (_sid or "").strip()
            if not re.fullmatch(r"\d{5}", _sid_clean):
                st.error("❌ Staff ID ต้องเป็นตัวเลข 5 หลัก เท่านั้น")
            else:
                st.session_state["staff_id"] = _sid_clean
                st.session_state["staff_id_verified"] = True
                st.session_state["is_admin"] = _sid_clean in ADMIN_STAFF_IDS
                st.rerun()

    st.stop()

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



# ============================================================
# SECTIONS
# ============================================================
render_section_cust_id()

children, n_children, total_edu_plans, total_child_extra = render_section_children(draft)
st.markdown("---")

parent_expenses, n_parent_expenses = render_section_parent_expenses(draft)
st.markdown("---")

saving_plan, initial_savings, monthly_contribution, n_topups = render_section_saving_plan(draft)
st.markdown("---")

assumptions = render_section_assumptions()
st.markdown("---")

render_section_review_and_run(
    children=children,
    parent_expenses=parent_expenses,
    saving_plan=saving_plan,
    assumptions=assumptions,
    n_children=n_children,
    total_edu_plans=total_edu_plans,
    total_child_extra=total_child_extra,
    n_parent_expenses=n_parent_expenses,
    n_topups=n_topups,
    initial_savings=initial_savings,
    monthly_contribution=monthly_contribution,
)
