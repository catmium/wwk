# """
# SQLite-backed storage for per-customer Page 3 bucket/asset definitions.

# Reuses the same data.db file as database.py. Mirrors that module's practice:
# each save() inserts a NEW snapshot row and old snapshots beyond
# KEEP_PER_CUST_ID are pruned in the same transaction. load_latest() returns
# the most recent snapshot for the given cust_id.

# Each snapshot stores the FULL bucket list (all buckets + their assets,
# including each asset's name) as a single JSON document. A human-readable
# snapshot_label (timestamp + bucket/asset summary, including asset names)
# is stored alongside for display in pickers.

# Public API
# ----------
# save_bucket_definitions(cust_id, defs, snapshot_label=None) -> int  (new row id)
# load_bucket_definitions(cust_id)                            -> list | None  (most recent)
# list_bucket_snapshots(cust_id)                              -> list[dict]   (newest first)
# load_bucket_snapshot_by_id(snapshot_id)                     -> list | None
# clear_bucket_definitions(cust_id)                           -> int          (rows deleted)
# has_saved_bucket_definitions(cust_id)                       -> bool
# get_saved_bucket_meta(cust_id)                              -> dict | None  (latest snapshot summary)
# """
# import json
# import os
# import sqlite3
# from datetime import datetime
# from typing import Any, Dict, List, Optional


# # Same DB file as database.py — colocated with the module so it persists.
# _DB_PATH = os.environ.get(
#     "WEALTH_KIDS_DB_PATH",
#     os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db"),
# )

# # Retention: keep at most this many snapshots per cust_id (same as database.py).
# KEEP_PER_CUST_ID = 10


# def _connect() -> sqlite3.Connection:
#     conn = sqlite3.connect(_DB_PATH)
#     conn.execute("PRAGMA journal_mode=WAL;")
#     return conn


# def init_bucket_assets_table() -> None:
#     """Create the bucket_snapshots table if it doesn't exist."""
#     with _connect() as conn:
#         conn.execute(
#             """
#             CREATE TABLE IF NOT EXISTS bucket_snapshots (
#                 id             INTEGER PRIMARY KEY AUTOINCREMENT,
#                 cust_id        TEXT    NOT NULL,
#                 snapshot_label TEXT,
#                 buckets_json   TEXT    NOT NULL,
#                 created_at     TEXT    NOT NULL
#             );
#             """
#         )
#         conn.execute(
#             "CREATE INDEX IF NOT EXISTS idx_bucket_snapshots_cust_created "
#             "ON bucket_snapshots (cust_id, created_at DESC);"
#         )
#         conn.commit()


# def _normalize_cust_id(cust_id: Any) -> str:
#     return str(cust_id or "").strip()


# def _coerce_bucket_entry(value: Any) -> Optional[Dict[str, Any]]:
#     """Decode one bucket payload back to a dict (handles double-encoded JSON)."""
#     seen = 0
#     while isinstance(value, str) and seen < 4:
#         try:
#             value = json.loads(value)
#         except Exception:
#             return None
#         seen += 1
#     return value if isinstance(value, dict) else None


# def _build_default_label(defs: List[Dict[str, Any]]) -> str:
#     """Build a human-readable label that includes the asset names."""
#     ts = datetime.now().strftime("%Y-%m-%d %H:%M")
#     asset_names: List[str] = []
#     for bdef in defs:
#         for a in (bdef.get("assets") or []):
#             nm = str(a.get("asset_name", "")).strip()
#             if nm:
#                 asset_names.append(nm)
#     n_b = len(defs)
#     n_a = len(asset_names)
#     # Keep label compact: show first few asset names, ellipsis if more
#     if asset_names:
#         preview = ", ".join(asset_names[:6])
#         if len(asset_names) > 6:
#             preview += ", ..."
#         return f"{ts} — {n_b} buckets / {n_a} assets ({preview})"
#     return f"{ts} — {n_b} buckets / {n_a} assets"


# def save_bucket_definitions(
#     cust_id: str,
#     defs: List[Dict[str, Any]],
#     snapshot_label: Optional[str] = None,
# ) -> int:
#     """
#     Insert a new snapshot of bucket+asset definitions and prune older
#     snapshots so this cust_id keeps at most KEEP_PER_CUST_ID rows.

#     Returns the new row id.
#     """
#     init_bucket_assets_table()
#     cid = _normalize_cust_id(cust_id)
#     if not cid:
#         raise ValueError("cust_id is required")
#     if not isinstance(defs, list):
#         raise TypeError("defs must be a list of bucket definition dicts")
#     # Defensively coerce each entry to dict before saving
#     cleaned: List[Dict[str, Any]] = []
#     for idx, bdef in enumerate(defs):
#         entry = _coerce_bucket_entry(bdef)
#         if entry is None:
#             raise TypeError(f"bucket at index {idx} is not a dict")
#         cleaned.append(entry)

#     label = (snapshot_label or "").strip() or _build_default_label(cleaned)
#     created_at = datetime.now().isoformat(timespec="seconds")
#     payload = json.dumps(cleaned, ensure_ascii=False)

#     with _connect() as conn:
#         cur = conn.execute(
#             "INSERT INTO bucket_snapshots (cust_id, snapshot_label, buckets_json, created_at) "
#             "VALUES (?, ?, ?, ?);",
#             (cid, label, payload, created_at),
#         )
#         new_id = int(cur.lastrowid)

#         # Keep only the latest KEEP_PER_CUST_ID rows for this cust_id.
#         conn.execute(
#             """
#             DELETE FROM bucket_snapshots
#             WHERE cust_id = ?
#               AND id NOT IN (
#                   SELECT id FROM bucket_snapshots
#                   WHERE cust_id = ?
#                   ORDER BY created_at DESC, id DESC
#                   LIMIT ?
#               );
#             """,
#             (cid, cid, KEEP_PER_CUST_ID),
#         )
#         conn.commit()
#     return new_id


# def _decode_buckets_payload(payload: str) -> Optional[List[Dict[str, Any]]]:
#     """Decode a buckets_json payload and ensure result is a list of dicts."""
#     try:
#         decoded = json.loads(payload)
#     except Exception:
#         return None
#     if not isinstance(decoded, list):
#         return None
#     out: List[Dict[str, Any]] = []
#     for item in decoded:
#         entry = _coerce_bucket_entry(item)
#         if entry is not None:
#             out.append(entry)
#     return out or None


# def load_bucket_definitions(cust_id: str) -> Optional[List[Dict[str, Any]]]:
#     """Return the MOST RECENT bucket definitions for this cust_id, or None."""
#     init_bucket_assets_table()
#     cid = _normalize_cust_id(cust_id)
#     if not cid:
#         return None
#     with _connect() as conn:
#         row = conn.execute(
#             "SELECT buckets_json FROM bucket_snapshots "
#             "WHERE cust_id = ? ORDER BY created_at DESC, id DESC LIMIT 1;",
#             (cid,),
#         ).fetchone()
#     if not row:
#         return None
#     return _decode_buckets_payload(row[0])


# def list_bucket_snapshots(cust_id: str) -> List[Dict[str, Any]]:
#     """List all snapshots for this cust_id, newest first.

#     Each entry: {id, snapshot_label, created_at, n_buckets, n_assets}.
#     """
#     init_bucket_assets_table()
#     cid = _normalize_cust_id(cust_id)
#     if not cid:
#         return []
#     with _connect() as conn:
#         rows = conn.execute(
#             "SELECT id, snapshot_label, created_at, buckets_json FROM bucket_snapshots "
#             "WHERE cust_id = ? ORDER BY created_at DESC, id DESC;",
#             (cid,),
#         ).fetchall()
#     out: List[Dict[str, Any]] = []
#     for _id, label, ts, payload in rows:
#         defs = _decode_buckets_payload(payload) or []
#         n_b = len(defs)
#         n_a = sum(len(d.get("assets") or []) for d in defs)
#         out.append(
#             {
#                 "id": int(_id),
#                 "snapshot_label": label or "",
#                 "created_at": ts or "",
#                 "n_buckets": n_b,
#                 "n_assets": n_a,
#             }
#         )
#     return out


# def load_bucket_snapshot_by_id(snapshot_id: int) -> Optional[List[Dict[str, Any]]]:
#     """Return a specific snapshot's buckets list, or None."""
#     init_bucket_assets_table()
#     try:
#         sid = int(snapshot_id)
#     except (TypeError, ValueError):
#         return None
#     with _connect() as conn:
#         row = conn.execute(
#             "SELECT buckets_json FROM bucket_snapshots WHERE id = ? LIMIT 1;",
#             (sid,),
#         ).fetchone()
#     if not row:
#         return None
#     return _decode_buckets_payload(row[0])


# def clear_bucket_definitions(cust_id: str) -> int:
#     """Delete ALL snapshots for this cust_id. Returns rows deleted."""
#     init_bucket_assets_table()
#     cid = _normalize_cust_id(cust_id)
#     if not cid:
#         return 0
#     with _connect() as conn:
#         cur = conn.execute("DELETE FROM bucket_snapshots WHERE cust_id = ?;", (cid,))
#         conn.commit()
#         return int(cur.rowcount or 0)


# def has_saved_bucket_definitions(cust_id: str) -> bool:
#     init_bucket_assets_table()
#     cid = _normalize_cust_id(cust_id)
#     if not cid:
#         return False
#     with _connect() as conn:
#         row = conn.execute(
#             "SELECT 1 FROM bucket_snapshots WHERE cust_id = ? LIMIT 1;",
#             (cid,),
#         ).fetchone()
#         return row is not None


# def get_saved_bucket_meta(cust_id: str) -> Optional[Dict[str, Any]]:
#     """Return the LATEST snapshot's meta:
#     {"updated_at", "n_buckets", "n_assets", "snapshot_label", "n_snapshots"} or None.
#     """
#     init_bucket_assets_table()
#     cid = _normalize_cust_id(cust_id)
#     if not cid:
#         return None
#     with _connect() as conn:
#         latest = conn.execute(
#             "SELECT created_at, snapshot_label, buckets_json FROM bucket_snapshots "
#             "WHERE cust_id = ? ORDER BY created_at DESC, id DESC LIMIT 1;",
#             (cid,),
#         ).fetchone()
#         if not latest:
#             return None
#         total = conn.execute(
#             "SELECT COUNT(*) FROM bucket_snapshots WHERE cust_id = ?;",
#             (cid,),
#         ).fetchone()
#     ts, label, payload = latest
#     defs = _decode_buckets_payload(payload) or []
#     n_b = len(defs)
#     n_a = sum(len(d.get("assets") or []) for d in defs)
#     return {
#         "updated_at": ts or "",
#         "n_buckets": n_b,
#         "n_assets": n_a,
#         "snapshot_label": label or "",
#         "n_snapshots": int(total[0]) if total else 0,
#     }

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
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from supabase import create_client, Client


KEEP_PER_CUST_ID = 10
_TABLE = "bucket_snapshots"
_client: Optional[Client] = None


# ------------------------------------------------------------
# Supabase client
# ------------------------------------------------------------
def _get_credentials() -> Tuple[str, str]:
    url = None
    key = None

    try:
        import streamlit as st
        secrets = st.secrets
        if "supabase" in secrets:
            sub = secrets["supabase"]
            url = sub.get("url") or sub.get("URL") or sub.get("SUPABASE_URL")
            key = (
                sub.get("key")
                or sub.get("KEY")
                or sub.get("SUPABASE_KEY")
                or sub.get("anon_key")
                or sub.get("service_role_key")
            )
        if not url:
            url = secrets.get("SUPABASE_URL")
        if not key:
            key = secrets.get("SUPABASE_KEY") or secrets.get("SUPABASE_SERVICE_ROLE_KEY")
    except Exception:
        pass

    url = url or os.environ.get("SUPABASE_URL")
    key = (
        key
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )

    if not url or not key:
        raise RuntimeError(
            "Supabase credentials missing. Expected in .streamlit/secrets.toml as:\n"
            "    [supabase]\n"
            '    url = "https://<project>.supabase.co"\n'
            '    key  = "<service-role-key>"\n'
            "Or env vars SUPABASE_URL / SUPABASE_KEY."
        )
    return str(url), str(key)


def _get_client() -> Client:
    global _client
    if _client is None:
        url, key = _get_credentials()
        _client = create_client(url, key)
    return _client


def init_bucket_assets_table() -> None:
    """Schema lives in Supabase; no-op kept for API compatibility."""
    return None


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
