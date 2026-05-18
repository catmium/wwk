"""
One-shot migration of legacy SQLite data.db rows into Supabase.

Usage
-----
1. Make sure Supabase URL/key are set in .streamlit/secrets.toml or env vars,
   OR pass them on the command line.
2. From the streamlit/ directory, run:

       python migrate_sqlite_to_supabase.py [--db PATH] [--secrets PATH] [--dry-run]
       python migrate_sqlite_to_supabase.py --url https://... --key eyJ... [--dry-run]

3. Script reads from data.db, writes to Supabase, and prints a summary.

Credential lookup order
-----------------------
1. CLI args:        --url and --key
2. Env vars:        SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY)
3. TOML file:       --secrets PATH (defaults to scanning parent dirs for .streamlit/secrets.toml)

Notes
-----
- Preserves `created_at` and `staff_id` from the original rows.
- Existing Supabase rows are left untouched — re-running this script will
  create duplicates, so run once and then rename/delete data.db.
- Use --dry-run first to see how many rows will be migrated.
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from supabase import create_client, Client


# ---------- TOML loader (stdlib on Py3.11+, fallback to tomli) ----------
def _load_toml(path: Path) -> dict:
    try:
        import tomllib  # Python 3.11+
        with open(path, "rb") as f:
            return tomllib.load(f)
    except ModuleNotFoundError:
        try:
            import tomli
            with open(path, "rb") as f:
                return tomli.load(f)
        except ModuleNotFoundError:
            # Last resort: very small subset parser for flat key=value and [section]
            return _parse_toml_fallback(path)


def _parse_toml_fallback(path: Path) -> dict:
    """Minimal parser for [section] key = "value" lines. Good enough for secrets.toml."""
    out: Dict[str, Any] = {}
    current: Dict[str, Any] = out
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip()
                current = out.setdefault(section, {})
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                current[k] = v
    return out


def _find_secrets_file(start: Path, explicit: Optional[Path]) -> Optional[Path]:
    if explicit:
        return explicit if explicit.exists() else None
    # Walk up looking for .streamlit/secrets.toml
    for parent in [start, *start.parents]:
        candidate = parent / ".streamlit" / "secrets.toml"
        if candidate.exists():
            return candidate
    return None


def _credentials_from_toml(secrets: dict) -> Tuple[Optional[str], Optional[str]]:
    url = None
    key = None
    if isinstance(secrets, dict):
        sub = secrets.get("supabase")
        if isinstance(sub, dict):
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
    return url, key


def _resolve_credentials(
    cli_url: Optional[str],
    cli_key: Optional[str],
    secrets_path: Optional[Path],
    script_dir: Path,
) -> Tuple[str, str]:
    # 1. CLI args
    url, key = cli_url, cli_key

    # 2. Env vars
    if not url:
        url = os.environ.get("SUPABASE_URL")
    if not key:
        key = (
            os.environ.get("SUPABASE_KEY")
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        )

    # 3. TOML file
    if not url or not key:
        found = _find_secrets_file(script_dir, secrets_path)
        if found:
            print(f"  reading credentials from: {found}")
            try:
                secrets = _load_toml(found)
            except Exception as e:
                print(f"  failed to parse {found}: {e}")
                secrets = {}
            t_url, t_key = _credentials_from_toml(secrets)
            url = url or t_url
            key = key or t_key
        else:
            print("  no .streamlit/secrets.toml found in parent directories")

    if not url or not key:
        raise RuntimeError(
            "Supabase credentials missing.\n"
            "Tried (in order):\n"
            "  1. CLI args --url / --key\n"
            "  2. env vars SUPABASE_URL / SUPABASE_KEY\n"
            "  3. .streamlit/secrets.toml in script dir or parents\n"
            "\n"
            "Either pass them on the command line:\n"
            '  python migrate_sqlite_to_supabase.py --url "https://...supabase.co" --key "eyJ..."\n'
            "\n"
            "Or point at your secrets file:\n"
            '  python migrate_sqlite_to_supabase.py --secrets ".streamlit/secrets.toml"\n'
            "\n"
            "Expected secrets.toml layout:\n"
            "  [supabase]\n"
            '  url = "https://<project>.supabase.co"\n'
            '  key = "<service-role-key>"'
        )
    return str(url), str(key)


# ---------- SQLite reader ----------
def _decode_json(value: Any) -> Any:
    """SQLite stored JSON columns as strings; decode to native list/dict so
    Supabase stores them as jsonb objects rather than jsonb-wrapped strings."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def migrate_simulations(sqlite_path: str, client: Optional[Client], dry_run: bool) -> int:
    if not Path(sqlite_path).exists():
        print(f"  [simulations] {sqlite_path} not found — skipping")
        return 0
    with sqlite3.connect(sqlite_path) as conn:
        try:
            rows = conn.execute(
                "SELECT cust_id, staff_id, created_at, draft_json "
                "FROM simulations ORDER BY id ASC;"
            ).fetchall()
        except sqlite3.OperationalError:
            # Legacy DB without staff_id column
            try:
                raw = conn.execute(
                    "SELECT cust_id, created_at, draft_json FROM simulations ORDER BY id ASC;"
                ).fetchall()
                rows = [(c, None, t, d) for (c, t, d) in raw]
            except sqlite3.OperationalError:
                print("  [simulations] table missing — skipping")
                return 0

    if not rows:
        print("  [simulations] no rows")
        return 0

    batch: List[Dict[str, Any]] = []
    for cust_id, staff_id, created_at, draft_json in rows:
        batch.append({
            "cust_id": str(cust_id),
            "staff_id": staff_id or None,
            "created_at": created_at,
            "draft_json": _decode_json(draft_json),
        })

    print(f"  [simulations] {len(batch)} rows to insert")
    if dry_run or client is None:
        return len(batch)

    inserted = 0
    chunk = 100
    for i in range(0, len(batch), chunk):
        part = batch[i:i + chunk]
        client.table("simulations").insert(part).execute()
        inserted += len(part)
        print(f"    inserted {inserted}/{len(batch)}")
    return inserted


def migrate_bucket_snapshots(sqlite_path: str, client: Optional[Client], dry_run: bool) -> int:
    if not Path(sqlite_path).exists():
        print(f"  [bucket_snapshots] {sqlite_path} not found — skipping")
        return 0
    with sqlite3.connect(sqlite_path) as conn:
        try:
            rows = conn.execute(
                "SELECT cust_id, snapshot_label, buckets_json, created_at "
                "FROM bucket_snapshots ORDER BY id ASC;"
            ).fetchall()
        except sqlite3.OperationalError:
            print("  [bucket_snapshots] table missing — skipping")
            return 0

    if not rows:
        print("  [bucket_snapshots] no rows")
        return 0

    batch: List[Dict[str, Any]] = []
    for cust_id, label, buckets_json, created_at in rows:
        batch.append({
            "cust_id": str(cust_id),
            "snapshot_label": label or None,
            "buckets_json": _decode_json(buckets_json),
            "created_at": created_at,
        })

    print(f"  [bucket_snapshots] {len(batch)} rows to insert")
    if dry_run or client is None:
        return len(batch)

    inserted = 0
    chunk = 100
    for i in range(0, len(batch), chunk):
        part = batch[i:i + chunk]
        client.table("bucket_snapshots").insert(part).execute()
        inserted += len(part)
        print(f"    inserted {inserted}/{len(batch)}")
    return inserted


def main():
    script_dir = Path(__file__).parent.resolve()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        default=str(script_dir / "data.db"),
        help="Path to data.db (default: ./data.db next to this script)",
    )
    parser.add_argument(
        "--secrets",
        default=None,
        help="Path to secrets.toml (default: walk up to find .streamlit/secrets.toml)",
    )
    parser.add_argument("--url", default=None, help="Supabase project URL (overrides toml/env)")
    parser.add_argument("--key", default=None, help="Supabase API key (overrides toml/env)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read SQLite and resolve credentials, but don't write to Supabase",
    )
    args = parser.parse_args()

    print(f"Source SQLite: {args.db}")
    print(f"Dry run: {args.dry_run}")
    print("Resolving Supabase credentials...")
    url, key = _resolve_credentials(
        cli_url=args.url,
        cli_key=args.key,
        secrets_path=Path(args.secrets) if args.secrets else None,
        script_dir=script_dir,
    )
    print(f"  url: {url}")
    print(f"  key: {key[:8]}...{key[-4:]} (length={len(key)})")

    client: Optional[Client] = None if args.dry_run else create_client(url, key)

    print("\nMigrating simulations...")
    n1 = migrate_simulations(args.db, client, args.dry_run)
    print("\nMigrating bucket_snapshots...")
    n2 = migrate_bucket_snapshots(args.db, client, args.dry_run)

    print("\nDone.")
    print(f"  simulations:      {n1} rows")
    print(f"  bucket_snapshots: {n2} rows")


if __name__ == "__main__":
    sys.exit(main() or 0)
