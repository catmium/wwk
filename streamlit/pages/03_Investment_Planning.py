"""Page 3 — Investment Planning (Monte Carlo).

Thin orchestrator. Section logic lives in p3_lib.* — see p3_lib/__init__.py
for the pipeline overview.
"""

import sys, os
# Parent dir for top-level app modules (strings, state, asset_store, engines).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# File's own dir so `import p3_lib` resolves when the page lives in pages/.
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

from strings import S
from state import (
    persist_all_widget_buffers,
    switch_page_with_persist,
    require_login,
)
from portfolio_bucket_engine import build_funding_maps_from_saving_df

from p3_lib.state import init_widget_state
from p3_lib.helpers import safe_summary_metric, required_upstream_ready
from p3_lib import section_bucket_config, section_mc_runner, section_results


# ──────────────────────────────────────────────────────
# Login + page chrome
# ──────────────────────────────────────────────────────
require_login()

st.set_page_config(
    page_title=S("p3", "page_title"),
    page_icon="📈",
    layout="wide",
)

st.title(S("p3", "title"))
st.caption(S("p3", "caption"))


# ──────────────────────────────────────────────────────
# State init + upstream gate
# ──────────────────────────────────────────────────────
init_widget_state()

if not required_upstream_ready():
    st.warning(S("p3", "gate_warn"))
    st.stop()


# ──────────────────────────────────────────────────────
# Read upstream simulation results + derived scalars
# ──────────────────────────────────────────────────────
expense_df = st.session_state.get("expense_df")
saving_df = st.session_state.get("saving_df")
saving_plan = st.session_state.get("saving_plan_obj")
assumptions = st.session_state.get("assumptions_obj")
summary_df = st.session_state.get("summary_df")

annual_contribution_map, annual_topup_map = build_funding_maps_from_saving_df(saving_df)

expense_start_year = (
    int(expense_df["year"].min())
    if expense_df is not None and not expense_df.empty
    else int(assumptions.start_year)
)
expense_end_year = (
    int(expense_df["year"].max())
    if expense_df is not None and not expense_df.empty
    else int(assumptions.start_year)
)
# Plan horizon spans from the earliest of (saving start, expense start) — money
# can already be saved/invested before expenses begin — through the last
# expense year.
saving_start_year = (
    int(saving_df["year"].min())
    if saving_df is not None and not saving_df.empty and "year" in saving_df.columns
    else expense_start_year
)
plan_start_year = min(saving_start_year, expense_start_year)
plan_end_year = expense_end_year
total_projected_expense = (
    float(expense_df["inflated_amount"].sum())
    if expense_df is not None and not expense_df.empty
    else 0.0
)

peak_annual_expense = float(safe_summary_metric(summary_df, "peak_annual_expense") or 0.0)
peak_annual_expense_year = int(safe_summary_metric(summary_df, "peak_annual_expense_year") or 0)
current_monthly_contribution = int(safe_summary_metric(summary_df, "current_monthly_contribution") or 0)
initial_savings = int(safe_summary_metric(summary_df, "initial_savings") or 0)
top_up = int(safe_summary_metric(summary_df, "total_topup") or 0)
ttl_cont = int(safe_summary_metric(summary_df, "total_contribution") or 0)


# ──────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(S("p3", "workflow_header"))
    st.markdown(S("sidebar", "step1_done"))
    st.markdown(S("sidebar", "step2_done"))
    st.markdown(S("p3", "step3_active"))
    if st.button(S("p3", "btn_back"), width="stretch"):
        switch_page_with_persist("pages/02_Expense_Simulation.py")

    if st.session_state.get("inv_investment_sim_done"):
        st.divider()
        st.markdown(S("p3", "sim_done_header"))
        st.caption(S("p3", "sim_done_caption"))


# ──────────────────────────────────────────────────────
# Section 1 — Plan context (compact KPI strip)
# ──────────────────────────────────────────────────────
st.subheader(S("p3", "sec1_header"))
with st.container(border=True):
    _t = plan_end_year - plan_start_year + 1
    _cx = st.columns(3)
    _cx[0].metric(S("p3", "ctx_total_exp"), f"฿{total_projected_expense:,.0f}")
    _cx[1].metric(S("p3", "ctx_horizon"), S("p3", "ctx_horizon_val", start=plan_start_year, end=plan_end_year, n=_t))
    _cx[2].metric(S("p3", "ctx_peak"), S("p3", "ctx_peak_val", amount=peak_annual_expense, year=peak_annual_expense_year))

    _cy = st.columns(3)
    _cy[0].metric(S("p3", "ctx_ttl_cont"), f"฿{ttl_cont+initial_savings+top_up:,.0f}")
    _cy[1].metric(S("p3", "ctx_initial"), f"฿{initial_savings+top_up:,.0f}")
    _cy[2].metric(f"{S('p3', 'ctx_monthly')} (ระยะเวลา {_t*12} เดือน)", f"฿{current_monthly_contribution:,.0f}")

# ── Required-return hint: shows the user a rough investment target ──
# วางไว้ "นอก" container เพื่อให้เด้งเป็น banner ด้านล่าง box สรุปข้อมูลแผน
# คำนวณด้วย bisection เหมือนหน้า 2 และ reuse _p2_min_return_cache ถ้า
# signature ตรง — เคย run หน้า 2 มาก่อนจะแสดงทันทีโดยไม่คำนวณซ้ำ.
_sp_solve = st.session_state.get("saving_plan_obj")
_as_solve = st.session_state.get("assumptions_obj")
_ch_solve = st.session_state.get("children_obj")
_pe_solve = st.session_state.get("parent_expenses_obj") or []

if _sp_solve is not None and _as_solve is not None and _ch_solve is not None:
    from dataclasses import replace as _dc_replace
    from simulation_core import simulate_education_plan

    def _p3_is_suff_at_rate(rate: float) -> bool:
        try:
            _as_test = _dc_replace(_as_solve, investment_return_rate=float(rate))
            _, _, _sum = simulate_education_plan(
                children=_ch_solve,
                saving_plan=_sp_solve,
                assumptions=_as_test,
                parent_expenses=_pe_solve,
            )
            _row = _sum.loc[_sum["metric"] == "is_current_plan_sufficient", "value"]
            return bool(_row.iloc[0]) if not _row.empty else False
        except Exception:
            return False

    _RATE_MAX = 0.30
    _sig = (
        float(_sp_solve.initial_savings),
        float(_sp_solve.monthly_contribution),
        float(_as_solve.general_inflation_rate),
        float(_as_solve.education_inflation_rate),
        int(getattr(_as_solve, "start_year", 0)),
        len(_ch_solve),
        len(_pe_solve),
    )
    # Reuse Page 2's cache if signature matches — same calculation
    _cache = st.session_state.get("_p2_min_return_cache", {})
    if _cache.get("sig") == _sig:
        _p3_min_rate = _cache.get("rate")
    else:
        with st.spinner("กำลังคำนวณผลตอบแทนการลงทุนขั้นต่ำที่ต้องการ..."):
            if _p3_is_suff_at_rate(0.0):
                _p3_min_rate = 0.0
            elif not _p3_is_suff_at_rate(_RATE_MAX):
                _p3_min_rate = None
            else:
                _lo, _hi = 0.0, _RATE_MAX
                for _ in range(18):  # ~0.0001 precision over 0..0.30
                    _mid = (_lo + _hi) / 2
                    if _p3_is_suff_at_rate(_mid):
                        _hi = _mid
                    else:
                        _lo = _mid
                _p3_min_rate = _hi
        st.session_state["_p2_min_return_cache"] = {"sig": _sig, "rate": _p3_min_rate}

    if _p3_min_rate is None:
        st.warning(
            f"⚠️ ถึงแม้ผลตอบแทนการลงทุนสูงถึง **{_RATE_MAX*100:.0f}% ต่อปี** "
            f"ก็ยังไม่เพียงพอ — แผนปัจจุบันต้องเพิ่มเงินออมรายเดือนหรือลดค่าใช้จ่าย"
        )
    elif _p3_min_rate <= 0.0:
        st.success(
            "✅ เงินออมปัจจุบันเพียงพออยู่แล้วโดยไม่ต้องลงทุน — "
            "การลงทุนช่วยเพิ่มเงินคงเหลือปลายแผน แต่ไม่จำเป็นต่อความสำเร็จ"
        )
    else:
        st.info(
            f"💡 หากไม่ต้องการเพิ่มเงิน คุณต้องลงทุนให้ได้ผลตอบแทน "
            f"อย่างน้อย **{(_p3_min_rate*100)+0.1:.1f}% ต่อปี** "
            f"เพื่อให้เงินเพียงพอกับค่าใช้จ่าย\n\n"
            f"ใช้เป็นเป้าหมายคร่าวๆ ในการเลือก asset เพื่อลงทุน "
            f"- ความเสี่ยงส่งผลกับโอกาสสำเร็จตามแผน"
        )


# ──────────────────────────────────────────────────────
# Section 2 — Bucket & Asset Configuration
# ──────────────────────────────────────────────────────
_bucket_state = section_bucket_config.render()


# ──────────────────────────────────────────────────────
# Section 3 — Auto allocation preview (used as MC initial override)
# ──────────────────────────────────────────────────────
_alloc_state = section_mc_runner.compute_allocation_preview(
    expense_df=expense_df,
    assumptions=assumptions,
    saving_plan=saving_plan,
    new_defs=_bucket_state["new_defs"],
    bucket_configs=_bucket_state["bucket_configs"],
    funding_rule=_bucket_state["funding_rule"],
)


# ──────────────────────────────────────────────────────
# Section 4 — MC config UI + Run button
# ──────────────────────────────────────────────────────
_mc_ui = section_mc_runner.render_mc_config(
    bucket_config_valid=_bucket_state["bucket_config_valid"],
    asset_config_valid=_bucket_state["asset_config_valid"],
    asset_errors_summary=_bucket_state["asset_errors_summary"],
)


# ──────────────────────────────────────────────────────
# Section 5 — Run Monte Carlo (if button pressed)
# ──────────────────────────────────────────────────────
if _mc_ui["run_mc"]:
    section_mc_runner.run_mc(
        expense_df=expense_df,
        saving_plan=saving_plan,
        assumptions=assumptions,
        annual_contribution_map=annual_contribution_map,
        annual_topup_map=annual_topup_map,
        bucket_configs=_bucket_state["bucket_configs"],
        funding_rule=_bucket_state["funding_rule"],
        new_defs=_bucket_state["new_defs"],
        auto_allocation_df=_alloc_state["auto_allocation_df"],
        run_output_placeholder=_mc_ui["run_output_placeholder"],
    )


# ──────────────────────────────────────────────────────
# Section 6 — Results
# ──────────────────────────────────────────────────────
section_results.render(
    expense_df=expense_df,
    saving_df=saving_df,
    saving_plan=saving_plan,
    assumptions=assumptions,
    summary_df=summary_df,
    annual_contribution_map=annual_contribution_map,
    annual_topup_map=annual_topup_map,
    new_defs=_bucket_state["new_defs"],
    initial_savings=initial_savings,
    total_projected_expense=total_projected_expense,
)


# ──────────────────────────────────────────────────────
# Flush widget buffers to draft on every rerun
# (must run AFTER every widget has rendered)
# ──────────────────────────────────────────────────────
persist_all_widget_buffers()
