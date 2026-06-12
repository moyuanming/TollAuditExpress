"""RuleLoader 单元测试 — 阶段 1 MVP 静态加载

行为契约：
  - load_all_enabled() 从 detection_rules 表读所有 enabled=1 的行
  - 行内 rule_expr 是 JSON 字符串，需要解析
  - enabled/dry_run 是 0/1 整数
  - 解析失败的规则被跳过（不抛错），并记录到 load_errors
"""

import json
import sqlite3
from unittest.mock import patch

import pytest

from apps.api.services.rule_loader import RuleLoader, _parse_rule_row, load_rules


_RULE_DDL = """
CREATE TABLE IF NOT EXISTS detection_rules (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    fraud_type TEXT NOT NULL,
    severity INTEGER DEFAULT 2,
    description TEXT,
    rule_expr TEXT NOT NULL,
    threshold REAL DEFAULT 0.5,
    enabled INTEGER DEFAULT 1,
    dry_run INTEGER DEFAULT 0,
    source TEXT DEFAULT 'manual',
    created_at TEXT,
    updated_at TEXT
)
"""


# ============================================================
# _parse_rule_row
# ============================================================


class TestParseRuleRow:
    def test_parses_valid_row(self):
        row = {
            "id": 1,
            "name": "test-rule",
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": json.dumps({"when": ["eq", "$trip.x", 1], "score": 0.7}),
            "threshold": 0.5,
            "dry_run": 1,
            "enabled": 1,
            "severity": 2,
            "source": "manual",
        }
        rule = _parse_rule_row(row)
        assert rule["id"] == 1
        assert rule["name"] == "test-rule"
        assert rule["fraud_type"] == "GATEWAY_ANOMALY"
        assert rule["threshold"] == 0.5
        assert rule["dry_run"] == 1
        assert rule["enabled"] == 1
        assert rule["rule_expr"]["when"] == ["eq", "$trip.x", 1]

    def test_raises_on_invalid_json_expr(self):
        row = {
            "id": 2,
            "name": "bad",
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": "not-json{",
            "threshold": 0.5,
            "dry_run": 0,
            "enabled": 1,
        }
        with pytest.raises(ValueError):
            _parse_rule_row(row)


# ============================================================
# RuleLoader class
# ============================================================


class TestRuleLoader:
    def test_load_all_enabled_filters_disabled(self, temp_db):
        _insert_rule(temp_db, id=1, name="r1", enabled=1, fraud_type="GATEWAY_ANOMALY")
        _insert_rule(temp_db, id=2, name="r2", enabled=0, fraud_type="OBU_SHIELD")
        _insert_rule(temp_db, id=3, name="r3", enabled=1, fraud_type="OBU_SHIELD")

        loader = RuleLoader()
        rules = loader.load_all_enabled()
        ids = sorted(r["id"] for r in rules)
        assert ids == [1, 3]

    def test_load_all_enabled_returns_empty_when_table_empty(self, temp_db):
        loader = RuleLoader()
        assert loader.load_all_enabled() == []

    def test_invalid_rule_excluded_with_error_recorded(self, temp_db):
        _insert_rule(temp_db, id=1, name="good", enabled=1, fraud_type="GATEWAY_ANOMALY")
        _insert_raw_row(
            temp_db,
            id=2,
            name="bad",
            enabled=1,
            fraud_type="OBU_SHIELD",
            rule_expr_text="not-json{",
        )
        loader = RuleLoader()
        rules = loader.load_all_enabled()
        assert len(rules) == 1
        assert rules[0]["id"] == 1
        assert any("bad" in e["name"] for e in loader.load_errors)


class TestParseRuleRowEdgeCases:
    def test_raises_when_rule_expr_is_not_string(self):
        """rule_expr 不是字符串时直接抛 ValueError。"""
        with pytest.raises(ValueError, match="rule_expr must be a JSON string"):
            _parse_rule_row({
                "id": 3, "name": "x", "fraud_type": "OBU_SHIELD",
                "rule_expr": {"already": "parsed"},
            })


class TestLoadAll:
    def test_returns_all_rules_including_disabled(self, temp_db):
        _insert_rule(temp_db, id=1, name="r1", enabled=1, fraud_type="GATEWAY_ANOMALY")
        _insert_rule(temp_db, id=2, name="r2", enabled=0, fraud_type="OBU_SHIELD")

        loader = RuleLoader()
        rules = loader.load_all()
        ids = sorted(r["id"] for r in rules)
        assert ids == [1, 2]

    def test_records_load_errors_for_invalid_rows(self, temp_db):
        _insert_raw_row(
            temp_db, id=5, name="broken", enabled=1,
            fraud_type="OBU_SHIELD", rule_expr_text="{not json",
        )
        loader = RuleLoader()
        rules = loader.load_all()
        assert rules == []
        assert loader.load_errors and loader.load_errors[0]["id"] == 5


class TestLoadRulesFunction:
    def test_load_rules_skips_invalid_via_validate(self, temp_db):
        """load_rules() 走 RuleLoader + rule_engine.validate_rule,校验失败的跳过。"""
        _insert_rule(temp_db, id=1, name="valid", enabled=1, fraud_type="GATEWAY_ANOMALY")
        _insert_raw_row(
            temp_db, id=2, name="bad_json", enabled=1,
            fraud_type="OBU_SHIELD", rule_expr_text="not-json{",
        )
        rules = load_rules()
        assert [r["id"] for r in rules] == [1]


# ============================================================
# helpers
# ============================================================


def _insert_rule(temp_db_path, id, name, enabled, fraud_type, threshold=0.5, dry_run=0, score=0.5):
    conn = sqlite3.connect(temp_db_path)
    conn.executescript(_RULE_DDL)
    conn.execute(
        "INSERT INTO detection_rules (id, name, fraud_type, rule_expr, threshold, dry_run, enabled) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            id,
            name,
            fraud_type,
            json.dumps({"when": True, "score": score}),
            threshold,
            dry_run,
            enabled,
        ),
    )
    conn.commit()
    conn.close()


def _insert_raw_row(temp_db_path, id, name, enabled, fraud_type, rule_expr_text):
    conn = sqlite3.connect(temp_db_path)
    conn.executescript(_RULE_DDL)
    conn.execute(
        "INSERT INTO detection_rules (id, name, fraud_type, rule_expr, threshold, dry_run, enabled) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (id, name, fraud_type, rule_expr_text, 0.5, 0, enabled),
    )
    conn.commit()
    conn.close()
