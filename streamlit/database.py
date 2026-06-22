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
