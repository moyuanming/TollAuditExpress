"""SQLite → Doris 一次性数据迁移脚本。

读 apps/api/data/audit.db, 全量 upsert 到 Doris ods_AI_DB。
保留原 SQLite 自增 id(显式传入), 保证 audit_results.audit_trip_id 等 FK 仍然有效。

用法:
  python -m apps.api.database.migrate_sqlite_to_doris          # 实际跑
  python -m apps.api.database.migrate_sqlite_to_doris --dry    # 只统计, 不写
  python -m apps.api.database.migrate_sqlite_to_doris --verify # 只做行数对比校验
"""

import argparse
import os
import sqlite3
import sys
from typing import Any, Dict, Iterable, List

import pymysql

# 让脚本可以独立运行
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from apps.api.core import config  # noqa: E402
from apps.api.database.doris_connection import get_connection  # noqa: E402

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "audit.db")


def _normalize(v: Any) -> Any:
    """SQLite 文本里的 None / 空串 / 'None' / 'null' 字符串统一规范成 NULL。"""
    if v is None:
        return None
    if isinstance(v, str):
        if v == "" or v.lower() in ("none", "null"):
            return None
    return v


def _row_to_insert(row: Dict[str, Any], cols: List[str]) -> tuple:
    return tuple(_normalize(row.get(c)) for c in cols)


def _fetch_all_sqlite(table: str) -> List[Dict[str, Any]]:
    if not os.path.exists(SQLITE_PATH):
        print(f"  [SKIP] SQLite file not found: {SQLITE_PATH}")
        return []
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT * FROM {table}")
        except sqlite3.OperationalError as e:
            print(f"  [SKIP] {table} does not exist in SQLite: {e}")
            return []
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _batch_insert(conn, sql: str, cols: List[str], rows: Iterable[Dict[str, Any]], batch_size: int = 500) -> int:
    """批量 upsert, 一次提交。"""
    cur = conn.cursor()
    params = [_row_to_insert(r, cols) for r in rows]
    n = 0
    for i in range(0, len(params), batch_size):
        chunk = params[i:i + batch_size]
        cur.executemany(sql, chunk)
        n += len(chunk)
    conn.commit()
    return n


def _count_doris(conn, table: str) -> int:
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
    return cur.fetchone()["c"]


def _migrate_scheduled_tasks(conn, dry: bool) -> int:
    rows = _fetch_all_sqlite("scheduled_tasks")
    if not rows:
        return 0
    cols = ["id", "name", "description", "task_type", "filter_rules", "schedule_type",
            "schedule_config", "enabled", "last_run_at", "next_run_at", "created_at", "updated_at"]
    placeholders = ", ".join(["%s"] * len(cols))
    sql = f"INSERT INTO scheduled_tasks ({', '.join(cols)}) VALUES ({placeholders})"
    if dry:
        return len(rows)
    return _batch_insert(conn, sql, cols, rows)


def _migrate_audit_trips(conn, dry: bool) -> int:
    rows = _fetch_all_sqlite("audit_trips")
    if not rows:
        return 0
    # passid 必须放第一列(Doris UNIQUE KEY 列必须在表首),id 作为兼容列保留 SQLite 自增
    cols = ["passid", "id", "entry_time", "entry_station_name", "entry_lane_id",
            "entry_vehicle_id", "entry_vehicle_type", "entry_vehicle_color",
            "entry_obu_id", "entry_media_type", "entry_image_license", "entry_image_trans",
            "exit_time", "exit_station_name", "exit_lane_id",
            "exit_vehicle_id", "exit_vehicle_type", "exit_vehicle_color",
            "exit_obu_id", "exit_media_type", "exit_image_license", "exit_image_trans",
            "gantry_count", "gantry_records", "audit_status", "risk_score",
            "entry_visual_type", "exit_visual_type", "fingerprint_sim",
            "created_at", "updated_at"]
    placeholders = ", ".join(["%s"] * len(cols))
    sql = f"INSERT INTO audit_trips ({', '.join(cols)}) VALUES ({placeholders})"
    if dry:
        return len(rows)
    return _batch_insert(conn, sql, cols, rows)


def _migrate_audit_results(conn, dry: bool) -> int:
    rows = _fetch_all_sqlite("audit_results")
    if not rows:
        return 0
    cols = ["id", "audit_trip_id", "fraud_type",
            "entry_vehicle_type", "entry_visual_type", "entry_color",
            "exit_vehicle_type", "exit_visual_type", "exit_color",
            "is_suspicious", "risk_score", "details", "process_status",
            "llm_is_same_vehicle", "llm_confidence", "llm_reason", "llm_model", "llm_checked_at",
            "created_at"]
    placeholders = ", ".join(["%s"] * len(cols))
    sql = f"INSERT INTO audit_results ({', '.join(cols)}) VALUES ({placeholders})"
    if dry:
        return len(rows)
    return _batch_insert(conn, sql, cols, rows)


def _migrate_audit_actions(conn, dry: bool) -> int:
    rows = _fetch_all_sqlite("audit_actions")
    if not rows:
        return 0
    cols = ["id", "result_id", "action", "operator", "comments", "created_at"]
    placeholders = ", ".join(["%s"] * len(cols))
    sql = f"INSERT INTO audit_actions ({', '.join(cols)}) VALUES ({placeholders})"
    if dry:
        return len(rows)
    return _batch_insert(conn, sql, cols, rows)


def _migrate_task_executions(conn, dry: bool) -> int:
    rows = _fetch_all_sqlite("task_executions")
    if not rows:
        return 0
    cols = ["id", "task_id", "status", "started_at", "completed_at", "result_summary",
            "error_message", "created_at"]
    placeholders = ", ".join(["%s"] * len(cols))
    sql = f"INSERT INTO task_executions ({', '.join(cols)}) VALUES ({placeholders})"
    if dry:
        return len(rows)
    return _batch_insert(conn, sql, cols, rows)


def verify() -> int:
    """只对比 SQLite 和 Doris 各表行数, 不写库。"""
    tables = ["scheduled_tasks", "audit_trips", "audit_results",
              "audit_actions", "task_executions"]
    print("=== Verify: SQLite vs Doris row counts ===")
    print(f"{'Table':<22} {'SQLite':>10} {'Doris':>10} {'OK?':>6}")
    print("-" * 52)
    all_ok = True
    with get_connection() as conn:
        for t in tables:
            sqlite_count = len(_fetch_all_sqlite(t))
            doris_count = _count_doris(conn, t)
            ok = "OK" if sqlite_count == doris_count else "DIFF"
            if ok != "OK":
                all_ok = False
            print(f"{t:<22} {sqlite_count:>10} {doris_count:>10} {ok:>6}")
    print("-" * 52)
    print("PASS" if all_ok else "FAIL — see DIFF rows")
    return 0 if all_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="只统计 SQLite 行数, 不写 Doris")
    parser.add_argument("--verify", action="store_true", help="只对比行数, 不迁移")
    args = parser.parse_args()

    if args.verify:
        return verify()

    print("=== Migrate SQLite → Doris ===")
    print(f"Source: {SQLITE_PATH}")
    print(f"Target: {config.DB_AUDIT_HOST}:{config.DB_AUDIT_PORT}/{config.DB_AUDIT_NAME}")
    print()

    steps = [
        ("scheduled_tasks", _migrate_scheduled_tasks),
        ("audit_trips",     _migrate_audit_trips),
        ("audit_results",   _migrate_audit_results),
        ("audit_actions",   _migrate_audit_actions),
        ("task_executions", _migrate_task_executions),
    ]

    if args.dry:
        print("[DRY-RUN]")
        for name, _fn in steps:
            n = len(_fetch_all_sqlite(name))
            print(f"  {name:<22} would migrate {n} rows")
        return 0

    with get_connection() as conn:
        for name, fn in steps:
            n = fn(conn, dry=False)
            print(f"  {name:<22} upserted {n} rows")

    print()
    print("=== Verify after migration ===")
    return verify()


if __name__ == "__main__":
    sys.exit(main())
