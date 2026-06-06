"""Section 2: Bucket & Asset Configuration.

Renders the bucket horizon table, per-bucket asset tables, asset performance
preview, and the Set Default reset button. Returns the validated bucket
definitions plus engine-ready configs.
"""

import copy
import streamlit as st
import pandas as pd
import altair as alt

from strings import S, SC
from state import draft_get, draft_set
from portfolio_bucket_engine import BucketFundingRule
from asset_store import (
    has_saved_bucket_definitions,
    get_saved_bucket_meta,
)

from .state import (
    PARAM_DEFAULTS,
    DEFAULT_ASSET as _DEFAULT_ASSET,
    with_min_max as _with_min_max,
    get_bucket_definitions as _get_bucket_definitions,
    build_bucket_configs_from_definitions as _build_bucket_configs_from_definitions,
)


def render() -> dict:
    """Render Section 2 UI and return the result.

    Returns dict with:
      new_defs (list[dict])      : current bucket+asset definitions (validated)
      bucket_configs (list)      : engine BucketConfig list
      funding_rule (BucketFundingRule)
      bucket_config_valid (bool)
      asset_config_valid (bool)
      asset_errors_summary (list[str])
    """
    # ============================================================
    # SECTION 2: BUCKET & ASSET CONFIGURATION
    # ============================================================
    st.subheader(S("p3", "sec2_header"))

    # ---------- Set Default button: reset bucket+asset config to PARAM_DEFAULTS ----------
    _set_default_col, _ = st.columns([1, 3])
    with _set_default_col:
        if st.button("↺ Set Default", key="btn_set_default_bucket_defs",
                     help="คืนค่าตั้งต้นของ bucket และ asset ทั้งหมดจาก PARAM_DEFAULTS",
                     width="stretch"):
            # Wipe stale widget keys so freshly-reset values aren't shadowed by
            # cached widget state (same cleanup as the cust_id-change path).
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
    
            _default_defs = copy.deepcopy(PARAM_DEFAULTS["inv_bucket_definitions"])
            st.session_state["inv_bucket_definitions"] = _default_defs
            draft_set("inv_bucket_definitions", _default_defs)
    
            # Bump render nonce so widget keys regenerate and honor new `value=` defaults
            st.session_state["_p3_render_nonce"] = (
                st.session_state.get("_p3_render_nonce", 0) + 1
            )
            st.toast("↺ คืนค่าตั้งต้นของ bucket และ asset เรียบร้อย")
            st.rerun()
    
    # ---------- Fixed 2-bucket structure (edit name + bucket 1 year_end only) ----------
    _DEFAULT_NEW_ASSETS = [
        _with_min_max({"asset_name": "Asset 1", "weight_pct": 100.0,
                       "mean_pct": 4.0, "std_pct": 8.0})
    ]
    
    _FIXED_BUCKET_TEMPLATE = [
        {"name": "สำหรับค่าใช้จ่าย", "idx": 0},
        {"name": "สำหรับลงทุนเพื่อการศึกษา", "idx": 1},
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
    # Force exactly 2 buckets — no add/remove allowed
    while len(_cur_defs) < 2:
        _cur_defs.append({
            "name": _FIXED_BUCKET_TEMPLATE[len(_cur_defs)]["name"],
            "year_start": 1, "year_end": None, "discount_rate": 0.04,
            "assets": _DEFAULT_NEW_ASSETS.copy(),
        })
    if len(_cur_defs) > 2:
        _cur_defs = _cur_defs[:2]
    
    # Seed sane default for first-render: bucket0 ends year 2
    if _cur_defs[0].get("year_end") is None:
        _cur_defs[0]["year_end"] = 2
    
    _new_defs = []
    # Nonce suffix for widget keys: bumped on LOAD button so Streamlit's widget
    # tracker sees brand-new keys and honors the freshly-loaded `value=` defaults.
    _nonce = st.session_state.get("_p3_render_nonce", 0)
    st.markdown(S("p3", "bucket_tbl_header"))
    st.caption(
        "กำหนดปีที่จะครอบคลุมค่าใช้จ่ายที่จะมาถึง เช่น Bucket สำหรับค่าใช้จ่าย "
        "ปีเริ่ม 1 ปีสิ้นสุด 2 หมายถึง จะกันเงินเผื่อสำหรับค่าใช้จ่ายที่จะมาถึง "
        "ใน 2 ปีข้างหน้าในทุกๆปี"
    )
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
                value=_cur_defs[0].get("name", "สำหรับค่าใช้จ่าย"),
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
            _b0_end_default = int(_cur_defs[0].get("year_end", 2) or 2)
            _b0_end_default = max(1, min(10, _b0_end_default))
            _b0_end = st.number_input(
                "ปีสิ้นสุด",
                value=_b0_end_default,
                min_value=1, max_value=10, step=1,
                key=f"bucket_year_end_0_v{_nonce}",
                label_visibility="collapsed",
            )
    
        # ── Bucket 1 — year_start auto-derived (LOCKED), year_end LOCKED = ∞ ──
        _b1_start = int(_b0_end) + 1
        # Force-refresh disabled display so bucket 2's start tracks bucket 1's end
        st.session_state[f"bucket_year_start_ro_1_v{_nonce}"] = str(_b1_start)
        _bc1, _bc2, _bc3 = st.columns([2, 1, 1])
        with _bc1:
            _b1_name = st.text_input(
                S("p3", "col_bucket_name"),
                value=_cur_defs[1].get("name", "สำหรับลงทุนเพื่อการศึกษา"),
                key=f"bucket_name_1_v{_nonce}",
                label_visibility="collapsed",
            )
        with _bc2:
            st.text_input(
                S("p3", "col_year_start"),
                disabled=True,
                key=f"bucket_year_start_ro_1_v{_nonce}",
                label_visibility="collapsed",
            )
        with _bc3:
            st.text_input(
                "ปีสิ้นสุด",
                value="∞",
                disabled=True,
                key=f"bucket_year_end_inf_1_v{_nonce}",
                label_visibility="collapsed",
            )
    
        # Build _new_defs (no overlap by construction — year_starts derived)
        _new_defs.append({
            "name": (str(_b0_name).strip() or "สำหรับค่าใช้จ่าย"),
            "year_start": 1,
            "year_end": int(_b0_end),
            "discount_rate": _cur_defs[0].get("discount_rate", 0.02),
            "assets": _cur_defs[0].get("assets", _DEFAULT_NEW_ASSETS.copy()),
        })
        _new_defs.append({
            "name": (str(_b1_name).strip() or "สำหรับลงทุนเพื่อการศึกษา"),
            "year_start": _b1_start,
            "year_end": None,
            "discount_rate": _cur_defs[1].get("discount_rate", 0.04),
            "assets": _cur_defs[1].get("assets", _DEFAULT_NEW_ASSETS.copy()),
        })
    
        # ── Validation (only need to check duplicate names — year ranges are
        # overlap-free by construction since year_starts are derived) ──
        _bucket_names = [d["name"] for d in _new_defs]
        _bucket_errors = []
        if len(set(_bucket_names)) != 2:
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
                f"{_summary_parts[-1]} (ปรับสัดส่วนเป้าหมายใหม่ทุกปีตามแผนรายจ่ายที่เหลือ)"
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
    
        with st.expander(_bdef_label, expanded=True):
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

            # ── Column headers (5 cols: name | weight | mean | std | delete) ──
            # Min/Max columns hidden — auto-derived as mean ± 4*std
            _COL_RATIOS = [2, 1, 1, 1, 0.5]
            _ah0, _ah1, _ah2, _ah3, _ah4 = st.columns(_COL_RATIOS)
            _ah0.caption(S("p3", "col_asset_name"))
            _ah1.caption(S("p3", "col_weight"))
            _ah2.caption(S("p3", "col_mean_return"))
            _ah3.caption(S("p3", "col_std"))
            _ah4.caption(" ")   # spacer for delete-button column

            # ── Per-row inputs (+ per-row delete button) ──
            _edited_assets = []
            for _ai, _a in enumerate(_cur_assets):
                _ac0, _ac1, _ac2, _ac3, _ac4 = st.columns(_COL_RATIOS)
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
                    # Per-asset delete button: bumps render nonce so all
                    # remaining asset widgets regenerate keys and reload from
                    # the freshly-trimmed list (otherwise Streamlit widget
                    # tracker would shadow the new values).
                    if st.button(
                        "🗑",
                        key=f"btn_del_asset_{_bi}_{_ai}_v{_nonce}",
                        help="ลบ asset นี้",
                        disabled=_n_cur <= 1,
                        width="stretch",
                    ):
                        _tmp = st.session_state.get("inv_bucket_definitions", [])
                        if _bi < len(_tmp) and len(_tmp[_bi]["assets"]) > 1:
                            _tmp[_bi]["assets"] = [
                                _aa for _aj, _aa in enumerate(_cur_assets) if _aj != _ai
                            ]
                            st.session_state["inv_bucket_definitions"] = _tmp
                            draft_set("inv_bucket_definitions", _tmp)
                            st.session_state["_p3_render_nonce"] = (
                                st.session_state.get("_p3_render_nonce", 0) + 1
                            )
                            st.rerun()
                # Auto-derive min/max as mean ± 4σ (99.99% coverage for normal dist)
                _a_min = float(_a_mean) - 4.0 * float(_a_std)
                _a_max = float(_a_mean) + 4.0 * float(_a_std)
                _edited_assets.append({
                    "asset_name": _a_name,
                    "weight_pct": float(_a_w),
                    "mean_pct":   float(_a_mean),
                    "std_pct":    float(_a_std),
                    "min_pct":    _a_min,
                    "max_pct":    _a_max,
                })

            # ── Add asset button (bottom) ──
            _add_col, _ = st.columns([1, 4])
            with _add_col:
                if st.button(SC("btn_add"), key=f"btn_add_asset_bottom_{_bi}",
                             width="stretch"):
                    _tmp = st.session_state.get("inv_bucket_definitions", [])
                    if _bi < len(_tmp):
                        _tmp[_bi]["assets"] = list(_cur_assets) + [_DEFAULT_ASSET.copy()]
                    st.session_state["inv_bucket_definitions"] = _tmp
                    draft_set("inv_bucket_definitions", _tmp)
                    st.session_state["_p3_render_nonce"] = (
                        st.session_state.get("_p3_render_nonce", 0) + 1
                    )
                    st.rerun()
    
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
                    if not _nm:
                        _errors_a.append(f"พบ asset ที่ยังไม่ได้ตั้งชื่อ (weight {float(_a2['weight_pct']):.1f}%)")
                    if _mean < 0:
                        _errors_a.append(f"'{_nm or '(no name)'}': {S('p3', 'col_mean_return')} ต้องไม่น้อยกว่า 0%")
                    if _std < 0:
                        _errors_a.append(f"'{_nm or '(no name)'}': Std Dev ต้องไม่ติดลบ")
            # WARNING
            for _a2 in _va:
                _nm = str(_a2.get("asset_name", "")).strip() or "(no name)"
                _std = float(_a2["std_pct"])
                if _std == 0:
                    _warns_a.append(f"'{_nm}': Std Dev = 0 — risk-free ไม่มีความเสี่ยง")
                elif _std > 50:
                    _warns_a.append(f"'{_nm}': Std Dev = {_std:.1f}% สูงผิดปกติ ลองตรวจสอบอีกครั้ง")
    
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
    
    # ---- Asset Performance Preview (hidden — flip flag below to re-enable) ----
    if False:  # was: with st.expander(S("p3", "preview_expander"), expanded=False):
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
    

    return {
        "new_defs": _new_defs,
        "bucket_configs": _bucket_configs,
        "funding_rule": _funding_rule,
        "bucket_config_valid": _bucket_config_valid,
        "asset_config_valid": _asset_config_valid,
        "asset_errors_summary": _asset_errors_summary,
    }
