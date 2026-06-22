"""Stateless helpers for Page 3: formatters, fingerprints, MC result reshaping."""

from typing import Optional
import pandas as pd
import streamlit as st


# ──────────────────────────────────────────────────────
# Money / number formatting
# ──────────────────────────────────────────────────────

def fmt_money(x: Optional[float]) -> str:
    if x is None:
        return "-"
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return str(x)


def fmt_c(v) -> str:
    """Compact currency formatter used by chart labels."""
    try:
        v = float(v)
        if abs(v) >= 1_000_000:
            return f"{v/1_000_000:.1f}M"
        if abs(v) >= 1_000:
            return f"{v/1_000:.0f}K"
        return f"{v:,.0f}"
    except Exception:
        return ""


# ──────────────────────────────────────────────────────
# HTML snippets used by KPI cards / group labels
# ──────────────────────────────────────────────────────

def kpi_card(label: str, value: str, color: str, bg: str, note: str = "") -> str:
    note_html = (
        f'<p style="margin:6px 0 0; font-size:11px; color:#999; line-height:1.4;">{note}</p>'
        if note else ""
    )
    return f"""
    <div style="background:{bg}; border-radius:10px; padding:18px 20px;
                border-left:4px solid {color}; box-sizing:border-box;">
      <p style="margin:0 0 8px; font-size:11px; font-weight:600; color:#888;
                letter-spacing:0.6px; text-transform:uppercase;">{label}</p>
      <p style="margin:0; font-size:26px; font-weight:700; color:{color}; line-height:1.2;">{value}</p>
      {note_html}
    </div>
    """


def group_label(icon: str, title: str) -> str:
    return (
        f'<div style="margin:20px 0 10px; display:flex; align-items:center; gap:8px;">'
        f'<span style="font-size:15px;">{icon}</span>'
        f'<span style="font-size:13px; font-weight:600; color:#555;">{title}</span>'
        f'</div>'
    )


# ──────────────────────────────────────────────────────
# Upstream readiness + summary-metric lookup
# ──────────────────────────────────────────────────────

def required_upstream_ready() -> bool:
    return (
        st.session_state.get("expense_df") is not None
        and st.session_state.get("saving_df") is not None
        and st.session_state.get("saving_plan_obj") is not None
        and st.session_state.get("assumptions_obj") is not None
    )


def safe_summary_metric(summary_df: Optional[pd.DataFrame], metric_name: str):
    if summary_df is None or not isinstance(summary_df, pd.DataFrame) or summary_df.empty:
        return None
    if "metric" not in summary_df.columns or "value" not in summary_df.columns:
        return None
    hit = summary_df.loc[summary_df["metric"] == metric_name, "value"]
    if hit.empty:
        return None
    return hit.iloc[0]


# ──────────────────────────────────────────────────────
# Stale-config detection
# ──────────────────────────────────────────────────────

def bucket_fingerprint(defs: list) -> tuple:
    """Hashable signature of bucket+asset config.
    Used to detect stale MC results when user edits config after running.
    """
    out = []
    for d in defs or []:
        assets = []
        for a in d.get("assets", []) or []:
            assets.append((
                str(a.get("asset_name", "")),
                round(float(a.get("weight_pct", 0.0)), 4),
                round(float(a.get("mean_pct", 0.0)), 4),
                round(float(a.get("std_pct", 0.0)), 4),
                round(float(a.get("min_pct", 0.0)), 4),
                round(float(a.get("max_pct", 0.0)), 4),
            ))
        out.append((
            str(d.get("name", "")),
            int(d.get("year_start", 0) or 0),
            (None if d.get("year_end") is None else int(d.get("year_end"))),
            tuple(assets),
        ))
    return tuple(out)


def saving_fingerprint(
    initial_savings: float,
    annual_contribution_map: dict,
    annual_topup_map: dict,
) -> tuple:
    """Hashable signature of saving-plan inputs (initial + per-year flows).
    Used to detect stale MC results when user edits saving plan (Page 1)
    and re-runs Page 2 sim, then comes back to Page 3.
    """
    return (
        round(float(initial_savings or 0.0), 2),
        tuple(sorted(
            (int(y), round(float(v), 2))
            for y, v in (annual_contribution_map or {}).items()
        )),
        tuple(sorted(
            (int(y), round(float(v), 2))
            for y, v in (annual_topup_map or {}).items()
        )),
    )


def term_fingerprint(term_assets: list) -> tuple:
    """Hashable signature of term-asset config.
    Used to detect stale MC results when the user edits term assets after a run.
    Term assets are NOT captured by bucket_fingerprint, so without this an edit
    to a term asset would silently leave stale Page-3 results unflagged.

    Reads engine-ready TermAssetConfig objects by attribute.
    """
    out = []
    for t in term_assets or []:
        _min = getattr(t, "min_return", None)
        _max = getattr(t, "max_return", None)
        out.append((
            str(getattr(t, "name", "")),
            int(getattr(t, "buy_year", 0) or 0),
            round(float(getattr(t, "min_initial_investment", 0.0) or 0.0), 2),
            int(getattr(t, "term_years", 0) or 0),
            int(getattr(t, "max_rollovers", 0) or 0),
            round(float(getattr(t, "mean_return", 0.0) or 0.0), 6),
            round(float(getattr(t, "std_dev", 0.0) or 0.0), 6),
            (None if _min is None else round(float(_min), 6)),
            (None if _max is None else round(float(_max), 6)),
            str(getattr(t, "distribution", "")),
        ))
    return tuple(out)


# ──────────────────────────────────────────────────────
# MC result analyzer
# ──────────────────────────────────────────────────────

def analyze_mc_result(mc_result) -> dict:
    engine_summary_df = getattr(mc_result, "mc_engine_summary_df", pd.DataFrame()).copy()
    bucket_summary_df = getattr(mc_result, "mc_bucket_summary_df", pd.DataFrame()).copy()
    year_summary_df = getattr(mc_result, "mc_year_summary_df", pd.DataFrame()).copy()
    path_summary_df = getattr(mc_result, "mc_path_summary_df", pd.DataFrame()).copy()
    path_detail_df = getattr(mc_result, "mc_path_detail_df", pd.DataFrame()).copy()

    weakest_bucket_row = pd.DataFrame()
    if not bucket_summary_df.empty and "success_probability" in bucket_summary_df.columns:
        tmp = bucket_summary_df.copy()
        if "expected_shortfall" not in tmp.columns:
            tmp["expected_shortfall"] = 0.0
        weakest_bucket_row = (
            tmp.sort_values(
                ["success_probability", "expected_shortfall"],
                ascending=[True, False],
            )
            .head(1)
            .reset_index(drop=True)
        )

    riskiest_years_df = pd.DataFrame()
    if not year_summary_df.empty:
        tmp = year_summary_df.copy()
        if "p10_ending_balance" not in tmp.columns:
            tmp["p10_ending_balance"] = 0.0
        riskiest_years_df = (
            tmp.sort_values(
                ["shortfall_probability", "p10_ending_balance", "year"],
                ascending=[False, True, True],
            )
            .head(15)
            .reset_index(drop=True)
        )

    worst_paths_df = pd.DataFrame()
    if not path_summary_df.empty:
        tmp = path_summary_df.copy()
        if "total_shortfall_amount" not in tmp.columns:
            tmp["total_shortfall_amount"] = 0.0
        worst_paths_df = (
            tmp.sort_values(
                ["final_total_balance", "total_shortfall_amount"],
                ascending=[True, False],
            )
            .head(20)
            .reset_index(drop=True)
        )

    terminal_balance_pivot = pd.DataFrame()
    shortfall_probability_pivot = pd.DataFrame()
    if not year_summary_df.empty:
        if {"year", "bucket_name", "p50_ending_balance"}.issubset(year_summary_df.columns):
            terminal_balance_pivot = year_summary_df.pivot(
                index="year",
                columns="bucket_name",
                values="p50_ending_balance",
            )
        if {"year", "bucket_name", "shortfall_probability"}.issubset(year_summary_df.columns):
            shortfall_probability_pivot = year_summary_df.pivot(
                index="year",
                columns="bucket_name",
                values="shortfall_probability",
            )

    return {
        "engine_summary_df": engine_summary_df,
        "bucket_summary_df": bucket_summary_df,
        "year_summary_df": year_summary_df,
        "path_summary_df": path_summary_df,
        "path_detail_df": path_detail_df,
        "weakest_bucket_row": weakest_bucket_row,
        "riskiest_years_df": riskiest_years_df,
        "worst_paths_df": worst_paths_df,
        "terminal_balance_pivot": terminal_balance_pivot,
        "shortfall_probability_pivot": shortfall_probability_pivot,
    }
