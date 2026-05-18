"""
SQLite-backed storage for per-customer Page 3 bucket/asset definitions.

Reuses the same data.db file as database.py. Mirrors that module's practice:
each save() inserts a NEW snapshot row and old snapshots beyond
KEEP_PER_CUST_ID are pruned in the same transaction. load_latest() returns
the most recent snapshot for the given cust_id.

Each snapshot stores the FULL bucket list (all buckets + their assets,
including each asset's name) as a single JSON document. A human-readable
snapshot_label (timestamp + bucket/asset summary, including asset names)
is stored alongside for display in pickers.

Public API
----------
save_bucket_definitions(cust_id, defs, snapshot_label=None) -> int  (new row id)
load_bucket_definitions(cust_id)                            -> list | None  (most recent)
list_bucket_snapshots(cust_id)                              -> list[dict]   (newest first)
load_bucket_snapshot_by_id(snapshot_id)                     -> list | None
clear_bucket_definitions(cust_id)                           -> int          (rows deleted)
has_saved_bucket_definitions(cust_id)                       -> bool
get_saved_bucket_meta(cust_id)                              -> dict | None  (latest snapshot summary)
"""
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


# Same DB file as database.py — colocated with the module so it persists.
_DB_PATH = os.environ.get(
    "WEALTH_KIDS_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db"),
)

# Retention: keep at most this many snapshots per cust_id (same as database.py).
KEEP_PER_CUST_ID = 10


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_bucket_assets_table() -> None:
    """Create the bucket_snapshots table if it doesn't exist."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bucket_snapshots (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                cust_id        TEXT    NOT NULL,
                snapshot_label TEXT,
                buckets_json   TEXT    NOT NULL,
                created_at     TEXT    NOT NULL
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bucket_snapshots_cust_created "
            "ON bucket_snapshots (cust_id, created_at DESC);"
        )
        conn.commit()


def _normalize_cust_id(cust_id: Any) -> str:
    return str(cust_id or "").strip()


def _coerce_bucket_entry(value: Any) -> Optional[Dict[str, Any]]:
    """Decode one bucket payload back to a dict (handles double-encoded JSON)."""
    seen = 0
    while isinstance(value, str) and seen < 4:
        try:
            value = json.loads(value)
        except Exception:
            return None
        seen += 1
    return value if isinstance(value, dict) else None


def _build_default_label(defs: List[Dict[str, Any]]) -> str:
    """Build a human-readable label that includes the asset names."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    asset_names: List[str] = []
    for bdef in defs:
        for a in (bdef.get("assets") or []):
            nm = str(a.get("asset_name", "")).strip()
            if nm:
                asset_names.append(nm)
    n_b = len(defs)
    n_a = len(asset_names)
    # Keep label compact: show first few asset names, ellipsis if more
    if asset_names:
        preview = ", ".join(asset_names[:6])
        if len(asset_names) > 6:
            preview += ", ..."
        return f"{ts} — {n_b} buckets / {n_a} assets ({preview})"
    return f"{ts} — {n_b} buckets / {n_a} assets"


def save_bucket_definitions(
    cust_id: str,
    defs: List[Dict[str, Any]],
    snapshot_label: Optional[str] = None,
) -> int:
    """
    Insert a new snapshot of bucket+asset definitions and prune older
    snapshots so this cust_id keeps at most KEEP_PER_CUST_ID rows.

    Returns the new row id.
    """
    init_bucket_assets_table()
    cid = _normalize_cust_id(cust_id)
    if not cid:
        raise ValueError("cust_id is required")
    if not isinstance(defs, list):
        raise TypeError("defs must be a list of bucket definition dicts")
    # Defensively coerce each entry to dict before saving
    cleaned: List[Dict[str, Any]] = []
    for idx, bdef in enumerate(defs):
        entry = _coerce_bucket_entry(bdef)
        if entry is None:
            raise TypeError(f"bucket at index {idx} is not a dict")
        cleaned.append(entry)

    label = (snapshot_label or "").strip() or _build_default_label(cleaned)
    created_at = datetime.now().isoformat(timespec="seconds")
    payload = json.dumps(cleaned, ensure_ascii=False)

    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO bucket_snapshots (cust_id, snapshot_label, buckets_json, created_at) "
            "VALUES (?, ?, ?, ?);",
            (cid, label, payload, created_at),
        )
        new_id = int(cur.lastrowid)

        # Keep only the latest KEEP_PER_CUST_ID rows for this cust_id.
        conn.execute(
            """
            DELETE FROM bucket_snapshots
            WHERE cust_id = ?
              AND id NOT IN (
                  SELECT id FROM bucket_snapshots
                  WHERE cust_id = ?
                  ORDER BY created_at DESC, id DESC
                  LIMIT ?
              );
            """,
            (cid, cid, KEEP_PER_CUST_ID),
        )
        conn.commit()
    return new_id


def _decode_buckets_payload(payload: str) -> Optional[List[Dict[str, Any]]]:
    """Decode a buckets_json payload and ensure result is a list of dicts."""
    try:
        decoded = json.loads(payload)
    except Exception:
        return None
    if not isinstance(decoded, list):
        return None
    out: List[Dict[str, Any]] = []
    for item in decoded:
        entry = _coerce_bucket_entry(item)
        if entry is not None:
            out.append(entry)
    return out or None


def load_bucket_definitions(cust_id: str) -> Optional[List[Dict[str, Any]]]:
    """Return the MOST RECENT bucket definitions for this cust_id, or None."""
    init_bucket_assets_table()
    cid = _normalize_cust_id(cust_id)
    if not cid:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT buckets_json FROM bucket_snapshots "
            "WHERE cust_id = ? ORDER BY created_at DESC, id DESC LIMIT 1;",
            (cid,),
        ).fetchone()
    if not row:
        return None
    return _decode_buckets_payload(row[0])


def list_bucket_snapshots(cust_id: str) -> List[Dict[str, Any]]:
    """List all snapshots for this cust_id, newest first.

    Each entry: {id, snapshot_label, created_at, n_buckets, n_assets}.
    """
    init_bucket_assets_table()
    cid = _normalize_cust_id(cust_id)
    if not cid:
        return []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, snapshot_label, created_at, buckets_json FROM bucket_snapshots "
            "WHERE cust_id = ? ORDER BY created_at DESC, id DESC;",
            (cid,),
        ).fetchall()
    out: List[Dict[str, Any]] = []
    for _id, label, ts, payload in rows:
        defs = _decode_buckets_payload(payload) or []
        n_b = len(defs)
        n_a = sum(len(d.get("assets") or []) for d in defs)
        out.append(
            {
                "id": int(_id),
                "snapshot_label": label or "",
                "created_at": ts or "",
                "n_buckets": n_b,
                "n_assets": n_a,
            }
        )
    return out


def load_bucket_snapshot_by_id(snapshot_id: int) -> Optional[List[Dict[str, Any]]]:
    """Return a specific snapshot's buckets list, or None."""
    init_bucket_assets_table()
    try:
        sid = int(snapshot_id)
    except (TypeError, ValueError):
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT buckets_json FROM bucket_snapshots WHERE id = ? LIMIT 1;",
            (sid,),
        ).fetchone()
    if not row:
        return None
    return _decode_buckets_payload(row[0])


def clear_bucket_definitions(cust_id: str) -> int:
    """Delete ALL snapshots for this cust_id. Returns rows deleted."""
    init_bucket_assets_table()
    cid = _normalize_cust_id(cust_id)
    if not cid:
        return 0
    with _connect() as conn:
        cur = conn.execute("DELETE FROM bucket_snapshots WHERE cust_id = ?;", (cid,))
        conn.commit()
        return int(cur.rowcount or 0)


def has_saved_bucket_definitions(cust_id: str) -> bool:
    init_bucket_assets_table()
    cid = _normalize_cust_id(cust_id)
    if not cid:
        return False
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM bucket_snapshots WHERE cust_id = ? LIMIT 1;",
            (cid,),
        ).fetchone()
        return row is not None


def get_saved_bucket_meta(cust_id: str) -> Optional[Dict[str, Any]]:
    """Return the LATEST snapshot's meta:
    {"updated_at", "n_buckets", "n_assets", "snapshot_label", "n_snapshots"} or None.
    """
    init_bucket_assets_table()
    cid = _normalize_cust_id(cust_id)
    if not cid:
        return None
    with _connect() as conn:
        latest = conn.execute(
            "SELECT created_at, snapshot_label, buckets_json FROM bucket_snapshots "
            "WHERE cust_id = ? ORDER BY created_at DESC, id DESC LIMIT 1;",
            (cid,),
        ).fetchone()
        if not latest:
            return None
        total = conn.execute(
            "SELECT COUNT(*) FROM bucket_snapshots WHERE cust_id = ?;",
            (cid,),
        ).fetchone()
    ts, label, payload = latest
    defs = _decode_buckets_payload(payload) or []
    n_b = len(defs)
    n_a = sum(len(d.get("assets") or []) for d in defs)
    return {
        "updated_at": ts or "",
        "n_buckets": n_b,
        "n_assets": n_a,
        "snapshot_label": label or "",
        "n_snapshots": int(total[0]) if total else 0,
    }
