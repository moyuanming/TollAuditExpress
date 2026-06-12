"""RuleEngine 单元测试 — 阶段 1 MVP 规则引擎骨架

DSL 设计：JSON s-expression 表达式
  when:  ["and", ["eq", "$trip.field", value], ...]
  score: ["add", ["mul", "$trip.field", 0.3], 0.5]
  threshold: 0.5

安全性：使用受限 AST 解析，禁止 eval / import / 函数调用 / 任意属性访问
"""

import pytest

from apps.api.services.rule_engine import (
    RuleEngine,
    RuleExprError,
    RuleValidationError,
    evaluate_condition,
    evaluate_rule,
    evaluate_score,
    validate_rule,
)


# ============================================================
# validate_rule
# ============================================================


class TestValidateRule:
    """规则结构校验 — 拒绝非法/危险 DSL"""

    def test_accepts_minimal_valid_rule(self):
        rule = {
            "id": 1,
            "name": "test",
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": json_when_score(),
        }
        validate_rule(rule)  # 不抛

    def test_rejects_non_dict_rule(self):
        with pytest.raises(RuleValidationError):
            validate_rule("not a dict")

    def test_rejects_missing_required_fields(self):
        with pytest.raises(RuleValidationError):
            validate_rule({"id": 1})

    def test_rejects_invalid_fraud_type(self):
        rule = {"id": 1, "name": "t", "fraud_type": "INVALID", "rule_expr": json_when_score()}
        with pytest.raises(RuleValidationError):
            validate_rule(rule)

    def test_rejects_invalid_threshold_range(self):
        expr = json_when_score()
        with pytest.raises(RuleValidationError):
            validate_rule({"id": 1, "name": "t", "fraud_type": "GATEWAY_ANOMALY", "rule_expr": expr, "threshold": 1.5})

    def test_rejects_non_json_rule_expr(self):
        rule = {"id": 1, "name": "t", "fraud_type": "GATEWAY_ANOMALY", "rule_expr": "not a dict"}
        with pytest.raises(RuleValidationError):
            validate_rule(rule)

    def test_rejects_rule_expr_without_when_or_score(self):
        rule = {"id": 1, "name": "t", "fraud_type": "GATEWAY_ANOMALY", "rule_expr": {"foo": "bar"}}
        with pytest.raises(RuleValidationError):
            validate_rule(rule)

    def test_accepts_all_mvp_fraud_types(self):
        for ft in (
            "TRUCK_AS_CAR",
            "ENTRY_EXIT_MISMATCH",
            "GATEWAY_ANOMALY",
            "VEHICLE_TYPE_DOWNGRADE",
            "SAME_PLATE_DIFF_VEHICLE",
            "OBU_UNBIND",
            "OBU_SHIELD",
        ):
            rule = {
                "id": 1,
                "name": f"rule-{ft}",
                "fraud_type": ft,
                "rule_expr": json_when_score(),
            }
            validate_rule(rule)


# ============================================================
# evaluate_condition
# ============================================================


class TestEvaluateCondition:
    """when 表达式求值 — 布尔结果"""

    def test_eq_returns_true_on_match(self):
        trip = {"gantry_count": 5}
        assert evaluate_condition(["eq", "$trip.gantry_count", 5], trip) is True

    def test_eq_returns_false_on_mismatch(self):
        trip = {"gantry_count": 3}
        assert evaluate_condition(["eq", "$trip.gantry_count", 5], trip) is False

    def test_ne_returns_true_on_mismatch(self):
        trip = {"gantry_count": 3}
        assert evaluate_condition(["ne", "$trip.gantry_count", 5], trip) is True

    def test_gt_and_lt(self):
        trip = {"x": 10}
        assert evaluate_condition(["gt", "$trip.x", 5], trip) is True
        assert evaluate_condition(["lt", "$trip.x", 5], trip) is False
        assert evaluate_condition(["gte", "$trip.x", 10], trip) is True
        assert evaluate_condition(["lte", "$trip.x", 10], trip) is True

    def test_and_combines_conditions(self):
        trip = {"a": 1, "b": 2}
        assert evaluate_condition(["and", ["eq", "$trip.a", 1], ["eq", "$trip.b", 2]], trip) is True
        assert evaluate_condition(["and", ["eq", "$trip.a", 1], ["eq", "$trip.b", 99]], trip) is False

    def test_or_combines_conditions(self):
        trip = {"a": 1, "b": 99}
        assert evaluate_condition(["or", ["eq", "$trip.a", 1], ["eq", "$trip.b", 2]], trip) is True
        # both branches False (a=1 != 99, b=99 != 2) → OR is False
        assert evaluate_condition(["or", ["eq", "$trip.a", 99], ["eq", "$trip.b", 2]], trip) is False

    def test_not_negates(self):
        trip = {"a": 1}
        assert evaluate_condition(["not", ["eq", "$trip.a", 99]], trip) is True
        assert evaluate_condition(["not", ["eq", "$trip.a", 1]], trip) is False

    def test_in_operator(self):
        trip = {"color": "blue"}
        assert evaluate_condition(["in", "$trip.color", ["blue", "red"]], trip) is True
        assert evaluate_condition(["in", "$trip.color", ["yellow"]], trip) is False

    def test_nested_logical_expression(self):
        trip = {"a": 1, "b": 2, "c": 3}
        expr = [
            "or",
            ["and", ["eq", "$trip.a", 1], ["eq", "$trip.b", 2]],
            ["eq", "$trip.c", 99],
        ]
        assert evaluate_condition(expr, trip) is True

    def test_missing_field_returns_none_for_eq(self):
        # 设计：缺失字段视为"无证据"，eq 判 False（不命中），不会抛错
        trip = {}
        assert evaluate_condition(["eq", "$trip.gantry_count", 5], trip) is False

    def test_unknown_operator_raises(self):
        trip = {"a": 1}
        with pytest.raises(RuleExprError):
            evaluate_condition(["__import__", "$trip.a"], trip)

    def test_rejects_function_call_form(self):
        trip = {"a": 1}
        # eval() 类调用必须被禁止
        with pytest.raises(RuleExprError):
            evaluate_condition(["call", "eval", "$trip.a"], trip)

    def test_string_field_comparison(self):
        trip = {"plate": "京A12345"}
        assert evaluate_condition(["eq", "$trip.plate", "京A12345"], trip) is True

    def test_literal_true_false(self):
        assert evaluate_condition(True, {}) is True
        assert evaluate_condition(False, {}) is False

    def test_null_field_treated_as_none(self):
        trip = {"plate": None}
        assert evaluate_condition(["eq", "$trip.plate", "京A"], trip) is False
        assert evaluate_condition(["eq", "$trip.plate", None], trip) is True

    def test_count_helper(self):
        # ["count", "$trip.list_field"] 返回列表长度
        trip = {"records": [1, 2, 3, 4]}
        assert evaluate_condition(["gt", ["count", "$trip.records"], 3], trip) is True
        assert evaluate_condition(["lt", ["count", "$trip.records"], 3], trip) is False


# ============================================================
# evaluate_score
# ============================================================


class TestEvaluateScore:
    """score 表达式求值 — 数值结果"""

    def test_literal_number(self):
        assert evaluate_score(0.7, {}) == 0.7
        assert evaluate_score(0, {}) == 0

    def test_field_access(self):
        trip = {"gantry_count": 5}
        assert evaluate_score("$trip.gantry_count", trip) == 5

    def test_add_expression(self):
        trip = {"a": 0.3, "b": 0.4}
        assert evaluate_score(["add", "$trip.a", "$trip.b"], trip) == pytest.approx(0.7)

    def test_mul_expression(self):
        trip = {"a": 0.5, "b": 0.4}
        assert evaluate_score(["mul", "$trip.a", "$trip.b"], trip) == pytest.approx(0.2)

    def test_complex_arithmetic(self):
        trip = {"skip": 3, "speed": 50}
        # skip * 0.2 + 0.3
        expr = ["add", ["mul", "$trip.skip", 0.2], 0.3]
        assert evaluate_score(expr, trip) == pytest.approx(0.9)

    def test_score_clamped_to_zero_one(self):
        # evaluate_score 不做限幅（DSL 内部可访问任意数值），限幅在 evaluate_rule 中
        trip = {"x": 5}
        assert evaluate_score(["mul", "$trip.x", 100], trip) == 500.0
        # 通过 evaluate_rule 限幅到 [0, 1]
        rule_over = {
            "id": 1,
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": {"when": True, "score": ["mul", "$trip.x", 100]},
        }
        assert evaluate_rule(rule_over, trip)["risk_score"] == 1.0
        rule_under = {
            "id": 2,
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": {"when": True, "score": ["mul", "$trip.x", -1]},
        }
        assert evaluate_rule(rule_under, trip)["risk_score"] == 0.0


# ============================================================
# evaluate_rule
# ============================================================


class TestEvaluateRule:
    """完整规则评估 — 返回 result dict 或 None"""

    def test_returns_none_when_condition_false(self):
        rule = {
            "id": 7,
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": {
                "when": ["gt", "$trip.gantry_count", 10],
                "score": 0.8,
            },
        }
        trip = {"gantry_count": 3}
        assert evaluate_rule(rule, trip) is None

    def test_returns_result_dict_when_condition_true(self):
        rule = {
            "id": 7,
            "fraud_type": "GATEWAY_ANOMALY",
            "threshold": 0.9,  # 抬高阈值使 score 0.8 未达线
            "rule_expr": {
                "when": ["gt", "$trip.gantry_count", 3],
                "score": 0.8,
            },
        }
        trip = {"gantry_count": 5}
        result = evaluate_rule(rule, trip)
        assert result is not None
        assert result["rule_id"] == 7
        assert result["fraud_type"] == "GATEWAY_ANOMALY"
        assert result["risk_score"] == pytest.approx(0.8)
        assert result["is_suspicious"] == 0  # score=0.8 < threshold=0.9 → 未达线

    def test_threshold_filtering_marks_suspicious(self):
        rule = {
            "id": 8,
            "fraud_type": "OBU_SHIELD",
            "threshold": 0.6,
            "rule_expr": {
                "when": ["eq", "$trip.has_no_obu", True],
                "score": 0.9,
            },
        }
        trip = {"has_no_obu": True}
        result = evaluate_rule(rule, trip)
        assert result["is_suspicious"] == 1
        assert result["risk_score"] == 0.9

    def test_dry_run_always_zero_suspicious(self):
        rule = {
            "id": 9,
            "fraud_type": "OBU_SHIELD",
            "dry_run": 1,
            "threshold": 0.1,
            "rule_expr": {
                "when": True,
                "score": 0.9,
            },
        }
        trip = {}
        result = evaluate_rule(rule, trip)
        assert result["is_suspicious"] == 0
        assert result["dry_run"] == 1


# ============================================================
# RuleEngine class
# ============================================================


def _build_rule(rule_id, fraud_type, when_expr, score=0.8, threshold=0.5, dry_run=0, enabled=1):
    return {
        "id": rule_id,
        "name": f"rule-{rule_id}",
        "fraud_type": fraud_type,
        "threshold": threshold,
        "dry_run": dry_run,
        "enabled": enabled,
        "rule_expr": {"when": when_expr, "score": score},
    }


class TestRuleEngine:
    """RuleEngine 类 — 注册规则、批量执行"""

    def test_register_and_run_single_rule(self):
        engine = RuleEngine()
        rule = _build_rule(1, "GATEWAY_ANOMALY", ["gt", "$trip.gantry_count", 3])
        engine.register(rule)
        trip = {"gantry_count": 5}
        results = engine.run(trip)
        assert len(results) == 1
        assert results[0]["fraud_type"] == "GATEWAY_ANOMALY"

    def test_disabled_rule_is_skipped(self):
        engine = RuleEngine()
        rule = _build_rule(1, "GATEWAY_ANOMALY", True, enabled=0)
        engine.register(rule)
        results = engine.run({})
        assert results == []

    def test_dry_run_results_have_zero_suspicious(self):
        engine = RuleEngine()
        rule = _build_rule(1, "OBU_SHIELD", True, dry_run=1, threshold=0.1)
        engine.register(rule)
        results = engine.run({})
        assert results[0]["is_suspicious"] == 0

    def test_fraud_type_filter_limits_evaluation(self):
        engine = RuleEngine()
        engine.register(_build_rule(1, "GATEWAY_ANOMALY", True))
        engine.register(_build_rule(2, "OBU_SHIELD", True))
        results = engine.run({}, fraud_types=["GATEWAY_ANOMALY"])
        assert len(results) == 1
        assert results[0]["fraud_type"] == "GATEWAY_ANOMALY"

    def test_run_batch_processes_each_trip(self):
        engine = RuleEngine()
        engine.register(_build_rule(1, "GATEWAY_ANOMALY", ["gt", "$trip.gantry_count", 3]))
        trips = [{"gantry_count": 5}, {"gantry_count": 1}, {"gantry_count": 10}]
        all_results = engine.run_batch(trips)
        assert len(all_results) == 3
        # trip 1 (count=5) and trip 2 (count=10) hit
        assert all_results[0] and all_results[0][0]["rule_id"] == 1
        assert all_results[1] == []
        assert all_results[2] and all_results[2][0]["rule_id"] == 1

    def test_unregister_removes_rule(self):
        engine = RuleEngine()
        engine.register(_build_rule(1, "GATEWAY_ANOMALY", True))
        engine.unregister(1)
        results = engine.run({})
        assert results == []

    def test_load_from_dicts_bulk_registers(self):
        engine = RuleEngine()
        rules = [
            _build_rule(1, "GATEWAY_ANOMALY", ["eq", "$trip.flag", "gw"]),
            _build_rule(2, "OBU_SHIELD", ["eq", "$trip.x", 1]),
        ]
        engine.load_from_dicts(rules)
        # rule 1 requires flag=gw; rule 2 requires x=1
        assert engine.run({"flag": "gw"})[0]["rule_id"] == 1
        assert engine.run({"x": 1})[0]["rule_id"] == 2
        assert engine.run({"x": 2}) == []
        assert engine.run({"flag": "other"}) == []


# ============================================================
# helpers
# ============================================================


def json_when_score(when_expr=None, score_expr=None):
    return {
        "when": when_expr if when_expr is not None else True,
        "score": score_expr if score_expr is not None else 0.5,
    }
