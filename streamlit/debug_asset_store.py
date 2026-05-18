"""
Terminal debug script — ตรวจสอบว่า asset config ถูกบันทึกลง DB จริงไหม

Usage (จากโฟลเดอร์ที่มี data.db):
    python3 debug_asset_store.py                # summary ทุก cust_id
    python3 debug_asset_store.py <cust_id>      # รายละเอียดของ cust_id นั้น
    python3 debug_asset_store.py <cust_id> --json   # dump JSON snapshot ล่าสุด
    python3 debug_asset_store.py --db /path/to/data.db <cust_id>

วาง script นี้ในโฟลเดอร์เดียวกับ data.db (หรือใช้ flag --db ชี้ path) แล้ว
run ผ่าน terminal เพื่อดูว่า bucket_snapshots มีข้อมูลอะไรบ้าง.
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime


def _resolve_db_path(cli_path: str | None) -> str:
    """หา data.db: priority = CLI flag > env var > co-located กับ script > CWD"""
    if cli_path:
        return os.path.abspath(cli_path)
    env_path = os.environ.get("WEALTH_KIDS_DB_PATH")
    if env_path:
        return os.path.abspath(env_path)
    here = os.path.dirname(os.path.abspath(__file__))
    co_located = os.path.join(here, "data.db")
    if os.path.exists(co_located):
        return co_located
    cwd_path = os.path.join(os.getcwd(), "data.db")
    return cwd_path


def _connect(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        print(f"❌ ไม่พบไฟล์ DB: {db_path}")
        print("   ลองระบุ path ผ่าน --db /path/to/data.db")
        sys.exit(1)
    return sqlite3.connect(db_path)


def cmd_summary(db_path: str) -> None:
    """แสดง overview: tables ที่มี + จำนวน snapshot ต่อ cust_id"""
    print(f"📂 DB: {db_path}")
    print(f"   ขนาดไฟล์: {os.path.getsize(db_path):,} bytes")
    print()

    with _connect(db_path) as conn:
        tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
            ).fetchall()
        ]
        print(f"📋 Tables: {tables}")
        print()

        if "bucket_snapshots" not in tables:
            print("⚠️  ตาราง bucket_snapshots ยังไม่ถูกสร้าง")
            print("   → ไม่มีการบันทึก asset config เลย (ยังไม่เคย save)")
            return

        total = conn.execute("SELECT COUNT(*) FROM bucket_snapshots;").fetchone()[0]
        print(f"🗃️  bucket_snapshots: {total} rows ทั้งหมด")
        print()

        if total == 0:
            print("⚠️  ไม่มี snapshot ใดๆ ในตาราง")
            print("   → user ยังไม่เคยกด 💾 บันทึก asset config หรือ run MC สำเร็จ")
            return

        rows = conn.execute(
            """
            SELECT cust_id,
                   COUNT(*)          AS n,
                   MAX(created_at)   AS latest,
                   MIN(created_at)   AS oldest
            FROM bucket_snapshots
            GROUP BY cust_id
            ORDER BY latest DESC;
            """
        ).fetchall()

    print(f"👥 พบ {len(rows)} cust_id ที่มี asset config บันทึกไว้:")
    print()
    print(f"  {'cust_id':<20} {'snapshots':>10} {'latest':<20} {'oldest':<20}")
    print(f"  {'-'*20} {'-'*10} {'-'*20} {'-'*20}")
    for cid, n, latest, oldest in rows:
        print(f"  {str(cid):<20} {n:>10} {str(latest):<20} {str(oldest):<20}")
    print()
    print("💡 ดูรายละเอียด: python3 debug_asset_store.py <cust_id>")


def cmd_detail(db_path: str, cust_id: str, dump_json: bool) -> None:
    """แสดง snapshot ทั้งหมดของ cust_id เดียว"""
    print(f"📂 DB: {db_path}")
    print(f"🔍 cust_id: {cust_id}")
    print()

    with _connect(db_path) as conn:
        tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        ]
        if "bucket_snapshots" not in tables:
            print("⚠️  ตาราง bucket_snapshots ยังไม่ถูกสร้าง")
            return

        rows = conn.execute(
            """
            SELECT id, snapshot_label, buckets_json, created_at
            FROM bucket_snapshots
            WHERE cust_id = ?
            ORDER BY created_at DESC, id DESC;
            """,
            (cust_id.strip(),),
        ).fetchall()

    if not rows:
        print(f"⚠️  ไม่พบ snapshot สำหรับ cust_id={cust_id!r}")
        print("   ลอง: python3 debug_asset_store.py (ไม่ใส่ argument) เพื่อดู cust_id ที่มี")
        return

    print(f"✅ พบ {len(rows)} snapshot:")
    print()

    for i, (snap_id, label, payload, created_at) in enumerate(rows):
        marker = "🟢 LATEST" if i == 0 else f"   #{i+1}"
        print(f"{marker}  snapshot_id={snap_id}  created_at={created_at}")
        print(f"         label: {label or '(no label)'}")

        try:
            defs = json.loads(payload)
        except Exception as e:
            print(f"         ❌ JSON parse error: {e}")
            continue

        if not isinstance(defs, list):
            print(f"         ⚠️  payload ไม่ใช่ list: type={type(defs).__name__}")
            continue

        print(f"         {len(defs)} bucket:")
        for b in defs:
            if not isinstance(b, dict):
                print(f"           - (bucket ไม่ใช่ dict: {type(b).__name__})")
                continue
            b_name = b.get("name", "?")
            b_ys = b.get("year_start", "?")
            b_ye = b.get("year_end")
            b_ye_str = "∞" if b_ye is None else str(b_ye)
            b_dr = b.get("discount_rate", 0.0)
            assets = b.get("assets") or []
            print(f"           - {b_name!r}: ปี {b_ys}–{b_ye_str}, "
                  f"discount_rate={float(b_dr):.2%}, {len(assets)} asset")
            for a in assets:
                if not isinstance(a, dict):
                    continue
                print(f"               • {a.get('asset_name', '?'):<20} "
                      f"weight={a.get('weight_pct', 0):>5.1f}%  "
                      f"mean={a.get('mean_pct', 0):>5.2f}%  "
                      f"std={a.get('std_pct', 0):>5.2f}%  "
                      f"range=[{a.get('min_pct', 0):>5.1f}%, {a.get('max_pct', 0):>5.1f}%]")
        print()

    if dump_json and rows:
        print("=" * 60)
        print("📄 JSON payload ของ snapshot ล่าสุด:")
        print("=" * 60)
        try:
            pretty = json.dumps(json.loads(rows[0][2]), ensure_ascii=False, indent=2)
            print(pretty)
        except Exception as e:
            print(f"❌ format ไม่ได้: {e}")
            print(rows[0][2])


def main():
    parser = argparse.ArgumentParser(
        description="ตรวจสอบ asset config ที่บันทึกใน data.db (bucket_snapshots table)"
    )
    parser.add_argument("cust_id", nargs="?", help="cust_id ที่ต้องการดูรายละเอียด (ว่าง = summary)")
    parser.add_argument("--db", help="path ไปยัง data.db (default: co-located หรือ CWD)")
    parser.add_argument("--json", action="store_true",
                        help="dump JSON payload เต็มของ snapshot ล่าสุด")
    args = parser.parse_args()

    db_path = _resolve_db_path(args.db)

    if args.cust_id:
        cmd_detail(db_path, args.cust_id, dump_json=args.json)
    else:
        cmd_summary(db_path)


if __name__ == "__main__":
    main()
