"""RuleLoader 单元测试 — 阶段 1 MVP 静态加载

行为契约：
  - load_all_enabled() 从 detection_rules 表读所有 enabled=1 的行
  - 行内 rule_expr 是 JSON 字符串，需要解析
  - enabled/dry_run 是 0/1 整数
  - 解析失败的规则被跳过（不抛错），并记录到 load_errors
"""

import json
import sqlite3
from unittest.mock import MagicMock, patch

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

    def test_raises_when_rule_expr_is_not_string(self):
        """rule_expr 不是字符串时直接抛 ValueError。"""
        with pytest.raises(ValueError, match="rule_expr must be a JSON string"):
            _parse_rule_row(
                {
                    "id": 3,
                    "name": "x",
                    "fraud_type": "OBU_SHIELD",
                    "rule_expr": {"already": "parsed"},
                }
            )

    def test_parses_with_default_values(self):
        """缺失可选字段时使用默认值"""
        row = {
            "id": 10,
            "name": "minimal",
            "fraud_type": "TRUCK_AS_CAR",
            "rule_expr": json.dumps({"when": True, "score": 0.5}),
        }
        rule = _parse_rule_row(row)
        assert rule["severity"] == 2
        assert rule["description"] is None
        assert rule["threshold"] == 0.5
        assert rule["dry_run"] == 0
        assert rule["enabled"] == 1
        assert rule["source"] == "manual"

    def test_parses_with_none_optional_fields(self):
        """可选字段为 None 时使用默认值"""
        row = {
            "id": 11,
            "name": "with_nones",
            "fraud_type": "OBU_SHIELD",
            "rule_expr": json.dumps({"when": True, "score": 0.5}),
            "severity": None,
            "threshold": None,
            "dry_run": None,
            "enabled": None,
            "source": None,
        }
        rule = _parse_rule_row(row)
        assert rule["severity"] == 2
        assert rule["threshold"] == 0.5
        assert rule["dry_run"] == 0
        assert rule["enabled"] == 1
        assert rule["source"] == "manual"

    def test_parses_description_field(self):
        row = {
            "id": 12,
            "name": "with_desc",
            "fraud_type": "OBU_SHIELD",
            "rule_expr": json.dumps({"when": True, "score": 0.5}),
            "description": "Detect OBU shield fraud",
        }
        rule = _parse_rule_row(row)
        assert rule["description"] == "Detect OBU shield fraud"

    def test_raises_on_missing_required_key(self):
        """缺少 id/name/fraud_type 等必需键时抛 KeyError"""
        row = {
            "rule_expr": json.dumps({"when": True, "score": 0.5}),
        }
        with pytest.raises(KeyError):
            _parse_rule_row(row)

    def test_parses_custom_source(self):
        row = {
            "id": 13,
            "name": "custom_source",
            "fraud_type": "OBU_SHIELD",
            "rule_expr": json.dumps({"when": True, "score": 0.5}),
            "source": "auto",
        }
        rule = _parse_rule_row(row)
        assert rule["source"] == "auto"


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

    def test_load_errors_cleared_on_new_loader(self, temp_db):
        """新 RuleLoader 实例不应继承旧的 load_errors"""
        _insert_raw_row(
            temp_db,
            id=1,
            name="bad",
            enabled=1,
            fraud_type="OBU_SHIELD",
            rule_expr_text="bad{",
        )
        loader1 = RuleLoader()
        loader1.load_all_enabled()
        assert len(loader1.load_errors) > 0

        loader2 = RuleLoader()
        assert loader2.load_errors == []

    def test_load_all_enabled_with_multiple_valid_rules(self, temp_db):
        _insert_rule(temp_db, id=1, name="r1", enabled=1, fraud_type="GATEWAY_ANOMALY")
        _insert_rule(temp_db, id=2, name="r2", enabled=1, fraud_type="OBU_SHIELD")
        _insert_rule(temp_db, id=3, name="r3", enabled=1, fraud_type="TRUCK_AS_CAR")

        loader = RuleLoader()
        rules = loader.load_all_enabled()
        assert len(rules) == 3

    def test_value_error_on_null_rule_expr_recorded_as_load_error(self, temp_db):
        """rule_expr 为 None 时触发 ValueError，记录到 load_errors"""
        # Cannot insert NULL for rule_expr (NOT NULL constraint),
        # so test with a row that has rule_expr as non-string type via raw SQL
        # Instead, verify that invalid JSON is properly recorded
        _insert_raw_row(
            temp_db,
            id=99,
            name="bad_expr",
            enabled=1,
            fraud_type="OBU_SHIELD",
            rule_expr_text="{{invalid}",
        )
        loader = RuleLoader()
        rules = loader.load_all_enabled()
        assert len(rules) == 0
        assert any(e["id"] == 99 for e in loader.load_errors)


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
            temp_db,
            id=5,
            name="broken",
            enabled=1,
            fraud_type="OBU_SHIELD",
            rule_expr_text="{not json",
        )
        loader = RuleLoader()
        rules = loader.load_all()
        assert rules == []
        assert loader.load_errors and loader.load_errors[0]["id"] == 5

    def test_load_all_returns_empty_when_table_empty(self, temp_db):
        loader = RuleLoader()
        assert loader.load_all() == []

    def test_load_all_includes_both_valid_and_invalid(self, temp_db):
        _insert_rule(temp_db, id=1, name="good", enabled=1, fraud_type="GATEWAY_ANOMALY")
        _insert_raw_row(
            temp_db,
            id=2,
            name="bad",
            enabled=0,
            fraud_type="OBU_SHIELD",
            rule_expr_text="not-json",
        )
        _insert_rule(temp_db, id=3, name="good2", enabled=0, fraud_type="TRUCK_AS_CAR")

        loader = RuleLoader()
        rules = loader.load_all()
        assert len(rules) == 2
        assert sorted(r["id"] for r in rules) == [1, 3]
        assert len(loader.load_errors) == 1


# ============================================================
# load_rules convenience function
# ============================================================


class TestLoadRulesFunction:
    def test_load_rules_skips_invalid_via_validate(self, temp_db):
        """load_rules() 走 RuleLoader + rule_engine.validate_rule,校验失败的跳过。"""
        _insert_rule(temp_db, id=1, name="valid", enabled=1, fraud_type="GATEWAY_ANOMALY")
        _insert_raw_row(
            temp_db,
            id=2,
            name="bad_json",
            enabled=1,
            fraud_type="OBU_SHIELD",
            rule_expr_text="not-json{",
        )
        rules = load_rules()
        assert [r["id"] for r in rules] == [1]

    def test_load_rules_skips_rule_with_invalid_fraud_type(self, temp_db):
        """fraud_type 不在白名单的规则被 validate_rule 拒绝"""
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "INSERT INTO detection_rules (id, name, fraud_type, rule_expr, enabled) VALUES (?, ?, ?, ?, ?)",
            (99, "bad_ft", "INVALID_TYPE", json.dumps({"when": True, "score": 0.5}), 1),
        )
        conn.commit()
        conn.close()

        rules = load_rules()
        assert not any(r["id"] == 99 for r in rules)

    def test_load_rules_returns_empty_when_no_rules(self, temp_db):
        rules = load_rules()
        assert rules == []

    def test_load_rules_returns_multiple_valid_rules(self, temp_db):
        _insert_rule(temp_db, id=1, name="r1", enabled=1, fraud_type="GATEWAY_ANOMALY")
        _insert_rule(temp_db, id=2, name="r2", enabled=1, fraud_type="OBU_SHIELD")
        rules = load_rules()
        assert len(rules) == 2


# ============================================================
# RuleLoader with mocked get_connection
# ============================================================


class TestRuleLoaderMockedConnection:
    """使用 mock 替代真实数据库连接的测试"""

    def test_load_all_enabled_with_mock_connection(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "name": "mocked-rule",
                "fraud_type": "GATEWAY_ANOMALY",
                "rule_expr": json.dumps({"when": True, "score": 0.7}),
                "threshold": 0.5,
                "dry_run": 0,
                "enabled": 1,
                "severity": 2,
                "source": "manual",
            },
        ]

        with patch("apps.api.services.rule_loader.get_connection", return_value=mock_conn):
            loader = RuleLoader()
            rules = loader.load_all_enabled()

        assert len(rules) == 1
        assert rules[0]["name"] == "mocked-rule"
        mock_cursor.execute.assert_called_once()
        assert "enabled = 1" in mock_cursor.execute.call_args[0][0]

    def test_load_all_with_mock_connection(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_cursor.fetchall.return_value = []

        with patch("apps.api.services.rule_loader.get_connection", return_value=mock_conn):
            loader = RuleLoader()
            rules = loader.load_all()

        assert rules == []
        mock_cursor.execute.assert_called_once()
        assert "ORDER BY id" in mock_cursor.execute.call_args[0][0]


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
