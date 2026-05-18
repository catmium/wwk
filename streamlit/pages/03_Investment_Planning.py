import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd
import altair as alt
from typing import Optional

from strings import S, SC

from portfolio_bucket_engine import (
    BucketConfig,
    BucketFundingRule,
    build_funding_maps_from_saving_df,
    prepare_annual_expense,
    assign_expense_to_buckets,
    calculate_bucket_requirements,
    allocate_initial_savings_to_buckets,
    validate_manual_allocation,
    create_manual_allocation_df,
)
from portfolio_bucket_engine_mc import (
    AssetReturnModel,
    BucketReturnModel,
    MonteCarloConfig,
    run_bucket_engine_monte_carlo_level2,
    DEFAULT_INTRA_BUCKET_CORRELATION,
)
from state import (
    draft_get,
    draft_set,
    ensure_widget_buffer,
    on_widget_change,
    persist_all_widget_buffers,
    set_field_value,
    switch_page_with_persist,
    _widget_key,
    require_login,
)
from asset_store import (
    save_bucket_definitions,
    load_bucket_definitions,
    has_saved_bucket_definitions,
    get_saved_bucket_meta,
)

require_login()

st.set_page_config(
    page_title=S("p3", "page_title"),
    page_icon="📈",
    layout="wide",
)

st.title(S("p3", "title"))
st.caption(S("p3", "caption"))

# ============================================================
# PERSISTENT STATE MODEL
# ============================================================
# inv_mc_*             = permanent state (survive page switching)
# _w_inv_mc_*          = widget state (cleared on navigation)
# inv_bucket_definitions = dynamic bucket+asset config

# Default asset entry template
_DEFAULT_ASSET = {"asset_name": "Asset", "weight_pct": 100.0,
                  "mean_pct": 3.0, "std_pct": 5.0,
                  "min_pct": -10.0, "max_pct": 10.0}

PARAM_DEFAULTS = {
    # MC controls
    "inv_mc_n_paths": 1000,
    "inv_mc_random_seed": 42,
    "inv_mc_keep_path_detail": True,
    "inv_mc_keep_asset_detail": False,

    # Dynamic bucket + asset definitions
    # ค่าในตาราง asset เก็บเป็น % (6.0 = 6%) แปลง → decimal เมื่อสร้าง model
    "inv_bucket_definitions": [
        {
            "name": "Liquidity",
            "year_start": 1,
            "year_end": 3,          # None = open-ended (last bucket)
            "discount_rate": 0.02,  # ใช้ในการคิด PV requirement (decimal)
            "assets": [
                {"asset_name": "iPlus", "weight_pct": 25.0,
                 "mean_pct": 1.0, "std_pct": 0.21, "min_pct": -0.2, "max_pct": 2.0},
                {"asset_name": "Ultimate GA2", "weight_pct": 35.0,
                 "mean_pct": 6.0, "std_pct": 5.0, "min_pct": -4.7, "max_pct": 12.5},
                {"asset_name": "GAINCOME", "weight_pct": 25.0,
                 "mean_pct": 6.0, "std_pct": 7.0, "min_pct": -7.8, "max_pct": 15},
                {"asset_name": "GCORE", "weight_pct": 15.0,
                 "mean_pct": 8.0, "std_pct": 10.0, "min_pct": -27.4, "max_pct": 30},
            ],
        },
        {
            "name": "Stability",
            "year_start": 4,
            "year_end": 7,
            "discount_rate": 0.04,
            "assets": [
                {"asset_name": "Life Settlement", "weight_pct": 34.0,
                 "mean_pct": 6.0, "std_pct": 6.0, "min_pct": -4.2, "max_pct": 16.0},
                {"asset_name": "UPINFRA", "weight_pct": 33.0,
                 "mean_pct": 9.0, "std_pct": 12.0, "min_pct": -4.7, "max_pct": 22.0},
                {"asset_name": "Ultimate GA3", "weight_pct": 33.0,
                 "mean_pct": 8.0, "std_pct": 7.0, "min_pct": -8.3, "max_pct": 24.0},
            ],
        },
        {
            "name": "Growth",
            "year_start": 8,
            "year_end": None,       # open-ended — bucket สุดท้ายต้อง None
            "discount_rate": 0.06,
            "assets": [
                {"asset_name": "US Index", "weight_pct": 100.0,
                 "mean_pct": 12.0, "std_pct": 15.0, "min_pct": 0.0, "max_pct": 30.0},
            ],
        },
    ],

    # outputs
    "inv_mc_result": None,
    "inv_mc_analysis": None,
    "inv_investment_sim_done": False,

    # allocation mode
    "inv_allocation_mode": "auto",           # "auto" | "manual"
    "inv_manual_alloc_input_mode": "amount", # "amount" | "percent"
}


# A5: canonical state.py pattern — widget-backed keys live in `w__{field}` buffers
# (auto-persisted by persist_all_widget_buffers), runtime keys stored directly.
# Bucket definitions remain a draft-only complex object (set via draft_set).
_WIDGET_DEFAULT_KEYS = (
    "inv_mc_n_paths",
    "inv_mc_random_seed",
    "inv_mc_keep_path_detail",
    "inv_mc_keep_asset_detail",
    "inv_allocation_mode",
    "inv_manual_alloc_input_mode",
)

_RUNTIME_DEFAULT_KEYS = (
    "inv_mc_result",
    "inv_mc_analysis",
    "inv_investment_sim_done",
)


def _init_widget_state() -> None:
    """Initialize Page 3 state using canonical state.py primitives.

    - Widget-backed keys: ensure_widget_buffer hydrates w__{field} from draft.
    - Runtime/output keys: direct session_state init (no widget, no draft).
    - Bucket definitions: hydrate from draft if present, else seed defaults.
    """
    # Nonce counter: bumped on LOAD to force Streamlit to discard cached widget
    # values. Streamlit's widget tracker survives `del st.session_state[key]`,
    # so changing the key string itself (via _v{N} suffix) is the only reliable
    # way to make `value=` parameter take effect after a LOAD.
    if "_p3_render_nonce" not in st.session_state:
        st.session_state["_p3_render_nonce"] = 0

    for k in _WIDGET_DEFAULT_KEYS:
        ensure_widget_buffer(k, PARAM_DEFAULTS[k])

    for k in _RUNTIME_DEFAULT_KEYS:
        if k not in st.session_state:
            st.session_state[k] = PARAM_DEFAULTS[k]

    # inv_bucket_definitions: complex object — keep as plain session_state mirror
    # of draft. Detect cust_id changes (fresh login / customer switch) and force
    # a full re-hydration, wiping every stale widget key that would otherwise
    # shadow the loaded values via Streamlit's "key takes precedence over value"
    # behavior. Without this, asset_* / bucket_name_* / bucket_year_* keys
    # cached from a previous customer make the new load silently show defaults.
    _cur_cid = (draft_get("cust_id", "") or "").strip()
    _last_hydrated_cid = st.session_state.get("_p3_hydrated_cid")
    _cid_changed = (_last_hydrated_cid != _cur_cid)

    if _cid_changed:
        _stale_widget_keys = [
            _k for _k in list(st.session_state.keys())
            if (
                _k.startswith("asset_")
                or _k.startswith("bucket_name_")
                or _k.startswith("bucket_year_end_")
                or _k.startswith("bucket_year_start_ro_")
                or _k.startswith("bucket_year_end_inf_")
            )
        ]
        for _k in _stale_widget_keys:
            del st.session_state[_k]

        # Auto-load saved asset config if available for this cust_id.
        # Order of precedence: saved DB config → draft → defaults.
        _auto_loaded = False
        _auto_load_err = None
        if _cur_cid:
            try:
                if has_saved_bucket_definitions(_cur_cid):
                    _loaded_defs = load_bucket_definitions(_cur_cid)
                    if _loaded_defs:
                        st.session_state["inv_bucket_definitions"] = _loaded_defs
                        draft_set("inv_bucket_definitions", _loaded_defs)
                        _auto_loaded = True
            except Exception as _e:
                _auto_load_err = str(_e)

        if not _auto_loaded:
            st.session_state["inv_bucket_definitions"] = draft_get(
                "inv_bucket_definitions",
                PARAM_DEFAULTS["inv_bucket_definitions"],
            )

        # Bump render nonce so any cached widget keys (incl. those that survived
        # the stale-key cleanup) are discarded on next render.
        st.session_state["_p3_render_nonce"] = (
            st.session_state.get("_p3_render_nonce", 0) + 1
        )
        st.session_state["_p3_hydrated_cid"] = _cur_cid
        st.session_state["_p3_auto_loaded"] = _auto_loaded
        st.session_state["_p3_auto_load_err"] = _auto_load_err
    elif "inv_bucket_definitions" not in st.session_state:
        st.session_state["inv_bucket_definitions"] = draft_get(
            "inv_bucket_definitions",
            PARAM_DEFAULTS["inv_bucket_definitions"],
        )


# ============================================================
# BUCKET DEFINITION HELPERS
# ============================================================

def _coerce_bucket_dict(value):
    """
    Make sure a bucket entry is a dict. Handles legacy rows that were saved
    as JSON-encoded strings (or double-encoded). Returns None if the value
    cannot be normalized to a dict.
    """
    import json as _json
    seen = 0
    while isinstance(value, str) and seen < 4:
        try:
            value = _json.loads(value)
        except Exception:
            return None
        seen += 1
    return value if isinstance(value, dict) else None


def _get_bucket_definitions() -> list:
    """ดึง bucket definitions จาก session state (with default fallback)"""
    raw = st.session_state.get(
        "inv_bucket_definitions",
        PARAM_DEFAULTS["inv_bucket_definitions"],
    )
    if not isinstance(raw, list):
        return list(PARAM_DEFAULTS["inv_bucket_definitions"])
    cleaned = []
    for item in raw:
        d = _coerce_bucket_dict(item)
        if d is not None:
            cleaned.append(d)
    # If everything got dropped, fall back to defaults so the UI keeps working
    if not cleaned:
        return list(PARAM_DEFAULTS["inv_bucket_definitions"])
    return cleaned


def _build_bucket_configs_from_definitions(defs: list) -> list:
    """สร้าง List[BucketConfig] จาก bucket definitions"""
    return [
        BucketConfig(
            bucket_name=str(d["name"]),
            start_offset_year=int(d["year_start"]),
            end_offset_year=None if d.get("year_end") is None else int(d["year_end"]),
            annual_return_rate=float(d["discount_rate"]),
        )
        for d in defs
    ]


# B6: position-based correlation fallback ใช้เมื่อชื่อ bucket ไม่ตรงกับ
# DEFAULT_INTRA_BUCKET_CORRELATION (e.g. "short term"/"medium term"/"long term"
# หรือชื่อที่ผู้ใช้กำหนดเอง). ลำดับ low → high สะท้อน gradient ความเสี่ยง.
_DEFAULT_CORR_BY_POSITION = [0.1, 0.3, 0.5]


def _build_bucket_return_models_from_definitions(defs: list) -> list:
    """
    สร้าง List[BucketReturnModel] จาก bucket definitions
    แต่ละ bucket มี assets (AssetReturnModel) พร้อม weight
    ค่าในตาราง UI เก็บเป็น % → แปลงเป็น decimal ที่นี่
    """
    models = []
    for idx, d in enumerate(defs):
        raw_assets = d.get("assets", [])
        asset_models = []
        for a in raw_assets:
            w = float(a.get("weight_pct", 0.0))
            if w <= 0:
                continue
            asset_models.append(AssetReturnModel(
                asset_name=str(a.get("asset_name", "Asset")),
                weight=w,
                mean_return=float(a.get("mean_pct", 0.0)) / 100.0,
                std_dev=float(a.get("std_pct", 0.0)) / 100.0,
                min_return=float(a.get("min_pct", -100.0)) / 100.0,
                max_return=float(a.get("max_pct", 100.0)) / 100.0,
                # Student-t (df=5) hardcoded — fat tails ใกล้เคียง equity return จริง
                distribution="student_t",
            ))

        # effective bucket-level params (weighted avg) for display / validation
        if asset_models:
            total_w = sum(a.weight for a in asset_models)
            eff_mean = sum(a.weight * a.mean_return for a in asset_models) / total_w
            eff_std  = sum(a.weight * a.std_dev for a in asset_models) / total_w
        else:
            eff_mean = float(d.get("discount_rate", 0.0))
            eff_std  = 0.0

        # B6: ถ้าชื่อ bucket ไม่อยู่ใน dict → ใช้ค่า correlation ตามตำแหน่ง
        # (รองรับชื่อ default ใหม่และชื่อ custom ที่ผู้ใช้ตั้ง)
        _bucket_name = str(d["name"])
        _pos_fallback = _DEFAULT_CORR_BY_POSITION[
            min(idx, len(_DEFAULT_CORR_BY_POSITION) - 1)
        ]
        _corr = DEFAULT_INTRA_BUCKET_CORRELATION.get(_bucket_name, _pos_fallback)
        models.append(BucketReturnModel(
            bucket_name=_bucket_name,
            mean_return=eff_mean,
            std_dev=eff_std,
            assets=asset_models,
            intra_bucket_correlation=_corr,
            # Student-t (df=5) hardcoded — มีผลเฉพาะกรณี bucket ไม่มี assets (fallback path)
            distribution="student_t",
        ))
    return models


def _required_upstream_ready() -> bool:
    return (
        st.session_state.get("expense_df") is not None
        and st.session_state.get("saving_df") is not None
        and st.session_state.get("saving_plan_obj") is not None
        and st.session_state.get("assumptions_obj") is not None
    )


def _fmt_money(x: Optional[float]) -> str:
    if x is None:
        return "-"
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return str(x)


def _kpi_card(label: str, value: str, color: str, bg: str, note: str = "") -> str:
    """Styled metric card rendered via st.markdown(unsafe_allow_html=True)."""
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


def _group_label(icon: str, title: str) -> str:
    return (
        f'<div style="margin:20px 0 10px; display:flex; align-items:center; gap:8px;">'
        f'<span style="font-size:15px;">{icon}</span>'
        f'<span style="font-size:13px; font-weight:600; color:#555;">{title}</span>'
        f'</div>'
    )


def _safe_summary_metric(summary_df: Optional[pd.DataFrame], metric_name: str):
    if summary_df is None or not isinstance(summary_df, pd.DataFrame) or summary_df.empty:
        return None
    if "metric" not in summary_df.columns or "value" not in summary_df.columns:
        return None

    hit = summary_df.loc[summary_df["metric"] == metric_name, "value"]
    if hit.empty:
        return None
    return hit.iloc[0]


def _build_bucket_return_models_from_state() -> list:
    """Build BucketReturnModel list จาก inv_bucket_definitions ใน session state"""
    return _build_bucket_return_models_from_definitions(_get_bucket_definitions())


def analyze_mc_result_local(mc_result):
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


# A5: init widget buffers + runtime state once per session (idempotent)
_init_widget_state()

if not _required_upstream_ready():
    st.warning(S("p3", "gate_warn"))
    st.stop()


# ============================================================
# READ UPSTREAM RESULTS
# ============================================================
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
total_projected_expense = (
    float(expense_df["inflated_amount"].sum())
    if expense_df is not None and not expense_df.empty
    else 0.0
)

peak_annual_expense = (
    float(_safe_summary_metric(summary_df, "peak_annual_expense"))
    if summary_df is not None and not summary_df.empty
    else 0.0
)

peak_annual_expense_year = (
    int(_safe_summary_metric(summary_df, "peak_annual_expense_year"))
    if summary_df is not None and not summary_df.empty
    else 0.0
)

current_monthly_contribution = (
    int(_safe_summary_metric(summary_df, "current_monthly_contribution"))
    if summary_df is not None and not summary_df.empty
    else 0.0
)

initial_savings = (
    int(_safe_summary_metric(summary_df, "initial_savings"))
    if summary_df is not None and not summary_df.empty
    else 0.0
)

top_up = (
    int(_safe_summary_metric(summary_df, "total_topup"))
    if summary_df is not None and not summary_df.empty
    else 0.0
)

ttl_cont = (
    int(_safe_summary_metric(summary_df, "total_contribution"))
    if summary_df is not None and not summary_df.empty
    else 0.0
)


n_expense_rows = len(expense_df) if expense_df is not None else 0
annual_contribution_total = float(sum(annual_contribution_map.values())) if annual_contribution_map else 0.0
annual_topup_total = float(sum(annual_topup_map.values())) if annual_topup_map else 0.0


# ============================================================
# SIDEBAR: WORKFLOW + NAVIGATION
# ============================================================
with st.sidebar:
    st.markdown(S("p3", "workflow_header"))
    st.markdown(S("sidebar", "step1_done"))
    st.markdown(S("sidebar", "step2_done"))
    st.markdown(S("p3", "step3_active"))
    if st.button(S("p3", "btn_back"), width="stretch"):
        switch_page_with_persist("pages/02_Expense_Simulation.py")

    # st.divider()
    # st.markdown(S("p3", "plan_summary"))
    # st.metric(S("p3", "ctx_total_exp"), f"฿{total_projected_expense:,.0f}")
    # st.metric(S("p3", "ctx_initial"), f"฿{initial_savings:,.0f}")
    # st.metric(S("p3", "ctx_monthly"), f"฿{current_monthly_contribution:,.0f}")
    # _t_years = expense_end_year - expense_start_year +1
    # st.caption(S("p3", "sidebar_horizon", start=expense_start_year, end=expense_end_year, n=_t_years))

    if st.session_state.get("inv_investment_sim_done"):
        st.divider()
        st.markdown(S("p3", "sim_done_header"))
        st.caption(S("p3", "sim_done_caption"))


# ============================================================
# SECTION 1: PLAN CONTEXT (COMPACT)
# ============================================================
st.subheader(S("p3", "sec1_header"))
with st.container(border=True):
    _t = expense_end_year - expense_start_year +1
    _cx = st.columns(3)
    _cx[0].metric(S("p3", "ctx_total_exp"), f"฿{total_projected_expense:,.0f}")
    _cx[1].metric(S("p3", "ctx_horizon"), S("p3", "ctx_horizon_val", start=expense_start_year, end=expense_end_year, n=_t))
    _cx[2].metric(S("p3", "ctx_peak"), S("p3", "ctx_peak_val", amount=peak_annual_expense, year=peak_annual_expense_year))
    
    _cy = st.columns(3)
    _cy[0].metric(S("p3", "ctx_ttl_cont"), f"฿{ttl_cont+initial_savings+top_up:,.0f}")
    _cy[1].metric(S("p3", "ctx_initial"), f"฿{initial_savings+top_up:,.0f}")
    _cy[2].metric(f"{S("p3", "ctx_monthly")} (ระยะเวลา {_t*12} เดือน)", f"฿{current_monthly_contribution:,.0f}")


# ============================================================
# SECTION 2: BUCKET & ASSET CONFIGURATION
# ============================================================
st.subheader(S("p3", "sec2_header"))
st.caption("3 Bucket ตายตัว — แก้ได้เฉพาะ ชื่อ และ ปีสิ้นสุด ของ Bucket 1 / 2 "
           "(Bucket 1 เริ่มที่ปี 1 และ Bucket 3 ปลายเปิด rolling window)")

# ---------- Fixed 3-bucket structure (edit name + middle year_ends only) ----------
_DEFAULT_NEW_ASSETS = [
    {"asset_name": "Asset 1", "weight_pct": 100.0,
     "mean_pct": 4.0, "std_pct": 8.0, "min_pct": -30.0, "max_pct": 30.0}
]

_FIXED_BUCKET_TEMPLATE = [
    {"name": "Liquidity", "idx": 0},
    {"name": "Stability", "idx": 1},
    {"name": "Growth",    "idx": 2},
]

# ---------- Saved bucket+asset config status (auto-loaded in _init_widget_state) ----------
_cust_id_for_load = (draft_get("cust_id", "") or "").strip()
if _cust_id_for_load:
    _auto_load_err = st.session_state.get("_p3_auto_load_err")
    if _auto_load_err:
        st.error(f"ตรวจสอบ asset config ก่อนหน้าไม่สำเร็จ: {_auto_load_err}")

    try:
        _has_saved_defs = has_saved_bucket_definitions(_cust_id_for_load)
    except Exception:
        _has_saved_defs = False

    if _has_saved_defs:
        _saved_meta = get_saved_bucket_meta(_cust_id_for_load) or {}
        _saved_ts = _saved_meta.get("updated_at", "")
        _saved_n = int(_saved_meta.get("n_buckets", 0))
        _info_msg = f"✅ โหลด asset config ที่บันทึกไว้แล้ว ({_saved_n} bucket)"
        if _saved_ts:
            _info_msg += f" — บันทึกล่าสุด: {_saved_ts}"
        st.success(_info_msg)
    else:
        st.info("ℹ️ ยังไม่มี asset config ที่บันทึกไว้สำหรับลูกค้านี้ — กำลังแสดงค่า default")

_cur_defs = _get_bucket_definitions()
# Force exactly 3 buckets — no add/remove allowed
while len(_cur_defs) < 3:
    _cur_defs.append({
        "name": _FIXED_BUCKET_TEMPLATE[len(_cur_defs)]["name"],
        "year_start": 1, "year_end": None, "discount_rate": 0.04,
        "assets": _DEFAULT_NEW_ASSETS.copy(),
    })
if len(_cur_defs) > 3:
    _cur_defs = _cur_defs[:3]

# Seed sane defaults for first-render: bucket0 ends year 3, bucket1 ends year 6
if _cur_defs[0].get("year_end") is None:
    _cur_defs[0]["year_end"] = 3
if _cur_defs[1].get("year_end") is None:
    _cur_defs[1]["year_end"] = max(int(_cur_defs[0]["year_end"]) + 1, 6)

_new_defs = []
# Nonce suffix for widget keys: bumped on LOAD button so Streamlit's widget
# tracker sees brand-new keys and honors the freshly-loaded `value=` defaults.
_nonce = st.session_state.get("_p3_render_nonce", 0)
st.markdown(S("p3", "bucket_tbl_header"))
with st.container(border=True):
    _hc1, _hc2, _hc3 = st.columns([2, 1, 1])
    _hc1.caption(S("p3", "col_bucket_name"))
    _hc2.caption(S("p3", "col_year_start"))
    _hc3.caption("ปีสิ้นสุด")

    # ── Bucket 0 — year_start LOCKED = 1, year_end editable ──
    _bc1, _bc2, _bc3 = st.columns([2, 1, 1])
    with _bc1:
        _b0_name = st.text_input(
            S("p3", "col_bucket_name"),
            value=_cur_defs[0].get("name", "Liquidity"),
            key=f"bucket_name_0_v{_nonce}",
            label_visibility="collapsed",
        )
    with _bc2:
        _skey0 = f"bucket_year_start_ro_0_v{_nonce}"
        st.session_state[_skey0] = "1"
        st.text_input(
            S("p3", "col_year_start"),
            disabled=True,
            key=_skey0,
            label_visibility="collapsed",
        )
    with _bc3:
        _b0_end = st.number_input(
            "ปีสิ้นสุด",
            value=int(_cur_defs[0].get("year_end", 3)),
            min_value=1, max_value=98, step=1,
            key=f"bucket_year_end_0_v{_nonce}",
            label_visibility="collapsed",
        )

    # ── Bucket 1 — year_start auto-derived (LOCKED), year_end editable ──
    _b1_start = int(_b0_end) + 1
    # Auto-repair: if cached bucket 1 end < new min_value, bump it up so the
    # number_input doesn't throw a StreamlitAPIException
    _cached_b1_end = st.session_state.get(f"bucket_year_end_1_v{_nonce}")
    if _cached_b1_end is not None and int(_cached_b1_end) < _b1_start:
        st.session_state[f"bucket_year_end_1_v{_nonce}"] = _b1_start
    # Force-refresh disabled display: Streamlit caches widget value by key,
    # so we must update session_state BEFORE rendering to pick up the new value
    st.session_state[f"bucket_year_start_ro_1_v{_nonce}"] = str(_b1_start)
    _bc1, _bc2, _bc3 = st.columns([2, 1, 1])
    with _bc1:
        _b1_name = st.text_input(
            S("p3", "col_bucket_name"),
            value=_cur_defs[1].get("name", "Stability"),
            key=f"bucket_name_1_v{_nonce}",
            label_visibility="collapsed",
        )
    with _bc2:
        st.text_input(
            S("p3", "col_year_start"),
            # value=str(_b1_start),
            disabled=True,
            key=f"bucket_year_start_ro_1_v{_nonce}",
            label_visibility="collapsed",
        )
    with _bc3:
        # Force value ≥ _b1_start to avoid overlap
        _b1_end_default = max(int(_cur_defs[1].get("year_end", _b1_start)), _b1_start)
        _b1_end = st.number_input(
            "ปีสิ้นสุด",
            value=_b1_end_default,
            min_value=_b1_start, max_value=99, step=1,
            key=f"bucket_year_end_1_v{_nonce}",
            label_visibility="collapsed",
        )

    # ── Bucket 2 — year_start auto-derived (LOCKED), year_end LOCKED = ∞ ──
    _b2_start = int(_b1_end) + 1
    # Force-refresh disabled display so bucket 3's start tracks bucket 2's end
    st.session_state[f"bucket_year_start_ro_2_v{_nonce}"] = str(_b2_start)
    _bc1, _bc2, _bc3 = st.columns([2, 1, 1])
    with _bc1:
        _b2_name = st.text_input(
            S("p3", "col_bucket_name"),
            value=_cur_defs[2].get("name", "Growth"),
            key=f"bucket_name_2_v{_nonce}",
            label_visibility="collapsed",
        )
    with _bc2:
        st.text_input(
            S("p3", "col_year_start"),
            # value=str(_b2_start),
            disabled=True,
            key=f"bucket_year_start_ro_2_v{_nonce}",
            label_visibility="collapsed",
        )
    with _bc3:
        st.text_input(
            "ปีสิ้นสุด",
            value="∞",
            disabled=True,
            key=f"bucket_year_end_inf_2_v{_nonce}",
            label_visibility="collapsed",
        )

    # Build _new_defs (no overlap by construction — year_starts derived)
    _new_defs.append({
        "name": (str(_b0_name).strip() or "Liquidity"),
        "year_start": 1,
        "year_end": int(_b0_end),
        "discount_rate": _cur_defs[0].get("discount_rate", 0.04),
        "assets": _cur_defs[0].get("assets", _DEFAULT_NEW_ASSETS.copy()),
    })
    _new_defs.append({
        "name": (str(_b1_name).strip() or "Stability"),
        "year_start": _b1_start,
        "year_end": int(_b1_end),
        "discount_rate": _cur_defs[1].get("discount_rate", 0.04),
        "assets": _cur_defs[1].get("assets", _DEFAULT_NEW_ASSETS.copy()),
    })
    _new_defs.append({
        "name": (str(_b2_name).strip() or "Growth"),
        "year_start": _b2_start,
        "year_end": None,
        "discount_rate": _cur_defs[2].get("discount_rate", 0.04),
        "assets": _cur_defs[2].get("assets", _DEFAULT_NEW_ASSETS.copy()),
    })

    # ── Validation (only need to check duplicate names — year ranges are
    # overlap-free by construction since year_starts are derived) ──
    _bucket_names = [d["name"] for d in _new_defs]
    _bucket_errors = []
    if len(set(_bucket_names)) != 3:
        _bucket_errors.append(S("p3", "err_bucket_dup"))
    _bucket_config_valid = len(_bucket_errors) == 0
    if _bucket_errors:
        for _err in _bucket_errors:
            st.error(_err)

    # ── Dynamic horizon summary (bottom of box) ──
    _summary_parts = []
    for _d in _new_defs:
        _y_end_lbl = "∞" if _d["year_end"] is None else str(_d["year_end"])
        _summary_parts.append(f"**{_d['name']}**: ปี {_d['year_start']}–{_y_end_lbl}")
    if _summary_parts:
        _summary_parts[-1] = (
            f"{_summary_parts[-1]} (rolling window — target weight ปรับใหม่ทุกปี)"
        )
        st.markdown(" | ".join(_summary_parts))

# ---------- Asset definition tables (per bucket) ----------
st.markdown(S("p3", "asset_tbl_header"))

# Track per-bucket asset validation. If any bucket fails, the Simulate
# button is disabled below. _asset_errors_summary holds short per-bucket
# labels used in the bottom warning.
_asset_config_valid = True
_asset_errors_summary: list = []

for _bi, _bdef in enumerate(_new_defs):
    _bname = _bdef["name"]
    _yr_end_label = "∞" if _bdef["year_end"] is None else str(_bdef["year_end"])
    _bdef_label = S("p3", "bucket_expander", name=_bname, start=_bdef["year_start"], end=_yr_end_label)

    with st.expander(_bdef_label, expanded=(_bi == 0)):
        _cur_assets = _bdef.get("assets") or _DEFAULT_NEW_ASSETS.copy()
        _n_cur = len(_cur_assets)

        # ── Metrics summary (above inputs) ──
        _va_pre = [a for a in _cur_assets if float(a.get("weight_pct", 0)) > 0]
        _tw_pre = sum(float(a["weight_pct"]) for a in _va_pre) or 1.0
        _em_pre = sum(float(a["weight_pct"]) * float(a.get("mean_pct", 0)) for a in _va_pre) / _tw_pre if _va_pre else 0.0
        _es_pre = sum(float(a["weight_pct"]) * float(a.get("std_pct", 0)) for a in _va_pre) / _tw_pre if _va_pre else 0.0
        _mw1, _mw2, _mw3 = st.columns(3)
        _mw1.metric(S("p3", "metric_n_assets"), len(_va_pre))
        _mw2.metric(S("p3", "metric_total_weight"), f"{sum(float(a['weight_pct']) for a in _va_pre):.1f}%")
        _mw3.metric(S("p3", "metric_eff_mean"), f"{_em_pre:.2f}%")
        if _va_pre:
            st.caption(S("p3", "asset_eff_caption", mean=_em_pre, std=_es_pre, n=len(_va_pre)))

        # ── Add / remove asset buttons ──
        _ab1, _ab2, _ = st.columns([1, 1, 4])
        with _ab1:
            if st.button(SC("btn_add"), key=f"btn_add_asset_{_bi}"):
                _tmp = st.session_state.get("inv_bucket_definitions", [])
                if _bi < len(_tmp):
                    _tmp[_bi]["assets"] = list(_cur_assets) + [_DEFAULT_ASSET.copy()]
                st.session_state["inv_bucket_definitions"] = _tmp
                draft_set("inv_bucket_definitions", _tmp)
                st.rerun()
        with _ab2:
            if st.button(SC("btn_remove_last"), key=f"btn_remove_asset_{_bi}",
                         disabled=_n_cur <= 1):
                _tmp = st.session_state.get("inv_bucket_definitions", [])
                if _bi < len(_tmp) and len(_tmp[_bi]["assets"]) > 1:
                    _tmp[_bi]["assets"] = list(_cur_assets)[:-1]
                st.session_state["inv_bucket_definitions"] = _tmp
                draft_set("inv_bucket_definitions", _tmp)
                st.rerun()

        # ── Column headers ──
        _ah0, _ah1, _ah2, _ah3, _ah4, _ah5 = st.columns([2, 1, 1, 1, 1, 1])
        _ah0.caption(S("p3", "col_asset_name"))
        _ah1.caption(S("p3", "col_weight"))
        _ah2.caption(S("p3", "col_mean_return"))
        _ah3.caption(S("p3", "col_std"))
        _ah4.caption(S("p3", "col_min_return"))
        _ah5.caption(S("p3", "col_max_return"))

        # ── Per-row inputs ──
        _edited_assets = []
        for _ai, _a in enumerate(_cur_assets):
            _ac0, _ac1, _ac2, _ac3, _ac4, _ac5 = st.columns([2, 1, 1, 1, 1, 1])
            with _ac0:
                _a_name = st.text_input(
                    S("p3", "col_asset_name"), label_visibility="collapsed",
                    value=_a.get("asset_name", "Asset"),
                    key=f"asset_{_bi}_{_ai}_name_v{_nonce}",
                )
            with _ac1:
                _a_w = st.number_input(
                    S("p3", "col_weight"), label_visibility="collapsed",
                    value=float(_a.get("weight_pct", 100.0)),
                    min_value=0.0, max_value=100.0, step=5.0, format="%.1f",
                    key=f"asset_{_bi}_{_ai}_weight_v{_nonce}",
                )
            with _ac2:
                _a_mean = st.number_input(
                    S("p3", "col_mean_return"), label_visibility="collapsed",
                    value=float(_a.get("mean_pct", 4.0)),
                    min_value=0.0, max_value=100.0,
                    step=0.5, format="%.2f",
                    key=f"asset_{_bi}_{_ai}_mean_v{_nonce}",
                )
            with _ac3:
                _a_std = st.number_input(
                    S("p3", "col_std"), label_visibility="collapsed",
                    value=float(_a.get("std_pct", 8.0)),
                    min_value=0.0, max_value=100.0, step=0.5, format="%.2f",
                    key=f"asset_{_bi}_{_ai}_std_v{_nonce}",
                )
            with _ac4:
                _a_min = st.number_input(
                    S("p3", "col_min_return"), label_visibility="collapsed",
                    value=float(_a.get("min_pct", -30.0)),
                    step=0.5, format="%.1f",
                    key=f"asset_{_bi}_{_ai}_min_v{_nonce}",
                )
            with _ac5:
                _a_max = st.number_input(
                    S("p3", "col_max_return"), label_visibility="collapsed",
                    value=float(_a.get("max_pct", 30.0)),
                    step=0.5, format="%.1f",
                    key=f"asset_{_bi}_{_ai}_max_v{_nonce}",
                )
            _edited_assets.append({
                "asset_name": _a_name,
                "weight_pct": float(_a_w),
                "mean_pct":   float(_a_mean),
                "std_pct":    float(_a_std),
                "min_pct":    float(_a_min),
                "max_pct":    float(_a_max),
            })

        # ── Validation box ──
        _va = [a for a in _edited_assets if float(a["weight_pct"]) > 0]
        _tw = sum(float(a["weight_pct"]) for a in _va)
        _errors_a, _warns_a = [], []

        # Duplicate asset names within the same bucket (case-insensitive)
        _seen_names: dict = {}
        for _a2 in _edited_assets:
            _nm = str(_a2.get("asset_name", "")).strip()
            if _nm:
                _key_lc = _nm.lower()
                _seen_names[_key_lc] = _seen_names.get(_key_lc, 0) + 1
        _dup_names = [n for n, c in _seen_names.items() if c > 1]

        # PROHIBIT
        if not _va:
            _errors_a.append(S("p3", "err_no_asset"))
        else:
            if abs(_tw - 100.0) > 0.1:
                _errors_a.append(f"น้ำหนักรวมต้องเป็น 100% (ปัจจุบัน {_tw:.1f}%)")
            if _dup_names:
                _errors_a.append(
                    f"ชื่อ asset ซ้ำในกลุ่มเดียวกัน: {', '.join(_dup_names)}"
                )
            for _a2 in _va:
                _nm = str(_a2.get("asset_name", "")).strip()
                _mean = float(_a2["mean_pct"])
                _std  = float(_a2["std_pct"])
                _lo   = float(_a2["min_pct"])
                _hi   = float(_a2["max_pct"])
                if not _nm:
                    _errors_a.append(f"พบ asset ที่ยังไม่ได้ตั้งชื่อ (weight {float(_a2['weight_pct']):.1f}%)")
                if _mean <= 0:
                    _errors_a.append(f"'{_nm or '(no name)'}': {S('p3', 'col_mean_return')} ต้องมากกว่า 0%")
                if _lo > _hi:
                    _errors_a.append(f"'{_nm or '(no name)'}': Min ต้องไม่เกิน Max")
                # Mean must lie inside the [Min, Max] range — otherwise clipping
                # in the simulator silently distorts the distribution
                if _lo <= _hi and not (_lo <= _mean <= _hi):
                    _errors_a.append(
                        f"'{_nm or '(no name)'}': Mean ({_mean:.2f}%) ต้องอยู่ในช่วง "
                        f"[Min {_lo:.1f}%, Max {_hi:.1f}%]"
                    )
                if _std < 0:
                    _errors_a.append(f"'{_nm or '(no name)'}': Std Dev ต้องไม่ติดลบ")
        # WARNING
        for _a2 in _va:
            _nm = str(_a2.get("asset_name", "")).strip() or "(no name)"
            _std = float(_a2["std_pct"])
            _lo  = float(_a2["min_pct"])
            _hi  = float(_a2["max_pct"])
            if _std == 0:
                _warns_a.append(f"'{_nm}': Std Dev = 0 — risk-free ไม่มีความเสี่ยง")
            elif _std > 50:
                _warns_a.append(f"'{_nm}': Std Dev = {_std:.1f}% สูงผิดปกติ ลองตรวจสอบอีกครั้ง")
            if _lo == _hi:
                _warns_a.append(f"'{_nm}': Min = Max — ผลตอบแทนคงที่ ไม่มี dispersion")

        if _errors_a or _warns_a:
            with st.container(border=False):
                for _e in _errors_a:
                    st.error(_e)
                for _w in _warns_a:
                    st.warning(_w)

        if _errors_a:
            _asset_config_valid = False
            _asset_errors_summary.append(f"**{_bname}** ({len(_errors_a)} ข้อผิดพลาด)")

        # save assets back
        _new_defs[_bi]["assets"] = _edited_assets

# ---- Derive discount_rate from asset weighted mean (no UI input needed) ----
for _bi_d, _bdef_d in enumerate(_new_defs):
    _valid_a_d = [a for a in _bdef_d.get("assets", []) if float(a.get("weight_pct", 0)) > 0]
    if _valid_a_d:
        _tw_d = sum(float(a["weight_pct"]) for a in _valid_a_d)
        _eff_d = sum(float(a["weight_pct"]) * float(a.get("mean_pct", 0)) for a in _valid_a_d) / _tw_d
        _new_defs[_bi_d]["discount_rate"] = _eff_d / 100.0

# ---- Asset Performance Preview ----
with st.expander(S("p3", "preview_expander"), expanded=False):
    import numpy as _np

    # ---- 1. Risk-Return Scatter ----
    _scatter_rows = []
    for _bd in _new_defs:
        _valid_a = [a for a in _bd.get("assets", []) if float(a.get("weight_pct", 0)) > 0]
        _total_w = sum(float(a["weight_pct"]) for a in _valid_a) or 1.0
        for _a in _valid_a:
            _scatter_rows.append({
                "bucket": _bd["name"],
                "asset": str(_a.get("asset_name", "?")),
                "mean_pct": float(_a.get("mean_pct", 0)),
                "std_pct": float(_a.get("std_pct", 0)),
                "weight_pct": float(_a.get("weight_pct", 0)),
                "norm_weight": float(_a["weight_pct"]) / _total_w * 100,
            })

    if _scatter_rows:
        _scatter_df = pd.DataFrame(_scatter_rows)

        st.markdown(S("p3", "preview_rr_map"))
        _rr_chart = (
            alt.Chart(_scatter_df)
            .mark_circle()
            .encode(
                x=alt.X("std_pct:Q", title="Std Dev % (ความเสี่ยง)", scale=alt.Scale(zero=True)),
                y=alt.Y("mean_pct:Q", title="Mean Return %"),
                color=alt.Color("bucket:N", title="Bucket"),
                size=alt.Size("norm_weight:Q", scale=alt.Scale(range=[80, 800]), legend=None),
                tooltip=[
                    alt.Tooltip("asset:N", title="Asset"),
                    alt.Tooltip("bucket:N", title="Bucket"),
                    alt.Tooltip("mean_pct:Q", title="Mean %", format=".2f"),
                    alt.Tooltip("std_pct:Q", title="Std Dev %", format=".2f"),
                    alt.Tooltip("norm_weight:Q", title="Weight %", format=".1f"),
                ],
            )
            .properties(height=320)
        )
        # reference lines
        _zero_line = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
            strokeDash=[4, 4], color="gray", opacity=0.5
        ).encode(y="y:Q")
        st.altair_chart(_rr_chart + _zero_line, width="stretch")

        # ---- 2. Asset Composition per Bucket ----
        st.markdown(S("p3", "preview_composition"))
        _comp_chart = (
            alt.Chart(_scatter_df)
            .mark_bar()
            .encode(
                x=alt.X("norm_weight:Q", stack="normalize", title="สัดส่วน", axis=alt.Axis(format="%")),
                y=alt.Y("bucket:N", title="Bucket"),
                color=alt.Color("asset:N", title="Asset"),
                tooltip=[
                    alt.Tooltip("bucket:N"),
                    alt.Tooltip("asset:N"),
                    alt.Tooltip("norm_weight:Q", title="Weight %", format=".1f"),
                ],
            )
            .properties(height=max(60 * len(_new_defs), 120))
        )
        st.altair_chart(_comp_chart, width="stretch")

        # ---- 3. Simulated Return Distribution ----
        st.markdown(S("p3", "preview_dist"))
        _SIM_N = 2000
        _rng_preview = _np.random.default_rng(42)
        _sim_rows = []
        for _bd in _new_defs:
            for _a in _bd.get("assets", []):
                _w = float(_a.get("weight_pct", 0))
                if _w <= 0:
                    continue
                _mu  = float(_a.get("mean_pct", 0)) / 100
                _sig = float(_a.get("std_pct", 0)) / 100
                _lo  = float(_a.get("min_pct", -100)) / 100
                _hi  = float(_a.get("max_pct", 100)) / 100
                if _sig > 0:
                    _samples = _np.clip(_rng_preview.normal(_mu, _sig, _SIM_N), _lo, _hi)
                else:
                    _samples = _np.full(_SIM_N, _mu)
                for _s in _samples:
                    _sim_rows.append({
                        "bucket": _bd["name"],
                        "asset": str(_a.get("asset_name", "?")),
                        "return_pct": float(_s) * 100,
                    })

        if _sim_rows:
            _sim_df = pd.DataFrame(_sim_rows)

            _dist_chart = (
                alt.Chart(_sim_df)
                .mark_bar(opacity=0.6, binSpacing=0)
                .encode(
                    x=alt.X("return_pct:Q", bin=alt.Bin(maxbins=40), title="Annual Return %"),
                    y=alt.Y("count():Q", title="จำนวน scenarios", stack=None),
                    color=alt.Color("asset:N", title="Asset"),
                    facet=alt.Facet("bucket:N", columns=3, title="Bucket"),
                    tooltip=[
                        alt.Tooltip("asset:N"),
                        alt.Tooltip("return_pct:Q", bin=True, format=".1f"),
                        alt.Tooltip("count():Q"),
                    ],
                )
                .properties(width=260, height=180)
            )
            st.altair_chart(_dist_chart)

        # ---- 4. Mean & Std comparison table ----
        st.markdown(S("p3", "preview_summary"))
        _summary_rows = []
        for _bd in _new_defs:
            _valid_a2 = [a for a in _bd.get("assets", []) if float(a.get("weight_pct", 0)) > 0]
            _tw2 = sum(float(a["weight_pct"]) for a in _valid_a2) or 1.0
            for _a in _valid_a2:
                _w2 = float(_a["weight_pct"]) / _tw2
                _summary_rows.append({
                    "Bucket": _bd["name"],
                    "Asset": str(_a.get("asset_name", "?")),
                    "Weight": f"{_w2 * 100:.1f}%",
                    "Mean Return": f"{_a.get('mean_pct', 0):.2f}%",
                    "Std Dev": f"{_a.get('std_pct', 0):.2f}%",
                    "Min Return": f"{_a.get('min_pct', 0):.1f}%",
                    "Max Return": f"{_a.get('max_pct', 0):.1f}%",
                    "Sharpe*": f"{(_a.get('mean_pct', 0) / _a['std_pct']):.2f}" if float(_a.get("std_pct", 0)) > 0 else "∞",
                })
        st.dataframe(pd.DataFrame(_summary_rows), width="stretch", hide_index=True)
        st.caption(S("p3", "preview_sharpe_note"))
    else:
        st.info(S("p3", "preview_empty"))

# ---- Save definitions to session state + draft (B2: survive navigation) ----
st.session_state["inv_bucket_definitions"] = _new_defs
draft_set("inv_bucket_definitions", _new_defs)

# ---- Build configs from definitions for downstream use ----
_bucket_configs = _build_bucket_configs_from_definitions(_new_defs)
_funding_rule = BucketFundingRule(
    contribution_priority=[d["name"] for d in _new_defs],
    allow_cross_bucket_transfer=True,
    transfer_direction="waterfall",
)

# ============================================================
# SECTION 3: INITIAL PORTFOLIO ALLOCATION (advanced — collapsed by default)
# ============================================================
# Initial allocation มีผลเฉพาะปีแรกของ simulation เท่านั้น เพราะ engine ทำ
# annual rebalance toward rolling-window target weights ที่ end-of-year ทุกปี
# (Step D ใน MC loop). โดยทั่วไปใช้ Auto allocation (waterfall) ก็เพียงพอ —
# เก็บ Manual mode ไว้สำหรับ stress test เคสพิเศษ.

# ---- Always compute auto preview (needed for downstream MC run) ----
_conservative_rate_map = {
    d["name"]: float(d["discount_rate"])
    for d in _new_defs
}

_allocation_preview_ok = False
_auto_allocation_df = pd.DataFrame()
_preview_requirement_df = pd.DataFrame()
_alloc_preview_err = None

try:
    _preview_expense_df = prepare_annual_expense(expense_df)
    _preview_assignment_df = assign_expense_to_buckets(
        annual_expense_df=_preview_expense_df,
        simulation_start_year=int(assumptions.start_year),
        bucket_configs=_bucket_configs,
    )
    _preview_requirement_df = calculate_bucket_requirements(
        bucket_assignment_df=_preview_assignment_df,
        simulation_start_year=int(assumptions.start_year),
        bucket_configs=_bucket_configs,
        discount_rate_override_map=_conservative_rate_map,
    )
    _auto_allocation_df = allocate_initial_savings_to_buckets(
        initial_savings=float(saving_plan.initial_savings),
        bucket_requirement_df=_preview_requirement_df,
        funding_rule=_funding_rule,
    )
    _allocation_preview_ok = True
except Exception as _e:
    _alloc_preview_err = _e

# Defaults outside expander (downstream MC run reads these)
_manual_allocation_df = None
_manual_allocation_valid = True
_alloc_mode = draft_get("inv_allocation_mode", "auto")

with st.expander(
    "⚙️ ขั้นสูง: การจัดสรรเงินเริ่มต้น (Initial Allocation) — Default: Auto",
    expanded=False,
):
    st.caption(
        "💡 ระบบทำ annual rebalance ทุกปีอยู่แล้ว → initial allocation มีผลเฉพาะปีแรก "
        "Default ใช้ Auto allocation (waterfall) ซึ่งเพียงพอสำหรับเคสปกติ "
        "เปิด Manual mode เฉพาะเมื่อต้องการ stress test เคสพิเศษ"
    )

    if not _allocation_preview_ok:
        st.warning(S("p3", "alloc_warn", err=_alloc_preview_err))
    else:
        st.markdown(S("p3", "alloc_rec_header"))
        _rate_desc = " | ".join(
            f"{d['name']} = {d['discount_rate']:.1%}"
            for d in _new_defs
        )
        st.caption(f"{S('p3', 'alloc_rate_desc', rates=_rate_desc)} โดยจัดสรรตามลำดับค่าใช้จ่ายที่เร็วที่สุดก่อน (waterfall)")

        _display_alloc = _auto_allocation_df.copy()
        _display_alloc["recommended_initial_amount"] = _display_alloc["recommended_initial_amount"].apply(lambda x: f"{x:,.0f}")
        _display_alloc["recommended_initial_weight"] = _display_alloc["recommended_initial_weight"].apply(lambda x: f"{x:.1%}")
        _display_alloc["unmet_required_amount"] = _display_alloc["unmet_required_amount"].apply(lambda x: f"{x:,.0f}")
        _display_alloc.columns = ["Bucket", "Recommended Amount", "Weight", "Unmet Requirement"]
        st.dataframe(_display_alloc, width="stretch", hide_index=True)

        # Bucket requirement detail — แสดง inline (Streamlit ไม่อนุญาต expander ซ้อน)
        _show_req = st.checkbox(
            S("p3", "alloc_req_expander"),
            value=False,
            key="_show_req_detail",
        )
        if _show_req:
            _req_display = _preview_requirement_df.copy()
            _req_display["required_present_value"] = _req_display["required_present_value"].apply(lambda x: f"{x:,.0f}")
            _req_display["total_future_expense"] = _req_display["total_future_expense"].apply(lambda x: f"{x:,.0f}")
            st.dataframe(_req_display, width="stretch", hide_index=True)

    # Toggle Auto / Manual — canonical w__{field} buffer
    _alloc_mode = st.radio(
        S("p3", "alloc_mode_label"),
        options=["auto", "manual"],
        format_func=lambda x: S("p3", "alloc_mode_auto") if x == "auto" else S("p3", "alloc_mode_manual"),
        horizontal=True,
        key=_widget_key("inv_allocation_mode"),
        on_change=on_widget_change,
        args=("inv_allocation_mode", str),
    )

    if _alloc_mode == "manual":
        st.markdown(S("p3", "manual_header"))
        _initial_savings_f = float(saving_plan.initial_savings)
        _dyn_bucket_names = [d["name"] for d in _new_defs]

        # ------ input mode toggle ------
        _input_mode = st.radio(
            S("p3", "manual_input_mode"),
            options=["amount", "percent"],
            format_func=lambda x: S("p3", "manual_opt_amount") if x == "amount" else S("p3", "manual_opt_pct"),
            horizontal=True,
            key=_widget_key("inv_manual_alloc_input_mode"),
            on_change=on_widget_change,
            args=("inv_manual_alloc_input_mode", str),
        )

        # Seed per-bucket w__{field} buffers from auto allocation (canonical pattern:
        # ensure_widget_buffer hydrates from draft if present, else uses the default).
        _auto_amt_map = {}
        if _allocation_preview_ok and not _auto_allocation_df.empty:
            _auto_amt_map = {
                str(r["bucket_name"]): float(r["recommended_initial_amount"])
                for _, r in _auto_allocation_df.iterrows()
            }
        for _bname in _dyn_bucket_names:
            _default_amt = _auto_amt_map.get(_bname, 0.0)
            _default_pct = (
                round(_default_amt / _initial_savings_f * 100, 2)
                if _initial_savings_f > 0 else 0.0
            )
            ensure_widget_buffer(f"inv_manual_alloc_amt_{_bname}", _default_amt)
            ensure_widget_buffer(f"inv_manual_alloc_pct_{_bname}", _default_pct)

        # ---- Render inputs dynamically per bucket ----
        _n_cols = min(len(_dyn_bucket_names), 4)
        _ma_cols = st.columns(_n_cols)
        _manual_amounts = {}

        if _input_mode == "amount":
            st.caption(S("p3", "manual_amount_hint", total=_initial_savings_f))
            for _ci, _bname in enumerate(_dyn_bucket_names):
                _bdef_yr = next((d for d in _new_defs if d["name"] == _bname), {})
                _yr_end_lbl = "∞" if _bdef_yr.get("year_end") is None else str(_bdef_yr.get("year_end"))
                _afield = f"inv_manual_alloc_amt_{_bname}"
                with _ma_cols[_ci % _n_cols]:
                    st.number_input(
                        f"{_bname} (บาท)",
                        min_value=0.0,
                        step=10_000.0,
                        format="%.0f",
                        key=_widget_key(_afield),
                        help=f"ปี {_bdef_yr.get('year_start', '?')} – {_yr_end_lbl}",
                        on_change=on_widget_change,
                        args=(_afield, float),
                    )
                _manual_amounts[_bname] = float(
                    st.session_state.get(_widget_key(_afield), 0.0)
                )

        else:  # percent mode
            st.caption(S("p3", "manual_pct_hint", total=_initial_savings_f))
            _pct_vals = {}
            for _ci, _bname in enumerate(_dyn_bucket_names):
                _bdef_yr = next((d for d in _new_defs if d["name"] == _bname), {})
                _yr_end_lbl = "∞" if _bdef_yr.get("year_end") is None else str(_bdef_yr.get("year_end"))
                _pfield = f"inv_manual_alloc_pct_{_bname}"
                with _ma_cols[_ci % _n_cols]:
                    st.number_input(
                        f"{_bname} (%)",
                        min_value=0.0,
                        max_value=100.0,
                        step=1.0,
                        format="%.2f",
                        key=_widget_key(_pfield),
                        help=f"ปี {_bdef_yr.get('year_start', '?')} – {_yr_end_lbl}",
                        on_change=on_widget_change,
                        args=(_pfield, float),
                    )
                _pct_vals[_bname] = float(
                    st.session_state.get(_widget_key(_pfield), 0.0)
                )

            _pct_total = sum(_pct_vals.values())
            _derived_parts = []
            for _bname in _dyn_bucket_names:
                _manual_amounts[_bname] = round(_initial_savings_f * _pct_vals[_bname] / 100, 2)
                _derived_parts.append(f"{_bname} = {_manual_amounts[_bname]:,.0f}")
            st.caption(" | ".join(_derived_parts) + f" | Total = {sum(_manual_amounts.values()):,.0f}")

        _manual_total = sum(_manual_amounts.values())

        # --- validation ---
        if _input_mode == "percent":
            _pct_total = sum(
                float(st.session_state.get(_widget_key(f"inv_manual_alloc_pct_{b}"), 0.0))
                for b in _dyn_bucket_names
            )
            if abs(_pct_total - 100.0) > 0.1:
                st.error(S("p3", "err_manual_pct", total=_pct_total))
                _manual_allocation_valid = False

        if _manual_allocation_valid:
            _validation_errors = validate_manual_allocation(
                manual_amounts=_manual_amounts,
                expected_bucket_names=_dyn_bucket_names,
                initial_savings=_initial_savings_f,
                tolerance=1.0,
            )
            if _validation_errors:
                for _err in _validation_errors:
                    st.error(_err)
                _manual_allocation_valid = False

        if _manual_allocation_valid:
            st.success(S("p3", "manual_valid", total=_manual_total))
            if _allocation_preview_ok and not _preview_requirement_df.empty:
                _manual_allocation_df = create_manual_allocation_df(
                    manual_amounts=_manual_amounts,
                    bucket_requirement_df=_preview_requirement_df,
                )
                st.session_state["_manual_allocation_df_cache"] = _manual_allocation_df

# ============================================================
# SECTION 4: MONTE CARLO RUN CONFIG
# ============================================================
st.subheader(S("p3", "sec4_header"))

with st.container(border=True):
    cc1, _ = st.columns(2)
    with cc1:
        st.number_input(
            S("p3", "label_n_paths"),
            min_value=100,
            max_value=5000,
            step=100,
            key=_widget_key("inv_mc_n_paths"),
            on_change=on_widget_change,
            args=("inv_mc_n_paths", int),
            help=S("p3", "label_n_paths_help"),
        )
    with _:
        _run_mc_disabled = (
            not _bucket_config_valid
            or not _asset_config_valid
            or (_alloc_mode == "manual" and not _manual_allocation_valid)
        )
        st.markdown("<br>", unsafe_allow_html=True)  # spacer to align button with number_input field
        run_mc = st.button(
            S("p3", "btn_run"),
            type="primary",
            width="stretch",
            disabled=_run_mc_disabled,
        )


    with st.expander(S("p3", "advanced_settings_header"), expanded=False):
        _adv1, _adv_div, _adv2 = st.columns([1, 0.3, 2])

        with _adv1:
            st.number_input(
                S("p3", "label_seed"),
                min_value=0,
                step=1,
                key=_widget_key("inv_mc_random_seed"),
                on_change=on_widget_change,
                args=("inv_mc_random_seed", int),
                help=S("p3", "label_seed_help"),
            )

        with _adv2:
            st.markdown("<br>", unsafe_allow_html=True)
            _dc1, _dc2 = st.columns(2)
            with _dc1:
                st.checkbox(
                    S("p3", "label_keep_path"),
                    key=_widget_key("inv_mc_keep_path_detail"),
                    on_change=on_widget_change,
                    args=("inv_mc_keep_path_detail", bool),
                    help=S("p3", "label_keep_path_help"),
                )
            with _dc2:
                st.checkbox(
                    S("p3", "label_keep_asset"),
                    key=_widget_key("inv_mc_keep_asset_detail"),
                    on_change=on_widget_change,
                    args=("inv_mc_keep_asset_detail", bool),
                    help=S("p3", "label_keep_asset_help"),
                )

    # placeholder สำหรับ progress + result — อยู่ใน box เดียวกับ config
    _run_output_placeholder = st.empty()

    # Validation warnings — same box as the button, anchored at the bottom
    if not _bucket_config_valid:
        st.warning(S("p3", "warn_fix_bucket"))
    elif not _asset_config_valid:
        _summary_txt = ", ".join(_asset_errors_summary) if _asset_errors_summary else ""
        st.warning(
            "⚠️ กรุณาแก้ไข asset configuration ก่อน — "
            + (_summary_txt or "ตรวจสอบข้อผิดพลาดในแต่ละ bucket ด้านบน")
        )
    elif _alloc_mode == "manual" and not _manual_allocation_valid:
        st.warning(S("p3", "warn_fix_alloc"))


# ============================================================
# SECTION 5: RUN MONTE CARLO
# ============================================================
if run_mc:
    try:
        bucket_configs = _bucket_configs        # จาก Section 3 (dynamic)
        funding_rule = _funding_rule            # จาก Section 3 (dynamic)
        bucket_return_models = _build_bucket_return_models_from_state()

        # save ไว้เพื่อ diagnostic (แสดงใน debug expander)
        st.session_state["_last_bucket_return_models"] = bucket_return_models

        # A5: read straight from canonical w__{field} widget buffers via draft_get
        mc_config = MonteCarloConfig(
            n_paths=int(draft_get("inv_mc_n_paths", PARAM_DEFAULTS["inv_mc_n_paths"])),
            random_seed=int(draft_get("inv_mc_random_seed", PARAM_DEFAULTS["inv_mc_random_seed"])),
            keep_path_detail=bool(draft_get("inv_mc_keep_path_detail", True)),
            keep_asset_detail=bool(draft_get("inv_mc_keep_asset_detail", False)),
            success_threshold=0.0,
        )

        # Fix 3: ส่ง manual allocation ถ้า user เลือก manual mode
        _alloc_override = None
        if draft_get("inv_allocation_mode", "auto") == "manual":
            _alloc_override = st.session_state.get("_manual_allocation_df_cache")

        with _run_output_placeholder.container():
            progress_bar       = st.progress(0)
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
            initial_allocation_override_df=_alloc_override,
            progress_callback=_mc_progress_callback,
            progress_update_every=10,
        )

        progress_bar.progress(100)
        status_placeholder.markdown(
            f"**Running Monte Carlo:** {int(mc_config.n_paths):,}/{int(mc_config.n_paths):,} ✅"
        )
        result_placeholder.success(S("p3", "sim_success"))

        st.session_state["inv_mc_result"] = mc_result
        st.session_state["inv_mc_analysis"] = analyze_mc_result_local(mc_result)
        st.session_state["inv_investment_sim_done"] = True

        # Persist bucket+asset config keyed by cust_id so it can be reloaded
        # on future visits. Failures are non-fatal — MC results are still valid.
        #
        # IMPORTANT: ใช้ _new_defs โดยตรง (snapshot ที่ build จาก widget ปัจจุบัน
        # ใน rerun นี้) แทนการอ่านจาก st.session_state เพื่อหลีกเลี่ยง stale
        # reference. _new_defs ถูก rebuild ทุก rerun จาก widget values ที่ผู้ใช้
        # พิมพ์จริง (ผ่าน _edited_assets) — เป็น source of truth ที่ใหม่ที่สุด.
        _cust_id_for_save = (draft_get("cust_id", "") or "").strip()
        if _cust_id_for_save:
            try:
                save_bucket_definitions(_cust_id_for_save, _new_defs)
                # แสดงชื่อ asset ที่บันทึกจริง เพื่อให้ผู้ใช้ verify ได้ทันที
                _saved_asset_names = []
                for _bd_save in _new_defs:
                    for _a_save in _bd_save.get("assets", []):
                        _nm_save = str(_a_save.get("asset_name", "")).strip()
                        if _nm_save:
                            _saved_asset_names.append(_nm_save)
                _preview_names = ", ".join(_saved_asset_names[:8])
                if len(_saved_asset_names) > 8:
                    _preview_names += ", ..."
                st.toast(
                    f"💾 บันทึก asset config สำเร็จ: {_preview_names}"
                    if _saved_asset_names else "💾 บันทึก asset config สำเร็จ"
                )
            except Exception as _save_err:
                st.toast(f"⚠️ บันทึก asset config ไม่สำเร็จ: {_save_err}")

    except Exception as e:
        st.session_state["inv_investment_sim_done"] = False
        st.error(S("p3", "sim_failed", error=e))
        st.exception(e)


# ============================================================
# SECTION 6: RESULTS
# ============================================================
if st.session_state.get("inv_investment_sim_done") and st.session_state.get("inv_mc_result") is not None:
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

    st.subheader(S("p3", "sec6_header"))

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

    # ---- Status banner ----
    if not engine_summary_df.empty:
        _row0 = engine_summary_df.iloc[0]
        _success_prob = float(_row0.get("success_probability", 0))
        _sfail_prob = float(_row0.get("shortfall_probability", 0))
        if _success_prob >= 0.80:
            st.success(S("p3", "status_good", prob=_success_prob, sfail=_sfail_prob))
        elif _success_prob >= 0.50:
            st.warning(S("p3", "status_warn", prob=_success_prob, sfail=_sfail_prob))
        else:
            st.error(S("p3", "status_bad", prob=_success_prob, sfail=_sfail_prob))

    # ============================================================
    # DEBUG DIAGNOSTIC
    # ============================================================
    with st.expander(S("p3", "diag_expander"), expanded=False):
        _alloc_df = getattr(mc_result, "initial_allocation_df", pd.DataFrame())

        # --- n_paths / funding check ---
        st.markdown(S("p3", "diag_run_params"))
        _d1, _d2, _d3 = st.columns(3)
        _n_paths_run = int(path_summary_df["path_id"].nunique()) if not path_summary_df.empty else 0
        _d1.metric(S("p3", "diag_n_paths"), _n_paths_run)
        _d2.metric(S("p3", "diag_initial"), _fmt_money(initial_savings))
        _d3.metric(S("p3", "diag_total_exp"), _fmt_money(total_projected_expense))

        # total lifetime contributions = sum ของทุกปีใน annual_contribution_map (ไม่คูณจำนวนปีซ้ำ)
        _lifetime_contrib = float(sum(annual_contribution_map.values())) if annual_contribution_map else 0.0
        _lifetime_topup   = float(sum(annual_topup_map.values()))        if annual_topup_map else 0.0
        _total_inflow     = initial_savings + _lifetime_contrib + _lifetime_topup
        _buffer           = _total_inflow - total_projected_expense
        st.caption(
            f"Lifetime funding check (0% return scenario): "
            f"initial_savings {initial_savings:,.0f} + contributions {_lifetime_contrib:,.0f} "
            f"+ topup {_lifetime_topup:,.0f} = **{_total_inflow:,.0f}** | "
            f"total expenses {total_projected_expense:,.0f} | "
            f"buffer = **{_buffer:,.0f}** ({'surplus ✅' if _buffer >= 0 else 'deficit ⚠️'})"
        )

        # --- Initial allocation ---
        if not _alloc_df.empty and "recommended_initial_amount" in _alloc_df.columns:
            _total_alloc = float(_alloc_df["recommended_initial_amount"].sum())
            _total_unmet = float(_alloc_df["unmet_required_amount"].sum()) if "unmet_required_amount" in _alloc_df.columns else 0.0
            st.caption(f"Initial allocation total = {_total_alloc:,.0f} | Unmet requirement = {_total_unmet:,.0f}")
            st.dataframe(_alloc_df, width="stretch", hide_index=True)

        # --- Actual return models used ---
        _last_models = st.session_state.get("_last_bucket_return_models")
        if _last_models:
            st.markdown(S("p3", "diag_models"))
            st.caption(S("p3", "diag_zero_std_warn"))
            _model_rows = []
            for m in _last_models:
                if m.assets:
                    total_w = sum(a.weight for a in m.assets)
                    for a in m.assets:
                        _model_rows.append({
                            "bucket": m.bucket_name,
                            "asset": a.asset_name,
                            "weight": f"{a.weight / total_w * 100:.1f}%",
                            "mean_return": f"{a.mean_return * 100:.2f}%",
                            "std_dev": f"{a.std_dev * 100:.2f}%",
                            "min_return": f"{a.min_return * 100:.1f}%",
                            "max_return": f"{a.max_return * 100:.1f}%",
                        })
                else:
                    _model_rows.append({
                        "bucket": m.bucket_name,
                        "asset": "(bucket-level)",
                        "weight": "100%",
                        "mean_return": f"{m.mean_return * 100:.2f}%",
                        "std_dev": f"{m.std_dev * 100:.2f}%",
                        "min_return": "-",
                        "max_return": "-",
                    })
            _model_df = pd.DataFrame(_model_rows)
            _has_zero_std = any(
                a.std_dev == 0
                for m in _last_models
                for a in (m.assets if m.assets else [m])
                if hasattr(a, "std_dev")
            )
            if _has_zero_std:
                st.error(S("p3", "diag_zero_std_err"))
            st.dataframe(_model_df, width="stretch", hide_index=True)

        # --- Path balance distribution ---
        if not path_summary_df.empty and "final_total_balance" in path_summary_df.columns:
            _bal = path_summary_df["final_total_balance"].astype(float)
            _n_success = int(path_summary_df["path_success"].sum())
            _n_total   = len(path_summary_df)
            st.markdown(S("p3", "diag_final_dist"))
            st.caption(
                f"min = {_bal.min():,.0f} | p10 = {_bal.quantile(0.10):,.0f} | "
                f"p50 = {_bal.quantile(0.50):,.0f} | p90 = {_bal.quantile(0.90):,.0f} | "
                f"max = {_bal.max():,.0f}"
            )
            _range = _bal.max() - _bal.min()
            if _range < 1:
                st.warning(f"⚠️ Range ของ final_total_balance = {_range:.2f} (แทบไม่มี variance) → std_dev อาจเป็น 0")
            st.caption(f"Paths succeed: {_n_success} / {_n_total} = {_n_success/_n_total:.2%}")

    if not engine_summary_df.empty:
        row = engine_summary_df.iloc[0]

        _first_sf_raw = row.get("first_shortfall_year_mode")
        _first_sf_str = (
            str(int(_first_sf_raw))
            if _first_sf_raw is not None and str(_first_sf_raw) not in ("", "nan", "None")
            else "-"
        )
        _success_pct   = f"{float(row['success_probability']):.1%}"
        _shortfall_pct = f"{float(row['shortfall_probability']):.1%}"
        _p10 = _fmt_money(row["p10_final_total_balance"])
        _p50 = _fmt_money(row["p50_final_total_balance"])
        _p90 = _fmt_money(row["p90_final_total_balance"])

        if not path_summary_df.empty and "final_total_balance" in path_summary_df.columns:
            _bal_series = path_summary_df["final_total_balance"].astype(float)
            _min_bal = _fmt_money(_bal_series.min())
            _max_bal = _fmt_money(_bal_series.max())
        else:
            _min_bal = "-"
            _max_bal = "-"

        with st.container(border=True):
            # ── Row 1: โอกาส + ปีที่มีโอกาสเงินไม่พอสูงสุด ──
            st.caption("📊 โอกาสสำเร็จตามแผน")
            _r1c1, _r1c2, _r1c3 = st.columns(3)
            with _r1c1:
                st.metric(S("p3", "kpi_success_prob"), _success_pct)
            with _r1c2:
                st.metric(S("p3", "kpi_shortfall_prob"), _shortfall_pct)
            with _r1c3:
                st.metric(S("p3", "kpi_first_sf_year"), _first_sf_str,
                        help="ปีที่พบ shortfall บ่อยที่สุดใน simulation")

            st.divider()

            # ── Row 2: Distribution ของเงินคงเหลือ ──
            st.caption("📈 เงินคงเหลือ ณ สิ้นแผน — กระจายตาม simulation")
            _r2c1, _r2c2, _r2c3, _r2c4, _r2c5 = st.columns(5)
            with _r2c1:
                st.metric("เงินคงเหลือ ต่ำสุด", _min_bal, help="เงินคงเหลือต่ำสุดที่พบในทุก simulation")
            with _r2c2:
                st.metric(S("p3", "kpi_p10_balance"), _p10, help="90% ของ simulation ได้มากกว่านี้")
            with _r2c3:
                st.metric(S("p3", "kpi_p50_balance"), _p50, help="ผลลัพธ์ median ของ simulation ทั้งหมด")
            with _r2c4:
                st.metric(S("p3", "kpi_p90_balance"), _p90, help="10% ของ simulation ได้มากกว่านี้")
            with _r2c5:
                st.metric("เงินคงเหลือ สูงสุด", _max_bal, help="เงินคงเหลือสูงสุดที่พบในทุก simulation")

    # ── เงินสะสม + ผลตอบแทน (P50) vs ค่าใช้จ่ายสะสม ──
    # Option A reconciliation: รวมผลตอบแทน P50 จาก MC simulation เข้าไปด้วย
    # เพื่อให้ ส่วนต่าง = P50 ending balance (สอดคล้องกับกราฟ P50 balance ด้านล่าง)
    #
    #   เงินสะสม + ผลตอบแทน (P50)
    #       = beginning_bal + Σ contribution + Σ topup + Σ investment_return (P50)
    #       = P50 total ending balance + Σ expense ที่ใช้ไปแล้ว
    #   ค่าใช้จ่ายสะสม = cumsum ของ inflated expense รายปี
    #   ส่วนต่าง        = เงินสะสม+ผลตอบแทน − ค่าใช้จ่ายสะสม = P50 ending balance
    if (
        saving_df is not None
        and not saving_df.empty
        and {"year", "annual_contribution", "annual_topup", "beginning_bal"}.issubset(saving_df.columns)
        and expense_df is not None
        and not expense_df.empty
        and {"year", "inflated_amount"}.issubset(expense_df.columns)
        and year_summary_df is not None
        and not year_summary_df.empty
        and {"year", "bucket_name", "p50_ending_balance"}.issubset(year_summary_df.columns)
    ):
        # ค่าใช้จ่ายสะสมรายปี (จาก inflated expense — deterministic)
        _se_exp = (
            expense_df.groupby("year", as_index=False)["inflated_amount"]
            .sum()
            .sort_values("year")
        )
        _se_exp["cum_expense"] = _se_exp["inflated_amount"].cumsum()
        _se_exp = _se_exp[["year", "cum_expense"]]

        # P50 total portfolio balance ปลายปี (sum across buckets ของ MC P50)
        _p50_total = (
            year_summary_df.groupby("year", as_index=False)["p50_ending_balance"]
            .sum()
            .rename(columns={"p50_ending_balance": "p50_total_balance"})
            .sort_values("year")
        )

        _se_df = (
            _p50_total.merge(_se_exp, on="year", how="outer")
            .sort_values("year")
            .reset_index(drop=True)
        )
        _se_df["p50_total_balance"] = _se_df["p50_total_balance"].fillna(0.0)
        _se_df["cum_expense"]       = _se_df["cum_expense"].ffill().fillna(0.0)
        # เงินสะสม + ผลตอบแทน (P50) = P50 ending balance + cum_expense
        # → ทำให้ surplus reconcile กับ P50 ending balance พอดี
        _se_df["total_savings"]     = _se_df["p50_total_balance"] + _se_df["cum_expense"]
        _se_df["surplus"]           = _se_df["p50_total_balance"]
        _se_df["year"]              = _se_df["year"].astype(int)

        _SE_SAVINGS = "เงินสะสม + ผลตอบแทน (P50)"
        _SE_EXPENSE = "ค่าใช้จ่ายสะสม"
        _SE_DIFF    = "เงินคงเหลือ (P50)"
        _se_label_map = {
            "total_savings": _SE_SAVINGS,
            "cum_expense":   _SE_EXPENSE,
            "surplus":       _SE_DIFF,
        }
        _se_long = _se_df.melt(
            id_vars="year",
            value_vars=["total_savings", "cum_expense", "surplus"],
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

        st.markdown("#### 💰 เงินสะสม + ผลตอบแทน (P50) vs ค่าใช้จ่ายสะสม")

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
            .mark_text(fontSize=11, fontWeight="bold", dy=-12)
            .encode(
                x=alt.X("year:O"),
                y=alt.Y("value:Q"),
                text=alt.Text("label_text:N"),
                color=alt.condition(
                    "datum.metric == 'surplus' && datum.value < 0",
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
            .mark_text(align="left", dx=8, fontSize=12, fontWeight="bold")
            .encode(
                x=alt.X("year:O"),
                y=alt.Y("value:Q"),
                text=alt.Text("label:N"),
                color=alt.Color("label:N", scale=_se_dark, legend=None),
            )
        )

        st.altair_chart(
            alt.layer(_se_base, _se_value_labels, _se_name_labels).properties(height=380),
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
    _SHOW_SEQUENCE_OF_RETURNS = False

    # Pre-process year_summary_df once — shared by Shortfall (#5) and P50 Balance (#7) charts
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
        chart_df["p50_label"] = chart_df["p50_ending_balance"].apply(_fmt_c)
        chart_df["sf_label"]  = chart_df["shortfall_probability"].apply(lambda x: f"{float(x):.1%}")
    else:
        chart_df = pd.DataFrame()

    # ============================================================
    # CHART 2: Final balance distribution
    # ============================================================
    if not path_summary_df.empty:
        st.markdown(S("p3", "chart_final_dist"))

        # ── pre-compute ─────────────────────────────────────────
        _bal_dist = path_summary_df["final_total_balance"].astype(float)
        _ns = (
            int(path_summary_df["path_success"].sum())
            if "path_success" in path_summary_df.columns
            else int((_bal_dist >= 0).sum())
        )
        _nt   = len(path_summary_df)
        _pct_s = _ns / _nt if _nt > 0 else 0.0
        _p10_v = float(_bal_dist.quantile(0.10))
        _p50_v = float(_bal_dist.quantile(0.50))
        _p90_v = float(_bal_dist.quantile(0.90))
        _min_v = float(_bal_dist.min())

        # ── Headline KPI ─────────────────────────────────────────
        _hl_icon = "✅" if _pct_s >= 0.7 else ("⚠️" if _pct_s >= 0.4 else "🚨")
        st.markdown(
            f"{_hl_icon} **{_pct_s:.0%} ของเส้นทางจำลอง มีเงินเหลือสิ้นแผน** "
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

        # ── เส้น P10 / P50 / P90 ─────────────────────────────────
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
            .mark_text(fontSize=10, fontWeight="bold", color="#a9acb0", angle=0)
            .encode(x="x:Q", y=alt.value(14), text="pctile:N")
        )

        # ── โซนเสี่ยง (ถ้ามี path ติดลบ) ─────────────────────────
        _hist_layers = [_hist_chart, _vlines, _vlabels]
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
                .mark_text(fontSize=12, fontWeight="bold", color="#dc2626")
                .encode(x="x:Q", y=alt.value(32), text=alt.value("⚠ โซนเสี่ยง"))
            )
            _hist_layers = [_red_rect, _hist_chart, _vlines, _vlabels, _zone_ann]

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

            st.markdown(S("p3", "chart_cagr_title"))
            st.caption(S("p3", "chart_cagr_caption"))

            _ck_cols = st.columns(4 if _expected_ret is not None else 3)
            _ck_cols[0].metric(S("p3", "kpi_cagr_p10"), f"{_cagr_p10 * 100:.2f}%")
            _ck_cols[1].metric(
                S("p3", "kpi_cagr_p50"),
                f"{_cagr_p50 * 100:.2f}%",
                delta=(
                    f"{(_cagr_p50 - _expected_ret) * 100:+.2f}%"
                    if _expected_ret is not None else None
                ),
                help=S("p3", "kpi_cagr_p50_help"),
            )
            _ck_cols[2].metric(S("p3", "kpi_cagr_p90"), f"{_cagr_p90 * 100:.2f}%")
            if _expected_ret is not None:
                _ck_cols[3].metric(
                    S("p3", "kpi_cagr_expected"),
                    f"{_expected_ret * 100:.2f}%",
                    help=S("p3", "kpi_cagr_expected_help"),
                )

            _cagr_hist_df = pd.DataFrame({"cagr_pct": _path_cagr.values * 100})
            _cagr_hist = (
                alt.Chart(_cagr_hist_df)
                .mark_bar(opacity=0.75, color="#60a5fa")
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

            _vline_rows = [
                {"x": _cagr_p10 * 100, "label": f"P10: {_cagr_p10 * 100:.2f}%",
                 "color": "#a6acb3"},
                {"x": _cagr_p50 * 100, "label": f"P50: {_cagr_p50 * 100:.2f}%",
                 "color": "#a6acb3"},
                {"x": _cagr_p90 * 100, "label": f"P90: {_cagr_p90 * 100:.2f}%",
                 "color": "#a6acb3"},
            ]
            if _expected_ret is not None:
                _vline_rows.append({
                    "x": _expected_ret * 100,
                    "label": f"คาดหวัง: {_expected_ret * 100:.2f}%",
                    "color": "#ef4444",
                })
            _vlines_df = pd.DataFrame(_vline_rows)
            _vlines_layer = (
                alt.Chart(_vlines_df)
                .mark_rule(strokeDash=[5, 3], strokeWidth=1.5)
                .encode(x="x:Q", color=alt.Color("color:N", scale=None, legend=None))
            )
            _vlabels_layer = (
                alt.Chart(_vlines_df)
                .mark_text(fontSize=10, fontWeight="bold")
                .encode(
                    x="x:Q",
                    y=alt.value(14),
                    text="label:N",
                    color=alt.Color("color:N", scale=None, legend=None),
                )
            )
            st.altair_chart(
                alt.layer(_cagr_hist, _vlines_layer, _vlabels_layer)
                .properties(height=300),
                width="stretch",
            )

    # ============================================================
    # CHART 4: Allocation Evolution (stacked area)
    # ============================================================
    # ── R6: Allocation Evolution Chart (stacked area, P50 per bucket per year) ──
    if not year_summary_df.empty and {"year", "bucket_name", "p50_ending_balance"}.issubset(year_summary_df.columns):
        st.markdown(S("p3", "chart_alloc_title"))
        st.caption(S("p3", "chart_alloc_caption"))

        _alloc_df = year_summary_df[["year", "bucket_name", "p50_ending_balance"]].copy()
        # Clip negative balances → 0 (defensive: balance ไม่ควรติดลบหลัง rebalance)
        _alloc_df["p50_ending_balance"] = _alloc_df["p50_ending_balance"].clip(lower=0)

        # Build complete (year × bucket) grid with explicit 0-fill for liquidated buckets.
        # ป้องกัน Altair interpolate area ของ bucket ที่ rollover แล้วเป็นสามเหลี่ยมข้ามหลายปี
        # (ทำให้กราฟมีพื้นที่ว่างใต้สี — ดูเป็นช่องดำ)
        _all_years = sorted(_alloc_df["year"].unique())
        _all_buckets = [str(d["name"]) for d in _new_defs]
        _grid = pd.MultiIndex.from_product(
            [_all_years, _all_buckets], names=["year", "bucket_name"]
        ).to_frame(index=False)
        _alloc_df = (
            _grid.merge(_alloc_df, on=["year", "bucket_name"], how="left")
            .fillna({"p50_ending_balance": 0.0})
        )
        # B7: ใช้ bucket_name ของผู้ใช้โดยตรง (รองรับชื่อ bucket แบบกำหนดเอง)
        _alloc_df["bucket_th"] = _alloc_df["bucket_name"].astype(str)

        _year_totals = _alloc_df.groupby("year")["p50_ending_balance"].sum().rename("_total")
        _alloc_df = _alloc_df.merge(_year_totals, on="year", how="left")
        # Drop trailing years where portfolio is fully depleted (total = 0 → div-by-zero)
        _alloc_df = _alloc_df[_alloc_df["_total"] > 0].copy()
        _alloc_df["weight_pct"] = (_alloc_df["p50_ending_balance"] / _alloc_df["_total"] * 100).round(1)

        # B7: ใช้ shared _bucket_color_scale ที่ hoist ไว้ด้านบน (สีตรงกับ P50 balance / shortfall)
        _alloc_chart = (
            alt.Chart(_alloc_df)
            .mark_area()
            .encode(
                x=alt.X("year:O", title="ปี"),
                y=alt.Y("weight_pct:Q", stack="normalize", title="สัดส่วน",
                        axis=alt.Axis(format="%")),
                color=alt.Color("bucket_th:N", title="กลุ่มลงทุน",
                    scale=_bucket_color_scale),
                tooltip=[
                    alt.Tooltip("year:O", title="ปี"),
                    alt.Tooltip("bucket_th:N", title="กลุ่มลงทุน"),
                    alt.Tooltip("p50_ending_balance:Q", title="ยอดเงิน P50", format=",.0f"),
                    alt.Tooltip("weight_pct:Q", title="สัดส่วน %", format=".1f"),
                ],
            )
            .properties(height=300)
        )
        st.altair_chart(_alloc_chart, width="stretch")

    # ============================================================
    # CHART 5: Shortfall probability per year (Liquidity bucket)
    # ============================================================
    if not chart_df.empty:
        st.markdown(S("p3", "chart_shortfall"))
        # Liquidity bucket เป็น bucket เดียวที่ shortfall มีความหมายเป็นรายปี —
        # bucket อื่นถูก rebalance / waterfall transfer ทำให้เลขรายปีของพวกมัน
        # ไม่สะท้อนความเสี่ยงจริงของแผน
        _liquidity_name = str(_new_defs[0]["name"]) if _new_defs else None
        _sf_chart_df = (
            chart_df[chart_df["bucket_name"].astype(str) == _liquidity_name].copy()
            if _liquidity_name else chart_df.iloc[0:0]
        )
        if not _sf_chart_df.empty:
            _sf_line = (
                alt.Chart(_sf_chart_df)
                .mark_line(point=True, color="#60a5fa", strokeWidth=2.5)
                .encode(
                    x=alt.X("year:O", title="ปี"),
                    y=alt.Y("shortfall_probability:Q", title="โอกาสเงินไม่พอ",
                            axis=alt.Axis(format="%")),
                    tooltip=[
                        alt.Tooltip("year:O",                   title="ปี"),
                        alt.Tooltip("bucket_th:N",              title="กลุ่มลงทุน"),
                        alt.Tooltip("shortfall_probability:Q",  title="โอกาสเงินไม่พอ", format=".1%"),
                    ],
                )
            )
            _sf_labels = (
                alt.Chart(_sf_chart_df)
                .mark_text(dy=-12, fontSize=11, fontWeight="bold", color="#1d4ed8")
                .encode(
                    x=alt.X("year:O"),
                    y=alt.Y("shortfall_probability:Q"),
                    text=alt.Text("sf_label:N"),
                )
            )
            st.caption(f"แสดงเฉพาะ bucket *{_liquidity_name}* — bucket อื่นถูก rebalance ระหว่างปี ทำให้ shortfall รายปีไม่สะท้อนความเสี่ยงจริง")
            st.altair_chart((_sf_line + _sf_labels).properties(height=320), width="stretch")

    # ============================================================
    # CHART 6: First shortfall year histogram
    # ============================================================
    if not path_summary_df.empty and "first_shortfall_year" in path_summary_df.columns:
        _nt = len(path_summary_df)
        # กรองเฉพาะ path ที่เกิด shortfall จริง (ไม่เอา null)
        _sf_raw = path_summary_df["first_shortfall_year"].dropna()
        shortfall_year_df = (
            _sf_raw
            .value_counts()
            .rename_axis("first_shortfall_year")
            .reset_index(name="n_paths")
        )
        # เรียงตามปีจริง (numeric) แล้วค่อยแปลงเป็น string สำหรับแกน
        shortfall_year_df["first_shortfall_year"] = (
            shortfall_year_df["first_shortfall_year"].astype(float).astype(int)
        )
        shortfall_year_df = shortfall_year_df.sort_values("first_shortfall_year").reset_index(drop=True)
        shortfall_year_df["pct"]       = shortfall_year_df["n_paths"] / _nt
        shortfall_year_df["pct_label"] = shortfall_year_df["pct"].apply(lambda x: f"{x:.1%}")
        shortfall_year_df["year_str"]  = shortfall_year_df["first_shortfall_year"].astype(str)

        _n_sf_paths = int(shortfall_year_df["n_paths"].sum())
        _year_order = shortfall_year_df["year_str"].tolist()

        st.markdown(S("p3", "chart_sf_year"))
        if shortfall_year_df.empty:
            st.success("ไม่มีเส้นทางที่เงินหมดก่อนสิ้นแผน 🎉")
        else:
            st.caption(
                f"แสดงเฉพาะ {_n_sf_paths:,} เส้นทาง ({_n_sf_paths / _nt:.1%}) ที่เกิดเหตุการณ์เงินไม่พอ "
                f"— ป้ายบน bar คือสัดส่วนจากเส้นทางทั้งหมด {_nt:,} เส้นทาง"
            )
            _sf_bars = (
                alt.Chart(shortfall_year_df)
                .mark_bar(color="#f87171", opacity=0.85)
                .encode(
                    x=alt.X(
                        "year_str:N",
                        title="ปีที่เงินหมดครั้งแรก",
                        sort=_year_order,
                    ),
                    y=alt.Y(
                        "pct:Q",
                        title=S("p3", "chart_sf_year_y"),
                        axis=alt.Axis(format="%"),
                    ),
                    tooltip=[
                        alt.Tooltip("year_str:N",  title="ปี"),
                        alt.Tooltip("n_paths:Q",   title="จำนวนเส้นทาง"),
                        alt.Tooltip("pct_label:N", title="โอกาสเงินหมดในปีนี้"),
                    ],
                )
            )
            _sf_labels = (
                alt.Chart(shortfall_year_df)
                .mark_text(dy=-8, fontSize=10, fontWeight="bold", color="#b91c1c")
                .encode(
                    x=alt.X("year_str:N", sort=_year_order),
                    y=alt.Y("pct:Q"),
                    text="pct_label:N",
                )
            )
            st.altair_chart(
                (_sf_bars + _sf_labels).properties(height=320),
                width="stretch",
            )

    # ============================================================
    # HIDDEN: Sequence-of-returns risk (toggle via _SHOW_SEQUENCE_OF_RETURNS)
    # ============================================================
    # ── Sequence-of-returns risk: tercile by dollar-weighted return ใน 3 ปีแรก ──
    # ใช้ beginning_balance เป็น weight เพื่อ factor การย้าย/ถ่ายเงินระหว่าง bucket:
    #   weighted_ret(path) = Σ(beginning_balance × sampled_return) / Σ(beginning_balance)
    # — bucket ที่ balance = 0 (ยังไม่ active หรือถูก transfer ออกหมด) จะไม่มี weight
    # HIDDEN: ซ่อนทั้ง block ชั่วคราว — ยังโหลด _path_detail_df ไว้สำหรับ CAGR ด้านล่าง
    if (
        _SHOW_SEQUENCE_OF_RETURNS
        and _path_detail_df is not None
        and not _path_detail_df.empty
        and {"path_id", "year", "sampled_return", "beginning_balance", "ending_balance"}.issubset(
            _path_detail_df.columns
        )
    ):
        _pd_df = _path_detail_df[
            ["path_id", "year", "sampled_return", "beginning_balance", "ending_balance"]
        ].copy()
        _pd_df["path_id"] = _pd_df["path_id"].astype(int)
        _pd_df["year"] = _pd_df["year"].astype(int)
        _pd_df["sampled_return"] = _pd_df["sampled_return"].astype(float)
        _pd_df["beginning_balance"] = _pd_df["beginning_balance"].astype(float)

        _years_sorted = sorted(_pd_df["year"].unique())
        _first3 = _years_sorted[:3]
        # ต้องมี ≥ 2 ปีต้นและ ≥ 2 paths ที่ไม่ tie กันถึงจะแบ่ง tercile ได้
        if len(_first3) >= 2 and _pd_df["path_id"].nunique() >= 3:
            _early = _pd_df[_pd_df["year"].isin(_first3)].copy()
            # dollar-weighted return: weight by beginning_balance per (path, year, bucket)
            _early["_weighted_ret"] = _early["beginning_balance"] * _early["sampled_return"]
            _agg = _early.groupby("path_id", as_index=True).agg(
                _num=("_weighted_ret", "sum"),
                _den=("beginning_balance", "sum"),
            )
            # path ที่ Σ beginning_balance = 0 ทั้ง 3 ปี (เคสหายาก) → ตัดทิ้ง
            _agg = _agg[_agg["_den"] > 0]
            _path_early_ret = (_agg["_num"] / _agg["_den"]).rename("avg_ret_3y")
            _bad_lbl  = S("p3", "chart_seq_bad")
            _mid_lbl  = S("p3", "chart_seq_mid")
            _good_lbl = S("p3", "chart_seq_good")
            try:
                _terciles = pd.qcut(
                    _path_early_ret,
                    q=3,
                    labels=[_bad_lbl, _mid_lbl, _good_lbl],
                )
            except ValueError:
                _terciles = None

            if _terciles is not None:
                _label_df = pd.DataFrame({
                    "path_id": _path_early_ret.index.astype(int),
                    "tercile": _terciles.astype(str).values,
                })
                _path_year_total = (
                    _pd_df.groupby(["path_id", "year"], as_index=False)[
                        "ending_balance"
                    ]
                    .sum()
                    .rename(columns={"ending_balance": "total_balance"})
                )
                _merged = _path_year_total.merge(_label_df, on="path_id", how="inner")
                _traj = (
                    _merged.groupby(["tercile", "year"], as_index=False)[
                        "total_balance"
                    ]
                    .median()
                )

                st.markdown(S("p3", "chart_seq_risk_title"))
                st.caption(S("p3", "chart_seq_risk_caption"))
                _seq_color_scale = alt.Scale(
                    domain=[_bad_lbl, _mid_lbl, _good_lbl],
                    range=["#ef4444", "#9ca3af", "#10b981"],
                )
                _seq_line = (
                    alt.Chart(_traj)
                    .mark_line(point=True, strokeWidth=2.5)
                    .encode(
                        x=alt.X("year:O", title="ปี"),
                        y=alt.Y(
                            "total_balance:Q",
                            title="ยอดเงินรวมทุก bucket (บาท, median ของแต่ละกลุ่ม)",
                            axis=alt.Axis(format=","),
                        ),
                        color=alt.Color(
                            "tercile:N",
                            title="ผลตอบแทน 3 ปีแรก",
                            scale=_seq_color_scale,
                            sort=[_bad_lbl, _mid_lbl, _good_lbl],
                        ),
                        tooltip=[
                            alt.Tooltip("year:O", title="ปี"),
                            alt.Tooltip("tercile:N", title="กลุ่ม"),
                            alt.Tooltip(
                                "total_balance:Q",
                                title="ยอดเงิน median (บาท)",
                                format=",.0f",
                            ),
                        ],
                    )
                )
                st.altair_chart(
                    _seq_line.properties(height=320),
                    width="stretch",
                )

    # ============================================================
    # CHART 7: P50 ending balance per bucket per year + cumulative expense overlay
    # ============================================================
    if not chart_df.empty:
        st.markdown(S("p3", "chart_p50_balance"))

        _band = (
            alt.Chart(chart_df)
            .mark_area(opacity=0.15)
            .encode(
                x=alt.X("year:O", title="ปี"),
                y=alt.Y("p10_ending_balance:Q", title="ยอดเงินคงเหลือ (บาท)",
                        axis=alt.Axis(format=",")),
                y2=alt.Y2("p90_ending_balance:Q"),
                color=alt.Color("bucket_th:N", scale=_bucket_color_scale, legend=None),
            )
        )
        _line = (
            alt.Chart(chart_df)
            .mark_line(point=True)
            .encode(
                x=alt.X("year:O", title="ปี"),
                y=alt.Y("p50_ending_balance:Q", title="ยอดเงินคงเหลือ (บาท)",
                        axis=alt.Axis(format=",")),
                color=alt.Color("bucket_th:N", scale=_bucket_color_scale, title="กลุ่มลงทุน"),
                tooltip=[
                    alt.Tooltip("year:O",                  title="ปี"),
                    alt.Tooltip("bucket_th:N",             title="กลุ่มลงทุน"),
                    alt.Tooltip("p10_ending_balance:Q",    title="กรณีแย่ (P10)",    format=",.0f"),
                    alt.Tooltip("p50_ending_balance:Q",    title="กรณีกลาง (P50)",   format=",.0f"),
                    alt.Tooltip("p90_ending_balance:Q",    title="กรณีดี (P90)",     format=",.0f"),
                ],
            )
        )
        _line_labels = (
            alt.Chart(chart_df)
            .mark_text(dy=-12, fontSize=11, fontWeight="bold")
            .encode(
                x=alt.X("year:O"),
                y=alt.Y("p50_ending_balance:Q"),
                text=alt.Text("p50_label:N"),
                color=alt.Color("bucket_th:N", scale=_bucket_color_scale, legend=None),
            )
        )

        # ── Cumulative expense overlay (เส้นประรวมค่าใช้จ่ายสะสม) ─────────────
        _cum_overlay = None
        if (
            expense_df is not None
            and not expense_df.empty
            and {"year", "inflated_amount"}.issubset(expense_df.columns)
        ):
            _yearly_exp = (
                expense_df.groupby("year", as_index=False)["inflated_amount"]
                .sum()
                .sort_values("year")
            )
            _yearly_exp["cum_expense"] = _yearly_exp["inflated_amount"].cumsum()
            _yr_min = int(chart_df["year"].min())
            _yr_max = int(chart_df["year"].max())
            _cum_df = _yearly_exp[
                (_yearly_exp["year"] >= _yr_min) & (_yearly_exp["year"] <= _yr_max)
            ].copy()
            if not _cum_df.empty:
                _cum_df["year"] = _cum_df["year"].astype(int)
                _cum_df["cum_label"] = _cum_df["cum_expense"].apply(_fmt_c)
                _cum_overlay = (
                    alt.Chart(_cum_df)
                    .mark_line(
                        strokeDash=[6, 4],
                        color="#374151",
                        strokeWidth=2,
                        point=alt.OverlayMarkDef(color="#374151", size=40),
                    )
                    .encode(
                        x=alt.X("year:O"),
                        y=alt.Y("cum_expense:Q", axis=alt.Axis(format=",")),
                        tooltip=[
                            alt.Tooltip("year:O", title="ปี"),
                            alt.Tooltip(
                                "cum_expense:Q",
                                title=S("p3", "chart_cum_exp_tooltip"),
                                format=",.0f",
                            ),
                        ],
                    )
                )

        _balance_layers = [_band, _line, _line_labels]
        if _cum_overlay is not None:
            _balance_layers.append(_cum_overlay)
            st.caption(S("p3", "chart_cum_exp_caption"))
        st.altair_chart(
            alt.layer(*_balance_layers).properties(height=340),
            width="stretch",
        )

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

else:
    st.info(S("p3", "no_result"))

# ============================================================
# FLUSH: persist all w__{field} widget buffers → draft on every rerun
# Must be at the bottom, after every widget has rendered.
# Fixes: user types value then navigates away without pressing Enter → value lost
# ============================================================
persist_all_widget_buffers()