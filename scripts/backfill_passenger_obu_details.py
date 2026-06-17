"""
客车OBU异常记录 details JSON 回填脚本

回填字段:
  - llm_call_status: 设为 "unknown"（旧记录无法追溯实际调用状态）
  - entry_image_trans: 从 audit_trips.entry_image_trans 补入
  - exit_image_trans:  从 audit_trips.exit_image_trans 补入

用法:
  docker exec toll-audit-express python scripts/backfill_passenger_obu_details.py [--dry-run]

Doris 不支持单条 UPDATE 带 JOIN，采用分批策略:
  1. SELECT 需回填的记录 (audit_results JOIN audit_trips)
  2. 在 Python 中合并 details JSON
  3. 分批 UPDATE audit_results SET details=... WHERE id=...
"""

import argparse
import json
import sys

sys.path.insert(0, "/app")

from apps.api.database.doris_connection import get_connection

FRAUD_TYPE = "PASSENGER_USES_TRUCK_OBU_NON_NEW_A"
BATCH_SIZE = 50  # Doris UPDATE 批次


def main():
    parser = argparse.ArgumentParser(description="回填客车OBU details JSON 缺失字段")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不执行 UPDATE")
    args = parser.parse_args()

    with get_connection() as conn:
        cur = conn.cursor()

        # 1. 查询所有需要回填的记录
        cur.execute(
            """
            SELECT ar.id, ar.details, at.entry_image_trans, at.exit_image_trans
            FROM audit_results ar
            JOIN audit_trips at ON ar.audit_trip_id = at.id
            WHERE ar.fraud_type = %s
            ORDER BY ar.id
            """,
            (FRAUD_TYPE,),
        )
        rows = cur.fetchall()

    total = len(rows)
    need_backfill = 0
    already_ok = 0
    updates = []  # (id, new_details_json)

    for row in rows:
        details = json.loads(row["details"])
        entry_img = row["entry_image_trans"]
        exit_img = row["exit_image_trans"]

        # 检查是否需要回填
        missing_llm = "llm_call_status" not in details
        missing_entry_img = "entry_image_trans" not in details and entry_img is not None
        missing_exit_img = "exit_image_trans" not in details and exit_img is not None

        if not (missing_llm or missing_entry_img or missing_exit_img):
            already_ok += 1
            continue

        need_backfill += 1

        # 合并字段
        if missing_llm:
            details["llm_call_status"] = "unknown"
        if missing_entry_img:
            details["entry_image_trans"] = entry_img
        if missing_exit_img:
            details["exit_image_trans"] = exit_img

        updates.append((row["id"], json.dumps(details, ensure_ascii=False)))

    print(f"总记录数: {total}")
    print(f"已完整:   {already_ok}")
    print(f"需回填:   {need_backfill}")

    if not updates:
        print("\n无需回填，退出。")
        return

    if args.dry_run:
        print(f"\n[dry-run] 将回填 {len(updates)} 条记录，不执行 UPDATE。")
        # 抽样展示
        for uid, udetails in updates[:3]:
            d = json.loads(udetails)
            print(f"  ID={uid}: llm_call_status={d.get('llm_call_status')}, "
                  f"entry_img={'Y' if d.get('entry_image_trans') else 'N'}, "
                  f"exit_img={'Y' if d.get('exit_image_trans') else 'N'}")
        if len(updates) > 3:
            print(f"  ... 共 {len(updates)} 条")
        return

    # 2. 分批 UPDATE
    with get_connection() as conn:
        cur = conn.cursor()
        done = 0
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i : i + BATCH_SIZE]
            for uid, udetails in batch:
                cur.execute(
                    "UPDATE audit_results SET details = %s WHERE id = %s",
                    (udetails, uid),
                )
            conn.commit()
            done += len(batch)
            print(f"  进度: {done}/{len(updates)}")

    print(f"\n✅ 回填完成: {done} 条记录已更新。")


if __name__ == "__main__":
    main()
