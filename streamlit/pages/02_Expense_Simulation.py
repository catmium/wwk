import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd
import altair as alt

from strings import S, SC, edu_level_label

st.set_page_config(
    page_title=S("p2", "page_title"),
    page_icon="📊",
    layout="wide",
)

# ============================================================
# SIDEBAR: WORKFLOW PROGRESS + NAVIGATION
# ============================================================
with st.sidebar:
    st.markdown(S("sidebar", "workflow_header"))
    st.markdown(S("sidebar", "step1_done"))
    st.markdown(S("p2", "step2_active"))
    st.markdown(S("sidebar", "step3"))
    st.markdown("---")

    if st.button(S("p2", "btn_back"), use_container_width=True):
        st.switch_page("01_User_Information.py")

    if st.button(S("p2", "btn_next"), use_container_width=True, type="primary"):
        st.switch_page("pages/03_Investment_Planning.py")

# ============================================================
# GATE: require simulation
# ============================================================
if not st.session_state.get("simulation_ran", False):
    st.title(S("p2", "title"))
    st.warning(S("p2", "gate_warn"))
    if st.button(S("p2", "gate_btn"), type="primary"):
        st.switch_page("01_User_Information.py")
    st.stop()

# ============================================================
# LOAD DATA
# ============================================================
expense_df = st.session_state.get("expense_df", pd.DataFrame()).copy()
saving_df  = st.session_state.get("saving_df",  pd.DataFrame()).copy()
summary_df = st.session_state.get("summary_df", pd.DataFrame()).copy()

if saving_df.empty:
    st.error(S("p2", "err_no_saving"))
    st.stop()

# derived columns
saving_df["cumulative_input"] = (
    saving_df["beginning_bal"].iloc[0]
    + saving_df["annual_contribution"].cumsum()
    + saving_df["annual_topup"].cumsum()
)
saving_df["cumulative_income"] = (
    saving_df["cumulative_input"]
    + saving_df["investment_return"].cumsum()
)
saving_df["cumulative_expense"] = saving_df["total_expense"].cumsum()
saving_df = saving_df.sort_values("year").reset_index(drop=True)

# ============================================================
# HELPERS
# ============================================================
def _get_metric(summary_df, key, default=None):
    """Pull a value from summary_df which has columns ['metric', 'value']."""
    if summary_df is None or summary_df.empty:
        return default
    if "metric" not in summary_df.columns:
        return default
    row = summary_df.loc[summary_df["metric"] == key, "value"]
    return row.iloc[0] if not row.empty else default


def _fmt(val, fmt=",.0f"):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        return format(float(val), fmt)
    except Exception:
        return str(val)


def _fmt_compact(val):
    """Format large numbers as '20.1M' or '870K' for chart labels."""
    try:
        v = float(val)
    except Exception:
        return ""
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    elif abs(v) >= 1_000:
        return f"{v / 1_000:.0f}K"
    else:
        return f"{v:.0f}"


def _get_first_shortfall_year(summary_df):
    val = _get_metric(summary_df, "first_shortfall_year")
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return str(int(val))


# ============================================================
# PAGE TITLE
# ============================================================
st.title(S("p2", "title"))
st.caption(S("p2", "caption"))
# st.markdown("---")

# ============================================================
# SECTION 1: KPI CARDS
# ============================================================

sufficient      = _get_metric(summary_df, "is_current_plan_sufficient", False)
total_expense   = _get_metric(summary_df, "total_projected_expense", 0)
final_balance   = _get_metric(summary_df, "final_ending_balance", 0)
add_monthly     = _get_metric(summary_df, "additional_monthly_needed", 0)
shortfall_year  = _get_first_shortfall_year(summary_df)
peak_expense    = _get_metric(summary_df, "peak_annual_expense", 0)
peak_year       = _get_metric(summary_df, "peak_annual_expense_year")
min_bal         = _get_metric(summary_df, "minimum_ending_balance", 0)
total_return    = _get_metric(summary_df, "total_investment_return", 0)
min_req         = _get_metric(summary_df, "minimum_required_monthly_contribution", 0)
total_funding   = _get_metric(summary_df, "total_funding", 0)

# Status banner
if sufficient:
    st.success(S("p2", "status_ok"))
else:
    extra = _fmt(add_monthly)
    yr    = S("p2", "shortfall_start", year=shortfall_year) if shortfall_year else ""
    st.error(S("p2", "status_fail", extra=extra, yr=f"฿{_fmt(min_req)}"))


# KPI strip
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric(S("p2", "kpi_total_expense"), f"฿{_fmt(total_expense)}")

_surplus_label = S("p2", "kpi_surplus") if (final_balance or 0) >= 0 else S("p2", "kpi_deficit")
bal_delta = f"฿{_fmt(abs(float(final_balance)))} {_surplus_label}"
k2.metric(S("p2", "kpi_final_balance"), f"฿{_fmt(total_funding)}", delta=bal_delta,
          delta_color="normal" if (final_balance or 0) >= 0 else "inverse")

k3.metric(S("p2", "kpi_shortfall_year"), shortfall_year or S("p2", "kpi_no_shortfall"))
k4.metric(S("p2", "kpi_peak_expense"), f"฿{_fmt(peak_expense)}",
          delta=S("p2", "kpi_peak_year_delta", year=int(peak_year)) if peak_year else None,
          delta_color="off")
k5.metric(S("p2", "kpi_invest_return"), f"฿{_fmt(total_return)}")

st.markdown("---")

# ============================================================
# SECTION 2: PORTFOLIO TRAJECTORY
# ============================================================
st.subheader(S("p2", "chart1_header"))
st.caption(S("p2", "chart1_caption"))

chart_df = saving_df[["year", "cumulative_income", "cumulative_expense", "ending_bal"]].copy()
chart_df["year"] = chart_df["year"].astype(str)

_series_fund = S("p2", "series_cum_fund")
_series_exp  = S("p2", "series_cum_exp")
_series_bal  = S("p2", "series_balance")

label_map = {
    "cumulative_income":  _series_fund,
    "cumulative_expense": _series_exp,
    "ending_bal":         _series_bal,
}

chart_long = (
    chart_df
    .melt(id_vars="year",
          value_vars=["cumulative_income", "cumulative_expense", "ending_bal"],
          var_name="metric", value_name="value")
)
chart_long["label"] = chart_long["metric"].map(label_map)
chart_long["label_text"] = chart_long["value"].apply(_fmt_compact)

color_scale = alt.Scale(
    domain=[_series_fund, _series_exp, _series_bal],
    range=["#4C9BE8", "#E8734C", "#50B87A"],
)

# Darker shades of the same hues — used for data labels so they stand out
dark_color_scale = alt.Scale(
    domain=[_series_fund, _series_exp, _series_bal],
    range=["#1A6FC4", "#C44E27", "#217A47"],
)

base = (
    alt.Chart(chart_long)
    .mark_line(point=True, strokeWidth=2)
    .encode(
        x=alt.X("year:O", title=S("p2", "axis_year")),
        y=alt.Y("value:Q", title=S("p2", "axis_amount"), axis=alt.Axis(format=",.0f")),
        color=alt.Color("label:N", title=S("p2", "legend_series"), scale=color_scale),
        tooltip=[
            alt.Tooltip("year:O", title=S("p2", "axis_year")),
            alt.Tooltip("label:N", title=S("p2", "legend_series")),
            alt.Tooltip("value:Q", title=S("p2", "axis_amount"), format=",.0f"),
        ],
    )
)

line_labels = (
    alt.Chart(chart_long)
    .mark_text(fontSize=12, fontWeight="bold", dy=-12)
    .encode(
        x=alt.X("year:O"),
        y=alt.Y("value:Q"),
        text=alt.Text("label_text:N"),
        color=alt.Color("label:N", scale=dark_color_scale, legend=None),
    )
)

first_shortfall_year = _get_first_shortfall_year(summary_df)
chart = base + line_labels

if first_shortfall_year:
    rule_df = pd.DataFrame({"year": [first_shortfall_year]})
    rule = (
        alt.Chart(rule_df).mark_rule(color="red", strokeWidth=2, strokeDash=[4, 4])
        .encode(x="year:O")
    )
    rule_text = (
        alt.Chart(rule_df)
        .mark_text(text=S("p2", "shortfall_marker"), color="red", align="left", dx=6, dy=-8, fontWeight="bold")
        .encode(x="year:O", y=alt.value(20))
    )
    chart = base + line_labels + rule + rule_text

st.altair_chart(
    chart.properties(height=380)
    .configure_axis(labelFontSize=12, titleFontSize=13)
    .configure_legend(titleFontSize=12, labelFontSize=11),
    use_container_width=True,
)

st.markdown("---")

# shared chart height for sections 3 and 4
_CHART_HEIGHT = 380

# ============================================================
# SECTION 3: ANNUAL EXPENSES + EXPENSE BREAKDOWN
# ============================================================
st.subheader(S("p2", "chart2_header"))

expense_chart_df = expense_df.copy()
required_cols = ["year", "category", "sub_category", "inflated_amount"]
missing = [c for c in required_cols if c not in expense_chart_df.columns]

if expense_chart_df.empty:
    st.info(S("p2", "info_no_expense"))
elif missing:
    st.error(S("p2", "err_missing_cols", cols=missing))
else:
    # ── shared data prep ──
    expense_chart_df["year"] = pd.to_numeric(expense_chart_df["year"], errors="coerce")
    expense_chart_df["inflated_amount"] = pd.to_numeric(expense_chart_df["inflated_amount"], errors="coerce").fillna(0)
    expense_chart_df["category"] = expense_chart_df["category"].fillna("Unknown").astype(str)
    expense_chart_df["sub_category"] = (
        expense_chart_df["sub_category"].fillna("Unknown").astype(str).apply(edu_level_label)
    )
    expense_chart_df = expense_chart_df.dropna(subset=["year"])
    expense_chart_df["year_str"] = expense_chart_df["year"].astype(int).astype(str)

    agg = expense_chart_df.groupby(["year_str", "year", "category", "sub_category"], as_index=False)["inflated_amount"].sum()
    total_df = agg.groupby(["year_str", "year"], as_index=False)["inflated_amount"].sum().rename(columns={"inflated_amount": "total"})
    total_df["label_text"] = total_df["total"].apply(_fmt_compact)
    year_order = total_df.sort_values("year")["year_str"].tolist()
    sub_cat_order = sorted(agg["sub_category"].unique().tolist())
    y_max = max(float(total_df["total"].max()) * 1.12, 1.0)

    # ── stacked bar chart (col 1) ──
    bars = (
        alt.Chart(agg)
        .mark_bar()
        .encode(
            x=alt.X("year_str:N", title=S("p2", "axis_year"), sort=year_order),
            y=alt.Y("inflated_amount:Q", title=S("p2", "axis_amount"), stack="zero",
                    scale=alt.Scale(domain=[0, y_max]), axis=alt.Axis(format=",.0f")),
            color=alt.Color("sub_category:N", title=S("p2", "legend_category"), sort=sub_cat_order),
            tooltip=[
                alt.Tooltip("year_str:N", title=S("p2", "axis_year")),
                alt.Tooltip("category:N", title=S("p2", "legend_category")),
                alt.Tooltip("sub_category:N", title=S("p2", "legend_category")),
                alt.Tooltip("inflated_amount:Q", title=S("p2", "axis_amount"), format=",.0f"),
            ],
        )
    )
    labels = (
        alt.Chart(total_df)
        .mark_text(dy=-8, fontSize=12, fontWeight="bold", color="#C44E27")
        .encode(
            x=alt.X("year_str:N", sort=year_order),
            y=alt.Y("total:Q"),
            text=alt.Text("label_text:N"),
        )
    )
    chart_exp = (bars + labels).properties(height=380)
    if first_shortfall_year:
        rule_df2 = pd.DataFrame({"year_str": [first_shortfall_year]})
        rule2 = (
            alt.Chart(rule_df2).mark_rule(color="red", strokeWidth=2, strokeDash=[4, 4])
            .encode(x=alt.X("year_str:N", sort=year_order))
        )
        rule_text2 = (
            alt.Chart(rule_df2)
            .mark_text(text=S("p2", "shortfall_marker"), color="red", align="left", dx=6, dy=12, fontWeight="bold")
            .encode(x=alt.X("year_str:N", sort=year_order), y=alt.value(12))
        )
        chart_exp = chart_exp + rule2 + rule_text2

    # ── col 1: category × subcategory — horizontal stacked bar ──

    exp_agg_sub = (
        expense_chart_df
        .groupby(["category", "sub_category"], as_index=False)["inflated_amount"].sum()
    )
    cat_totals = exp_agg_sub.groupby("category", as_index=False)["inflated_amount"].sum()
    cat_order = cat_totals.sort_values("inflated_amount", ascending=False)["category"].tolist()
    cat_totals["label_text"] = cat_totals["inflated_amount"].apply(_fmt_compact)
    x_max_cat = max(float(cat_totals["inflated_amount"].max()) * 1.25, 1.0)

    cat_bars = (
        alt.Chart(exp_agg_sub)
        .mark_bar()
        .encode(
            y=alt.Y("category:N", title=None, sort=cat_order,
                    axis=alt.Axis(labelLimit=200)),
            x=alt.X("inflated_amount:Q", title=S("p2", "axis_total_amount"),
                    stack="zero", scale=alt.Scale(domain=[0, x_max_cat]),
                    axis=alt.Axis(format=",.0f")),
            color=alt.Color("sub_category:N", sort=sub_cat_order, legend=None),
            tooltip=[
                alt.Tooltip("category:N", title=S("p2", "legend_category")),
                alt.Tooltip("sub_category:N", title=S("p2", "legend_category")),
                alt.Tooltip("inflated_amount:Q", title=S("p2", "axis_amount"), format=",.0f"),
            ],
        )
    )
    cat_total_labels = (
        alt.Chart(cat_totals)
        .mark_text(align="left", dx=6, fontSize=12, fontWeight="bold", color="#C44E27")
        .encode(
            y=alt.Y("category:N", sort=cat_order),
            x=alt.X("inflated_amount:Q"),
            text=alt.Text("label_text:N"),
        )
    )
    chart_cat = (cat_bars + cat_total_labels).properties(height=_CHART_HEIGHT)

    # ── col 2: stacked bar by year (fixed to same height) ──
    chart_exp = chart_exp.properties(height=_CHART_HEIGHT)

    # ── render side by side ──
    _ec1, _ec2 = st.columns([2, 4])
    with _ec1:
        st.caption(S("p2", "chart4_caption"))
        st.altair_chart(
            chart_cat
            .configure_axis(labelFontSize=11, titleFontSize=12),
            use_container_width=True,
        )
    with _ec2:
        st.caption(S("p2", "chart2_caption"))
        st.altair_chart(
            chart_exp
            .configure_axis(labelFontSize=12, titleFontSize=13)
            .configure_legend(titleFontSize=12, labelFontSize=11),
            use_container_width=True,
        )


st.markdown("---")

# ============================================================
# SECTION 4: FUNDING SOURCES
# ============================================================
st.subheader(S("p2", "chart3_header"))

_fc1, _fc2 = st.columns([2, 4])

_comp_initial = S("p2", "comp_initial")
_comp_contrib = S("p2", "comp_contrib")
_comp_topup   = S("p2", "comp_topup")
_comp_return  = S("p2", "comp_return")

with _fc1:
    st.caption(S("p2", "chart3_lifetime"))

    x = saving_df.copy()
    x["initial_input"] = 0.0
    if "beginning_bal" in x.columns:
        x.loc[x.index[0], "initial_input"] = pd.to_numeric(x["beginning_bal"], errors="coerce").fillna(0).iloc[0]

    component_df = pd.DataFrame({
        "Component": [_comp_initial, _comp_contrib, _comp_topup, _comp_return],
        "Amount":    [
            x["initial_input"].sum(),
            pd.to_numeric(x["annual_contribution"], errors="coerce").fillna(0).sum(),
            pd.to_numeric(x["annual_topup"],        errors="coerce").fillna(0).sum(),
            pd.to_numeric(x["investment_return"],   errors="coerce").fillna(0).sum(),
        ],
    })

    comp_order = component_df["Component"].tolist()
    x_max_c = max(float(component_df["Amount"].max()) * 1.30, 1.0)
    component_df["label_text"] = component_df["Amount"].apply(_fmt_compact)

    bars_c = (
        alt.Chart(component_df)
        .mark_bar()
        .encode(
            y=alt.Y("Component:N", title=None, sort=comp_order,
                    axis=alt.Axis(labelLimit=200)),
            x=alt.X("Amount:Q", title=S("p2", "axis_amount"),
                    scale=alt.Scale(domain=[0, x_max_c]), axis=alt.Axis(format=",.0f")),
            color=alt.Color("Component:N", sort=comp_order, legend=None),
            tooltip=[
                alt.Tooltip("Component:N"),
                alt.Tooltip("Amount:Q", format=",.0f"),
            ],
        )
    )
    labels_c = (
        alt.Chart(component_df)
        .mark_text(align="left", dx=6, fontSize=11, fontWeight="bold", color="#1A6FC4")
        .encode(
            y=alt.Y("Component:N", sort=comp_order),
            x=alt.X("Amount:Q"),
            text=alt.Text("label_text:N"),
        )
    )

    st.altair_chart(
        (bars_c + labels_c)
        .properties(height=_CHART_HEIGHT)
        .configure_axis(labelFontSize=11, titleFontSize=12),
        use_container_width=True,
    )

with _fc2:
    st.caption(S("p2", "chart3_by_year"))

    x2 = saving_df.copy()
    x2["initial_input"] = 0.0
    if "beginning_bal" in x2.columns:
        x2.loc[x2.index[0], "initial_input"] = pd.to_numeric(x2["beginning_bal"], errors="coerce").fillna(0).iloc[0]

    numeric_cols = ["initial_input", "annual_contribution", "annual_topup", "investment_return"]
    for col in numeric_cols:
        x2[col] = pd.to_numeric(x2[col], errors="coerce").fillna(0)
    x2["year_str"] = pd.to_numeric(x2["year"], errors="coerce").dropna().astype(int).astype(str)

    label_map2 = {
        "initial_input":       _comp_initial,
        "annual_contribution": _comp_contrib,
        "annual_topup":        _comp_topup,
        "investment_return":   _comp_return,
    }
    long2 = x2.melt(id_vars="year_str", value_vars=numeric_cols, var_name="component", value_name="amount")
    long2["label"] = long2["component"].map(label_map2)
    long2["order"] = long2["component"].map({k: i for i, k in enumerate(numeric_cols)})

    year_order2 = x2["year_str"].tolist()
    comp_order2 = [label_map2[k] for k in numeric_cols]
    total2 = long2.groupby("year_str", as_index=False)["amount"].sum().rename(columns={"amount": "total"})
    total2["label_text"] = total2["total"].apply(_fmt_compact)
    y_max2 = max(float(total2["total"].max()) * 1.12, 1.0)

    bars2 = (
        alt.Chart(long2)
        .mark_bar()
        .encode(
            x=alt.X("year_str:N", title=S("p2", "axis_year"), sort=year_order2),
            y=alt.Y("amount:Q", title=S("p2", "axis_amount"), stack="zero",
                    scale=alt.Scale(domain=[0, y_max2]), axis=alt.Axis(format=",.0f")),
            color=alt.Color("label:N", title=S("p2", "legend_component"), sort=comp_order2),
            order=alt.Order("order:Q", sort="ascending"),
            tooltip=[
                alt.Tooltip("year_str:N", title=S("p2", "axis_year")),
                alt.Tooltip("label:N", title=S("p2", "legend_component")),
                alt.Tooltip("amount:Q", title=S("p2", "axis_amount"), format=",.0f"),
            ],
        )
    )
    labels2 = (
        alt.Chart(total2)
        .mark_text(dy=-8, fontSize=12, fontWeight="bold", color="#1A6FC4")
        .encode(
            x=alt.X("year_str:N", sort=year_order2),
            y=alt.Y("total:Q"),
            text=alt.Text("label_text:N"),
        )
    )

    chart_funding = (bars2 + labels2).properties(height=_CHART_HEIGHT)
    if first_shortfall_year:
        rule_df3 = pd.DataFrame({"year_str": [first_shortfall_year]})
        rule3 = (
            alt.Chart(rule_df3).mark_rule(color="red", strokeWidth=2, strokeDash=[4, 4])
            .encode(x=alt.X("year_str:N", sort=year_order2))
        )
        rule_text3 = (
            alt.Chart(rule_df3)
            .mark_text(text=S("p2", "shortfall_marker"), color="red", align="left",
                       dx=6, dy=12, fontWeight="bold")
            .encode(x=alt.X("year_str:N", sort=year_order2), y=alt.value(12))
        )
        chart_funding = chart_funding + rule3 + rule_text3

    st.altair_chart(
        chart_funding
        .configure_axis(labelFontSize=11, titleFontSize=12)
        .configure_legend(titleFontSize=11, labelFontSize=10),
        use_container_width=True,
    )

st.markdown("---")

# ============================================================
# SECTION 5: DETAIL TABLES (collapsed)
# ============================================================
# 📊 ตารางข้อมูล
st.subheader("ตารางข้อมูล")
with st.expander(S("p2", "tbl_summary"), expanded=False):
    if summary_df.empty:
        st.info(S("p2", "info_no_summary"))
    else:
        display_df = summary_df.copy()
        display_df.columns = [c.capitalize() for c in display_df.columns]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

with st.expander(S("p2", "tbl_expense"), expanded=False):
    if expense_df.empty:
        st.info(S("p2", "info_no_expense"))
    else:
        st.dataframe(expense_df, use_container_width=True, hide_index=True)
        st.download_button(
            S("p2", "dl_expense"),
            expense_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="expense.csv",
            mime="text/csv",
        )

with st.expander(S("p2", "tbl_saving"), expanded=False):
    st.dataframe(saving_df, use_container_width=True, hide_index=True)
    st.download_button(
        S("p2", "dl_saving"),
        saving_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="saving.csv",
        mime="text/csv",
    )

st.markdown("---")

# ============================================================
# BOTTOM CTA
# ============================================================
st.markdown(S("p2", "cta_header"))
st.caption(S("p2", "cta_caption"))
if st.button(S("p2", "cta_btn"), type="primary", use_container_width=True):
    st.switch_page("pages/03_Investment_Planning.py")
