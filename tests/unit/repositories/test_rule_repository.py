"""RuleRepository 单元测试 — 阶段 1 MVP

行为契约：
  - list_rules() 全表扫描，order by id
  - list_rules(enabled_only=True) 过滤 enabled=1
  - get_rule(id) 不存在时返回 None
  - create_rule 必须传 name/fraud_type/rule_expr_json，其它可选
  - update_rule 接收 partial dict（None 表示不更新）
  - delete_rule 返回是否真删除了一行
  - toggle_enabled / set_dry_run 是便利方法
"""

import json

import pytest

from apps.api.database.repositories.rule_repository import RuleRepository


# ============================================================
# fixtures & helpers
# ============================================================


@pytest.fixture
def repo(temp_db):
    return RuleRepository()


def _sample_rule_dict(**overrides):
    base = {
        "name": "test-rule",
        "fraud_type": "GATEWAY_ANOMALY",
        "rule_expr": json.dumps({"when": ["gt", "$trip.gantry_count", 3], "score": 0.7}),
        "threshold": 0.5,
        "dry_run": 1,
        "enabled": 1,
        "severity": 2,
        "description": "test description",
        "source": "manual",
    }
    base.update(overrides)
    return base


# ============================================================
# list_rules
# ============================================================


class TestListRules:
    def test_returns_empty_list_when_no_rules(self, repo):
        assert repo.list_rules() == []

    def test_lists_all_rules(self, repo):
        repo.create_rule(_sample_rule_dict(name="r1"))
        repo.create_rule(_sample_rule_dict(name="r2"))
        rules = repo.list_rules()
        assert len(rules) == 2
        names = sorted(r["name"] for r in rules)
        assert names == ["r1", "r2"]

    def test_enabled_only_filter(self, repo):
        repo.create_rule(_sample_rule_dict(name="on", enabled=1))
        repo.create_rule(_sample_rule_dict(name="off", enabled=0))
        enabled = repo.list_rules(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0]["name"] == "on"


# ============================================================
# get_rule
# ============================================================


class TestGetRule:
    def test_returns_none_for_missing_id(self, repo):
        assert repo.get_rule(999) is None

    def test_returns_rule_by_id(self, repo):
        rid = repo.create_rule(_sample_rule_dict(name="r1"))
        rule = repo.get_rule(rid)
        assert rule is not None
        assert rule["id"] == rid
        assert rule["name"] == "r1"
        assert rule["fraud_type"] == "GATEWAY_ANOMALY"
        assert isinstance(rule["rule_expr"], dict)
        assert rule["rule_expr"]["when"] == ["gt", "$trip.gantry_count", 3]


# ============================================================
# create_rule
# ============================================================


class TestCreateRule:
    def test_creates_with_minimal_fields(self, repo):
        minimal = {
            "name": "min",
            "fraud_type": "OBU_SHIELD",
            "rule_expr": json.dumps({"when": True, "score": 0.5}),
        }
        rid = repo.create_rule(minimal)
        assert isinstance(rid, int)
        rule = repo.get_rule(rid)
        assert rule["name"] == "min"
        assert rule["threshold"] == 0.5
        assert rule["enabled"] == 1

    def test_raises_when_required_field_missing(self, repo):
        with pytest.raises(ValueError):
            repo.create_rule({"name": "x"})


# ============================================================
# update_rule
# ============================================================


class TestUpdateRule:
    def test_updates_specified_fields(self, repo):
        rid = repo.create_rule(_sample_rule_dict(name="orig", threshold=0.5))
        ok = repo.update_rule(rid, {"name": "renamed", "threshold": 0.9})
        assert ok is True
        rule = repo.get_rule(rid)
        assert rule["name"] == "renamed"
        assert rule["threshold"] == 0.9

    def test_returns_false_for_missing_id(self, repo):
        assert repo.update_rule(999, {"name": "x"}) is False

    def test_ignores_none_values(self, repo):
        rid = repo.create_rule(_sample_rule_dict(name="keep", threshold=0.5))
        repo.update_rule(rid, {"name": None, "threshold": 0.8})
        rule = repo.get_rule(rid)
        assert rule["name"] == "keep"
        assert rule["threshold"] == 0.8


# ============================================================
# delete_rule
# ============================================================


class TestDeleteRule:
    def test_deletes_existing_rule(self, repo):
        rid = repo.create_rule(_sample_rule_dict(name="del"))
        assert repo.delete_rule(rid) is True
        assert repo.get_rule(rid) is None

    def test_returns_false_for_missing_id(self, repo):
        assert repo.delete_rule(999) is False


# ============================================================
# convenience methods
# ============================================================


class TestToggleAndDryRun:
    def test_toggle_enabled(self, repo):
        rid = repo.create_rule(_sample_rule_dict(enabled=1))
        assert repo.toggle_enabled(rid, False) is True
        assert repo.get_rule(rid)["enabled"] == 0
        assert repo.toggle_enabled(rid, True) is True
        assert repo.get_rule(rid)["enabled"] == 1

    def test_set_dry_run(self, repo):
        rid = repo.create_rule(_sample_rule_dict(dry_run=0))
        assert repo.set_dry_run(rid, 1) is True
        assert repo.get_rule(rid)["dry_run"] == 1
