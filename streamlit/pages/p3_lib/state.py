"""Page 3 state: PARAM_DEFAULTS, widget initialization, bucket definition helpers.

Keys:
  inv_mc_*               permanent (survive page switching)
  _w_inv_mc_*            widget state (cleared on navigation)
  inv_bucket_definitions dynamic bucket + asset config
"""

import streamlit as st

from state import draft_get, draft_set, ensure_widget_buffer
from asset_store import (
    load_bucket_definitions,
    has_saved_bucket_definitions,
)


# ──────────────────────────────────────────────────────
# Default asset template + helpers
# ──────────────────────────────────────────────────────

def with_min_max(asset: dict) -> dict:
    """Auto-derive min_pct / max_pct from μ ± 4σ (99.99% normal coverage)."""
    mean = float(asset.get("mean_pct", 0.0))
    std = float(asset.get("std_pct", 0.0))
    return {**asset, "min_pct": mean - 4.0 * std, "max_pct": mean + 4.0 * std}


DEFAULT_ASSET = with_min_max({
    "asset_name": "Asset", "weight_pct": 100.0,
    "mean_pct": 3.0, "std_pct": 5.0,
})

PARAM_DEFAULTS = {
    # MC controls
    "inv_mc_n_paths": 1000,
    "inv_mc_random_seed": 42,
    "inv_mc_keep_path_detail": True,
    "inv_mc_keep_asset_detail": False,

    # 2-bucket simplified model — last bucket must have year_end=None.
    # asset values stored as % (6.0 = 6%), converted to decimal at model build.
    "inv_bucket_definitions": [
        {
            "name": "สำหรับค่าใช้จ่าย",
            "year_start": 1,
            "year_end": 1,
            "discount_rate": 0.02,
            "assets": [
                with_min_max({"asset_name": "FCD TD", "weight_pct": 50.0,
                              "mean_pct": 3.6, "std_pct": 0.21}),
                with_min_max({"asset_name": "Ultimate GA1", "weight_pct": 50.0,
                              "mean_pct": 4.0, "std_pct": 2.6}),
            ],
        },
        {
            "name": "สำหรับลงทุนเพื่อการศึกษา",
            "year_start": 2,
            "year_end": None,
            "discount_rate": 0.04,
            "assets": [
                with_min_max({"asset_name": "Ultimate GA2", "weight_pct": 60.0,
                              "mean_pct": 5.0, "std_pct": 5.0}),
                with_min_max({"asset_name": "GAINCOME", "weight_pct": 40.0,
                              "mean_pct": 6.0, "std_pct": 7.0}),
            ],
        },
    ],

    # outputs
    "inv_mc_result": None,
    "inv_mc_analysis": None,
    "inv_investment_sim_done": False,
}


_WIDGET_DEFAULT_KEYS = (
    "inv_mc_n_paths",
    "inv_mc_random_seed",
    "inv_mc_keep_path_detail",
    "inv_mc_keep_asset_detail",
)

_RUNTIME_DEFAULT_KEYS = (
    "inv_mc_result",
    "inv_mc_analysis",
    "inv_investment_sim_done",
)


# ──────────────────────────────────────────────────────
# Widget state init (idempotent, called once per render)
# ──────────────────────────────────────────────────────

# Widget-key prefixes that shadow freshly-loaded/reset bucket+asset values.
# Streamlit's widget tracker survives `del st.session_state[key]`, so callers
# must ALSO bump _p3_render_nonce to force keys to regenerate with new suffixes.
_STALE_WIDGET_PREFIXES = (
    "asset_",
    "bucket_name_",
    "bucket_year_end_",
    "bucket_year_start_ro_",
    "bucket_year_end_inf_",
)


def wipe_stale_widget_keys(extra_prefixes: tuple = ()) -> None:
    """Delete widget-state keys that would shadow reloaded bucket/asset values."""
    prefixes = _STALE_WIDGET_PREFIXES + tuple(extra_prefixes)
    for k in [k for k in list(st.session_state.keys()) if k.startswith(prefixes)]:
        del st.session_state[k]


def init_widget_state() -> None:
    """Hydrate widget buffers + runtime keys; reload saved config on cust_id change.

    - Widget-backed keys: ensure_widget_buffer hydrates w__{field} from draft
    - Runtime/output keys: direct session_state init
    - Bucket definitions: hydrate from draft, fallback to defaults
    - Cust_id change → wipe stale widget keys, auto-load saved config if present
    """
    if "_p3_render_nonce" not in st.session_state:
        st.session_state["_p3_render_nonce"] = 0

    for k in _WIDGET_DEFAULT_KEYS:
        ensure_widget_buffer(k, PARAM_DEFAULTS[k])

    for k in _RUNTIME_DEFAULT_KEYS:
        if k not in st.session_state:
            st.session_state[k] = PARAM_DEFAULTS[k]

    _cur_cid = (draft_get("cust_id", "") or "").strip()
    _last_hydrated_cid = st.session_state.get("_p3_hydrated_cid")
    _cid_changed = (_last_hydrated_cid != _cur_cid)

    if _cid_changed:
        # Cust_id change: wipe widget keys that would shadow loaded values.
        # (nonce is bumped below so widget keys regenerate with new suffixes.)
        wipe_stale_widget_keys()

        _auto_loaded = False
        _auto_load_err = None
        if _cur_cid:
            try:
                if has_saved_bucket_definitions(_cur_cid):
                    _loaded = load_bucket_definitions(_cur_cid)
                    if _loaded:
                        st.session_state["inv_bucket_definitions"] = _loaded
                        draft_set("inv_bucket_definitions", _loaded)
                        _auto_loaded = True
            except Exception as e:
                _auto_load_err = str(e)

        if not _auto_loaded:
            st.session_state["inv_bucket_definitions"] = draft_get(
                "inv_bucket_definitions",
                PARAM_DEFAULTS["inv_bucket_definitions"],
            )

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


# ──────────────────────────────────────────────────────
# Bucket definition helpers
# ──────────────────────────────────────────────────────

def coerce_bucket_dict(value):
    """Normalize a bucket entry to a dict.
    Handles legacy rows saved as JSON-encoded (or double-encoded) strings.
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


def get_bucket_definitions() -> list:
    """Get bucket definitions from session state (with default fallback)."""
    raw = st.session_state.get(
        "inv_bucket_definitions",
        PARAM_DEFAULTS["inv_bucket_definitions"],
    )
    if not isinstance(raw, list):
        return list(PARAM_DEFAULTS["inv_bucket_definitions"])
    cleaned = []
    for item in raw:
        d = coerce_bucket_dict(item)
        if d is not None:
            cleaned.append(d)
    if not cleaned:
        return list(PARAM_DEFAULTS["inv_bucket_definitions"])
    return cleaned


def build_bucket_configs_from_definitions(defs: list) -> list:
    """List[BucketConfig] from bucket definitions."""
    from portfolio_bucket_engine import BucketConfig
    return [
        BucketConfig(
            bucket_name=str(d["name"]),
            start_offset_year=int(d["year_start"]),
            end_offset_year=None if d.get("year_end") is None else int(d["year_end"]),
            annual_return_rate=float(d["discount_rate"]),
        )
        for d in defs
    ]


# Position-based correlation fallback when bucket name not in dict.
DEFAULT_CORR_BY_POSITION = [0.1, 0.3]


def build_bucket_return_models_from_definitions(defs: list) -> list:
    """List[BucketReturnModel] from bucket definitions.

    Assets carry weight + return distribution. UI stores returns as %,
    converted to decimal here. Student-t (df=5) hardcoded for fat tails.
    """
    from portfolio_bucket_engine_mc import (
        AssetReturnModel,
        BucketReturnModel,
        DEFAULT_INTRA_BUCKET_CORRELATION,
    )

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
                distribution="student_t",
            ))

        if asset_models:
            total_w = sum(a.weight for a in asset_models)
            eff_mean = sum(a.weight * a.mean_return for a in asset_models) / total_w
            eff_std = sum(a.weight * a.std_dev for a in asset_models) / total_w
        else:
            eff_mean = float(d.get("discount_rate", 0.0))
            eff_std = 0.0

        bname = str(d["name"])
        pos_fallback = DEFAULT_CORR_BY_POSITION[
            min(idx, len(DEFAULT_CORR_BY_POSITION) - 1)
        ]
        corr = DEFAULT_INTRA_BUCKET_CORRELATION.get(bname, pos_fallback)
        models.append(BucketReturnModel(
            bucket_name=bname,
            mean_return=eff_mean,
            std_dev=eff_std,
            assets=asset_models,
            intra_bucket_correlation=corr,
            distribution="student_t",
        ))
    return models
