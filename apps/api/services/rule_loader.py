"""RuleLoader — 阶段 1 MVP 静态规则加载

行为：
  - load_all_enabled() 从 detection_rules 读 enabled=1 的行
  - rule_expr 字段是 JSON 字符串，解析为 dict
  - 解析失败的规则不抛错，跳过并记录到 load_errors
  - 阶段 2 升级为热加载（定时轮询 + 文件监听）
"""

import json
from typing import Any

from apps.api.database.doris_connection import get_connection


def _parse_rule_row(row: dict[str, Any]) -> dict[str, Any]:
    """把 DB 行解析为 rule dict。

    Raises:
        ValueError: rule_expr 不是合法 JSON
    """
    raw_expr = row.get("rule_expr")
    if not isinstance(raw_expr, str):
        raise ValueError(f"rule_expr must be a JSON string, got {type(raw_expr).__name__}")
    try:
        parsed_expr = json.loads(raw_expr)
    except json.JSONDecodeError as e:
        raise ValueError(f"rule_expr is not valid JSON: {e}") from e

    return {
        "id": row["id"],
        "name": row["name"],
        "fraud_type": row["fraud_type"],
        "severity": int(row.get("severity", 2) or 2),
        "description": row.get("description"),
        "rule_expr": parsed_expr,
        "threshold": float(row.get("threshold", 0.5) or 0.5),
        "dry_run": int(row.get("dry_run", 0) or 0),
        "enabled": int(row.get("enabled", 1) or 1),
        "source": row.get("source") or "manual",
    }


class RuleLoader:
    """从 Doris detection_rules 表加载规则。

    阶段 1：进程启动时同步加载一次。后续可在 load_errors 上接告警。
    """

    def __init__(self) -> None:
        self.load_errors: list[dict[str, Any]] = []

    def load_all_enabled(self) -> list[dict[str, Any]]:
        """读取所有 enabled=1 的规则；解析失败的跳过并记录。"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM detection_rules WHERE enabled = 1 ORDER BY id"
            )
            rows = cursor.fetchall()

        rules: list[dict[str, Any]] = []
        for row in rows:
            try:
                rule = _parse_rule_row(row)
            except (ValueError, KeyError) as e:
                self.load_errors.append(
                    {
                        "id": row.get("id"),
                        "name": row.get("name"),
                        "error": str(e),
                    }
                )
                continue
            rules.append(rule)
        return rules

    def load_all(self) -> list[dict[str, Any]]:
        """读取所有规则（含 disabled），用于 RuleStudio 后台展示。"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM detection_rules ORDER BY id")
            rows = cursor.fetchall()

        rules: list[dict[str, Any]] = []
        for row in rows:
            try:
                rules.append(_parse_rule_row(row))
            except (ValueError, KeyError) as e:
                self.load_errors.append(
                    {
                        "id": row.get("id"),
                        "name": row.get("name"),
                        "error": str(e),
                    }
                )
        return rules


def load_rules() -> list[dict[str, Any]]:
    """便捷函数：加载所有 enabled 规则并校验，供 task_executor 调用。"""
    from apps.api.core.logging_config import get_logger
    from apps.api.services.rule_engine import RuleValidationError, validate_rule
    _logger = get_logger(__name__)

    loader = RuleLoader()
    raw = loader.load_all_enabled()
    rules: list[dict[str, Any]] = []
    for r in raw:
        try:
            validate_rule(r)
            rules.append(r)
        except RuleValidationError as e:
            _logger.warning("Rule %d validation failed: %s", r.get("id"), e)
    _logger.info("Loaded %d/%d valid rules", len(rules), len(raw))
    return rules
