"""detection_rules 数据访问层 — 阶段 1 MVP

与 RuleLoader 的关系：
  - RuleLoader 是只读静态加载（带错误收集，规则调度用）
  - RuleRepository 是 CRUD 后台管理（RuleStudio 页面用）
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from apps.api.database.doris_connection import get_connection

_BEIJING_TZ = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(_BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


class RuleRepository:
    """detection_rules 表 CRUD"""

    REQUIRED_FIELDS = ("name", "fraud_type", "rule_expr")
    _WRITEABLE_FIELDS = (
        "name",
        "fraud_type",
        "severity",
        "description",
        "rule_expr",
        "threshold",
        "dry_run",
        "enabled",
        "source",
    )

    def list_rules(self, enabled_only: bool = False) -> list[dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            sql = "SELECT * FROM detection_rules"
            if enabled_only:
                sql += " WHERE enabled = 1"
            sql += " ORDER BY id"
            cursor.execute(sql)
            rows = cursor.fetchall()
        return [self._deserialize(row) for row in rows]

    def get_rule(self, rule_id: int) -> dict | None:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM detection_rules WHERE id = %s", (rule_id,))
            row = cursor.fetchone()
        return self._deserialize(row) if row else None

    def create_rule(self, data: dict) -> int:
        for field in self.REQUIRED_FIELDS:
            if field not in data or data[field] in (None, ""):
                raise ValueError(f"missing required field: {field}")

        with get_connection() as conn:
            cursor = conn.cursor()
            now = _now()
            rule_expr_str = self._serialize_expr(data["rule_expr"])
            cursor.execute(
                """
                INSERT INTO detection_rules
                    (name, fraud_type, severity, description, rule_expr,
                     threshold, dry_run, enabled, source, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    data["name"],
                    data["fraud_type"],
                    int(data.get("severity", 2) or 2),
                    data.get("description"),
                    rule_expr_str,
                    float(data.get("threshold", 0.5) or 0.5),
                    1 if data.get("dry_run") else 0,
                    1 if data.get("enabled", 1) else 0,
                    data.get("source") or "manual",
                    now,
                    now,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def update_rule(self, rule_id: int, updates: dict) -> bool:
        fields = []
        values = []
        for key in self._WRITEABLE_FIELDS:
            if key not in updates:
                continue
            value = updates[key]
            if value is None:
                continue
            if key == "rule_expr":
                value = self._serialize_expr(value)
            if key in ("dry_run", "enabled"):
                value = 1 if value else 0
            if key in ("threshold",):
                value = float(value)
            if key in ("severity",):
                value = int(value)
            fields.append(f"{key} = %s")
            values.append(value)

        if not fields:
            return False

        fields.append("updated_at = %s")
        values.append(_now())
        values.append(rule_id)

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE detection_rules SET {', '.join(fields)} WHERE id = %s",
                values,
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_rule(self, rule_id: int) -> bool:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM detection_rules WHERE id = %s", (rule_id,))
            conn.commit()
            return cursor.rowcount > 0

    def toggle_enabled(self, rule_id: int, enabled: int) -> bool:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE detection_rules SET enabled = %s, updated_at = %s WHERE id = %s",
                (1 if enabled else 0, _now(), rule_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def set_dry_run(self, rule_id: int, dry_run: int) -> bool:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE detection_rules SET dry_run = %s, updated_at = %s WHERE id = %s",
                (1 if dry_run else 0, _now(), rule_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------
    # 序列化辅助
    # ------------------------------------------------------------

    @staticmethod
    def _serialize_expr(value: Any) -> str:
        """rule_expr 入库前转 JSON 字符串（接受 dict 或已序列化字符串）。"""
        if isinstance(value, str):
            json.loads(value)
            return value
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _deserialize(row: dict[str, Any]) -> dict[str, Any]:
        """DB 行 → dict；rule_expr 反序列化为 dict。"""
        out = dict(row)
        raw = out.get("rule_expr")
        if isinstance(raw, str):
            try:
                out["rule_expr"] = json.loads(raw)
            except json.JSONDecodeError:
                pass
        return out
