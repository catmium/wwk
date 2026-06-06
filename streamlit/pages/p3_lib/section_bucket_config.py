"""Section 2: Bucket & Asset Configuration.

Renders the bucket horizon table, per-bucket asset tables, asset performance
preview, and the Set Default reset button. Returns the validated bucket
definitions plus engine-ready configs.
"""

import copy
import streamlit as st
import pandas as pd
import altair as alt

from strings import S, SC, edu_level_label
from state import draft_get, draft_set
from portfolio_bucket_engine import BucketFundingRule
from portfolio_bucket_engine_mc import TermAssetConfig
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
                    or _k.startswith("term_")
                )
            ]
            for _k in _stale_widget_keys:
                del st.session_state[_k]

            _default_defs = copy.deepcopy(PARAM_DEFAULTS["inv_bucket_definitions"])
            st.session_state["inv_bucket_definitions"] = _default_defs
            draft_set("inv_bucket_definitions", _default_defs)

            # Term assets are optional and have no PARAM_DEFAULTS entry — reset to empty.
            st.session_state["inv_term_asset_defs"] = []
            st.session_state["inv_term_assets"] = []
            draft_set("inv_term_asset_defs", [])
    
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
    
    # Seed sane default for first-render: short bucket reserves 1 year ahead
    if _cur_defs[0].get("year_end") is None:
        _cur_defs[0]["year_end"] = 1
    
    _new_defs = []
    # Nonce suffix for widget keys: bumped on LOAD button so Streamlit's widget
    # tracker sees brand-new keys and honors the freshly-loaded `value=` defaults.
    _nonce = st.session_state.get("_p3_render_nonce", 0)
    st.markdown(S("p3", "bucket_tbl_header"))
    st.caption(
        "กำหนดจำนวนปีที่จะเผื่อเงินสำหรับค่าใช้จ่ายที่จะมาถึงล่วงหน้า เช่น ตั้งค่า 1 ปี "
        "หมายถึง จะกันเงินเผื่อสำหรับค่าใช้จ่ายที่จะมาถึงใน 1 ปีข้างหน้าในทุกๆปี"
    )
    # Bucket names are FIXED (non-editable) and not displayed — the user only
    # sets the short bucket's look-ahead window; the long bucket absorbs the rest.
    _b0_name = str(_cur_defs[0].get("name", "สำหรับค่าใช้จ่าย")).strip() or "สำหรับค่าใช้จ่าย"
    _b1_name = str(_cur_defs[1].get("name", "สำหรับลงทุนเพื่อการศึกษา")).strip() or "สำหรับลงทุนเพื่อการศึกษา"

    # Single visible input: how many years of upcoming expenses the short
    # bucket reserves for (default 1). The long bucket covers the remainder.
    _b0_end_default = int(_cur_defs[0].get("year_end", 1) or 1)
    _b0_end_default = max(1, min(10, _b0_end_default))
    _b0_in_col, _ = st.columns([1, 2])
    with _b0_in_col:
        _b0_end = st.number_input(
            "เผื่อค่าใช้จ่ายล่วงหน้า (ปี)",
            value=_b0_end_default,
            min_value=1, max_value=10, step=1,
            key=f"bucket_year_end_0_v{_nonce}",
        )
    _b1_start = int(_b0_end) + 1

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

    # ── Validation (duplicate names — year ranges overlap-free by construction) ──
    _bucket_names = [d["name"] for d in _new_defs]
    _bucket_errors = []
    if len(set(_bucket_names)) != 2:
        _bucket_errors.append(S("p3", "err_bucket_dup"))
    _bucket_config_valid = len(_bucket_errors) == 0
    if _bucket_errors:
        for _err in _bucket_errors:
            st.error(_err)
    
    # ---------- Asset definition tables (per bucket) ----------
    st.markdown(S("p3", "asset_tbl_header"))
    
    # Track per-bucket asset validation. If any bucket fails, the Simulate
    # button is disabled below. _asset_errors_summary holds short per-bucket
    # labels used in the bottom warning.
    _asset_config_valid = True
    _asset_errors_summary: list = []
    
    for _bi, _bdef in enumerate(_new_defs):
        _bname = _bdef["name"]
        if _bi == 0:
            # Short bucket: title spells out the look-ahead window (x years).
            _bdef_label = (
                f"{_bname} (เผื่อเงินสำหรับค่าใช้จ่าย {int(_bdef['year_end'])} ปีล่วงหน้า ในทุกๆปี)"
            )
        else:
            # Long bucket: name only — no year-range parentheses.
            _bdef_label = str(_bname)

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

    # ============================================================
    # TERM ASSETS (optional) — สินทรัพย์แบบมี term ใต้ long bucket
    # ============================================================
    # Term money is a SIDECAR ledger drawn from / paid back to the LONG bucket.
    # Optional: starts empty, so the engine behaves exactly as before until the
    # user adds one. Editable raw dicts live in inv_term_asset_defs (draft-backed);
    # the engine-ready List[TermAssetConfig] is rebuilt into inv_term_assets here.
    with st.expander("สำหรับลงทุนสินทรัพย์แบบมีกำหนดระยะเวลา", expanded=bool(
        st.session_state.get("inv_term_asset_defs")
        or draft_get("inv_term_asset_defs", [])
    )):
        st.caption(
            "สินทรัพย์ที่ล็อกเงินก้อนไว้จนครบกำหนด เช่น Term Deposit, Structured Note, "
            "Term Fund — เงินที่ใช้ลงทุนหักจากเงินหลังเผื่อค่าใช้จ่าย หากเงินไม่พอจะไม่ซื้อ "
            "(สามารถต่ออายุได้ตามจำนวนครั้งที่กำหนด)"
        )

        # Planning chart placeholder — created here (right after the caption)
        # but filled at the end of this section, once each term asset's live
        # values have been collected into _edited_terms.
        _term_chart_ph = st.empty()

        # buy_year offset (1-indexed from plan start) → absolute year for the engine
        _assumptions_obj = st.session_state.get("assumptions_obj")
        _term_start_year = int(getattr(_assumptions_obj, "start_year", 0) or 0)

        # Plan years the customer can invest in (absolute), derived from the
        # customer's expense plan. Falls back to a 30-year window from the plan
        # start when the expense plan isn't available yet.
        _term_expense_df = st.session_state.get("expense_df")
        if (
            _term_expense_df is not None
            and not _term_expense_df.empty
            and "year" in _term_expense_df.columns
        ):
            _plan_years = list(range(
                int(_term_expense_df["year"].min()),
                int(_term_expense_df["year"].max()) + 1,
            ))
        elif _term_start_year > 0:
            _plan_years = list(range(_term_start_year, _term_start_year + 30))
        else:
            _plan_years = []

        # Last year that actually has an expense. A term asset maturing AFTER
        # this can never fund an expense → its purchase would be wasted, so we
        # block the simulation when that happens.
        _last_expense_year = (
            int(_term_expense_df["year"].max())
            if (
                _term_expense_df is not None
                and not _term_expense_df.empty
                and "year" in _term_expense_df.columns
            )
            else None
        )

        _DIST_LABELS = {
            "fixed": "คงที่ (การันตีเงินต้น)",
            "student_t": "ผันผวนตาม NAV",
        }
        _DIST_KEYS = ["fixed", "student_t"]

        _DEFAULT_TERM = {
            "name": "Term Asset",
            "buy_year_offset": 1,
            "term_years": 5,
            "min_initial_investment": 1_000_000.0,
            "max_rollovers": 0,
            "mean_pct": 3.0,
            "std_pct": 0.0,
            "distribution": "fixed",
        }

        # Hydrate editable term defs from session/draft (optional → default empty)
        _cur_terms = st.session_state.get("inv_term_asset_defs")
        if not isinstance(_cur_terms, list):
            _cur_terms = draft_get("inv_term_asset_defs", []) or []
        if not isinstance(_cur_terms, list):
            _cur_terms = []

        _edited_terms = []
        _term_errors = []

        if not _cur_terms:
            st.info("ℹ️ ยังไม่มี term asset — กดปุ่มด้านล่างเพื่อเพิ่ม (ไม่บังคับ)")

        for _ti, _t in enumerate(_cur_terms):
            with st.container(border=True):
                _t_show = st.checkbox(
                    "แสดงสินทรัพย์ในกราฟ",
                    value=bool(_t.get("show_in_chart", True)),
                    key=f"term_{_ti}_show_v{_nonce}",
                )
                # ── Row 1: name | buy-year (dropdown) | term years | rollovers | delete ──
                _tc0, _tc1, _tc2, _tc3, _tc4 = st.columns([2, 1, 1, 1, 0.5])
                with _tc0:
                    _t_name = st.text_input(
                        "ชื่อ Term Asset",
                        value=str(_t.get("name", "Term Asset")),
                        key=f"term_{_ti}_name_v{_nonce}",
                    )
                with _tc1:
                    if _plan_years:
                        # Absolute-year dropdown — single-select the year to invest.
                        _cur_off = int(_t.get("buy_year_offset", 1) or 1)
                        _cur_buy_year = _term_start_year + _cur_off - 1
                        _by_index = (
                            _plan_years.index(_cur_buy_year)
                            if _cur_buy_year in _plan_years else 0
                        )
                        _t_buy_year_sel = st.selectbox(
                            "ปีที่ต้องการลงทุน",
                            options=_plan_years,
                            index=_by_index,
                            key=f"term_{_ti}_buyyear_v{_nonce}",
                        )
                        _t_buy_off = int(_t_buy_year_sel) - _term_start_year + 1
                    else:
                        _t_buy_off = st.number_input(
                            "ปีที่ซื้อ (นับจากปีเริ่ม)",
                            value=int(_t.get("buy_year_offset", 1) or 1),
                            min_value=1, max_value=50, step=1,
                            key=f"term_{_ti}_buyoff_v{_nonce}",
                        )
                with _tc2:
                    _t_term_yrs = st.number_input(
                        "ระยะเวลา (ปี)",
                        value=int(_t.get("term_years", 5) or 5),
                        min_value=1, max_value=50, step=1,
                        key=f"term_{_ti}_termyrs_v{_nonce}",
                    )
                with _tc3:
                    _t_rollovers = st.number_input(
                        "ต่ออายุ (ครั้ง)",
                        value=int(_t.get("max_rollovers", 0) or 0),
                        min_value=0, max_value=20, step=1,
                        key=f"term_{_ti}_rollovers_v{_nonce}",
                    )
                with _tc4:
                    # Spacer lowers the delete button so it lines up with the
                    # input boxes (which each carry a label line above them).
                    st.markdown(
                        "<div style='height:1.8em'></div>",
                        unsafe_allow_html=True,
                    )
                    if st.button(
                        "🗑",
                        key=f"term_del_{_ti}_v{_nonce}",
                        help="ลบ term asset นี้",
                        width="stretch",
                    ):
                        _tmp_terms = [
                            _tt for _tj, _tt in enumerate(_cur_terms) if _tj != _ti
                        ]
                        st.session_state["inv_term_asset_defs"] = _tmp_terms
                        draft_set("inv_term_asset_defs", _tmp_terms)
                        st.session_state["_p3_render_nonce"] = (
                            st.session_state.get("_p3_render_nonce", 0) + 1
                        )
                        st.rerun()

                # ── Row 2: distribution | investment amount | mean | std ──
                _td0, _td1, _td2, _td3 = st.columns([1.5, 1.5, 1, 1])
                with _td0:
                    _t_dist_default = str(_t.get("distribution", "fixed"))
                    if _t_dist_default not in _DIST_KEYS:
                        _t_dist_default = "fixed"
                    _t_dist = st.selectbox(
                        "ประเภทผลตอบแทน",
                        options=_DIST_KEYS,
                        index=_DIST_KEYS.index(_t_dist_default),
                        format_func=lambda k: _DIST_LABELS.get(k, k),
                        key=f"term_{_ti}_dist_v{_nonce}",
                    )
                with _td1:
                    _t_min_inv = st.number_input(
                        "เงินลงทุน",
                        value=int(_t.get("min_initial_investment", 1_000_000) or 0),
                        min_value=0, step=100_000, format="%d",
                        key=f"term_{_ti}_mininv_v{_nonce}",
                    )
                with _td2:
                    _t_mean = st.number_input(
                        "ผลตอบแทนเฉลี่ย %",
                        value=float(_t.get("mean_pct", 3.0) or 0.0),
                        min_value=0.0, max_value=100.0, step=0.5, format="%.2f",
                        key=f"term_{_ti}_mean_v{_nonce}",
                    )
                with _td3:
                    _is_fixed = (_t_dist == "fixed")
                    _t_std = st.number_input(
                        "ความเสี่ยง (Std) %",
                        value=(0.0 if _is_fixed else float(_t.get("std_pct", 0.0) or 0.0)),
                        min_value=0.0, max_value=100.0, step=0.5, format="%.2f",
                        disabled=_is_fixed,
                        help=("คงที่ → ไม่มีความผันผวน (Std = 0)" if _is_fixed else None),
                        key=f"term_{_ti}_std_v{_nonce}",
                    )

                # fixed → force std to 0 (validate_term_assets requires std_dev==0)
                if _t_dist == "fixed":
                    _t_std = 0.0

                _edited_terms.append({
                    "name": str(_t_name).strip(),
                    "buy_year_offset": int(_t_buy_off),
                    "term_years": int(_t_term_yrs),
                    "min_initial_investment": float(_t_min_inv),
                    "max_rollovers": int(_t_rollovers),
                    "mean_pct": float(_t_mean),
                    "std_pct": float(_t_std),
                    "distribution": str(_t_dist),
                    "show_in_chart": bool(_t_show),
                })

        # ── Add term asset button ──
        _term_add_col, _ = st.columns([1, 4])
        with _term_add_col:
            if st.button("➕ เพิ่ม Term Asset", key="btn_add_term_asset",
                         width="stretch"):
                _tmp_terms = list(_cur_terms) + [copy.deepcopy(_DEFAULT_TERM)]
                st.session_state["inv_term_asset_defs"] = _tmp_terms
                draft_set("inv_term_asset_defs", _tmp_terms)
                st.session_state["_p3_render_nonce"] = (
                    st.session_state.get("_p3_render_nonce", 0) + 1
                )
                st.rerun()

        # ── Validation (names non-empty + unique, investment > 0) ──
        _seen_term_names: dict = {}
        for _et in _edited_terms:
            _tnm = _et["name"].strip()
            if not _tnm:
                _term_errors.append("พบ term asset ที่ยังไม่ได้ตั้งชื่อ")
            else:
                _lc = _tnm.lower()
                _seen_term_names[_lc] = _seen_term_names.get(_lc, 0) + 1
            if _et["min_initial_investment"] <= 0:
                _term_errors.append(
                    f"'{_tnm or '(no name)'}': เงินลงทุนต้องมากกว่า 0"
                )
            # Usable year (engine timing): the matured lump is withdrawn in a
            # dedicated payout year = buy + term*(rollovers+1). If that year lands
            # AFTER the last expense year, the cash can never fund an expense →
            # block the run with a clear warning.
            _buy_year_abs = _term_start_year + int(_et["buy_year_offset"]) - 1
            _maturity_year = (
                _buy_year_abs
                + int(_et["term_years"]) * (int(_et["max_rollovers"]) + 1)
            )
            if _last_expense_year is not None and _maturity_year > _last_expense_year:
                _term_errors.append(
                    f"'{_tnm or '(no name)'}': สินทรัพย์ครบกำหนดหลังปีสุดท้ายที่มีค่าใช้จ่าย"
                )
        _dup_term = [n for n, c in _seen_term_names.items() if c > 1]
        if _dup_term:
            _term_errors.append(f"ชื่อ term asset ซ้ำ: {', '.join(_dup_term)}")

        for _te in _term_errors:
            st.error(_te)

        # Term errors must block the run — fold into the asset-config gate
        # that the Simulate button already checks.
        if _term_errors:
            _asset_config_valid = False
            _asset_errors_summary.append(
                f"Term asset ({len(_term_errors)} ข้อผิดพลาด)"
            )

        # ── Planning chart: yearly expense vs each term asset's deterministic
        # value trajectory (filled into the placeholder above the input rows) ──
        with _term_chart_ph.container():
            # ── Education timeline (year span per child × education level) ──
            # Mirrors the result-page Chart-6 timeline so the user can see when
            # each child is in each level while planning term assets.
            st.caption("ช่วงปีที่ลูกแต่ละคนอยู่ในแต่ละระดับการศึกษา")
            if (
                _term_expense_df is not None
                and not _term_expense_df.empty
                and {"year", "child_name", "category", "sub_category"}.issubset(
                    _term_expense_df.columns
                )
            ):
                _edu_mask_t = (
                    _term_expense_df["category"].astype(str).str.endswith(" education")
                    & (_term_expense_df["child_name"].astype(str) != "Parent")
                )
                _edu_src_t = _term_expense_df[_edu_mask_t].copy()
                if not _edu_src_t.empty:
                    _agg_t = {
                        "year_start": ("year", "min"),
                        "year_end": ("year", "max"),
                        "avg_inflated": ("inflated_amount", "mean"),
                        "total_inflated": ("inflated_amount", "sum"),
                    }
                    if "child_age" in _edu_src_t.columns:
                        _agg_t["age_start"] = ("child_age", "min")
                        _agg_t["age_end"] = ("child_age", "max")
                    _tl_t = (
                        _edu_src_t.groupby(["child_name", "sub_category"], as_index=False)
                        .agg(**_agg_t)
                    )
                    _tl_t["year_start"] = _tl_t["year_start"].astype(int)
                    _tl_t["year_end"] = _tl_t["year_end"].astype(int)
                    _tl_t["year_end_excl"] = _tl_t["year_end"] + 1
                    # Include the child's OTHER (non-education) expenses inside
                    # each level's window, attributed by year. Parent excluded.
                    _np_tlt = _term_expense_df[_term_expense_df["child_name"].astype(str) != "Parent"]
                    _cy_tlt = (
                        _np_tlt.groupby(["child_name", "year"])["inflated_amount"].sum()
                        if not _np_tlt.empty else pd.Series(dtype=float)
                    )
                    _tl_t["total_inflated"] = _tl_t.apply(
                        lambda r: float(sum(
                            float(_cy_tlt.get((str(r["child_name"]), _yy), 0.0))
                            for _yy in range(int(r["year_start"]), int(r["year_end"]) + 1)
                        )),
                        axis=1,
                    )
                    _tl_t["avg_inflated"] = _tl_t["total_inflated"] / (
                        _tl_t["year_end"].astype(int) - _tl_t["year_start"].astype(int) + 1
                    ).clip(lower=1)
                    _tl_t["_mid"] = (_tl_t["year_start"] + _tl_t["year_end_excl"]) / 2.0
                    _tl_t["_total_label"] = _tl_t["total_inflated"].apply(
                        lambda v: f"{float(v) / 1e6:.1f}M" if abs(float(v)) >= 1e6
                        else (f"{float(v) / 1e3:.0f}K" if abs(float(v)) >= 1e3 else f"{float(v):.0f}")
                    )
                    _tl_t["ระดับ"] = _tl_t["sub_category"].astype(str).apply(edu_level_label)
                    _lvl_keys_t = [
                        "kindergarten", "elementary", "middle_school", "high_school",
                        "bachelor", "master", "doctor", "other",
                    ]
                    _lvl_order_t = [edu_level_label(_k) for _k in _lvl_keys_t]
                    _present_t = [_l for _l in _lvl_order_t if _l in _tl_t["ระดับ"].unique()]
                    for _l in _tl_t["ระดับ"].unique():
                        if _l not in _present_t:
                            _present_t.append(_l)
                    _tt_t = [
                        alt.Tooltip("child_name:N", title="ลูก"),
                        alt.Tooltip("ระดับ:N", title="ระดับ"),
                        alt.Tooltip("year_start:Q", title="ปีเริ่ม", format="d"),
                        alt.Tooltip("year_end:Q", title="ปีจบ", format="d"),
                        alt.Tooltip("avg_inflated:Q", title="ค่าใช้จ่ายเฉลี่ย/ปี (฿)", format=",.0f"),
                        alt.Tooltip("total_inflated:Q", title="ค่าใช้จ่ายรวม (฿)", format=",.0f"),
                    ]
                    if "age_start" in _tl_t.columns:
                        _tt_t.insert(3, alt.Tooltip("age_start:Q", title="อายุเริ่ม", format="d"))
                        _tt_t.insert(4, alt.Tooltip("age_end:Q", title="อายุจบ", format="d"))
                    _n_child_t = _tl_t["child_name"].nunique()
                    _tl_chart_t = (
                        alt.Chart(_tl_t)
                        .mark_bar(cornerRadius=4, opacity=0.85)
                        .encode(
                            x=alt.X(
                                "year_start:Q", title="ปี", scale=alt.Scale(zero=False),
                                axis=alt.Axis(format="d", tickMinStep=1),
                            ),
                            x2=alt.X2("year_end_excl:Q"),
                            y=alt.Y("child_name:N", title="ลูก", sort=None),
                            color=alt.Color("ระดับ:N", title="ระดับการศึกษา", sort=_present_t),
                            tooltip=_tt_t,
                        )
                        .properties(height=max(70 * max(_n_child_t, 1), 160))
                    )
                    _tl_labels_t = (
                        alt.Chart(_tl_t)
                        .mark_text(fontSize=18, fontWeight="bold", color="#1f2937")
                        .encode(
                            x=alt.X("_mid:Q"),
                            y=alt.Y("child_name:N", sort=None),
                            text=alt.Text("_total_label:N"),
                            tooltip=_tt_t,
                        )
                    )
                    st.altair_chart(_tl_chart_t + _tl_labels_t, width="stretch")
                else:
                    st.info("ไม่มีค่าใช้จ่ายการศึกษาในแผนนี้")
            else:
                st.info("ไม่มีข้อมูลค่าใช้จ่ายสำหรับสร้าง timeline")

            if (
                _term_expense_df is not None
                and not _term_expense_df.empty
                and "year" in _term_expense_df.columns
                and "inflated_amount" in _term_expense_df.columns
            ):
                import re as _re_term

                _ce = _term_expense_df.copy()
                _ce["year"] = pd.to_numeric(_ce["year"], errors="coerce")
                _ce["inflated_amount"] = pd.to_numeric(
                    _ce["inflated_amount"], errors="coerce"
                ).fillna(0.0)
                _ce = _ce.dropna(subset=["year"])
                _ce["year"] = _ce["year"].astype(int)

                # child filter: ทั้งหมด / Child 1 / Child 2 / ...
                _ALL_LBL = "ทั้งหมด"
                if "child_name" in _ce.columns:
                    _cnames = _ce["child_name"].dropna().astype(str).unique().tolist()

                    def _csort(n):
                        _m = _re_term.search(r"(\d+)", n)
                        if n.startswith("Child") and _m:
                            return (0, int(_m.group(1)), n)
                        return (1, 0, n)

                    _cnames = sorted(_cnames, key=_csort)
                    _copts = [_ALL_LBL] + _cnames
                    if len(_copts) > 1:
                        _cpick = st.radio(
                            "เลือกดูค่าใช้จ่าย",
                            options=_copts,
                            index=0,
                            horizontal=True,
                            key=f"term_expense_child_filter_v{_nonce}",
                        )
                        if _cpick != _ALL_LBL:
                            _ce = _ce[_ce["child_name"].astype(str) == _cpick]

                _exp_year = (
                    _ce.groupby("year", as_index=False)["inflated_amount"]
                    .sum()
                    .rename(columns={"inflated_amount": "value"})
                )
                _exp_year["series"] = "ค่าใช้จ่ายรายปี"

                def _compact_baht(v):
                    v = float(v)
                    if abs(v) >= 1_000_000:
                        return f"{v / 1_000_000:.2f}M"
                    if abs(v) >= 1_000:
                        return f"{v / 1_000:.0f}K"
                    return f"{v:.0f}"

                _exp_year["kind"] = "expense"
                _exp_year["vlabel"] = _exp_year["value"].apply(_compact_baht)
                _chart_frames = [_exp_year[["year", "value", "series", "kind", "vlabel"]]]

                _rollover_pts = []
                _band_frames = []
                _Z9010 = 1.2816  # rough p10/p90 z-score (normal approx)
                for _ct in _edited_terms:
                    if not _ct.get("show_in_chart", True):
                        continue
                    _cnm = str(_ct.get("name", "")).strip() or "Term Asset"
                    _cby = _term_start_year + int(_ct.get("buy_year_offset", 1)) - 1
                    _cty = max(1, int(_ct.get("term_years", 1)))
                    _cro = int(_ct.get("max_rollovers", 0))
                    _cpr = float(_ct.get("min_initial_investment", 0) or 0.0)
                    _crt = float(_ct.get("mean_pct", 0) or 0.0) / 100.0
                    # Plot the value at the START of each year (BB) =
                    # principal*(1+r)^(year-buy). The line runs from the buy year
                    # to the payout/usable year = buy + term*(rollovers+1):
                    # BB(buy) = principal, BB(payout) = matured/usable amount.
                    _cpay = _cby + _cty * (_cro + 1)
                    _cseries = f"Term: {_cnm}"
                    _tvals = []
                    for _yy in range(_cby, _cpay + 1):
                        _bb = _cpr * ((1.0 + _crt) ** (_yy - _cby))
                        _tvals.append({
                            "year": _yy,
                            "value": _bb,
                            "series": _cseries,
                            "kind": "term",
                            "vlabel": _compact_baht(_bb),
                        })
                    if _tvals:
                        _chart_frames.append(pd.DataFrame(_tvals))
                    # rollover boundaries (start of each new round): buy + term*k
                    for _kk in range(1, _cro + 1):
                        _ry = _cby + _cty * _kk
                        _rollover_pts.append({
                            "year": _ry,
                            "value": _cpr * ((1.0 + _crt) ** (_ry - _cby)),
                            "series": _cseries,
                            "label": f"ต่ออายุครั้งที่ {_kk} (ปี {_ry})",
                        })

                    # rough P10–P90 band — compound the per-year p10/p90 single-year
                    # return (mean ± z*std). Only for volatile (std>0) assets.
                    _csd = float(_ct.get("std_pct", 0) or 0.0) / 100.0
                    if _csd > 0:
                        _r_lo = max(-0.99, _crt - _Z9010 * _csd)
                        _r_hi = _crt + _Z9010 * _csd
                        _band_frames.append(pd.DataFrame([
                            {
                                "year": _yy2,
                                "low": _cpr * ((1.0 + _r_lo) ** (_yy2 - _cby)),
                                "high": _cpr * ((1.0 + _r_hi) ** (_yy2 - _cby)),
                                "series": _cseries,
                            }
                            for _yy2 in range(_cby, _cpay + 1)
                        ]))

                # Shared term-asset palette (matches Chart 5.2 in results), keyed
                # by the FULL sorted list of term names so each asset keeps its
                # colour whether or not it's toggled on. Expense = light purple.
                _all_term_names_cfg = sorted(
                    (str(_t2.get("name", "")).strip() or "Term Asset")
                    for _t2 in _edited_terms
                )
                _TERM_PAL_CFG = ["#f97316", "#eab308", "#fb923c", "#f59e0b", "#facc15", "#d97706"]
                _series_color_scale_cfg = alt.Scale(
                    domain=["ค่าใช้จ่ายรายปี"] + [f"Term: {_n}" for _n in _all_term_names_cfg],
                    range=["#c4b5fd"] + [
                        _TERM_PAL_CFG[_i % len(_TERM_PAL_CFG)]
                        for _i in range(len(_all_term_names_cfg))
                    ],
                )
                _plot_df = pd.concat(_chart_frames, ignore_index=True)
                _base = alt.Chart(_plot_df).encode(
                    x=alt.X("year:Q", title="ปี", axis=alt.Axis(format="d", tickMinStep=1)),
                    y=alt.Y("value:Q", title="จำนวนเงิน (บาท)", axis=alt.Axis(format=",.0f")),
                    color=alt.Color("series:N", scale=_series_color_scale_cfg, title=""),
                )
                _line = _base.mark_line(point=True).encode(
                    tooltip=[
                        alt.Tooltip("series:N", title=""),
                        alt.Tooltip("year:Q", title="ปี", format="d"),
                        alt.Tooltip("value:Q", title="บาท", format=",.0f"),
                    ],
                )
                # data labels on every point (expense + term) — start-of-year
                # amounts for terms, yearly totals for expense. Font matches the
                # result-page standard (fontSize=14, bold).
                _data_labels = (
                    alt.Chart(_plot_df)
                    .mark_text(dy=-12, fontSize=14, fontWeight="bold")
                    .encode(
                        x=alt.X("year:Q"),
                        y=alt.Y("value:Q"),
                        text=alt.Text("vlabel:N"),
                        color=alt.Color("series:N", scale=_series_color_scale_cfg, title=""),
                    )
                )
                _band_layer = None
                if _band_frames:
                    _band_df = pd.concat(_band_frames, ignore_index=True)
                    _band_layer = (
                        alt.Chart(_band_df)
                        .mark_area(opacity=0.15)
                        .encode(
                            x=alt.X("year:Q"),
                            y=alt.Y("low:Q"),
                            y2=alt.Y2("high:Q"),
                            color=alt.Color("series:N", scale=_series_color_scale_cfg, title=""),
                        )
                    )
                _layers = ([_band_layer] if _band_layer is not None else []) + [_line, _data_labels]
                if _rollover_pts:
                    _ro_df = pd.DataFrame(_rollover_pts)
                    _marks = (
                        alt.Chart(_ro_df)
                        .mark_point(shape="diamond", size=170, filled=True, color="#C44E27")
                        .encode(
                            x=alt.X("year:Q"),
                            y=alt.Y("value:Q"),
                            tooltip=[
                                alt.Tooltip("series:N", title=""),
                                alt.Tooltip("label:N", title="เหตุการณ์"),
                                alt.Tooltip("year:Q", title="ปี", format="d"),
                                alt.Tooltip("value:Q", title="บาท", format=",.0f"),
                            ],
                        )
                    )
                    _layers.append(_marks)

                st.altair_chart(
                    alt.layer(*_layers).properties(height=340),
                    width="stretch",
                )
                st.caption(
                    "เส้นค่าใช้จ่ายรายปี (กรองตามบุตรได้) เทียบกับมูลค่าเงินต้นปีของ term asset "
                    "— ตัวเลขกำกับคือมูลค่า ณ ต้นปีนั้น จุดสุดท้ายคือปีที่ถอนเงินมาใช้ได้ "
                    "— จุด ◆ คือปีที่ต่ออายุ"
                )
            else:
                st.info("ยังไม่มีข้อมูลค่าใช้จ่ายสำหรับแสดงกราฟ")

        # ── Persist editable defs + build engine-ready List[TermAssetConfig] ──
        st.session_state["inv_term_asset_defs"] = _edited_terms
        draft_set("inv_term_asset_defs", _edited_terms)

        _term_assets_built: list = []
        if not _term_errors:
            for _et in _edited_terms:
                _is_fixed = (_et["distribution"] == "fixed")
                _mean_dec = float(_et["mean_pct"]) / 100.0
                _std_dec = 0.0 if _is_fixed else float(_et["std_pct"]) / 100.0
                if _is_fixed:
                    _min_ret = None
                    _max_ret = None
                else:
                    _min_ret = _mean_dec - 4.0 * _std_dec
                    _max_ret = _mean_dec + 4.0 * _std_dec
                _term_assets_built.append(TermAssetConfig(
                    name=_et["name"].strip(),
                    buy_year=_term_start_year + int(_et["buy_year_offset"]) - 1,
                    min_initial_investment=float(_et["min_initial_investment"]),
                    term_years=int(_et["term_years"]),
                    max_rollovers=int(_et["max_rollovers"]),
                    mean_return=_mean_dec,
                    std_dev=_std_dec,
                    min_return=_min_ret,
                    max_return=_max_ret,
                    distribution=_et["distribution"],
                ))
        st.session_state["inv_term_assets"] = _term_assets_built

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
