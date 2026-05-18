# """
# SQLite-backed storage for user simulation drafts.

# Each call to save_draft() inserts a NEW row, so history is preserved.
# load_latest_draft() returns the most recent row for a given cust_id.

# Draft values can include dates, ints, floats, bools, strs, None.
# We serialize them as a JSON list of [field, type, value] triples so types
# round-trip cleanly.
# """
# import os
# import sqlite3
# import json
# from datetime import date, datetime
# from typing import Optional, Dict, Any, List


# # Place the DB file next to this module so it persists across reruns.
# _DB_PATH = os.environ.get(
#     "WEALTH_KIDS_DB_PATH",
#     os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db"),
# )

# # Retention: keep at most this many snapshots per cust_id.
# KEEP_PER_CUST_ID = 10


# def _connect() -> sqlite3.Connection:
#     conn = sqlite3.connect(_DB_PATH)
#     conn.execute("PRAGMA journal_mode=WAL;")
#     return conn


# def init_db() -> None:
#     """Create the simulations table if it doesn't exist, and migrate legacy
#     schemas (those without a staff_id column) by adding the column in place."""
#     with _connect() as conn:
#         conn.execute(
#             """
#             CREATE TABLE IF NOT EXISTS simulations (
#                 id          INTEGER PRIMARY KEY AUTOINCREMENT,
#                 cust_id     TEXT    NOT NULL,
#                 staff_id    TEXT,
#                 created_at  TEXT    NOT NULL,
#                 draft_json  TEXT    NOT NULL
#             );
#             """
#         )
#         # Migrate: add staff_id column for DBs created before this change.
#         cols = {row[1] for row in conn.execute("PRAGMA table_info(simulations);").fetchall()}
#         if "staff_id" not in cols:
#             conn.execute("ALTER TABLE simulations ADD COLUMN staff_id TEXT;")
#         conn.execute(
#             "CREATE INDEX IF NOT EXISTS idx_simulations_cust_id_created "
#             "ON simulations (cust_id, created_at DESC);"
#         )
#         conn.execute(
#             "CREATE INDEX IF NOT EXISTS idx_simulations_staff_id "
#             "ON simulations (staff_id);"
#         )
#         conn.commit()


# # ------------------------------------------------------------
# # Type-aware (de)serialization for draft values
# # ------------------------------------------------------------
# def _serialize_value(v: Any):
#     if v is None:
#         return ["null", None]
#     if isinstance(v, date) and not isinstance(v, datetime):
#         return ["date", v.isoformat()]
#     if isinstance(v, datetime):
#         return ["datetime", v.isoformat()]
#     if isinstance(v, bool):
#         return ["bool", v]
#     if isinstance(v, int):
#         return ["int", v]
#     if isinstance(v, float):
#         return ["float", v]
#     if isinstance(v, str):
#         return ["str", v]
#     if isinstance(v, (list, dict)):
#         # JSON-encode complex containers (e.g. inv_bucket_definitions) so
#         # they round-trip cleanly. Previously these fell through to str(v),
#         # which stored a Python repr that could not be parsed back.
#         return ["json", json.dumps(v, ensure_ascii=False)]
#     # Fallback: store its repr as a string
#     return ["str", str(v)]


# def _deserialize_value(type_str: str, value: Any) -> Any:
#     if type_str == "null":
#         return None
#     if type_str == "date":
#         return date.fromisoformat(value)
#     if type_str == "datetime":
#         return datetime.fromisoformat(value)
#     if type_str == "bool":
#         return bool(value)
#     if type_str == "int":
#         return int(value)
#     if type_str == "float":
#         return float(value)
#     if type_str == "json":
#         return json.loads(value)
#     # Legacy rows: a list/dict that was saved with the old fallback path
#     # arrives here as a Python repr string. Try to recover via literal_eval
#     # so old drafts don't silently revert to PARAM_DEFAULTS on load.
#     if type_str == "str" and isinstance(value, str):
#         _s = value.lstrip()
#         if _s.startswith("[") or _s.startswith("{"):
#             try:
#                 import ast as _ast
#                 return _ast.literal_eval(value)
#             except Exception:
#                 pass
#     return value  # str or unknown


# def _draft_to_json(draft: Dict[str, Any]) -> str:
#     payload = []
#     for k in sorted(draft.keys()):
#         type_str, value = _serialize_value(draft[k])
#         payload.append([k, type_str, value])
#     return json.dumps(payload, ensure_ascii=False)


# def _json_to_draft(draft_json: str) -> Dict[str, Any]:
#     payload = json.loads(draft_json)
#     out: Dict[str, Any] = {}
#     for row in payload:
#         if not isinstance(row, list) or len(row) < 3:
#             continue
#         field, type_str, value = row[0], row[1], row[2]
#         try:
#             out[field] = _deserialize_value(type_str, value)
#         except Exception:
#             out[field] = value
#     return out


# # ------------------------------------------------------------
# # Public API
# # ------------------------------------------------------------
# def save_draft(cust_id: str, draft: Dict[str, Any], staff_id: Optional[str] = None) -> int:
#     """
#     Insert a new draft snapshot and prune old snapshots so that this
#     cust_id keeps at most KEEP_PER_CUST_ID rows.

#     The insert and prune happen in the same transaction so the table
#     never exceeds the cap, even under concurrent writes.

#     Returns the new row id.
#     """
#     init_db()
#     cust_id = str(cust_id).strip()
#     if not cust_id:
#         raise ValueError("cust_id is required")
#     staff_id_clean = str(staff_id).strip() if staff_id is not None else None
#     if staff_id_clean == "":
#         staff_id_clean = None
#     created_at = datetime.now().isoformat(timespec="seconds")
#     payload = _draft_to_json(draft)
#     with _connect() as conn:
#         cur = conn.execute(
#             "INSERT INTO simulations (cust_id, staff_id, created_at, draft_json) "
#             "VALUES (?, ?, ?, ?);",
#             (cust_id, staff_id_clean, created_at, payload),
#         )
#         new_id = int(cur.lastrowid)

#         # Keep only the latest KEEP_PER_CUST_ID rows for this cust_id.
#         # Uses the (cust_id, created_at DESC) index for both the keep-set
#         # subquery and the outer scan.
#         conn.execute(
#             """
#             DELETE FROM simulations
#             WHERE cust_id = ?
#               AND id NOT IN (
#                   SELECT id FROM simulations
#                   WHERE cust_id = ?
#                   ORDER BY created_at DESC, id DESC
#                   LIMIT ?
#               );
#             """,
#             (cust_id, cust_id, KEEP_PER_CUST_ID),
#         )
#         conn.commit()
#         return new_id


# def prune_cust_id(cust_id: str, keep: int = KEEP_PER_CUST_ID) -> int:
#     """
#     Manually prune snapshots for a cust_id, keeping only the latest `keep` rows.
#     Returns the number of rows deleted. Useful for one-off cleanup.
#     """
#     init_db()
#     cust_id = str(cust_id).strip()
#     if not cust_id:
#         return 0
#     if keep < 0:
#         raise ValueError("keep must be >= 0")
#     with _connect() as conn:
#         cur = conn.execute(
#             """
#             DELETE FROM simulations
#             WHERE cust_id = ?
#               AND id NOT IN (
#                   SELECT id FROM simulations
#                   WHERE cust_id = ?
#                   ORDER BY created_at DESC, id DESC
#                   LIMIT ?
#               );
#             """,
#             (cust_id, cust_id, keep),
#         )
#         conn.commit()
#         return int(cur.rowcount or 0)


# def has_previous_data(cust_id: str) -> bool:
#     """True if any saved draft exists for this cust_id."""
#     init_db()
#     cust_id = str(cust_id).strip()
#     if not cust_id:
#         return False
#     with _connect() as conn:
#         row = conn.execute(
#             "SELECT 1 FROM simulations WHERE cust_id = ? LIMIT 1;",
#             (cust_id,),
#         ).fetchone()
#         return row is not None


# def load_latest_draft(cust_id: str) -> Optional[Dict[str, Any]]:
#     """Return the most recent draft dict for this cust_id, or None."""
#     init_db()
#     cust_id = str(cust_id).strip()
#     if not cust_id:
#         return None
#     with _connect() as conn:
#         row = conn.execute(
#             "SELECT draft_json FROM simulations "
#             "WHERE cust_id = ? ORDER BY created_at DESC, id DESC LIMIT 1;",
#             (cust_id,),
#         ).fetchone()
#         if not row:
#             return None
#         return _json_to_draft(row[0])


# def get_latest_meta(cust_id: str) -> Optional[Dict[str, Any]]:
#     """Return {id, created_at, staff_id} for the latest record, or None."""
#     init_db()
#     cust_id = str(cust_id).strip()
#     if not cust_id:
#         return None
#     with _connect() as conn:
#         row = conn.execute(
#             "SELECT id, created_at, staff_id FROM simulations "
#             "WHERE cust_id = ? ORDER BY created_at DESC, id DESC LIMIT 1;",
#             (cust_id,),
#         ).fetchone()
#         if not row:
#             return None
#         return {"id": int(row[0]), "created_at": row[1], "staff_id": row[2] or ""}


# def list_snapshots(cust_id: str) -> List[Dict[str, Any]]:
#     """Return all snapshots for a cust_id, newest first.

#     Each item: {"id": int, "created_at": str, "n_fields": int, "staff_id": str}.
#     """
#     init_db()
#     cust_id = str(cust_id).strip()
#     if not cust_id:
#         return []
#     with _connect() as conn:
#         rows = conn.execute(
#             "SELECT id, created_at, draft_json, staff_id FROM simulations "
#             "WHERE cust_id = ? ORDER BY created_at DESC, id DESC;",
#             (cust_id,),
#         ).fetchall()
#     out: List[Dict[str, Any]] = []
#     for rid, created_at, draft_json, staff_id in rows:
#         try:
#             n_fields = len(json.loads(draft_json) or [])
#         except Exception:
#             n_fields = 0
#         out.append({
#             "id": int(rid),
#             "created_at": created_at,
#             "n_fields": n_fields,
#             "staff_id": staff_id or "",
#         })
#     return out


# def load_snapshot_by_id(snapshot_id: int) -> Optional[Dict[str, Any]]:
#     """Return the draft dict for a specific snapshot row id, or None."""
#     init_db()
#     try:
#         sid = int(snapshot_id)
#     except Exception:
#         return None
#     with _connect() as conn:
#         row = conn.execute(
#             "SELECT draft_json FROM simulations WHERE id = ? LIMIT 1;",
#             (sid,),
#         ).fetchone()
#         if not row:
#             return None
#         return _json_to_draft(row[0])


# def list_all_cust_ids() -> List[Dict[str, Any]]:
#     """Return all distinct cust_ids with snapshot count, latest timestamp,
#     and the staff_id of the most-recent snapshot."""
#     init_db()
#     with _connect() as conn:
#         rows = conn.execute(
#             """
#             SELECT s.cust_id,
#                    COUNT(*)              AS n,
#                    MAX(s.created_at)     AS latest,
#                    (SELECT s2.staff_id
#                       FROM simulations s2
#                      WHERE s2.cust_id = s.cust_id
#                      ORDER BY s2.created_at DESC, s2.id DESC
#                      LIMIT 1)            AS latest_staff_id
#             FROM simulations s
#             GROUP BY s.cust_id
#             ORDER BY latest DESC;
#             """
#         ).fetchall()
#     return [
#         {
#             "cust_id": r[0],
#             "n_snapshots": int(r[1]),
#             "latest": r[2],
#             "latest_staff_id": r[3] or "",
#         }
#         for r in rows
#     ]


# def count_records(cust_id: str) -> int:
#     """How many saved snapshots exist for this cust_id."""
#     init_db()
#     cust_id = str(cust_id).strip()
#     if not cust_id:
#         return 0
#     with _connect() as conn:
#         row = conn.execute(
#             "SELECT COUNT(*) FROM simulations WHERE cust_id = ?;",
#             (cust_id,),
#         ).fetchone()
#         return int(row[0]) if row else 0
"""
Supabase-backed storage for user simulation drafts.

Replaces the SQLite implementation. Public API is preserved so callers
(sections.py, pages/02_Expense_Simulation.py, pages/03_Investment_Planning.py,
pages/05_Saved_Snapshots.py) do not need any changes.

Configuration
-------------
Reads Supabase credentials from Streamlit secrets or env vars.

.streamlit/secrets.toml (any of these layouts works):

    [supabase]
    url = "https://<project>.supabase.co"
    key = "<service-role-key>"

    # or
    SUPABASE_URL = "..."
    SUPABASE_KEY = "..."

Env var fallback: SUPABASE_URL, SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY).

Schema
------
Create once via Supabase SQL Editor:

    create table simulations (
        id          bigserial primary key,
        cust_id     text not null,
        staff_id    text,
        created_at  timestamptz not null default now(),
        draft_json  jsonb not null
    );
    create index idx_simulations_cust_created on simulations (cust_id, created_at desc);
    create index idx_simulations_staff_id     on simulations (staff_id);
"""
import json
import os
from datetime import date, datetime
from typing import Optional, Dict, Any, List, Tuple

from supabase import create_client, Client


# Retention: keep at most this many snapshots per cust_id.
KEEP_PER_CUST_ID = 10

_TABLE = "simulations"
_client: Optional[Client] = None


# ------------------------------------------------------------
# Supabase client
# ------------------------------------------------------------
def _get_credentials() -> Tuple[str, str]:
    """Locate (url, key) from Streamlit secrets or env vars."""
    url = None
    key = None

    try:
        import streamlit as st  # lazy import — avoid hard dep at import time
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


def init_db() -> None:
    """Schema lives in Supabase; this is a no-op kept for API compatibility."""
    return None


# ------------------------------------------------------------
# Type-aware (de)serialization for draft values
# (Preserved so old SQLite drafts migrated into jsonb still round-trip.)
# ------------------------------------------------------------
def _serialize_value(v: Any):
    if v is None:
        return ["null", None]
    if isinstance(v, date) and not isinstance(v, datetime):
        return ["date", v.isoformat()]
    if isinstance(v, datetime):
        return ["datetime", v.isoformat()]
    if isinstance(v, bool):
        return ["bool", v]
    if isinstance(v, int):
        return ["int", v]
    if isinstance(v, float):
        return ["float", v]
    if isinstance(v, str):
        return ["str", v]
    if isinstance(v, (list, dict)):
        return ["json", json.dumps(v, ensure_ascii=False)]
    return ["str", str(v)]


def _deserialize_value(type_str: str, value: Any) -> Any:
    if type_str == "null":
        return None
    if type_str == "date":
        return date.fromisoformat(value)
    if type_str == "datetime":
        return datetime.fromisoformat(value)
    if type_str == "bool":
        return bool(value)
    if type_str == "int":
        return int(value)
    if type_str == "float":
        return float(value)
    if type_str == "json":
        return json.loads(value)
    if type_str == "str" and isinstance(value, str):
        _s = value.lstrip()
        if _s.startswith("[") or _s.startswith("{"):
            try:
                import ast as _ast
                return _ast.literal_eval(value)
            except Exception:
                pass
    return value


def _draft_to_payload(draft: Dict[str, Any]) -> List[List[Any]]:
    """Type-tagged list, stored natively as jsonb in Supabase."""
    payload = []
    for k in sorted(draft.keys()):
        type_str, value = _serialize_value(draft[k])
        payload.append([k, type_str, value])
    return payload


def _payload_to_draft(payload: Any) -> Dict[str, Any]:
    """Accepts a parsed list OR a JSON string (legacy rows)."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return {}
    out: Dict[str, Any] = {}
    if not isinstance(payload, list):
        return out
    for row in payload:
        if not isinstance(row, list) or len(row) < 3:
            continue
        field, type_str, value = row[0], row[1], row[2]
        try:
            out[field] = _deserialize_value(type_str, value)
        except Exception:
            out[field] = value
    return out


# ------------------------------------------------------------
# Internal: prune
# ------------------------------------------------------------
def _prune_simulations(cust_id: str, keep: int, client: Optional[Client] = None) -> int:
    """Keep the latest `keep` rows for this cust_id; delete the rest."""
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
def save_draft(cust_id: str, draft: Dict[str, Any], staff_id: Optional[str] = None) -> int:
    """Insert a new draft snapshot and prune older snapshots beyond KEEP_PER_CUST_ID.
    Returns the new row id."""
    cust_id = str(cust_id).strip()
    if not cust_id:
        raise ValueError("cust_id is required")
    staff_id_clean = str(staff_id).strip() if staff_id is not None else None
    if staff_id_clean == "":
        staff_id_clean = None

    payload = _draft_to_payload(draft)
    client = _get_client()
    res = (
        client.table(_TABLE)
        .insert({
            "cust_id": cust_id,
            "staff_id": staff_id_clean,
            "draft_json": payload,  # jsonb-native
        })
        .execute()
    )
    if not res.data:
        raise RuntimeError("Supabase insert returned no row")
    new_id = int(res.data[0]["id"])

    _prune_simulations(cust_id, KEEP_PER_CUST_ID, client=client)
    return new_id


def prune_cust_id(cust_id: str, keep: int = KEEP_PER_CUST_ID) -> int:
    cust_id = str(cust_id).strip()
    if not cust_id:
        return 0
    if keep < 0:
        raise ValueError("keep must be >= 0")
    return _prune_simulations(cust_id, keep)


def has_previous_data(cust_id: str) -> bool:
    cust_id = str(cust_id).strip()
    if not cust_id:
        return False
    client = _get_client()
    res = (
        client.table(_TABLE)
        .select("id")
        .eq("cust_id", cust_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def load_latest_draft(cust_id: str) -> Optional[Dict[str, Any]]:
    cust_id = str(cust_id).strip()
    if not cust_id:
        return None
    client = _get_client()
    res = (
        client.table(_TABLE)
        .select("draft_json")
        .eq("cust_id", cust_id)
        .order("created_at", desc=True)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return _payload_to_draft(res.data[0]["draft_json"])


def get_latest_meta(cust_id: str) -> Optional[Dict[str, Any]]:
    cust_id = str(cust_id).strip()
    if not cust_id:
        return None
    client = _get_client()
    res = (
        client.table(_TABLE)
        .select("id,created_at,staff_id")
        .eq("cust_id", cust_id)
        .order("created_at", desc=True)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    r = res.data[0]
    return {
        "id": int(r["id"]),
        "created_at": r["created_at"],
        "staff_id": r.get("staff_id") or "",
    }


def list_snapshots(cust_id: str) -> List[Dict[str, Any]]:
    """All snapshots for a cust_id, newest first.
    Each item: {"id", "created_at", "n_fields", "staff_id"}."""
    cust_id = str(cust_id).strip()
    if not cust_id:
        return []
    client = _get_client()
    res = (
        client.table(_TABLE)
        .select("id,created_at,draft_json,staff_id")
        .eq("cust_id", cust_id)
        .order("created_at", desc=True)
        .order("id", desc=True)
        .execute()
    )
    out: List[Dict[str, Any]] = []
    for r in res.data or []:
        payload = r.get("draft_json")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = []
        n_fields = len(payload) if isinstance(payload, list) else 0
        out.append({
            "id": int(r["id"]),
            "created_at": r.get("created_at") or "",
            "n_fields": n_fields,
            "staff_id": r.get("staff_id") or "",
        })
    return out


def load_snapshot_by_id(snapshot_id: int) -> Optional[Dict[str, Any]]:
    try:
        sid = int(snapshot_id)
    except Exception:
        return None
    client = _get_client()
    res = (
        client.table(_TABLE)
        .select("draft_json")
        .eq("id", sid)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return _payload_to_draft(res.data[0]["draft_json"])


def list_all_cust_ids() -> List[Dict[str, Any]]:
    """All distinct cust_ids with snapshot count, latest timestamp,
    and the staff_id of the most-recent snapshot."""
    client = _get_client()
    res = (
        client.table(_TABLE)
        .select("cust_id,staff_id,created_at")
        .order("created_at", desc=True)
        .order("id", desc=True)
        .execute()
    )
    by_cust: Dict[str, Dict[str, Any]] = {}
    for r in res.data or []:
        cid = r["cust_id"]
        if cid not in by_cust:
            by_cust[cid] = {
                "cust_id": cid,
                "n_snapshots": 0,
                "latest": r.get("created_at") or "",
                "latest_staff_id": r.get("staff_id") or "",
            }
        by_cust[cid]["n_snapshots"] += 1
    return sorted(by_cust.values(), key=lambda x: x["latest"], reverse=True)


def count_records(cust_id: str) -> int:
    cust_id = str(cust_id).strip()
    if not cust_id:
        return 0
    client = _get_client()
    res = (
        client.table(_TABLE)
        .select("id", count="exact")
        .eq("cust_id", cust_id)
        .execute()
    )
    return int(res.count or 0)
