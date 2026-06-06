"""Section 6: Monte Carlo Results.

Renders status banner, KPI cards, charts (final balance distribution,
CAGR, P50 bucket trajectories, shortfall, P50 balance overlay),
data tables, and additional visualizations (fan chart, education
timeline, goal funded ratio summary, cashflow table, heatmap,
drawdown distribution).

The body is a verbatim extraction of the original Section 6 — kept
together so it can evolve in sync with chart-by-chart edits. All
references to in-scope variables flow through `ctx` and the local
unpacking at the top of `render()`.
"""

import streamlit as st
import pandas as pd
import altair as alt

from strings import S, edu_level_label
from portfolio_bucket_engine_mc import DEFAULT_INTRA_BUCKET_CORRELATION

from .helpers import (
    fmt_money as _fmt_money,
    fmt_c as _fmt_c,
    bucket_fingerprint as _bucket_fingerprint,
    saving_fingerprint as _saving_fingerprint,
    analyze_mc_result as analyze_mc_result_local,
)


def render(
    *,
    expense_df,
    saving_df,
    saving_plan,
    assumptions,
    summary_df,
    annual_contribution_map: dict,
    annual_topup_map: dict,
    new_defs: list,
    initial_savings: float,
    total_projected_expense: float,
) -> None:
    """Render Section 6 results. Reads MC result from session_state."""

    _new_defs = new_defs  # alias used by extracted body

    if not (
        st.session_state.get("inv_investment_sim_done")
        and st.session_state.get("inv_mc_result") is not None
    ):
        st.info(S("p3", "no_result"))
        return

    # Stale-result detection — warn the user when the MC result no longer
    # matches current inputs. Two independent checks:
    #   (1) bucket / asset config edited on Page 3 itself
    #   (2) saving plan changed (e.g. user went back to Page 1, edited
    #       initial_savings / monthly_contribution / topups, re-ran Page 2)
    _stale_msgs: list[str] = []

    _current_bucket_fp = _bucket_fingerprint(_new_defs)
    _saved_bucket_fp = st.session_state.get("inv_mc_fingerprint")
    if _saved_bucket_fp is not None and _saved_bucket_fp != _current_bucket_fp:
        _stale_msgs.append(
            "การตั้งค่า **bucket / asset** เปลี่ยนไปหลังการ simulation ครั้งล่าสุด"
        )

    _current_saving_fp = _saving_fingerprint(
        initial_savings, annual_contribution_map, annual_topup_map
    )
    _saved_saving_fp = st.session_state.get("inv_mc_saving_fingerprint")
    if _saved_saving_fp is not None and _saved_saving_fp != _current_saving_fp:
        _stale_msgs.append(
            "**แผนการออม** (เงินออมเริ่มต้น / รายเดือน / เงินก้อนพิเศษ) "
            "เปลี่ยนไปหลังการ simulation ครั้งล่าสุด"
        )

    if _stale_msgs:
        st.warning(
            "⚠️ " + " | ".join(_stale_msgs)
            + " — ผลลัพธ์ด้านล่างไม่ตรงกับข้อมูลปัจจุบัน กรุณากด Run อีกครั้ง"
        )
        st.stop()

    mc_result = st.session_state["inv_mc_result"]
    analysis = st.session_state.get("inv_mc_analysis") or analyze_mc_result_local(mc_result)

    engine_summary_df = analysis["engine_summary_df"]
    bucket_summary_df = analysis["bucket_summary_df"]
    year_summary_df = analysis["year_summary_df"]
    path_summary_df = analysis["path_summary_df"]
    weakest_bucket_row = analysis["weakest_bucket_row"]
    riskiest_years_df = analysis["riskiest_years_df"]
    worst_paths_df = analysis["worst_paths_df"]
    terminal_balance_pivot = analysis["terminal_balance_pivot"]
    shortfall_probability_pivot = analysis["shortfall_probability_pivot"]

    # Anchor for results section (visual marker only — auto-scroll removed
    # because st.components.v1.html is being removed after 2026-06-01 and
    # st.html() does not execute scripts. Results render directly below the
    # Run button so manual scrolling is minimal.)
    st.markdown('<div id="mc-results-anchor"></div>', unsafe_allow_html=True)
    st.subheader(S("p3", "sec6_header"))
    # Consume the one-shot flag (no-op now — kept so existing setters don't
    # leave stale flags in session_state).
    st.session_state.pop("_p3_scroll_to_results", False)

    # Compact currency formatter used by every chart in this section.
    # Defined here so it's in scope even when individual data frames are empty.
    def _fmt_c(v):
        try:
            v = float(v)
            if abs(v) >= 1_000_000:
                return f"{v/1_000_000:.1f}M"
            if abs(v) >= 1_000:
                return f"{v/1_000:.0f}K"
            return f"{v:,.0f}"
        except Exception:
            return ""

    # ── Simulation Diagnostic expander hidden (kept block-wrapped for easy
    # re-enable: flip to `if True:` and the content renders inline; flip back
    # to `with st.expander(...)` to restore the original card). ──
    if False:
        pass

    # ── Status banner + headline KPIs share one bordered container ──
    if not engine_summary_df.empty:
        row = engine_summary_df.iloc[0]

        _success_prob = float(row.get("success_probability", 0))
        _sfail_prob = float(row.get("shortfall_probability", 0))
        _success_pct = f"{_success_prob:.1%}"
        _shortfall_pct = f"{_sfail_prob:.1%}"
        _exp = _fmt_money(row.get("expected_final_total_balance"))

        # ── First-shortfall year: show "{year} ({modal share}%)" ──
        # The modal share = fraction of paths whose first_shortfall_year
        # equals the modal year — answers "ปีนี้มี % โอกาสเงินไม่พอเท่าไหร่".
        _first_sf_raw = row.get("first_shortfall_year_mode")
        if (
            _first_sf_raw is not None
            and str(_first_sf_raw) not in ("", "nan", "None")
        ):
            _modal_year = int(_first_sf_raw)
            _modal_pct_str = ""
            if (
                not path_summary_df.empty
                and "first_shortfall_year" in path_summary_df.columns
            ):
                _sf_series = path_summary_df["first_shortfall_year"].dropna()
                if not _sf_series.empty and len(path_summary_df) > 0:
                    _modal_frac = (_sf_series.astype(int) == _modal_year).sum() / len(path_summary_df)
                    _modal_pct_str = f" ({_modal_frac:.1%})"
            _first_sf_str = f"{_modal_year}{_modal_pct_str}"
        else:
            _first_sf_str = "-"

        with st.container(border=True):
            if _success_prob >= 0.80:
                st.success(S("p3", "status_good", prob=_success_prob, sfail=_sfail_prob))
            elif _success_prob >= 0.50:
                st.warning(S("p3", "status_warn", prob=_success_prob, sfail=_sfail_prob))
            else:
                st.error(S("p3", "status_bad", prob=_success_prob, sfail=_sfail_prob))

            _r1c1, _r1c2, _r1c3, _r1c4 = st.columns(4)
            with _r1c1:
                st.metric(S("p3", "kpi_success_prob"), _success_pct)
            with _r1c2:
                st.metric(S("p3", "kpi_shortfall_prob"), _shortfall_pct)
            with _r1c3:
                st.metric(
                    "เงินคงเหลือปลายแผนเฉลี่ย",
                    _exp,
                    help="ค่าเฉลี่ย (mean) ของเงินคงเหลือปลายแผนจากทุก simulation",
                )
            with _r1c4:
                st.metric(
                    S("p3", "kpi_first_sf_year"),
                    _first_sf_str,
                    help="ปีที่พบ shortfall บ่อยที่สุดใน simulation พร้อมสัดส่วน path ที่เริ่มขาดเงินในปีนั้น",
                )

    # ── เงินสะสมเฉลี่ย vs ค่าใช้จ่ายสะสม ──
    # ใช้ MEAN (expected) ของ total portfolio ending balance — ตรงกับ KPI
    # "เงินคงเหลือปลายแผน (คาดการณ์)" ด้านบน. P10–P90 band โชว์ช่วงความ
    # ผันผวน. คำนวณจาก mc_path_detail_df โดยตรง (รวม ending_balance ข้าม
    # bucket ต่อ (path, year) แล้วหา mean/P10/P90 ข้าม path) — ต่างจาก
    # เดิมที่ใช้ sum-of-per-bucket-P50 ใน year_summary_df ซึ่งเป็นการ
    # ประมาณที่ไม่ถูกต้องทางคณิตศาสตร์ (sum of medians ≠ median of sums).
    _path_detail_for_chart1 = getattr(mc_result, "mc_path_detail_df", pd.DataFrame())
    if (
        expense_df is not None
        and not expense_df.empty
        and {"year", "inflated_amount"}.issubset(expense_df.columns)
        and _path_detail_for_chart1 is not None
        and not _path_detail_for_chart1.empty
        and {"path_id", "year", "ending_balance"}.issubset(_path_detail_for_chart1.columns)
    ):
        # 1) ค่าใช้จ่ายสะสมรายปี (deterministic)
        _se_exp = (
            expense_df.groupby("year", as_index=False)["inflated_amount"]
            .sum()
            .sort_values("year")
        )
        _se_exp["cum_expense"] = _se_exp["inflated_amount"].cumsum()
        _se_exp = _se_exp[["year", "cum_expense"]]

        # 2) Total portfolio per (path, year) = sum across buckets
        _path_year_total = (
            _path_detail_for_chart1
            .groupby(["path_id", "year"], as_index=False)["ending_balance"]
            .sum()
        )
        # 3) Stats across paths per year: mean / P10 / P90
        _stats = _path_year_total.groupby("year")["ending_balance"].agg(
            mean_bal="mean",
            p10_bal=lambda s: float(s.quantile(0.10)),
            p90_bal=lambda s: float(s.quantile(0.90)),
        ).reset_index()
        _stats["year"] = _stats["year"].astype(int)

        # 4) Merge + derive plot columns
        _se_df = (
            _stats.merge(_se_exp, on="year", how="outer")
            .sort_values("year")
            .reset_index(drop=True)
        )
        for _c in ("mean_bal", "p10_bal", "p90_bal"):
            _se_df[_c] = _se_df[_c].fillna(0.0)
        _se_df["cum_expense"] = _se_df["cum_expense"].ffill().fillna(0.0)
        _se_df["year"] = _se_df["year"].astype(int)
        # เงินสะสมเฉลี่ย = mean ending balance + cum_expense
        _se_df["sr_mean"] = _se_df["mean_bal"] + _se_df["cum_expense"]
        _se_df["sr_p10"]  = _se_df["p10_bal"]  + _se_df["cum_expense"]
        _se_df["sr_p90"]  = _se_df["p90_bal"]  + _se_df["cum_expense"]
        # เงินคงเหลือเฉลี่ย = mean ending balance
        _se_df["bal_mean"] = _se_df["mean_bal"]

        _SE_SAVINGS = "เงินสะสมเฉลี่ย"
        _SE_EXPENSE = "ค่าใช้จ่ายสะสม"
        _SE_DIFF    = "เงินคงเหลือเฉลี่ย"
        _se_label_map = {
            "sr_mean":     _SE_SAVINGS,
            "cum_expense": _SE_EXPENSE,
            "bal_mean":    _SE_DIFF,
        }
        _se_long = _se_df.melt(
            id_vars="year",
            value_vars=["sr_mean", "cum_expense", "bal_mean"],
            var_name="metric",
            value_name="value",
        )
        _se_long["label"] = _se_long["metric"].map(_se_label_map)
        _se_long["label_text"] = _se_long["value"].apply(_fmt_c)

        _se_color = alt.Scale(
            domain=[_SE_SAVINGS, _SE_EXPENSE, _SE_DIFF],
            range=["#50B87A", "#E8734C", "#4C9BE8"],
        )
        _se_dark = alt.Scale(
            domain=[_SE_SAVINGS, _SE_EXPENSE, _SE_DIFF],
            range=["#217A47", "#C44E27", "#1A6FC4"],
        )

        st.markdown("#### 1. 💰 เงินสะสมเฉลี่ย vs ค่าใช้จ่ายสะสม")
        st.caption(
            "แถบเขียวอ่อน = ช่วง P10–P90 ของเงินสะสม+ผลตอบแทน | "
            "แถบฟ้าอ่อน = ช่วง P10–P90 ของเงินคงเหลือ (80% ของ simulation) | "
            "เส้น = ค่าคาดการณ์ (mean)"
        )

        # ── P10–P90 band around the "savings + return" line (green) ──
        _band_df = _se_df[["year", "sr_p10", "sr_p90", "p10_bal", "p90_bal"]].copy()
        _se_band = (
            alt.Chart(_band_df)
            .mark_area(opacity=0.18, color="#50B87A")
            .encode(
                x=alt.X("year:O", title="ปี"),
                y=alt.Y("sr_p10:Q", title="บาท", axis=alt.Axis(format=",.0f")),
                y2=alt.Y2("sr_p90:Q"),
                tooltip=[
                    alt.Tooltip("year:O",   title="ปี"),
                    alt.Tooltip("sr_p10:Q", title="P10 (กรณีแย่)", format=",.0f"),
                    alt.Tooltip("sr_p90:Q", title="P90 (กรณีดี)", format=",.0f"),
                ],
            )
        )

        # ── P10–P90 band around the "remaining balance" line (blue) ──
        _bal_band = (
            alt.Chart(_band_df)
            .mark_area(opacity=0.18, color="#4C9BE8")
            .encode(
                x=alt.X("year:O"),
                y=alt.Y("p10_bal:Q", axis=alt.Axis(format=",.0f")),
                y2=alt.Y2("p90_bal:Q"),
                tooltip=[
                    alt.Tooltip("year:O",    title="ปี"),
                    alt.Tooltip("p10_bal:Q", title="เงินคงเหลือ P10", format=",.0f"),
                    alt.Tooltip("p90_bal:Q", title="เงินคงเหลือ P90", format=",.0f"),
                ],
            )
        )

        _se_base = (
            alt.Chart(_se_long)
            .mark_line(point=True, strokeWidth=2)
            .encode(
                x=alt.X("year:O", title="ปี"),
                y=alt.Y("value:Q", title="บาท", axis=alt.Axis(format=",.0f")),
                color=alt.Color("label:N", title="รายการ", scale=_se_color),
                tooltip=[
                    alt.Tooltip("year:O",  title="ปี"),
                    alt.Tooltip("label:N", title="รายการ"),
                    alt.Tooltip("value:Q", title="บาท", format=",.0f"),
                ],
            )
        )
        _se_value_labels = (
            alt.Chart(_se_long)
            .mark_text(fontSize=14, fontWeight="bold", dy=-12)
            .encode(
                x=alt.X("year:O"),
                y=alt.Y("value:Q"),
                text=alt.Text("label_text:N"),
                color=alt.condition(
                    "datum.metric == 'bal_mean' && datum.value < 0",
                    alt.value("#dc2626"),
                    alt.Color("label:N", scale=_se_dark, legend=None),
                ),
            )
        )
        _se_last = (
            _se_long.sort_values("year").groupby("label", as_index=False).tail(1)
        )
        _se_name_labels = (
            alt.Chart(_se_last)
            .mark_text(align="left", dx=8, fontSize=14, fontWeight="bold")
            .encode(
                x=alt.X("year:O"),
                y=alt.Y("value:Q"),
                text=alt.Text("label:N"),
                color=alt.Color("label:N", scale=_se_dark, legend=None),
            )
        )

        st.altair_chart(
            alt.layer(_se_band, _bal_band, _se_base, _se_value_labels, _se_name_labels).properties(height=380),
            width="stretch",
        )

    # B7: shared bucket palette — ใช้ตรงกันทั้ง P50 balance, shortfall line, และ allocation evolution
    _bucket_color_range = ["#60a5fa", "#34d399", "#f97316"]
    _bucket_domain = [str(d["name"]) for d in _new_defs]
    _bucket_color_scale = alt.Scale(
        domain=_bucket_domain,
        range=_bucket_color_range[:len(_bucket_domain)] if _bucket_domain else _bucket_color_range,
    )

    _path_detail_df = getattr(mc_result, "mc_path_detail_df", None)

    # Pre-process year_summary_df once — shared by Shortfall (Chart 4) and
    # Balance (Chart 6) charts. year_summary_df has P10/P50/P90 per bucket
    # but not the mean — compute mean from path_detail_df and merge in.
    if not year_summary_df.empty:
        chart_df = year_summary_df.copy()
        chart_df["bucket_th"] = chart_df["bucket_name"].astype(str)
        _active = chart_df[
            (chart_df["p10_ending_balance"] != 0)
            | (chart_df["p50_ending_balance"] != 0)
            | (chart_df["p90_ending_balance"] != 0)
        ]
        if not _active.empty:
            _max_active_year = _active.groupby("bucket_name")["year"].max().rename("_max_active_year")
            chart_df = chart_df.merge(_max_active_year, on="bucket_name", how="left")
            chart_df = chart_df[chart_df["year"] <= chart_df["_max_active_year"] + 1].drop(columns=["_max_active_year"])

        # Merge beginning_balance stats per (year, bucket) from path_detail_df
        # — Chart 6 displays beginning balance (= ending of previous year +
        # contribution + rebalance) which is what's "available at start of year"
        # for paying expenses. P10/P50/P90 from path_detail (year_summary_df
        # only carries ending stats).
        if (
            _path_detail_df is not None
            and not _path_detail_df.empty
            and {"year", "bucket_name", "beginning_balance"}.issubset(_path_detail_df.columns)
        ):
            _bb_stats = (
                _path_detail_df.groupby(["year", "bucket_name"], as_index=False)["beginning_balance"]
                .agg(
                    p10_beginning_balance=lambda s: float(s.quantile(0.10)),
                    p50_beginning_balance=lambda s: float(s.quantile(0.50)),
                    p90_beginning_balance=lambda s: float(s.quantile(0.90)),
                    mean_beginning_balance="mean",
                )
            )
            _bb_stats["year"] = _bb_stats["year"].astype(int)
            _bb_stats["bucket_name"] = _bb_stats["bucket_name"].astype(str)
            chart_df["year"] = chart_df["year"].astype(int)
            chart_df["bucket_name"] = chart_df["bucket_name"].astype(str)
            chart_df = chart_df.merge(_bb_stats, on=["year", "bucket_name"], how="left")
        else:
            # Fallback: reuse ending stats if path_detail is unavailable
            chart_df["p10_beginning_balance"]  = chart_df["p10_ending_balance"]
            chart_df["p50_beginning_balance"]  = chart_df["p50_ending_balance"]
            chart_df["p90_beginning_balance"]  = chart_df["p90_ending_balance"]
            chart_df["mean_beginning_balance"] = chart_df["p50_ending_balance"]

        chart_df["p50_label"]  = chart_df["p50_ending_balance"].apply(_fmt_c)
        chart_df["mean_label"] = chart_df["mean_beginning_balance"].apply(_fmt_c)
        chart_df["sf_label"]   = chart_df["shortfall_probability"].apply(lambda x: f"{float(x):.1%}")
    else:
        chart_df = pd.DataFrame()

    # ============================================================
    # CHART 2: Final balance distribution
    # ============================================================
    if not path_summary_df.empty:
        st.markdown("#### 2. 📊 การกระจายตัวของเงินคงเหลือ ณ สิ้นแผน — ทุกเส้นทางจำลอง")

        # ── pre-compute ─────────────────────────────────────────
        _bal_dist = path_summary_df["final_total_balance"].astype(float)
        _ns = (
            int(path_summary_df["path_success"].sum())
            if "path_success" in path_summary_df.columns
            else int((_bal_dist >= 0).sum())
        )
        _nt    = len(path_summary_df)
        _pct_s = _ns / _nt if _nt > 0 else 0.0
        _p10_v = float(_bal_dist.quantile(0.10))
        _p50_v = float(_bal_dist.quantile(0.50))
        _p90_v = float(_bal_dist.quantile(0.90))
        _mean_v = float(_bal_dist.mean())
        _min_v  = float(_bal_dist.min())

        # ── Headline summary ─────────────────────────────────────
        _hl_icon = "✅" if _pct_s >= 0.7 else ("⚠️" if _pct_s >= 0.4 else "🚨")
        st.caption(
            f"{_hl_icon} {_pct_s:.0%} ของเส้นทางจำลอง "
            f"มีเงินเหลือสิ้นแผนและเงินเพียงพอกับค่าใช้จ่ายทุกปี "
            f"({_ns:,} จาก {_nt:,} เส้นทาง)"
        )

        # ── Histogram — สีแยกโซน ─────────────────────────────────
        _hist_df = path_summary_df[["final_total_balance"]].copy()
        _hist_df["_zone"] = _hist_df["final_total_balance"].apply(
            lambda v: "เงินไม่พอ" if float(v) < 0 else "เงินเหลือ"
        )
        _hist_chart = (
            alt.Chart(_hist_df)
            .mark_bar(opacity=0.75)
            .encode(
                x=alt.X(
                    "final_total_balance:Q",
                    bin=alt.Bin(maxbins=50),
                    title="เงินคงเหลือสุทธิ ณ สิ้นแผน (บาท)",
                    axis=alt.Axis(format=",.0f"),
                ),
                y=alt.Y("count():Q", title="จำนวนเส้นทางจำลอง"),
                color=alt.Color(
                    "_zone:N",
                    scale=alt.Scale(
                        domain=["เงินไม่พอ", "เงินเหลือ"],
                        range=["#ef4444", "#22c55e"],
                    ),
                    legend=alt.Legend(title="สถานะ"),
                ),
                tooltip=[
                    alt.Tooltip(
                        "final_total_balance:Q",
                        bin=alt.Bin(maxbins=50),
                        title="ช่วงเงินคงเหลือ (บาท)",
                        format=",.0f",
                    ),
                    alt.Tooltip("count():Q", title="จำนวนเส้นทาง"),
                ],
            )
        )

        # ── เส้น P10 / P50 / P90 (เทา) ────────────────────────────
        _pctile_df = pd.DataFrame([
            {"x": _p10_v, "pctile": f"P10: {_fmt_c(_p10_v)}"},
            {"x": _p50_v, "pctile": f"P50: {_fmt_c(_p50_v)}"},
            {"x": _p90_v, "pctile": f"P90: {_fmt_c(_p90_v)}"},
        ])
        _vlines = (
            alt.Chart(_pctile_df)
            .mark_rule(strokeDash=[5, 3], strokeWidth=1.5, color="#a6acb3")
            .encode(x="x:Q")
        )
        _vlabels = (
            alt.Chart(_pctile_df)
            .mark_text(fontSize=14, fontWeight="bold", color="#a9acb0", angle=0)
            .encode(x="x:Q", y=alt.value(14), text="pctile:N")
        )

        # ── เส้นเงินคงเหลือเฉลี่ย (mean, ฟ้า) ────────────────────
        _mean_df = pd.DataFrame([
            {"x": _mean_v, "lbl": f"เงินคงเหลือเฉลี่ย: {_fmt_c(_mean_v)}"}
        ])
        _mean_line = (
            alt.Chart(_mean_df)
            .mark_rule(strokeDash=[5, 3], strokeWidth=2, color="#4C9BE8")
            .encode(x="x:Q")
        )
        _mean_label = (
            alt.Chart(_mean_df)
            .mark_text(fontSize=14, fontWeight="bold", color="#4C9BE8", angle=0)
            .encode(x="x:Q", y=alt.value(32), text="lbl:N")
        )

        # ── โซนเสี่ยง (ถ้ามี path ติดลบ) ─────────────────────────
        _hist_layers = [_hist_chart, _vlines, _vlabels, _mean_line, _mean_label]
        if _min_v < 0:
            _rect_df = pd.DataFrame([{"x1": _min_v * 1.1, "x2": 0.0}])
            _red_rect = (
                alt.Chart(_rect_df)
                .mark_rect(opacity=0.08, color="red")
                .encode(x="x1:Q", x2="x2:Q")
            )
            _zone_ann_df = pd.DataFrame([{"x": _min_v * 0.55}])
            _zone_ann = (
                alt.Chart(_zone_ann_df)
                .mark_text(fontSize=14, fontWeight="bold", color="#dc2626")
                .encode(x="x:Q", y=alt.value(50), text=alt.value("⚠ โซนเสี่ยง"))
            )
            _hist_layers = [
                _red_rect, _hist_chart, _vlines, _vlabels,
                _mean_line, _mean_label, _zone_ann,
            ]

        st.altair_chart(
            alt.layer(*_hist_layers).properties(height=340),
            width="stretch",
        )

    # ============================================================
    # CHART 3: Annualized return (CAGR) distribution
    # ============================================================
    # ── R6.5: Annualized Return Distribution (dollar-weighted, full horizon) ──
    # Realized CAGR per path = Σ(beginning_balance × sampled_return) / Σ(beginning_balance)
    # over ALL years × buckets. ใช้ beginning_balance เป็น weight เหมือน Task 5
    # แต่ขยาย window จาก 3 ปีแรก → ทุกปี เพื่อสะท้อนผลตอบแทนเฉลี่ยตลอดแผน
    if (
        _path_detail_df is not None
        and not _path_detail_df.empty
        and {"path_id", "sampled_return", "beginning_balance"}.issubset(
            _path_detail_df.columns
        )
    ):
        _cagr_src = _path_detail_df[
            ["path_id", "sampled_return", "beginning_balance"]
        ].copy()
        _cagr_src["sampled_return"] = _cagr_src["sampled_return"].astype(float)
        _cagr_src["beginning_balance"] = _cagr_src["beginning_balance"].astype(float)
        _cagr_src["_weighted_ret"] = (
            _cagr_src["beginning_balance"] * _cagr_src["sampled_return"]
        )
        _cagr_agg = _cagr_src.groupby("path_id", as_index=True).agg(
            _num=("_weighted_ret", "sum"),
            _den=("beginning_balance", "sum"),
        )
        _cagr_agg = _cagr_agg[_cagr_agg["_den"] > 0]
        _path_cagr = (_cagr_agg["_num"] / _cagr_agg["_den"]).rename("realized_cagr")

        if not _path_cagr.empty:
            # Expected return: initial-allocation-weighted bucket mean
            _expected_ret = None
            _alloc_df_exp = getattr(mc_result, "initial_allocation_df", pd.DataFrame())
            if (
                not _alloc_df_exp.empty
                and "recommended_initial_amount" in _alloc_df_exp.columns
                and "bucket_name" in _alloc_df_exp.columns
            ):
                _bucket_exp_map = {
                    str(d["name"]): float(d.get("discount_rate", 0.0))
                    for d in _new_defs
                }
                _alloc_sum = float(_alloc_df_exp["recommended_initial_amount"].sum())
                if _alloc_sum > 0:
                    _expected_ret = sum(
                        float(r["recommended_initial_amount"])
                        * _bucket_exp_map.get(str(r["bucket_name"]), 0.0)
                        for _, r in _alloc_df_exp.iterrows()
                    ) / _alloc_sum

            _cagr_p10 = float(_path_cagr.quantile(0.10))
            _cagr_p50 = float(_path_cagr.quantile(0.50))
            _cagr_p90 = float(_path_cagr.quantile(0.90))

            st.markdown("#### 3. 📈 ผลตอบแทนต่อปีที่เกิดขึ้นจริง (Annualized Return) — กระจายตัวทุกเส้นทาง")
            st.caption(
                "ผลตอบแทนต่อปีที่แต่ละ simulation ทำได้จริง "
                "(เฉลี่ยตลอดแผน ถ่วงน้ำหนักด้วยเงินที่มีในแต่ละปี) "
                "— เทียบกับ ‘ผลตอบแทนเฉลี่ย’ ที่ตั้งไว้ตอนเลือก asset"
            )

            _cagr_hist_df = pd.DataFrame({"cagr_pct": _path_cagr.values * 100})
            _cagr_hist = (
                alt.Chart(_cagr_hist_df)
                .mark_bar(opacity=0.75, color="#FEF3C7")
                .encode(
                    x=alt.X(
                        "cagr_pct:Q",
                        bin=alt.Bin(maxbins=40),
                        title="ผลตอบแทนต่อปี %",
                        axis=alt.Axis(format=".2f"),
                    ),
                    y=alt.Y("count():Q", title="จำนวนเส้นทาง"),
                    tooltip=[
                        alt.Tooltip(
                            "cagr_pct:Q",
                            bin=alt.Bin(maxbins=40),
                            title="ช่วงผลตอบแทน %",
                            format=".2f",
                        ),
                        alt.Tooltip("count():Q", title="จำนวนเส้นทาง"),
                    ],
                )
            )

            # ── P10/P50/P90 lines (gray, label at y=14) ──
            _pctile_rows = [
                {"x": _cagr_p10 * 100, "label": f"P10: {_cagr_p10 * 100:.2f}%"},
                {"x": _cagr_p50 * 100, "label": f"P50: {_cagr_p50 * 100:.2f}%"},
                {"x": _cagr_p90 * 100, "label": f"P90: {_cagr_p90 * 100:.2f}%"},
            ]
            _pctile_df = pd.DataFrame(_pctile_rows)
            _pctile_lines = (
                alt.Chart(_pctile_df)
                .mark_rule(strokeDash=[5, 3], strokeWidth=1.5, color="#a6acb3")
                .encode(x="x:Q")
            )
            _pctile_labels = (
                alt.Chart(_pctile_df)
                .mark_text(fontSize=14, fontWeight="bold", color="#a9acb0")
                .encode(x="x:Q", y=alt.value(14), text="label:N")
            )

            _cagr_layers = [_cagr_hist, _pctile_lines, _pctile_labels]

            # ── ผลตอบแทนเฉลี่ย line (blue, label at y=32 — ใต้ P50) ──
            if _expected_ret is not None:
                _exp_df = pd.DataFrame([{
                    "x": _expected_ret * 100,
                    "label": f"ผลตอบแทนเฉลี่ย: {_expected_ret * 100:.2f}%",
                }])
                _exp_line = (
                    alt.Chart(_exp_df)
                    .mark_rule(strokeDash=[5, 3], strokeWidth=2, color="#1d4ed8")
                    .encode(x="x:Q")
                )
                _exp_label = (
                    alt.Chart(_exp_df)
                    .mark_text(fontSize=14, fontWeight="bold", color="#1d4ed8")
                    .encode(x="x:Q", y=alt.value(32), text="label:N")
                )
                _cagr_layers.extend([_exp_line, _exp_label])

            st.altair_chart(
                alt.layer(*_cagr_layers).properties(height=300),
                width="stretch",
            )

    # ============================================================
    # CHART 4: Shortfall probability per year (Liquidity bucket)
    # ============================================================
    if not chart_df.empty:
        st.markdown("#### 4. ⚠️ ความน่าจะเป็นที่เงินไม่พอในแต่ละปี")
        st.caption(
            "เส้นกราฟแสดงสัดส่วนของ simulation ที่เงินไม่พอจ่ายค่าใช้จ่ายตั้งแต่ปีนั้น "
            "— เลขสูงขึ้น = ความเสี่ยงปีนั้นสูงขึ้น"
        )
        # ใช้ bucket แรก (bill-paying) เป็นตัววัด — bucket อื่นถูก rebalance
        # ระหว่างปี ทำให้ shortfall รายปีของพวกมันไม่สะท้อนความเสี่ยงจริง
        _first_bucket_name = str(_new_defs[0]["name"]) if _new_defs else None
        _sf_chart_df = (
            chart_df[chart_df["bucket_name"].astype(str) == _first_bucket_name].copy()
            if _first_bucket_name else chart_df.iloc[0:0]
        )
        if not _sf_chart_df.empty:
            _sf_line = (
                alt.Chart(_sf_chart_df)
                .mark_line(point=True, color="#f87171", strokeWidth=2.5)
                .encode(
                    x=alt.X("year:O", title="ปี"),
                    y=alt.Y("shortfall_probability:Q", title="โอกาสเงินไม่พอ",
                            axis=alt.Axis(format="%")),
                    tooltip=[
                        alt.Tooltip("year:O",                   title="ปี"),
                        alt.Tooltip("shortfall_probability:Q",  title="โอกาสเงินไม่พอ", format=".1%"),
                    ],
                )
            )
            _sf_labels = (
                alt.Chart(_sf_chart_df)
                .mark_text(dy=-12, fontSize=14, fontWeight="bold", color="#fca5a5")
                .encode(
                    x=alt.X("year:O"),
                    y=alt.Y("shortfall_probability:Q"),
                    text=alt.Text("sf_label:N"),
                )
            )
            st.altair_chart((_sf_line + _sf_labels).properties(height=320), width="stretch")

    # ============================================================
    # CHART 5 (LEGACY — disabled): old stacked-area chart was replaced by
    # the new 3-graph section in Chart 6 below. Block kept in if-False so
    # the entire region can be re-enabled by flipping the guard.
    # ============================================================
    if False and (
        _path_detail_df is not None
        and not _path_detail_df.empty
        and {"year", "bucket_name", "beginning_balance"}.issubset(_path_detail_df.columns)
        and len(_new_defs) >= 2
    ):
        _b0_name_t = str(_new_defs[0]["name"])
        _b1_name_t = str(_new_defs[1]["name"])

        _target_df = (
            _path_detail_df.groupby(["year", "bucket_name"], as_index=False)["beginning_balance"]
            .mean()
            .rename(columns={"beginning_balance": "required_amount"})
        )
        _target_df["year"] = _target_df["year"].astype(int)
        _target_df["bucket_name"] = _target_df["bucket_name"].astype(str)

        if not _target_df.empty:
            st.markdown("#### 5. 🎯 เงินคงเหลือต้นปีของแต่ละ bucket (เฉลี่ย — Mean ของ Simulation)")
            st.caption(
                "ค่าเฉลี่ย (mean) ของ beginning_balance ต่อ bucket ต่อปี จาก Monte Carlo simulation "
                "— สะท้อน allocation ที่เกิดขึ้นจริงในกรณีค่าคาดการณ์ของทุก simulation"
            )

            # Force complete (year × bucket) grid with 0-fill
            _all_years_t = sorted(_target_df["year"].unique().tolist())
            _all_buckets_t = [_b0_name_t, _b1_name_t]
            _grid_t = pd.MultiIndex.from_product(
                [_all_years_t, _all_buckets_t], names=["year", "bucket_name"]
            ).to_frame(index=False)
            _target_df = (
                _grid_t.merge(_target_df, on=["year", "bucket_name"], how="left")
                .fillna({"required_amount": 0.0})
            )
            _target_df["required_amount"] = _target_df["required_amount"].clip(lower=0)
            _target_df["bucket_th"] = _target_df["bucket_name"].astype(str)

            _year_totals_t = (
                _target_df.groupby("year")["required_amount"].sum().rename("_total")
            )
            _target_df = _target_df.merge(_year_totals_t, on="year", how="left")
            import numpy as _np_target
            _target_df["weight_frac"] = _np_target.where(
                _target_df["_total"] > 0,
                _target_df["required_amount"] / _target_df["_total"].replace(0, 1),
                0.0,
            )
            _target_df["weight_pct"] = (_target_df["weight_frac"] * 100).round(1)

            # ── View 1: absolute baht (stacked area) ──
            _target_abs_chart = (
                alt.Chart(_target_df)
                .mark_area()
                .encode(
                    x=alt.X("year:O", title="ปี"),
                    y=alt.Y(
                        "required_amount:Q",
                        stack=True,
                        title="เงินเป้าหมาย (บาท)",
                        axis=alt.Axis(format=",.0f"),
                    ),
                    color=alt.Color(
                        "bucket_th:N", title="กลุ่มลงทุน", scale=_bucket_color_scale
                    ),
                    tooltip=[
                        alt.Tooltip("year:O", title="ปี"),
                        alt.Tooltip("bucket_th:N", title="กลุ่มลงทุน"),
                        alt.Tooltip(
                            "required_amount:Q", title="เงินเป้าหมาย", format=",.0f"
                        ),
                        alt.Tooltip("weight_pct:Q", title="สัดส่วน %", format=".1f"),
                    ],
                )
                .properties(height=300)
            )
            st.altair_chart(_target_abs_chart, width="stretch")

            # ── View 2: normalized % (stacked area, 0–100%) ──
            _target_pct_chart = (
                alt.Chart(_target_df)
                .mark_area()
                .encode(
                    x=alt.X("year:O", title="ปี"),
                    y=alt.Y(
                        "weight_frac:Q",
                        stack=True,
                        title="สัดส่วน",
                        scale=alt.Scale(domain=[0, 1]),
                        axis=alt.Axis(format=".0%"),
                    ),
                    color=alt.Color(
                        "bucket_th:N", title="กลุ่มลงทุน", scale=_bucket_color_scale
                    ),
                    tooltip=[
                        alt.Tooltip("year:O", title="ปี"),
                        alt.Tooltip("bucket_th:N", title="กลุ่มลงทุน"),
                        alt.Tooltip(
                            "required_amount:Q", title="เงินเป้าหมาย", format=",.0f"
                        ),
                        alt.Tooltip("weight_pct:Q", title="สัดส่วน %", format=".1f"),
                    ],
                )
                .properties(height=240)
            )
            st.altair_chart(_target_pct_chart, width="stretch")

    # ============================================================
    # CHART 6: เงินคงเหลือต้นปี — 3 sub-graphs (replaces old Chart 5+6)
    #   6.1 Stacked area (bucket 1 ล่าง, bucket 2 บน) — mean
    #   6.2 bucket 2 (long) — band + mean
    #   6.3 bucket 1 (bill-paying) — band + mean + target (rolling window)
    # ============================================================
    if not chart_df.empty and len(_new_defs) >= 2:
        st.markdown("#### 5. 💼 การจัดสรรเงินในแต่ละปี — ภาพรวม + รายละเอียดแต่ละ bucket")
        _b0_name = str(_new_defs[0]["name"])  # bucket 1 (bill-paying)
        _b1_name = str(_new_defs[1]["name"])  # bucket 2 (long / growth)

        # ── 6.1 Stacked area: bucket 1 (b0) ล่าง, bucket 2 (b1) บน ──
        _stack_df = chart_df[
            ["year", "bucket_name", "bucket_th", "mean_beginning_balance"]
        ].copy()
        _stack_df["mean_beginning_balance"] = (
            _stack_df["mean_beginning_balance"].fillna(0.0).clip(lower=0)
        )
        _stack_df["_stack_order"] = (
            _stack_df["bucket_name"].map({_b0_name: 0, _b1_name: 1})
            .fillna(99).astype(int)
        )
        st.markdown("##### 5.1 ภาพรวมการจัดสรรเงิน")
        st.caption(
            f"🟦 **{_b0_name}** | "
            f"🟩 **{_b1_name}**"
        )
        _stack_area = (
            alt.Chart(_stack_df)
            .mark_area(opacity=0.85)
            .encode(
                x=alt.X("year:O", title="ปี"),
                y=alt.Y(
                    "mean_beginning_balance:Q",
                    stack="zero",
                    title="ยอดเงิน ณ ต้นปี (บาท)",
                    axis=alt.Axis(format=",.0f"),
                ),
                color=alt.Color(
                    "bucket_th:N", scale=_bucket_color_scale, legend=None,
                ),
                order=alt.Order("_stack_order:Q"),
                tooltip=[
                    alt.Tooltip("year:O",                    title="ปี"),
                    alt.Tooltip("bucket_th:N",               title="กลุ่มลงทุน"),
                    alt.Tooltip("mean_beginning_balance:Q",  title="ค่าเฉลี่ย", format=",.0f"),
                ],
            )
            .properties(height=300)
        )

        # ── Total label per year (sum of bucket 1 + bucket 2) on top of stack ──
        _total_per_year = (
            _stack_df.groupby("year", as_index=False)["mean_beginning_balance"]
            .sum()
            .rename(columns={"mean_beginning_balance": "total"})
        )
        _total_per_year["total_label"] = _total_per_year["total"].apply(_fmt_c)
        _stack_totals = (
            alt.Chart(_total_per_year)
            .mark_text(dy=-10, fontSize=14, fontWeight="bold", color="#a9acb0")
            .encode(
                x=alt.X("year:O"),
                y=alt.Y("total:Q"),
                text=alt.Text("total_label:N"),
            )
        )

        st.altair_chart(
            alt.layer(_stack_area, _stack_totals).properties(height=320),
            width="stretch",
        )

    # ── Compute target for bucket 1 (bill-paying) — used by 6.3 ──
    _target_chart_df = pd.DataFrame()
    if (
        not chart_df.empty
        and len(_new_defs) >= 2
        and expense_df is not None
        and not expense_df.empty
        and {"year", "inflated_amount"}.issubset(expense_df.columns)
        and assumptions is not None
    ):
        _exp_by_year_t = (
            expense_df.groupby("year")["inflated_amount"].sum().sort_index()
        )
        _last_exp_year_t = int(_exp_by_year_t.index.max())
        _b0_start_off_t = int(_new_defs[0].get("year_start", 1))
        _b0_end_off_t = _new_defs[0].get("year_end")
        _window_0_t = (
            int(_b0_end_off_t) - _b0_start_off_t + 1
            if _b0_end_off_t is not None else 1
        )
        if _window_0_t < 1:
            _window_0_t = 1

        def _sum_exp_t(_y_from: int, _y_to: int) -> float:
            if _y_from > _y_to:
                return 0.0
            return float(sum(
                float(_exp_by_year_t.get(_t, 0.0))
                for _t in range(_y_from, _y_to + 1)
            ))

        _all_chart_years_t = sorted(int(y) for y in chart_df["year"].unique())
        _tgt_rows_t = []
        for _y in _all_chart_years_t:
            _b0_win_end_t = min(_y + _window_0_t - 1, _last_exp_year_t)
            _tgt_rows_t.append({
                "year": _y, "bucket_name": _b0_name,
                "target_amount": round(_sum_exp_t(_y, _b0_win_end_t), 2),
            })
        _target_chart_df = pd.DataFrame(_tgt_rows_t)
        if not _target_chart_df.empty:
            _target_chart_df["bucket_th"] = _target_chart_df["bucket_name"].astype(str)

    # ── Helper: per-bucket band + mean + optional target ──
    def _render_per_bucket_chart(_bname: str, _heading: str, _show_target: bool):
        _df_b = chart_df[chart_df["bucket_name"].astype(str) == _bname].copy()
        if _df_b.empty:
            st.markdown(_heading)
            st.info(f"ไม่มีข้อมูลของ {_bname}")
            return

        _SERIES_MEAN   = "เส้นค่าเฉลี่ย"
        _SERIES_BAND   = "ช่วง P10–P90"
        _SERIES_TARGET = "เป้าหมาย (rolling window)"

        _style_domain = [_SERIES_MEAN, _SERIES_BAND]
        _stroke_range = [[1, 0], [0, 0]]
        _opac_range   = [0, 0.15]
        if _show_target:
            _style_domain.append(_SERIES_TARGET)
            _stroke_range.append([6, 4])
            _opac_range.append(0)

        _stroke_scale_b = alt.Scale(domain=_style_domain, range=_stroke_range)
        _opac_scale_b   = alt.Scale(domain=_style_domain, range=_opac_range)

        _mean_long_b = _df_b[
            ["year", "bucket_th", "mean_beginning_balance", "mean_label"]
        ].copy()
        _mean_long_b["series"] = _SERIES_MEAN
        _mean_long_b = _mean_long_b.rename(columns={"mean_beginning_balance": "value"})

        if _show_target and not _target_chart_df.empty:
            _tgt_b = _target_chart_df[
                _target_chart_df["bucket_name"].astype(str) == _bname
            ][["year", "bucket_th", "target_amount"]].copy()
            _tgt_b["series"] = _SERIES_TARGET
            _tgt_b = _tgt_b.rename(columns={"target_amount": "value"})
        else:
            _tgt_b = pd.DataFrame(columns=["year", "bucket_th", "value", "series"])

        _lines_long_b = pd.concat([_mean_long_b, _tgt_b], ignore_index=True, sort=False)

        _band_df_b = _df_b[
            ["year", "bucket_th", "p10_beginning_balance", "p90_beginning_balance"]
        ].copy()
        _band_df_b["series"] = _SERIES_BAND
        _band_b = (
            alt.Chart(_band_df_b)
            .mark_area(opacity=0.15)
            .encode(
                x=alt.X("year:O", title="ปี"),
                y=alt.Y("p10_beginning_balance:Q",
                        title="ยอดเงิน ณ ต้นปี (บาท)",
                        axis=alt.Axis(format=",")),
                y2=alt.Y2("p90_beginning_balance:Q"),
                color=alt.Color("bucket_th:N", scale=_bucket_color_scale, legend=None),
                opacity=alt.Opacity(
                    "series:N",
                    scale=_opac_scale_b,
                    legend=None,
                ),
            )
        )
        # Mean line — bucket color, solid (separate layer from target so they
        # can use different colors)
        _mean_only_b = _lines_long_b[_lines_long_b["series"] == _SERIES_MEAN]
        _mean_line_b = (
            alt.Chart(_mean_only_b)
            .mark_line(point=True)
            .encode(
                x=alt.X("year:O"),
                y=alt.Y("value:Q", axis=alt.Axis(format=",")),
                color=alt.Color(
                    "bucket_th:N", scale=_bucket_color_scale, legend=None,
                ),
                tooltip=[
                    alt.Tooltip("year:O",      title="ปี"),
                    alt.Tooltip("bucket_th:N", title="กลุ่มลงทุน"),
                    alt.Tooltip("series:N",    title="ประเภท"),
                    alt.Tooltip("value:Q",     title="บาท", format=",.0f"),
                ],
            )
        )

        _line_layers_b = [_mean_line_b]

        # Target line — separate layer with darker color so it stands out
        if _show_target:
            _target_only_b = _lines_long_b[_lines_long_b["series"] == _SERIES_TARGET]
            if not _target_only_b.empty:
                _target_line_b = (
                    alt.Chart(_target_only_b)
                    .mark_line(strokeDash=[6, 4], strokeWidth=2.5, color="#1d4ed8")
                    .encode(
                        x=alt.X("year:O"),
                        y=alt.Y("value:Q"),
                        tooltip=[
                            alt.Tooltip("year:O",   title="ปี"),
                            alt.Tooltip("series:N", title="ประเภท"),
                            alt.Tooltip("value:Q",  title="บาท", format=",.0f"),
                        ],
                    )
                )
                _line_layers_b.append(_target_line_b)

        _labels_b = (
            alt.Chart(_df_b)
            .mark_text(dy=-12, fontSize=14, fontWeight="bold")
            .encode(
                x=alt.X("year:O"),
                y=alt.Y("mean_beginning_balance:Q"),
                text=alt.Text("mean_label:N"),
                color=alt.Color("bucket_th:N", scale=_bucket_color_scale, legend=None),
            )
        )

        st.markdown(_heading)
        st.altair_chart(
            alt.layer(_band_b, *_line_layers_b, _labels_b)
            .resolve_scale(opacity="independent", strokeDash="independent")
            .properties(height=320),
            width="stretch",
        )

    if not chart_df.empty and len(_new_defs) >= 2:
        # ── 6.2 bucket 2 (long) — no target ──
        _render_per_bucket_chart(
            _b1_name,
            "##### 5.2 การจัดสรรเงินสำหรับลงทุนเพื่อการศึกษา — แถบ P10–P90, เส้นค่าเฉลี่ย",
            _show_target=False,
        )
        # ── 6.3 bucket 1 (bill-paying) — with target ──
        _render_per_bucket_chart(
            _b0_name,
            "##### 5.3 การจัดสรรเงินสำหรับค่าใช้จ่าย — แถบ P10–P90, เส้นค่าเฉลี่ย, เส้นประแสดงเป้าหมายเพื่อให้ครอบคลุมค่าใช้จ่าย",
            _show_target=True,
        )

    # Legacy block — disabled (kept for reference; replaced by 6.1–6.3 above)
    if False:

        # ── Compute target for BUCKET แรก only (bill-paying bucket) ──
        # ตรงกับ engine: ต้นปี y, bucket 0 ต้องมีเงินพอจ่ายค่าใช้จ่าย
        # ในอีก window_0 ปีถัดไป. ไม่ทำ target ของ bucket 2 เพราะค่าตัวเลข
        # สูงเกินสเกลกราฟ (ทับเส้น mean ของทั้ง 2 buckets).
        #   target_b0(y) = Σ expense[t]  for t in [y, y+window_0-1]
        _target_chart_df = pd.DataFrame()
        if (
            expense_df is not None
            and not expense_df.empty
            and {"year", "inflated_amount"}.issubset(expense_df.columns)
            and assumptions is not None
            and _new_defs
        ):
            _exp_by_year = (
                expense_df.groupby("year")["inflated_amount"].sum().sort_index()
            )
            _sim_start = int(getattr(assumptions, "start_year", _exp_by_year.index.min()))
            _last_exp_year = int(_exp_by_year.index.max())

            _b0_name = str(_new_defs[0]["name"])
            _b0_start_off = int(_new_defs[0].get("year_start", 1))
            _b0_end_off = _new_defs[0].get("year_end")
            _window_0 = (
                int(_b0_end_off) - _b0_start_off + 1
                if _b0_end_off is not None else 1
            )
            if _window_0 < 1:
                _window_0 = 1

            def _sum_exp(_y_from: int, _y_to: int) -> float:
                if _y_from > _y_to:
                    return 0.0
                return float(
                    sum(
                        float(_exp_by_year.get(_t, 0.0))
                        for _t in range(_y_from, _y_to + 1)
                    )
                )

            _all_chart_years = sorted(int(y) for y in chart_df["year"].unique())
            _tgt_rows = []
            for _y in _all_chart_years:
                _b0_win_end = min(_y + _window_0 - 1, _last_exp_year)
                _t0 = _sum_exp(_y, _b0_win_end)
                _tgt_rows.append({
                    "year": _y, "bucket_name": _b0_name, "target_amount": round(_t0, 2),
                })
            _target_chart_df = pd.DataFrame(_tgt_rows)
            if not _target_chart_df.empty:
                _target_chart_df["bucket_th"] = _target_chart_df["bucket_name"].astype(str)

        # ── Build a long-form lines DataFrame so the legend can show all
        # three series (Mean + Band + Target) with the right style swatch. ──
        _SERIES_MEAN   = "เส้นค่าเฉลี่ย"
        _SERIES_BAND   = "ช่วง P10–P90"
        _SERIES_TARGET = "เป้าหมาย (bucket แรก)"
        _STYLE_DOMAIN  = [_SERIES_MEAN, _SERIES_BAND, _SERIES_TARGET]

        # Mean line data
        _mean_long = chart_df[["year", "bucket_th", "mean_beginning_balance", "mean_label",
                               "p10_beginning_balance", "p90_beginning_balance"]].copy()
        _mean_long["series"] = _SERIES_MEAN
        _mean_long = _mean_long.rename(columns={"mean_beginning_balance": "value"})

        # Target line data (only bucket 0)
        if not _target_chart_df.empty:
            _target_long = _target_chart_df[["year", "bucket_th", "target_amount"]].copy()
            _target_long["series"] = _SERIES_TARGET
            _target_long = _target_long.rename(columns={"target_amount": "value"})
        else:
            _target_long = pd.DataFrame(columns=["year", "bucket_th", "value", "series"])

        _lines_long = pd.concat([_mean_long, _target_long], ignore_index=True, sort=False)

        # strokeDash legend: maps series name → dash pattern
        _stroke_scale = alt.Scale(
            domain=_STYLE_DOMAIN,
            range=[[1, 0], [0, 0], [6, 4]],   # solid / (band shown via area) / dashed
        )

        # ── Band layer — encoded with a fake "series" so it shows in legend ──
        _band_df = chart_df[["year", "bucket_th", "p10_beginning_balance",
                             "p90_beginning_balance"]].copy()
        _band_df["series"] = _SERIES_BAND
        _band = (
            alt.Chart(_band_df)
            .mark_area(opacity=0.15)
            .encode(
                x=alt.X("year:O", title="ปี"),
                y=alt.Y("p10_beginning_balance:Q", title="ยอดเงิน ณ ต้นปี (บาท)",
                        axis=alt.Axis(format=",")),
                y2=alt.Y2("p90_beginning_balance:Q"),
                color=alt.Color("bucket_th:N", scale=_bucket_color_scale, legend=None),
                opacity=alt.Opacity(
                    "series:N",
                    scale=alt.Scale(domain=_STYLE_DOMAIN, range=[0, 0.15, 0]),
                    legend=alt.Legend(title="ประเภทเส้น", orient="right"),
                ),
            )
        )

        # ── Combined line layer (Mean + Target) with strokeDash legend ──
        _lines = (
            alt.Chart(_lines_long)
            .mark_line(point=True)
            .encode(
                x=alt.X("year:O", title="ปี"),
                y=alt.Y("value:Q", title="ยอดเงิน ณ ต้นปี (บาท)",
                        axis=alt.Axis(format=",")),
                color=alt.Color("bucket_th:N", scale=_bucket_color_scale, title="กลุ่มลงทุน"),
                strokeDash=alt.StrokeDash(
                    "series:N",
                    scale=_stroke_scale,
                    legend=alt.Legend(title="ประเภทเส้น", orient="right"),
                ),
                tooltip=[
                    alt.Tooltip("year:O",      title="ปี"),
                    alt.Tooltip("bucket_th:N", title="กลุ่มลงทุน"),
                    alt.Tooltip("series:N",    title="ประเภท"),
                    alt.Tooltip("value:Q",     title="บาท", format=",.0f"),
                ],
            )
        )

        # ── Value labels on the Mean line only ──
        _line_labels = (
            alt.Chart(chart_df)
            .mark_text(dy=-12, fontSize=14, fontWeight="bold")
            .encode(
                x=alt.X("year:O"),
                y=alt.Y("mean_beginning_balance:Q"),
                text=alt.Text("mean_label:N"),
                color=alt.Color("bucket_th:N", scale=_bucket_color_scale, legend=None),
            )
        )

        st.altair_chart(
            alt.layer(_band, _lines, _line_labels)
            .resolve_scale(opacity="independent", strokeDash="independent")
            .properties(height=380),
            width="stretch",
        )

    # ── Tables (📊 ตารางข้อมูล) moved to the bottom of the page ──
    # "🔭 มุมมองเพิ่มเติม" header removed; charts below flow directly.

    _viz_path_df = getattr(mc_result, "mc_path_detail_df", pd.DataFrame())

    # Portfolio total per (path_id, year) — sum across buckets.
    # Used by fan chart, cashflow table, and drawdown chart.
    if (
        _viz_path_df is not None
        and not _viz_path_df.empty
        and {"path_id", "year", "ending_balance"}.issubset(_viz_path_df.columns)
    ):
        _agg_cols = {"ending_balance": "sum"}
        for _c in ("beginning_balance", "contribution_in", "investment_return", "expense_out"):
            if _c in _viz_path_df.columns:
                _agg_cols[_c] = "sum"
        _port_path_year = (
            _viz_path_df.groupby(["path_id", "year"], as_index=False)
            .agg(_agg_cols)
            .sort_values(["path_id", "year"])
        )
    else:
        _port_path_year = pd.DataFrame()

    # ── Chart 7 (Fan Chart) removed ──

    # ── Education Timeline (Gantt) — x-axis = actual calendar year ──
    # ดึงจาก expense_df (rows ที่เป็นการศึกษา) แล้ว groupby (child × level) เพื่อหา
    # ช่วงปีจริง (min/max year) แทนการใช้อายุ — ผู้ใช้จะเห็นว่าค่าใช้จ่ายแต่ละ
    # ระดับการศึกษาเกิดขึ้นในปี พ.ศ./ค.ศ. ไหนตรง ๆ
    # ── Per-Goal Funded Ratio Summary (Timeline chart embedded inside) ──
    st.markdown("#### 6. 🎯 สรุปสถานะแต่ละเป้าหมายการศึกษา (Funded Ratio)")

    # ── Education Timeline (moved from old Chart 6) ──
    # x-axis = actual calendar year. Legend sorted by education level.
    st.caption("ช่วงปีที่ลูกแต่ละคนอยู่ในแต่ละระดับการศึกษา")
    if (
        expense_df is not None
        and not expense_df.empty
        and {"year", "child_name", "category", "sub_category"}.issubset(expense_df.columns)
    ):
        _edu_mask = (
            expense_df["category"].astype(str).str.endswith(" education")
            & (expense_df["child_name"].astype(str) != "Parent")
        )
        _edu_src = expense_df[_edu_mask].copy()

        if not _edu_src.empty:
            _agg_dict = {
                "year_start": ("year", "min"),
                "year_end":   ("year", "max"),
                "avg_inflated": ("inflated_amount", "mean"),
            }
            if "child_age" in _edu_src.columns:
                _agg_dict["age_start"] = ("child_age", "min")
                _agg_dict["age_end"]   = ("child_age", "max")

            _tl_df = (
                _edu_src.groupby(["child_name", "sub_category"], as_index=False)
                .agg(**_agg_dict)
            )
            _tl_df["year_start"] = _tl_df["year_start"].astype(int)
            _tl_df["year_end"]   = _tl_df["year_end"].astype(int)
            _tl_df["year_end_excl"] = _tl_df["year_end"] + 1
            # Translate sub_category keys → Thai labels so colors match
            # Page 2 Chart 2 (which also stores translated labels in sub_category)
            _tl_df["ระดับ"] = _tl_df["sub_category"].astype(str).apply(edu_level_label)

            # Education-level order for legend + color scale (translated labels)
            # อนุบาล → ป.ตรี → ป.โท → ป.เอก
            _level_order_keys = [
                "kindergarten", "elementary", "middle_school", "high_school",
                "bachelor", "master", "doctor", "other",
            ]
            _level_order = [edu_level_label(k) for k in _level_order_keys]
            _present_levels = [
                lvl for lvl in _level_order if lvl in _tl_df["ระดับ"].unique()
            ]
            for lvl in _tl_df["ระดับ"].unique():
                if lvl not in _present_levels:
                    _present_levels.append(lvl)

            _tt = [
                alt.Tooltip("child_name:N",   title="ลูก"),
                alt.Tooltip("ระดับ:N",         title="ระดับ"),
                alt.Tooltip("year_start:Q",   title="ปีเริ่ม",   format="d"),
                alt.Tooltip("year_end:Q",     title="ปีจบ",     format="d"),
                alt.Tooltip("avg_inflated:Q", title="ค่าใช้จ่ายเฉลี่ย/ปี (฿)", format=",.0f"),
            ]
            if "age_start" in _tl_df.columns:
                _tt.insert(3, alt.Tooltip("age_start:Q", title="อายุเริ่ม", format="d"))
                _tt.insert(4, alt.Tooltip("age_end:Q",   title="อายุจบ",   format="d"))

            _n_children_tl = _tl_df["child_name"].nunique()
            _tl_chart = (
                alt.Chart(_tl_df)
                .mark_bar(cornerRadius=4, opacity=0.85)
                .encode(
                    x=alt.X(
                        "year_start:Q",
                        title="ปี",
                        scale=alt.Scale(zero=False),
                        axis=alt.Axis(format="d", tickMinStep=1),
                    ),
                    x2=alt.X2("year_end_excl:Q"),
                    y=alt.Y("child_name:N", title="ลูก", sort=None),
                    color=alt.Color(
                        "ระดับ:N",
                        title="ระดับการศึกษา",
                        sort=_present_levels,
                    ),
                    tooltip=_tt,
                )
                .properties(height=max(70 * max(_n_children_tl, 1), 160))
            )
            st.altair_chart(_tl_chart, width="stretch")
        else:
            st.info("ไม่มีค่าใช้จ่ายการศึกษาในแผนนี้")
    else:
        st.info("ไม่มีข้อมูลค่าใช้จ่ายสำหรับสร้าง timeline")

    # ── Goal FR computation (renders the goal summary table inside Chart 6) ──
    _goal_path_df = getattr(mc_result, "mc_path_detail_df", pd.DataFrame())
    if (
        expense_df is not None
        and not expense_df.empty
        and {"year", "child_name", "category", "sub_category", "inflated_amount"}.issubset(expense_df.columns)
        and _goal_path_df is not None
        and not _goal_path_df.empty
        and {"path_id", "year", "expense_out"}.issubset(_goal_path_df.columns)
    ):
        _goal_mask = (
            expense_df["category"].astype(str).str.endswith(" education")
            & (expense_df["child_name"].astype(str) != "Parent")
        )
        _goal_src = expense_df[_goal_mask].copy()

        # Pre-compute non-education ("extra") expenses per child (excluding Parent)
        # Used by the cost column — full child-extras total is attached to every
        # goal row for that child (not prorated across levels).
        _extras_mask = (
            ~expense_df["category"].astype(str).str.endswith(" education")
            & (expense_df["child_name"].astype(str) != "Parent")
        )
        _extras_src_df = expense_df[_extras_mask]
        _extras_by_child = (
            _extras_src_df.groupby("child_name")["inflated_amount"].sum().to_dict()
            if not _extras_src_df.empty else {}
        )

        # Per-(child, year) inflated total — ALL expenses for that child
        # (education + extras), excluding Parent. ใช้สำหรับ "เงินจ่ายจริงเฉลี่ย"
        # โดยถ่วงน้ำหนัก expense_out ด้วย child-share รายปี
        _nonparent_src_df = expense_df[expense_df["child_name"].astype(str) != "Parent"]
        _child_year_inflated = (
            _nonparent_src_df.groupby(["child_name", "year"])["inflated_amount"].sum()
            if not _nonparent_src_df.empty else pd.Series(dtype=float)
        )

        if not _goal_src.empty:
            # Build goal list: (child_name, sub_category)
            _goals_df = (
                _goal_src.groupby(["child_name", "sub_category"], as_index=False)
                .agg(
                    year_start=("year", "min"),
                    year_end=("year", "max"),
                    goal_required=("inflated_amount", "sum"),
                )
            )
            _goals_df["year_start"] = _goals_df["year_start"].astype(int)
            _goals_df["year_end"] = _goals_df["year_end"].astype(int)

            # Annual planned expense total (denominator of goal-share)
            _annual_total = (
                expense_df.groupby("year")["inflated_amount"].sum().rename("annual_total")
            )

            # Total paid per (path_id, year) — sum across buckets.
            # NOTE: engine writes expense_out = full planned expense even when the
            # portfolio can't cover it (balance goes negative — that's how shortfall
            # is recorded). We derive *realized* paid here by capping at the
            # pre-expense portfolio value:
            #   pre_expense   = sum(ending_balance) + sum(expense_out)
            #   realized_paid = max(0, min(attempted, pre_expense))
            # → full when healthy, partial when balance crosses zero mid-year,
            #   zero when portfolio was already underwater before expense.
            _paid_py = (
                _goal_path_df.groupby(["path_id", "year"], as_index=False)
                .agg(
                    _attempted=("expense_out", "sum"),
                    _ending_sum=("ending_balance", "sum"),
                )
            )
            _paid_py["year"] = _paid_py["year"].astype(int)
            _paid_py["_pre_expense"] = _paid_py["_ending_sum"] + _paid_py["_attempted"]
            # Tolerance against engine's 2-decimal rounding of balances/expense:
            # if pre_expense covers attempted within 1 THB, treat as fully paid.
            # (Without this, sub-cent negative ending_sum makes per-path FR
            # round to 0.9999... → P(จ่ายเต็ม) collapses to 0% in healthy years.)
            _ROUND_TOL = 1.0
            _paid_py["total_paid"] = _paid_py["_attempted"].where(
                _paid_py["_pre_expense"] >= _paid_py["_attempted"] - _ROUND_TOL,
                _paid_py["_pre_expense"].clip(lower=0.0),
            )
            _paid_py = _paid_py[["path_id", "year", "total_paid"]]

            _goal_rows_summary = []
            for _, _g in _goals_df.iterrows():
                _ch = str(_g["child_name"])
                _lv = str(_g["sub_category"])
                _ys = int(_g["year_start"])
                _ye = int(_g["year_end"])
                _req = float(_g["goal_required"])

                if _req <= 0:
                    continue

                # All metrics use CHILD-WINDOW scope: every expense of this child
                # (education + extras) within [_ys, _ye]. The row label says
                # "Child — education level" but the numbers reflect the child's
                # entire bill during that life chapter — keeps cost, paid, FR,
                # P(จ่ายเต็ม), and ขาด on the same denominator so the displayed
                # ratios are internally consistent.
                _child_share_map = {}
                _cost_total = 0.0
                for _y_iter in range(_ys, _ye + 1):
                    try:
                        _ch_amt = float(_child_year_inflated.loc[(_ch, _y_iter)])
                    except KeyError:
                        _ch_amt = 0.0
                    try:
                        _ann_amt = float(_annual_total.loc[_y_iter])
                    except (KeyError, AttributeError):
                        _ann_amt = 0.0
                    _child_share_map[_y_iter] = (
                        (_ch_amt / _ann_amt) if _ann_amt > 0 else 0.0
                    )
                    _cost_total += _ch_amt

                if _cost_total <= 0:
                    continue

                _paid_child_win = _paid_py[
                    _paid_py["year"].isin(_child_share_map.keys())
                ].copy()
                if _paid_child_win.empty:
                    continue

                _paid_child_win["share"] = _paid_child_win["year"].map(_child_share_map)
                _paid_child_win["child_funded"] = (
                    _paid_child_win["total_paid"].astype(float)
                    * _paid_child_win["share"].astype(float)
                )
                _child_funded_path = (
                    _paid_child_win.groupby("path_id")["child_funded"].sum()
                )
                if _child_funded_path.empty:
                    continue

                _fr_series = (_child_funded_path / _cost_total).astype(float)
                _fr_med = float(_fr_series.quantile(0.50))
                _fr_p10 = float(_fr_series.quantile(0.10))
                _fr_p90 = float(_fr_series.quantile(0.90))
                # P(จ่ายเต็ม) = สัดส่วน path ที่จ่ายได้ครบ (child_funded ≥ cost_total).
                # ใส่ tolerance 1e-9 กัน path ที่จ่ายเต็มจริงแต่ลงเอยที่ 0.99999998
                # จาก share × total_paid arithmetic.
                _p_funded = float((_fr_series >= (1.0 - 1e-9)).mean())
                _funded_avg = float(_child_funded_path.mean())
                # Funded Ratio (avg) คำนวณตรงจากตัวเลขที่แสดง:
                #   FR = เงินจ่ายจริงเฉลี่ย / ค่าใช้จ่าย
                # mathematically เทียบเท่ากับ mean(child_funded / cost_total)
                # เพราะ cost_total คงที่ต่อแถว — แต่เขียนแบบนี้ตรงกับตาราง.
                _fr_avg = _funded_avg / _cost_total if _cost_total > 0 else 0.0

                # Status threshold ผูกกับ display rounding (FR ใช้ :,.0f →
                # ปัดเป็นจำนวนเต็ม %). ถ้าผู้ใช้เห็น "100%" ต้องเป็น 🟢 เพื่อ
                # ความสอดคล้องในตาราง. FR=99.6% display="100%" → 🟢 (≥0.995).
                if _fr_avg >= 0.995:
                    _tl = "green"
                elif _fr_avg >= 0.795:
                    _tl = "yellow"
                else:
                    _tl = "red"

                _goal_rows_summary.append({
                    "traffic_light": _tl,
                    "child_name": _ch,
                    "level_label": _lv,
                    "start_year": _ys,
                    "end_year": _ye,
                    "fr_median": _fr_med,
                    "fr_avg": _fr_avg,
                    "fr_p10": _fr_p10,
                    "fr_p90": _fr_p90,
                    "p_funded": _p_funded,
                    "total_required": _req,
                    "funded_avg": _funded_avg,
                    "cost_total": _cost_total,
                })

            if _goal_rows_summary:
                def _light_label_goal(tl: str) -> str:
                    return {
                        "green":  S("p3b", "light_green"),
                        "yellow": S("p3b", "light_yellow"),
                        "red":    S("p3b", "light_red"),
                    }.get(tl, tl)

                # Sort: by education level (start_year proxy), then by child_name
                _goal_rows_summary.sort(
                    key=lambda r: (r["start_year"], r["child_name"])
                )

                _goal_display_rows = []
                for _r in _goal_rows_summary:
                    _goal_display_rows.append({
                        S("p3b", "tbl_status"):        _light_label_goal(_r["traffic_light"]),
                        S("p3b", "tbl_goal"):          f"{_r['child_name']} — {_r['level_label']}",
                        S("p3b", "tbl_due"):           f"{int(_r['start_year'])}–{int(_r['end_year'])}",
                        "ค่าใช้จ่าย":                   _fmt_money(_r["cost_total"]),
                        "เงินที่สามารถจ่ายได้เฉลี่ย":      _fmt_money(_r["funded_avg"]),
                        "Funded Ratio":                f"{_r['fr_avg']*100:,.0f}%",
                        "Funded Ratio (P10-P90)":      f"{_r['fr_p10']*100:,.0f}% – {_r['fr_p90']*100:,.0f}%",
                    })
                st.caption(
                    "1 แถวต่อเป้าหมาย (ลูก - ระดับการศึกษา) — "
                    "Funded Ratio (FR) = เงินที่สามารถจ่ายได้จากการจำลอง / ค่าใช้จ่าย"
                )
                st.dataframe(
                    pd.DataFrame(_goal_display_rows), width="stretch", hide_index=True
                )
                st.caption(
                    "🟢 ผ่าน (FR ≥ 100%) | 🟡 เสี่ยง (FR 80–100%) | 🔴 ไม่ผ่าน (FR < 80%)"
                )
            else:
                st.info("ไม่สามารถคำนวณสรุปเป้าหมายได้")
        else:
            st.info("ไม่มีเป้าหมายการศึกษาในแผนนี้")
    else:
        st.info("ไม่มีข้อมูลสำหรับสร้างสรุปเป้าหมาย — กรุณารัน Monte Carlo อีกครั้ง")

    # ── 2) Cashflow per year (mean MC + per-child planned expenses, recomputed ending) ──
    # ใช้ค่า mean (เฉลี่ย) ของ MC สำหรับ balance/contribution/return
    # ค่าใช้จ่ายต่อลูกแต่ละคน (planned, inflated) จาก expense_df
    # ending = beginning + contribution + return − Σ planned expense (คำนวณเองเพื่อให้ balance พอดี)
    # remark = "ชื่อลูก: ระดับชั้น (อายุ X)" สำหรับ row ที่มี expense > 0 ในปีนั้น
    st.markdown("#### 7. 💵 ตารางการไหลของเงินรายปี (Average Scenario)")
    st.caption(
        "ตัวเลขเงินคงเหลือ / เงินสะสม / ผลตอบแทน เป็นค่าเฉลี่ยจาก Monte Carlo "
        "— ค่าใช้จ่ายแสดงตามแผน (สมมติจ่ายเต็มทุกปี)"
    )
    if not _port_path_year.empty:
        # ----- Mean MC components per year (sum-across-buckets already in _port_path_year) -----
        # ใช้ mean เพราะ linearity of expectation: mean(A+B−C) = mean(A)+mean(B)−mean(C)
        # → ทำให้ ending ที่คำนวณเองตรงกับค่าเฉลี่ยที่แต่ละคอลัมน์แสดง
        _mc_agg = {}
        if "beginning_balance" in _port_path_year.columns:
            _mc_agg["_avg_beginning"] = ("beginning_balance", "mean")
        if "contribution_in" in _port_path_year.columns:
            _mc_agg["_avg_contribution"] = ("contribution_in", "mean")
        if "investment_return" in _port_path_year.columns:
            _mc_agg["_avg_inv_return"] = ("investment_return", "mean")

        _cf_full = _port_path_year.groupby("year", as_index=False).agg(**_mc_agg)
        _cf_full["year"] = _cf_full["year"].astype(int)

        # ----- Per-child planned expense (inflated) from expense_df -----
        _child_cols_ordered = []
        if (
            expense_df is not None
            and not expense_df.empty
            and {"year", "child_name", "inflated_amount"}.issubset(expense_df.columns)
        ):
            # Preserve order of first appearance; push "Parent" to the end
            _seen, _order = set(), []
            for _n in expense_df["child_name"].astype(str).tolist():
                if _n not in _seen:
                    _seen.add(_n)
                    _order.append(_n)
            _child_cols_ordered = [n for n in _order if n != "Parent"] + [n for n in _order if n == "Parent"]

            _exp_by_child = (
                expense_df.groupby(["year", "child_name"], as_index=False)["inflated_amount"]
                .sum()
                .pivot(index="year", columns="child_name", values="inflated_amount")
                .fillna(0.0)
                .reset_index()
            )
            _exp_by_child["year"] = _exp_by_child["year"].astype(int)
            _cf_full = _cf_full.merge(_exp_by_child, on="year", how="left")
            for _cn in _child_cols_ordered:
                if _cn in _cf_full.columns:
                    _cf_full[_cn] = _cf_full[_cn].fillna(0.0)

        # ----- Build remark per year: "ชื่อ: ระดับการศึกษา (อายุ N) | ..." -----
        # แสดงเฉพาะ education entries เท่านั้น — ไม่รวม extras
        _remarks_by_year = {}
        if (
            expense_df is not None
            and not expense_df.empty
            and {"year", "child_name", "category", "sub_category", "inflated_amount"}.issubset(expense_df.columns)
        ):
            _edu_mask_rmk = (
                expense_df["category"].astype(str).str.endswith(" education")
                & (expense_df["child_name"].astype(str) != "Parent")
                & (expense_df["inflated_amount"] > 0)
            )
            _exp_edu = expense_df[_edu_mask_rmk].copy()
            _has_age_col = "child_age" in _exp_edu.columns
            for _yr, _grp in _exp_edu.groupby("year"):
                _parts_by_child = []
                # Iterate in display order (children first, Parent last)
                for _cn in _child_cols_ordered:
                    _sub_grp = _grp[_grp["child_name"].astype(str) == _cn]
                    if _sub_grp.empty:
                        continue
                    for _, _r in _sub_grp.iterrows():
                        _sub_str = str(_r.get("sub_category", "")).strip()
                        _age_val = _r.get("child_age") if _has_age_col else None
                        if pd.notna(_age_val):
                            _parts_by_child.append(f"{_cn}: {_sub_str} (อายุ {int(_age_val)})")
                        else:
                            _parts_by_child.append(f"{_cn}: {_sub_str}")
                _remarks_by_year[int(_yr)] = " | ".join(_parts_by_child)

        _cf_full["_remark"] = _cf_full["year"].map(_remarks_by_year).fillna("")

        # ----- Recompute ending balance for balance identity -----
        # ending = beginning + contribution + return − Σ per-child planned expense
        # ทำให้แต่ละแถวสมดุล (รวมแล้วเท่ากับ ending ทุกครั้ง) ต่างจาก median ที่ non-linear
        _expense_sum = pd.Series(0.0, index=_cf_full.index)
        for _cn in _child_cols_ordered:
            if _cn in _cf_full.columns:
                _expense_sum = _expense_sum + _cf_full[_cn].astype(float)
        _beg_part = _cf_full["_avg_beginning"] if "_avg_beginning" in _cf_full.columns else 0.0
        _ctr_part = _cf_full["_avg_contribution"] if "_avg_contribution" in _cf_full.columns else 0.0
        _ret_part = _cf_full["_avg_inv_return"] if "_avg_inv_return" in _cf_full.columns else 0.0
        _cf_full["_recomputed_ending"] = _beg_part + _ctr_part + _ret_part - _expense_sum

        # ----- Compose display in user-requested column order -----
        _display_pairs = [("year", "ปี")]
        if "_avg_beginning" in _cf_full.columns:
            _display_pairs.append(("_avg_beginning", "เงินคงเหลือต้นปี"))
        if "_avg_contribution" in _cf_full.columns:
            _display_pairs.append(("_avg_contribution", "เงินสะสมเข้าใหม่"))
        if "_avg_inv_return" in _cf_full.columns:
            _display_pairs.append(("_avg_inv_return", "ผลตอบแทน"))
        for _cn in _child_cols_ordered:
            if _cn in _cf_full.columns:
                _label = "ค่าใช้จ่าย: ผู้ปกครอง" if _cn == "Parent" else f"ค่าใช้จ่าย: {_cn}"
                _display_pairs.append((_cn, _label))
        _display_pairs.append(("_recomputed_ending", "เงินคงเหลือสิ้นปี"))
        _display_pairs.append(("_remark", "หมายเหตุ"))

        _cf_display = _cf_full[[p[0] for p in _display_pairs]].copy()
        _cf_display.columns = [p[1] for p in _display_pairs]

        _money_cols = [p[1] for p in _display_pairs if p[0] not in ("year", "_remark")]
        for _c in _money_cols:
            _cf_display[_c] = _cf_display[_c].round(0)

        _cf_styled = (
            _cf_display.style.format({c: "{:,.0f}" for c in _money_cols})
            .set_properties(**{"text-align": "right"}, subset=_money_cols)
        )
        st.dataframe(_cf_styled, width="stretch", hide_index=True)
        st.download_button(
            "⬇ ดาวน์โหลดตารางการไหลของเงิน CSV",
            _cf_display.to_csv(index=False).encode("utf-8-sig"),
            file_name="cashflow_per_year.csv",
            mime="text/csv",
        )
    else:
        st.info(S("p3", "dd_no_data"))

    # ── Charts 11 (Heatmap) and 12 (Drawdown trajectory) removed ──

    # ============================================================
    # 📊 ตารางข้อมูล (moved to bottom of page)
    # ============================================================
    st.markdown("---")
    st.markdown(S("p3", "tables_header"))

    with st.expander(S("p3", "tbl_engine"), expanded=False):
        st.dataframe(engine_summary_df, width="stretch")

    with st.expander(S("p3", "tbl_bucket"), expanded=False):
        st.dataframe(bucket_summary_df, width="stretch")

    with st.expander(S("p3", "tbl_risk_years"), expanded=False):
        st.dataframe(riskiest_years_df, width="stretch")

    with st.expander(S("p3", "tbl_worst_paths"), expanded=False):
        st.dataframe(worst_paths_df, width="stretch")

    with st.expander(S("p3", "tbl_allocation"), expanded=False):
        st.markdown(S("p3", "tbl_alloc_req"))
        st.dataframe(mc_result.bucket_requirement_df, width="stretch")
        st.markdown(S("p3", "tbl_alloc_init"))
        st.dataframe(mc_result.initial_allocation_df, width="stretch")

    if not terminal_balance_pivot.empty:
        with st.expander(S("p3", "tbl_p50_pivot"), expanded=False):
            st.dataframe(terminal_balance_pivot, width="stretch")

    if not shortfall_probability_pivot.empty:
        with st.expander(S("p3", "tbl_sf_pivot"), expanded=False):
            st.dataframe(shortfall_probability_pivot, width="stretch")

    st.markdown(S("p3", "raw_header"))

    if not mc_result.mc_path_detail_df.empty:
        with st.expander(S("p3", "tbl_path_detail"), expanded=False):
            st.caption(S("p3", "tbl_path_hint"))
            _pid_options_path = sorted(mc_result.mc_path_detail_df["path_id"].unique().tolist()) if "path_id" in mc_result.mc_path_detail_df.columns else []
            _pid_filter_path = st.multiselect(
                S("p3", "tbl_path_filter"),
                options=_pid_options_path,
                default=[],
                key="path_detail_pid_filter",
            )
            _path_detail_view = mc_result.mc_path_detail_df[
                mc_result.mc_path_detail_df["path_id"].isin(_pid_filter_path)
            ] if _pid_filter_path else mc_result.mc_path_detail_df
            st.dataframe(_path_detail_view.head(500), width="stretch", hide_index=True)
            st.caption(S("p3", "tbl_path_rows", shown=min(len(_path_detail_view), 500), total=len(_path_detail_view)))
            st.download_button(
                S("p3", "dl_path"),
                mc_result.mc_path_detail_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="mc_path_detail.csv",
                mime="text/csv",
            )

    asset_detail_df = getattr(mc_result, "mc_path_asset_detail_df", pd.DataFrame())
    if not asset_detail_df.empty:
        with st.expander(S("p3", "tbl_asset_detail"), expanded=False):
            st.info(S("p3", "tbl_asset_verify"), icon="🔬")

            # ---- Filter controls ----
            _fc1, _fc2, _fc3 = st.columns(3)
            _pid_options = sorted(asset_detail_df["path_id"].unique().tolist()) if "path_id" in asset_detail_df.columns else []
            _bkt_options = sorted(asset_detail_df["bucket_name"].unique().tolist()) if "bucket_name" in asset_detail_df.columns else []
            _yr_options  = sorted(asset_detail_df["year"].unique().tolist()) if "year" in asset_detail_df.columns else []

            with _fc1:
                _sel_paths = st.multiselect(S("p3", "filter_path_id"), options=_pid_options, default=[], key="adtl_pid")
            with _fc2:
                _sel_buckets = st.multiselect(S("p3", "filter_bucket"), options=_bkt_options, default=[], key="adtl_bkt")
            with _fc3:
                _sel_years = st.multiselect(S("p3", "filter_year"), options=_yr_options, default=[], key="adtl_yr")

            _adtl_view = asset_detail_df.copy()
            if _sel_paths:
                _adtl_view = _adtl_view[_adtl_view["path_id"].isin(_sel_paths)]
            if _sel_buckets:
                _adtl_view = _adtl_view[_adtl_view["bucket_name"].isin(_sel_buckets)]
            if _sel_years:
                _adtl_view = _adtl_view[_adtl_view["year"].isin(_sel_years)]

            st.dataframe(_adtl_view.head(500), width="stretch", hide_index=True)
            st.caption(S("p3", "tbl_asset_rows", shown=min(len(_adtl_view), 500), total=len(_adtl_view)))

            # ---- Quick verification ----
            if not _adtl_view.empty and {"path_id", "year", "bucket_name", "weighted_contribution"}.issubset(_adtl_view.columns):
                _verify_agg = (
                    _adtl_view.groupby(["path_id", "year", "bucket_name"])["weighted_contribution"]
                    .sum()
                    .reset_index()
                    .rename(columns={"weighted_contribution": "sum_weighted_contribution"})
                )
                with st.expander(S("p3", "tbl_verify_expander"), expanded=False):
                    st.dataframe(_verify_agg.head(200), width="stretch", hide_index=True)
                    st.caption(S("p3", "tbl_verify_caption"))

            st.download_button(
                S("p3", "dl_asset"),
                asset_detail_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="mc_path_asset_detail.csv",
                mime="text/csv",
            )
