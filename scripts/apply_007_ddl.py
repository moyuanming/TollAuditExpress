#!/usr/bin/env python3
"""Apply 007_truck_obu_audit DDL to production Doris ods_AI_DB.

Reads credentials from .env (gitignored) and runs only the additive statements
for the new audit_truck_obu_daily_stats table + index on audit_results.
"""
import sys
from pathlib import Path

import pymysql
from dotenv import dotenv_values

ENV_PATH = Path(__file__).parent.parent / ".env"

# §007 的两段可重入 DDL（其他 DDL 已在生产库存在,避免误触）
TARGET_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS audit_truck_obu_daily_stats (
        date DATE NOT NULL,
        fraud_type VARCHAR(50) NOT NULL,
        scanned_count BIGINT NOT NULL DEFAULT 0,
        suspicious_count BIGINT NOT NULL DEFAULT 0,
        confirmed_count BIGINT NOT NULL DEFAULT 0,
        last_run_at DATETIME,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
    UNIQUE KEY(date, fraud_type)
    DISTRIBUTED BY HASH(fraud_type) BUCKETS 4
    PROPERTIES (
        "replication_num" = "1",
        "enable_unique_key_merge_on_write" = "true"
    )
    """,
    "ALTER TABLE audit_results ADD INDEX IF NOT EXISTS idx_results_type_created (fraud_type, created_at)",
]


def main():
    cfg = dotenv_values(ENV_PATH)
    host = cfg.get("DB_AUDIT_HOST")
    port = int(cfg.get("DB_AUDIT_PORT", "9030"))
    user = cfg.get("DB_AUDIT_USER")
    pwd = cfg.get("DB_AUDIT_PASSWORD", "")
    db = cfg.get("DB_AUDIT_NAME", "ods_AI_DB")
    if not (host and user):
        print("ERROR: missing DB_AUDIT_HOST/USER in .env", file=sys.stderr)
        sys.exit(2)

    print(f"Connecting to Doris {host}:{port} db={db} as {user}...")
    conn = pymysql.connect(
        host=host, port=port, user=user, password=pwd, database=db,
        connect_timeout=10, autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME FROM information_schema.tables "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='audit_truck_obu_daily_stats'",
                (db,),
            )
            exists_before = cur.fetchone() is not None
            print(f"  audit_truck_obu_daily_stats exists before: {exists_before}")

            for i, stmt in enumerate(TARGET_STATEMENTS, 1):
                first_line = stmt.strip().splitlines()[0][:80]
                print(f"  [{i}/{len(TARGET_STATEMENTS)}] {first_line}...")
                cur.execute(stmt)
                print("    done")

            cur.execute("DESCRIBE audit_truck_obu_daily_stats")
            cols = cur.fetchall()
            print(f"\n  audit_truck_obu_daily_stats columns ({len(cols)}):")
            for col in cols:
                print(f"    - {col[0]:20s} {col[1]:30s} null={col[2]} default={col[4]}")

            cur.execute(
                "SELECT INDEX_NAME, COLUMN_NAME, NON_UNIQUE "
                "FROM information_schema.statistics "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='audit_results' "
                "AND INDEX_NAME='idx_results_type_created'",
                (db,),
            )
            idx = cur.fetchall()
            print(f"\n  idx_results_type_created index rows: {len(idx)}")
            for r in idx:
                print(f"    - {r}")
    finally:
        conn.close()
    print("\nDDL applied successfully.")


if __name__ == "__main__":
    main()
