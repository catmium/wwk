"""
Supabase-backed storage for per-customer Page 3 bucket/asset definitions.

Replaces the SQLite implementation. Public API is preserved — downstream
callers do not need changes.

Each snapshot stores the FULL bucket list (all buckets + their assets,
including each asset's name) as a single jsonb document. A human-readable
snapshot_label (timestamp + bucket/asset summary, including asset names)
is stored alongside for display in pickers.

Configuration
-------------
Reads Supabase credentials from Streamlit secrets or env vars (see
database.py docstring for accepted layouts).

Schema (run once in Supabase SQL Editor)
----------------------------------------
    create table bucket_snapshots (
        id             bigserial primary key,
        cust_id        text not null,
        snapshot_label text,
        buckets_json   jsonb not null,
        created_at     timestamptz not null default now()
    );
    create index idx_bucket_snapshots_cust_created
        on bucket_snapshots (cust_id, created_at desc);

Public API
----------
save_bucket_definitions(cust_id, defs, snapshot_label=None) -> int (new row id)
load_bucket_definitions(cust_id)                            -> list | None  (most recent)
list_bucket_snapshots(cust_id)                              -> list[dict]   (newest first)
load_bucket_snapshot_by_id(snapshot_id)                     -> list | None
clear_bucket_definitions(cust_id)                           -> int          (rows deleted)
has_saved_bucket_definitions(cust_id)                       -> bool
get_saved_bucket_meta(cust_id)                              -> dict | None  (latest snapshot summary)
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from supabase import create_client, Client

from database import _get_credentials


KEEP_PER_CUST_ID = 10
_TABLE = "bucket_snapshots"
_client: Optional[Client] = None


# ------------------------------------------------------------
# Supabase client
# ------------------------------------------------------------
def _get_client() -> Client:
    global _client
    if _client is None:
        url, key = _get_credentials()
        _client = create_client(url, key)
    return _client


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _normalize_cust_id(cust_id: Any) -> str:
    return str(cust_id or "").strip()


def _coerce_bucket_entry(value: Any) -> Optional[Dict[str, Any]]:
    """Decode one bucket payload back to a dict (handles double-encoded JSON
    from legacy SQLite rows)."""
    seen = 0
    while isinstance(value, str) and seen < 4:
        try:
            value = json.loads(value)
        except Exception:
            return None
        seen += 1
    return value if isinstance(value, dict) else None


def _coerce_bucket_list(payload: Any) -> Optional[List[Dict[str, Any]]]:
    """Decode buckets payload. jsonb returns a parsed list; legacy returns string."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None
    if not isinstance(payload, list):
        return None
    out: List[Dict[str, Any]] = []
    for item in payload:
        entry = _coerce_bucket_entry(item)
        if entry is not None:
            out.append(entry)
    return out or None


def _build_default_label(defs: List[Dict[str, Any]]) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    asset_names: List[str] = []
    for bdef in defs:
        for a in (bdef.get("assets") or []):
            nm = str(a.get("asset_name", "")).strip()
            if nm:
                asset_names.append(nm)
    n_b = len(defs)
    n_a = len(asset_names)
    if asset_names:
        preview = ", ".join(asset_names[:6])
        if len(asset_names) > 6:
            preview += ", ..."
        return f"{ts} — {n_b} buckets / {n_a} assets ({preview})"
    return f"{ts} — {n_b} buckets / {n_a} assets"


def _prune_bucket_snapshots(cust_id: str, keep: int, client: Optional[Client] = None) -> int:
    client = client or _get_client()
    rows = (
        client.table(_TABLE)
        .select("id")
        .eq("cust_id", cust_id)
        .order("created_at", desc=True)
        .order("id", desc=True)
        .execute()
        .data
        or []
    )
    ids_to_delete = [r["id"] for r in rows[keep:]]
    if not ids_to_delete:
        return 0
    client.table(_TABLE).delete().in_("id", ids_to_delete).execute()
    return len(ids_to_delete)


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------
def save_bucket_definitions(
    cust_id: str,
    defs: List[Dict[str, Any]],
    snapshot_label: Optional[str] = None,
) -> int:
    cid = _normalize_cust_id(cust_id)
    if not cid:
        raise ValueError("cust_id is required")
    if not isinstance(defs, list):
        raise TypeError("defs must be a list of bucket definition dicts")

    cleaned: List[Dict[str, Any]] = []
    for idx, bdef in enumerate(defs):
        entry = _coerce_bucket_entry(bdef)
        if entry is None:
            raise TypeError(f"bucket at index {idx} is not a dict")
        cleaned.append(entry)

    label = (snapshot_label or "").strip() or _build_default_label(cleaned)

    client = _get_client()
    res = (
        client.table(_TABLE)
        .insert({
            "cust_id": cid,
            "snapshot_label": label,
            "buckets_json": cleaned,  # jsonb-native
        })
        .execute()
    )
    if not res.data:
        raise RuntimeError("Supabase insert returned no row")
    new_id = int(res.data[0]["id"])

    _prune_bucket_snapshots(cid, KEEP_PER_CUST_ID, client=client)
    return new_id


def load_bucket_definitions(cust_id: str) -> Optional[List[Dict[str, Any]]]:
    cid = _normalize_cust_id(cust_id)
    if not cid:
        return None
    client = _get_client()
    res = (
        client.table(_TABLE)
        .select("buckets_json")
        .eq("cust_id", cid)
        .order("created_at", desc=True)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return _coerce_bucket_list(res.data[0]["buckets_json"])


def list_bucket_snapshots(cust_id: str) -> List[Dict[str, Any]]:
    cid = _normalize_cust_id(cust_id)
    if not cid:
        return []
    client = _get_client()
    res = (
        client.table(_TABLE)
        .select("id,snapshot_label,created_at,buckets_json")
        .eq("cust_id", cid)
        .order("created_at", desc=True)
        .order("id", desc=True)
        .execute()
    )
    out: List[Dict[str, Any]] = []
    for r in res.data or []:
        defs = _coerce_bucket_list(r.get("buckets_json")) or []
        n_b = len(defs)
        n_a = sum(len(d.get("assets") or []) for d in defs)
        out.append({
            "id": int(r["id"]),
            "snapshot_label": r.get("snapshot_label") or "",
            "created_at": r.get("created_at") or "",
            "n_buckets": n_b,
            "n_assets": n_a,
        })
    return out


def load_bucket_snapshot_by_id(snapshot_id: int) -> Optional[List[Dict[str, Any]]]:
    try:
        sid = int(snapshot_id)
    except (TypeError, ValueError):
        return None
    client = _get_client()
    res = (
        client.table(_TABLE)
        .select("buckets_json")
        .eq("id", sid)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return _coerce_bucket_list(res.data[0]["buckets_json"])


def clear_bucket_definitions(cust_id: str) -> int:
    cid = _normalize_cust_id(cust_id)
    if not cid:
        return 0
    client = _get_client()
    res = (
        client.table(_TABLE)
        .select("id", count="exact")
        .eq("cust_id", cid)
        .execute()
    )
    n = int(res.count or 0)
    if n == 0:
        return 0
    client.table(_TABLE).delete().eq("cust_id", cid).execute()
    return n


def has_saved_bucket_definitions(cust_id: str) -> bool:
    cid = _normalize_cust_id(cust_id)
    if not cid:
        return False
    client = _get_client()
    res = (
        client.table(_TABLE)
        .select("id")
        .eq("cust_id", cid)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def get_saved_bucket_meta(cust_id: str) -> Optional[Dict[str, Any]]:
    cid = _normalize_cust_id(cust_id)
    if not cid:
        return None
    client = _get_client()
    latest_res = (
        client.table(_TABLE)
        .select("created_at,snapshot_label,buckets_json")
        .eq("cust_id", cid)
        .order("created_at", desc=True)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if not latest_res.data:
        return None
    total_res = (
        client.table(_TABLE)
        .select("id", count="exact")
        .eq("cust_id", cid)
        .execute()
    )
    r = latest_res.data[0]
    defs = _coerce_bucket_list(r.get("buckets_json")) or []
    n_b = len(defs)
    n_a = sum(len(d.get("assets") or []) for d in defs)
    return {
        "updated_at": r.get("created_at") or "",
        "n_buckets": n_b,
        "n_assets": n_a,
        "snapshot_label": r.get("snapshot_label") or "",
        "n_snapshots": int(total_res.count or 0),
    }
