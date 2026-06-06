"""Sections 3-5: Allocation preview, MC config UI, and MC execution.

- compute_allocation_preview() runs the engine's deterministic auto-allocation
  preview (used by downstream MC as initial allocation override).
- render_mc_config() draws the n_paths + advanced settings UI and returns
  the run-button state + placeholder for the progress widget.
- run_mc() executes the Monte Carlo and writes results to session_state.
"""

import streamlit as st
import pandas as pd

from strings import S
from state import draft_get, _widget_key, on_widget_change
from portfolio_bucket_engine import (
    prepare_annual_expense,
    assign_expense_to_buckets,
    calculate_bucket_requirements,
    allocate_initial_savings_to_buckets,
)
from portfolio_bucket_engine_mc import (
    MonteCarloConfig,
    run_bucket_engine_monte_carlo_level2,
)
from asset_store import save_bucket_definitions

from .state import (
    PARAM_DEFAULTS,
    build_bucket_return_models_from_state,
)
from .helpers import analyze_mc_result, bucket_fingerprint, saving_fingerprint, term_fingerprint


# ──────────────────────────────────────────────────────
# SECTION 3 — Allocation preview (always computed)
# ──────────────────────────────────────────────────────

def compute_allocation_preview(
    expense_df,
    assumptions,
    saving_plan,
    new_defs: list,
    bucket_configs: list,
    funding_rule,
) -> dict:
    """Compute the auto-allocation preview used as MC initial allocation.

    Returns dict with auto_allocation_df, preview_requirement_df,
    allocation_preview_ok, alloc_preview_err (if any).
    """
    conservative_rate_map = {
        d["name"]: float(d["discount_rate"]) for d in new_defs
    }

    out = {
        "auto_allocation_df": pd.DataFrame(),
        "preview_requirement_df": pd.DataFrame(),
        "allocation_preview_ok": False,
        "alloc_preview_err": None,
    }

    try:
        preview_expense_df = prepare_annual_expense(expense_df)
        preview_assignment_df = assign_expense_to_buckets(
            annual_expense_df=preview_expense_df,
            simulation_start_year=int(assumptions.start_year),
            bucket_configs=bucket_configs,
        )
        preview_requirement_df = calculate_bucket_requirements(
            bucket_assignment_df=preview_assignment_df,
            simulation_start_year=int(assumptions.start_year),
            bucket_configs=bucket_configs,
            discount_rate_override_map=conservative_rate_map,
        )
        auto_allocation_df = allocate_initial_savings_to_buckets(
            initial_savings=float(saving_plan.initial_savings),
            bucket_requirement_df=preview_requirement_df,
            funding_rule=funding_rule,
        )
        out["auto_allocation_df"] = auto_allocation_df
        out["preview_requirement_df"] = preview_requirement_df
        out["allocation_preview_ok"] = True
    except Exception as e:
        out["alloc_preview_err"] = e

    return out


# ──────────────────────────────────────────────────────
# SECTION 4 — MC Config UI
# ──────────────────────────────────────────────────────

def render_mc_config(
    bucket_config_valid: bool,
    asset_config_valid: bool,
    asset_errors_summary: list,
) -> dict:
    """Draw the MC config block. Returns dict with run_mc (bool) +
    run_output_placeholder (st.empty for progress widget).
    """
    st.subheader(S("p3", "sec4_header"))

    with st.container(border=True):
        cc1, cc2 = st.columns(2)
        with cc1:
            st.number_input(
                S("p3", "label_n_paths"),
                min_value=100,
                max_value=50000,
                step=100,
                key=_widget_key("inv_mc_n_paths"),
                on_change=on_widget_change,
                args=("inv_mc_n_paths", int),
                help=S("p3", "label_n_paths_help"),
            )
        with cc2:
            run_mc_disabled = (
                not bucket_config_valid
                or not asset_config_valid
            )
            st.markdown("<br>", unsafe_allow_html=True)
            run_mc = st.button(
                S("p3", "btn_run"),
                type="primary",
                width="stretch",
                disabled=run_mc_disabled,
            )

        with st.expander(S("p3", "advanced_settings_header"), expanded=False):
            adv1, adv_div, adv2 = st.columns([1, 0.3, 2])

            with adv1:
                st.number_input(
                    S("p3", "label_seed"),
                    min_value=0,
                    step=1,
                    key=_widget_key("inv_mc_random_seed"),
                    on_change=on_widget_change,
                    args=("inv_mc_random_seed", int),
                    help=S("p3", "label_seed_help"),
                )

            with adv2:
                st.markdown("<br>", unsafe_allow_html=True)
                dc1, dc2 = st.columns(2)
                with dc1:
                    st.checkbox(
                        S("p3", "label_keep_path"),
                        key=_widget_key("inv_mc_keep_path_detail"),
                        on_change=on_widget_change,
                        args=("inv_mc_keep_path_detail", bool),
                        help=S("p3", "label_keep_path_help"),
                    )
                with dc2:
                    st.checkbox(
                        S("p3", "label_keep_asset"),
                        key=_widget_key("inv_mc_keep_asset_detail"),
                        on_change=on_widget_change,
                        args=("inv_mc_keep_asset_detail", bool),
                        help=S("p3", "label_keep_asset_help"),
                    )

        # Placeholder for progress + result (inside the same box as config)
        run_output_placeholder = st.empty()

        # Validation warnings anchored at the bottom of the box.
        if not bucket_config_valid:
            st.warning(S("p3", "warn_fix_bucket"))
        elif not asset_config_valid:
            summary_txt = ", ".join(asset_errors_summary) if asset_errors_summary else ""
            st.warning(
                "⚠️ กรุณาแก้ไข asset configuration ก่อน — "
                + (summary_txt or "ตรวจสอบข้อผิดพลาดในแต่ละ bucket ด้านบน")
            )

    return {
        "run_mc": run_mc,
        "run_output_placeholder": run_output_placeholder,
    }


# ──────────────────────────────────────────────────────
# SECTION 5 — Run Monte Carlo
# ──────────────────────────────────────────────────────

def run_mc(
    *,
    expense_df,
    saving_plan,
    assumptions,
    annual_contribution_map: dict,
    annual_topup_map: dict,
    bucket_configs: list,
    funding_rule,
    new_defs: list,
    auto_allocation_df,
    run_output_placeholder,
) -> None:
    """Execute the Monte Carlo simulation and persist results to session_state.

    Side effects:
      - st.session_state["inv_mc_result"]
      - st.session_state["inv_mc_analysis"]
      - st.session_state["inv_investment_sim_done"]
      - st.session_state["inv_mc_fingerprint"]
      - Saves bucket config to asset_store (keyed by cust_id)
    """
    try:
        bucket_return_models = build_bucket_return_models_from_state()
        st.session_state["_last_bucket_return_models"] = bucket_return_models

        mc_config = MonteCarloConfig(
            n_paths=int(draft_get("inv_mc_n_paths", PARAM_DEFAULTS["inv_mc_n_paths"])),
            random_seed=int(draft_get("inv_mc_random_seed", PARAM_DEFAULTS["inv_mc_random_seed"])),
            keep_path_detail=bool(draft_get("inv_mc_keep_path_detail", True)),
            keep_asset_detail=bool(draft_get("inv_mc_keep_asset_detail", False)),
            success_threshold=0.0,
        )

        # Manual allocation override (currently always None since manual mode
        # is disabled — kept for forward compatibility).
        alloc_override = None
        if draft_get("inv_allocation_mode", "auto") == "manual":
            alloc_override = st.session_state.get("_manual_allocation_df_cache")

        with run_output_placeholder.container():
            progress_bar = st.progress(0)
            status_placeholder = st.empty()
            result_placeholder = st.empty()

        def _mc_progress_callback(current_path: int, total_paths: int):
            pct = int(current_path / total_paths * 100)
            progress_bar.progress(pct)
            status_placeholder.markdown(
                f"**Running Monte Carlo:** {current_path:,}/{total_paths:,}"
            )

        mc_result = run_bucket_engine_monte_carlo_level2(
            expense_df=expense_df,
            initial_savings=float(saving_plan.initial_savings),
            annual_contribution_map=annual_contribution_map,
            annual_topup_map=annual_topup_map,
            bucket_configs=bucket_configs,
            funding_rule=funding_rule,
            bucket_return_models=bucket_return_models,
            mc_config=mc_config,
            simulation_start_year=int(assumptions.start_year),
            initial_allocation_override_df=alloc_override,
            term_assets=st.session_state.get("inv_term_assets", []),
            progress_callback=_mc_progress_callback,
            progress_update_every=10,
        )

        progress_bar.progress(100)
        status_placeholder.markdown(
            f"**Running Monte Carlo:** {int(mc_config.n_paths):,}/{int(mc_config.n_paths):,} ✅"
        )
        result_placeholder.success(S("p3", "sim_success"))

        st.session_state["inv_mc_result"] = mc_result
        st.session_state["inv_mc_analysis"] = analyze_mc_result(mc_result)
        st.session_state["inv_investment_sim_done"] = True
        st.session_state["_p3_scroll_to_results"] = True
        # Snapshot bucket+asset config used for this MC run — used to detect
        # stale results if user edits config after the run completes.
        st.session_state["inv_mc_fingerprint"] = bucket_fingerprint(new_defs)
        # Same for saving plan (initial + per-year contribution/topup maps).
        # If user goes back to Page 1, edits saving and re-runs Page 2 sim,
        # the maps change → fingerprint mismatches → warn on Page 3.
        st.session_state["inv_mc_saving_fingerprint"] = saving_fingerprint(
            float(saving_plan.initial_savings),
            annual_contribution_map,
            annual_topup_map,
        )
        # Term assets are NOT part of bucket_fingerprint — snapshot them
        # separately so editing a term asset after this run flags Page-3
        # results as stale. Read from inv_term_assets (rebuilt each rerun by
        # section_bucket_config.render), same source the engine ran on.
        st.session_state["inv_mc_term_fingerprint"] = term_fingerprint(
            st.session_state.get("inv_term_assets", [])
        )

        # Persist bucket+asset config keyed by cust_id. Failures are non-fatal.
        # IMPORTANT: use new_defs directly (the freshly-built snapshot from
        # widget values this rerun) — not a session_state re-read which can
        # be stale.
        cust_id_for_save = (draft_get("cust_id", "") or "").strip()
        if cust_id_for_save:
            try:
                save_bucket_definitions(cust_id_for_save, new_defs)
                saved_asset_names = []
                for bd_save in new_defs:
                    for a_save in bd_save.get("assets", []):
                        nm = str(a_save.get("asset_name", "")).strip()
                        if nm:
                            saved_asset_names.append(nm)
                preview_names = ", ".join(saved_asset_names[:8])
                if len(saved_asset_names) > 8:
                    preview_names += ", ..."
                st.toast(
                    f"💾 บันทึก asset config สำเร็จ: {preview_names}"
                    if saved_asset_names else "💾 บันทึก asset config สำเร็จ"
                )
            except Exception as save_err:
                st.toast(f"⚠️ บันทึก asset config ไม่สำเร็จ: {save_err}")

    except Exception as e:
        st.session_state["inv_investment_sim_done"] = False
        st.error(S("p3", "sim_failed", error=e))
        st.exception(e)
