"""
Session-state and draft management for the multi-page app.

Single source of truth:
- st.session_state["draft"] : all user inputs
- st.session_state["expense_df"], saving_df, summary_df : simulation outputs

Widget buffers live under keys of the form ``w__{field}``; helpers below keep
them in sync with the draft so widgets survive reruns and page switches.
"""
from datetime import date

import streamlit as st


# ============================================================
# SCALAR HELPERS
# ============================================================
def _none_if_blank(text):
    if text is None:
        return None
    text = str(text).strip()
    return None if text == "" else text


def _to_optional_int(text):
    text = _none_if_blank(text)
    if text is None:
        return None
    return int(text)


# ============================================================
# WIDGET KEY / STATE PRIMITIVES
# ============================================================
def _widget_key(field: str) -> str:
    return f"w__{field}"


def _ensure_state(key, default):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


def init_app_state():
    """
    Initialize core session-state keys and seed draft defaults.
    """
    _ensure_state("draft", {})
    _ensure_state("simulation_ran", False)
    _ensure_state("expense_df", None)
    _ensure_state("saving_df", None)
    _ensure_state("summary_df", None)
    _ensure_state("input_snapshot", None)

    draft = st.session_state["draft"]
    today_year = date.today().year

    defaults = {
        "cust_id": "",
        "n_children": 1,
        "n_parent_expenses": 0,
        "n_topups": 0,
        "initial_savings": 2_000_000.0,
        "monthly_contribution": 50_000.0,
        "saving_start_year": today_year,
        "assump_start_year": today_year,
        "general_inflation_rate": 0.02,
        "education_inflation_rate": 0.03,
        "investment_return_rate": 0.04,
        "return_compound_mode": "yearly",
        "expense_timing": "end_of_year",
        "open_recurring_default_years": 5,
        "inflation_base_year": str(today_year),
        "auto_add_hs": False,
        "default_highschool_start_age": 16,
        "default_highschool_end_age": 18,
        # Rolling-window bucket horizons (absolute year offsets, 1-indexed).
        # Contiguous: Liquidity = [1, liq_end] | Stability = [liq_end+1, stab_end] |
        # Growth = [stab_end+1, ∞)
        "liquidity_end_year": 2,
        "stability_end_year": 5,
    }

    for k, v in defaults.items():
        draft.setdefault(k, v)

    # Migrate legacy duration keys → absolute end-year keys (one-way, idempotent).
    # Old: liquidity_years = N (count of years from year 1)
    #      stability_years = M (count of years after liquidity)
    # New: liquidity_end_year = N, stability_end_year = N + M
    if "liquidity_years" in draft and "liquidity_end_year" not in {k for k in draft if draft.get(k) != defaults.get(k)}:
        try:
            draft["liquidity_end_year"] = int(draft["liquidity_years"])
        except Exception:
            pass
    if "stability_years" in draft:
        try:
            _liq = int(draft.get("liquidity_end_year", draft.get("liquidity_years", 2)))
            _stab_dur = int(draft["stability_years"])
            # Only overwrite if user has not already adopted new key explicitly
            if draft.get("stability_end_year") == defaults["stability_end_year"]:
                draft["stability_end_year"] = _liq + _stab_dur
        except Exception:
            pass


def draft_get(field, default=None):
    return st.session_state["draft"].get(field, default)


def draft_set(field, value):
    st.session_state["draft"][field] = value


def set_field_value(field, value):
    """
    Update both source-of-truth and current widget buffer.
    Useful for template loading / programmatic preset.
    """
    draft_set(field, value)
    st.session_state[_widget_key(field)] = value


def ensure_widget_buffer(field, default):
    """
    Make widget buffer reflect draft on first render only.
    """
    if field not in st.session_state["draft"]:
        st.session_state["draft"][field] = default

    wkey = _widget_key(field)
    if wkey not in st.session_state:
        st.session_state[wkey] = st.session_state["draft"][field]


def on_widget_change(field, cast=None):
    val = st.session_state[_widget_key(field)]
    if cast is not None and val is not None:
        try:
            val = cast(val)
        except Exception:
            pass
    draft_set(field, val)


def persist_all_widget_buffers():
    """
    Force copy all current widget buffers into draft.
    This is the critical commit step before navigation.

    Skips internal display-only buffers (e.g. percent-display mirrors used by
    p_percent_input) so they never leak into the persisted draft / DB.
    """
    for key, value in list(st.session_state.items()):
        if key.startswith("w__"):
            field = key[3:]
            if field.endswith("__pct_display"):
                continue
            st.session_state["draft"][field] = value


def switch_page_with_persist(page_path: str):
    persist_all_widget_buffers()
    st.switch_page(page_path)


# ============================================================
# LOGIN / ADMIN GUARDS
# ============================================================
# Staff ID เป็นเพียง tracking — ไม่ได้ authenticate
# Page 5 จำกัดเฉพาะ admin staff ID = "63589"
ADMIN_STAFF_IDS = {"63589"}


def hide_admin_pages_from_sidebar():
    """ซ่อน Page 5 (Saved_Snapshots) จาก sidebar nav ถ้าไม่ใช่ admin.
    ต้องเรียกในทุกหน้า เพราะ Streamlit render sidebar ใหม่ทุก page."""
    if not st.session_state.get("is_admin"):
        st.markdown(
            """
            <style>
            [data-testid="stSidebarNav"] a[href*="Saved_Snapshots"],
            [data-testid="stSidebarNavLink"][href*="Saved_Snapshots"] {
                display: none !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )


def require_login():
    """กั้นไม่ให้เข้าหน้าอื่นถ้ายังไม่ผ่าน welcome gate ใน Page 1"""
    if not st.session_state.get("staff_id_verified"):
        st.warning("⚠️ กรุณาเข้าสู่ระบบที่หน้าแรกก่อน")
        switch_page_with_persist("01_User_Information.py")
        st.stop()
    hide_admin_pages_from_sidebar()


def require_admin():
    """กั้นเฉพาะ admin Staff ID เท่านั้น (ใช้กับ Page 5)"""
    require_login()
    if not st.session_state.get("is_admin"):
        st.error("🚫 คุณไม่มีสิทธิ์เข้าถึงหน้านี้ (admin only)")
        st.info("กลับไปที่หน้าแรกเพื่อใช้งานฟีเจอร์อื่น")
        st.stop()


def apply_loaded_draft_to_state(loaded_draft: dict) -> int:
    """
    Overwrite st.session_state['draft'] with a draft loaded from DB,
    clearing widget buffers so each widget refreshes from the new draft.
    Returns number of fields applied.
    """
    if not isinstance(loaded_draft, dict):
        return 0
    draft = st.session_state.setdefault("draft", {})
    for k, v in loaded_draft.items():
        draft[k] = v

    # Clear ALL cached widget/runtime state so the next render rehydrates
    # from the freshly-loaded draft. Without this, Streamlit widgets with a
    # `key=` parameter silently shadow the new `value=` (the widget keeps the
    # previously-cached value), and Page 3's `_init_widget_state()` skips
    # re-hydrating `inv_bucket_definitions` when it's already in session_state.
    keys_to_remove = [
        k for k in list(st.session_state.keys())
        if (
            k.startswith("w__")
            or k.startswith("asset_")
            or k.startswith("bucket_name_")
            or k.startswith("bucket_year_end_")
            or k.startswith("bucket_year_start_ro_")
            or k.startswith("bucket_year_end_inf_")
            or k == "inv_bucket_definitions"
        )
    ]
    for k in keys_to_remove:
        del st.session_state[k]

    return len(loaded_draft)
