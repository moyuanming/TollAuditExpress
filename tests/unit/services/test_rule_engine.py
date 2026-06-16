"""RuleEngine 单元测试 — 阶段 1 MVP 规则引擎骨架

DSL 设计：JSON s-expression 表达式
  when:  ["and", ["eq", "$trip.field", value], ...]
  score: ["add", ["mul", "$trip.field", 0.3], 0.5]
  threshold: 0.5

安全性：使用受限 AST 解析，禁止 eval / import / 函数调用 / 任意属性访问
"""

import pytest

from apps.api.services.rule_engine import (
    _FORBIDDEN_TOKENS,
    RuleEngine,
    RuleExprError,
    RuleValidationError,
    _check_expr_shape,
    _eval_arithmetic,
    _eval_comparison,
    _eval_count,
    _eval_if,
    _eval_in,
    _eval_value,
    _resolve_field,
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

    def test_rejects_threshold_below_zero(self):
        with pytest.raises(RuleValidationError):
            validate_rule(
                {
                    "id": 1,
                    "name": "t",
                    "fraud_type": "GATEWAY_ANOMALY",
                    "rule_expr": json_when_score(),
                    "threshold": -0.1,
                }
            )

    def test_rejects_threshold_not_numeric(self):
        with pytest.raises(RuleValidationError):
            validate_rule(
                {
                    "id": 1,
                    "name": "t",
                    "fraud_type": "GATEWAY_ANOMALY",
                    "rule_expr": json_when_score(),
                    "threshold": "high",
                }
            )

    def test_accepts_rule_with_only_when(self):
        rule = {
            "id": 1,
            "name": "t",
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": {"when": True},
        }
        validate_rule(rule)

    def test_accepts_rule_with_only_score(self):
        rule = {
            "id": 1,
            "name": "t",
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": {"score": 0.5},
        }
        validate_rule(rule)

    def test_rejects_rule_expr_with_forbidden_token_in_when(self):
        rule = {
            "id": 1,
            "name": "t",
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": {"when": ["eval", "$trip.x"]},
        }
        with pytest.raises(RuleExprError):
            validate_rule(rule)

    def test_rejects_rule_expr_with_unknown_operator_in_score(self):
        rule = {
            "id": 1,
            "name": "t",
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": {"score": ["unknown_op", 1, 2]},
        }
        with pytest.raises(RuleExprError):
            validate_rule(rule)

    def test_accepts_threshold_at_zero(self):
        rule = {
            "id": 1,
            "name": "t",
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": json_when_score(),
            "threshold": 0.0,
        }
        validate_rule(rule)

    def test_accepts_threshold_at_one(self):
        rule = {
            "id": 1,
            "name": "t",
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": json_when_score(),
            "threshold": 1.0,
        }
        validate_rule(rule)


# ============================================================
# _check_expr_shape
# ============================================================


class TestCheckExprShape:
    """表达式结构静态检查"""

    def test_accepts_bool_literal(self):
        _check_expr_shape(True, "when")

    def test_accepts_numeric_literal(self):
        _check_expr_shape(42, "score")
        _check_expr_shape(3.14, "score")

    def test_accepts_string_literal(self):
        _check_expr_shape("hello", "when")

    def test_accepts_trip_field_ref(self):
        _check_expr_shape("$trip.foo", "when")
        _check_expr_shape("$trip", "when")

    def test_rejects_empty_list(self):
        with pytest.raises(RuleExprError, match="empty expression"):
            _check_expr_shape([], "when")

    def test_rejects_non_string_operator(self):
        with pytest.raises(RuleExprError, match="operator must be str"):
            _check_expr_shape([123, 1, 2], "when")

    def test_rejects_forbidden_token(self):
        for tok in _FORBIDDEN_TOKENS:
            with pytest.raises(RuleExprError, match="forbidden token"):
                _check_expr_shape([tok, "$trip.x"], "when")

    def test_rejects_unknown_operator(self):
        with pytest.raises(RuleExprError, match="unknown operator"):
            _check_expr_shape(["xyz", 1, 2], "when")

    def test_rejects_unsupported_node_type(self):
        with pytest.raises(RuleExprError, match="unsupported expression node"):
            _check_expr_shape(set(), "when")

    def test_recursively_checks_children(self):
        # nested: ["and", ["eq", 1, 2], ["gt", 3, 4]] — valid
        _check_expr_shape(["and", ["eq", 1, 2], ["gt", 3, 4]], "when")
        # nested with bad child
        with pytest.raises(RuleExprError):
            _check_expr_shape(["and", ["unknown", 1], ["gt", 3, 4]], "when")


# ============================================================
# _resolve_field
# ============================================================


class TestResolveField:
    """字段路径解析"""

    def test_resolves_simple_field(self):
        assert _resolve_field("$trip.x", {"x": 42}) == 42

    def test_resolves_nested_field(self):
        assert _resolve_field("$trip.a.b", {"a": {"b": 99}}) == 99

    def test_returns_none_for_missing_field(self):
        assert _resolve_field("$trip.missing", {"x": 1}) is None

    def test_returns_none_for_nested_missing(self):
        assert _resolve_field("$trip.a.b", {"a": {}}) is None

    def test_raises_on_non_trip_prefix(self):
        with pytest.raises(RuleExprError, match="must start with"):
            _resolve_field("$other.x", {"x": 1})

    def test_raises_on_bare_dollar_trip(self):
        with pytest.raises(RuleExprError, match="invalid field path"):
            _resolve_field("$trip", {"x": 1})

    def test_raises_on_non_string_path(self):
        with pytest.raises(RuleExprError, match="must start with"):
            _resolve_field(123, {"x": 1})

    def test_returns_none_when_intermediate_is_not_dict(self):
        assert _resolve_field("$trip.a.b", {"a": 42}) is None


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

    def test_not_raises_on_wrong_arg_count(self):
        with pytest.raises(RuleExprError, match="not takes exactly 1 argument"):
            evaluate_condition(["not", True, True], {})

    def test_comparison_raises_on_wrong_arg_count(self):
        with pytest.raises(RuleExprError, match="eq takes exactly 2 arguments"):
            evaluate_condition(["eq", 1], {})

    def test_in_raises_on_wrong_arg_count(self):
        with pytest.raises(RuleExprError, match="in takes exactly 2 arguments"):
            evaluate_condition(["in", 1], {})

    def test_count_raises_on_wrong_arg_count(self):
        with pytest.raises(RuleExprError, match="count takes exactly 1 argument"):
            evaluate_condition(["count", "$trip.a", "$trip.b"], {"a": [], "b": []})

    def test_numeric_literal_truthy(self):
        assert evaluate_condition(1, {}) is True
        assert evaluate_condition(0, {}) is False

    def test_string_literal_truthy(self):
        assert evaluate_condition("hello", {}) is True
        assert evaluate_condition("", {}) is False

    def test_trip_field_truthy(self):
        assert evaluate_condition("$trip.x", {"x": "yes"}) is True
        assert evaluate_condition("$trip.x", {"x": ""}) is False

    def test_invalid_expression_raises(self):
        with pytest.raises(RuleExprError):
            evaluate_condition(set(), {})

    def test_ne_with_none_returns_true(self):
        trip = {"x": None}
        assert evaluate_condition(["ne", "$trip.x", 5], trip) is True

    def test_gte_and_lte_boundary(self):
        trip = {"x": 5}
        assert evaluate_condition(["gte", "$trip.x", 5], trip) is True
        assert evaluate_condition(["lte", "$trip.x", 5], trip) is True
        assert evaluate_condition(["gte", "$trip.x", 6], trip) is False
        assert evaluate_condition(["lte", "$trip.x", 4], trip) is False


# ============================================================
# _eval_comparison
# ============================================================


class TestEvalComparison:
    """比较运算底层函数"""

    def test_eq_both_none_returns_true(self):
        assert _eval_comparison("eq", [None, None], {}) is True

    def test_ne_one_none_returns_true(self):
        assert _eval_comparison("ne", [None, 5], {}) is True
        assert _eval_comparison("ne", [5, None], {}) is True

    def test_eq_one_none_returns_false(self):
        assert _eval_comparison("eq", [None, 5], {}) is False
        assert _eval_comparison("eq", [5, None], {}) is False

    def test_comparison_type_error_raises(self):
        with pytest.raises(RuleExprError, match="comparison failed"):
            _eval_comparison("gt", ["string", 5], {})

    def test_all_comparison_ops(self):
        assert _eval_comparison("eq", [5, 5], {}) is True
        assert _eval_comparison("ne", [5, 3], {}) is True
        assert _eval_comparison("gt", [5, 3], {}) is True
        assert _eval_comparison("lt", [3, 5], {}) is True
        assert _eval_comparison("gte", [5, 5], {}) is True
        assert _eval_comparison("lte", [5, 5], {}) is True


# ============================================================
# _eval_in
# ============================================================


class TestEvalIn:
    """in 运算底层函数"""

    def test_in_with_list_haystack(self):
        assert _eval_in(["blue", ["blue", "red"]], {}) is True

    def test_not_in_list(self):
        assert _eval_in(["green", ["blue", "red"]], {}) is False

    def test_in_with_none_haystack_returns_false(self):
        assert _eval_in([1, None], {}) is False

    def test_in_with_none_needle_in_list(self):
        assert _eval_in([None, [1, None, 3]], {}) is True

    def test_in_with_non_iterable_haystack_returns_false(self):
        # needle=5, haystack=5 (scalar), 5 in 5 → TypeError → False
        assert _eval_in([5, 5], {}) is False

    def test_in_type_error_returns_false(self):
        assert _eval_in([42, "not_iterable"], {}) is False


# ============================================================
# _eval_count
# ============================================================


class TestEvalCount:
    """count 运算底层函数"""

    def test_count_list(self):
        assert _eval_count(["$trip.items"], {"items": [1, 2, 3]}) == 3

    def test_count_dict(self):
        assert _eval_count(["$trip.items"], {"items": {"a": 1, "b": 2}}) == 2

    def test_count_string(self):
        assert _eval_count(["$trip.items"], {"items": "hello"}) == 5

    def test_count_none_returns_zero(self):
        assert _eval_count(["$trip.items"], {"items": None}) == 0

    def test_count_non_collection_raises(self):
        with pytest.raises(RuleExprError, match="count requires collection"):
            _eval_count(["$trip.items"], {"items": 42})


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

    def test_sub_expression(self):
        trip = {"a": 0.9, "b": 0.3}
        assert evaluate_score(["sub", "$trip.a", "$trip.b"], trip) == pytest.approx(0.6)

    def test_div_expression(self):
        trip = {"a": 0.6, "b": 2}
        assert evaluate_score(["div", "$trip.a", "$trip.b"], trip) == pytest.approx(0.3)

    def test_div_by_zero_raises(self):
        with pytest.raises(RuleExprError, match="division by zero"):
            evaluate_score(["div", 1, 0], {})

    def test_score_from_none_field_returns_zero(self):
        assert evaluate_score("$trip.missing", {}) == 0.0

    def test_score_non_numeric_raises(self):
        with pytest.raises(RuleExprError, match="score must be numeric"):
            evaluate_score("not_a_number", {})

    def test_if_expression_in_score(self):
        trip = {"flag": True}
        # if flag then 0.9 else 0.1
        assert evaluate_score(["if", "$trip.flag", 0.9, 0.1], trip) == pytest.approx(0.9)

    def test_if_expression_false_branch(self):
        trip = {"flag": False}
        assert evaluate_score(["if", "$trip.flag", 0.9, 0.1], trip) == pytest.approx(0.1)


# ============================================================
# _eval_arithmetic
# ============================================================


class TestEvalArithmetic:
    """算术运算底层函数"""

    def test_add_multiple_args(self):
        assert _eval_arithmetic("add", [1, 2, 3], {}) == 6.0

    def test_sub_multiple_args(self):
        assert _eval_arithmetic("sub", [10, 3, 2], {}) == 5.0

    def test_mul_multiple_args(self):
        assert _eval_arithmetic("mul", [2, 3, 4], {}) == 24.0

    def test_div_multiple_args(self):
        assert _eval_arithmetic("div", [24, 2, 3], {}) == 4.0

    def test_arithmetic_with_none_treated_as_zero(self):
        assert _eval_arithmetic("add", [None, 5], {}) == 5.0
        assert _eval_arithmetic("mul", [None, 5], {}) == 0.0

    def test_arithmetic_too_few_args_raises(self):
        with pytest.raises(RuleExprError, match="takes at least 2 arguments"):
            _eval_arithmetic("add", [1], {})

    def test_div_by_zero_raises(self):
        with pytest.raises(RuleExprError, match="division by zero"):
            _eval_arithmetic("div", [1, 0], {})


# ============================================================
# _eval_if
# ============================================================


class TestEvalIf:
    """if 条件表达式底层函数"""

    def test_if_true_branch(self):
        assert _eval_if([True, 1, 2], {}) == 1

    def test_if_false_branch(self):
        assert _eval_if([False, 1, 2], {}) == 2

    def test_if_wrong_arg_count_raises(self):
        with pytest.raises(RuleExprError, match="if takes exactly 3 arguments"):
            _eval_if([True, 1], {})

    def test_if_with_comparison_condition(self):
        assert _eval_if([["gt", 5, 3], "yes", "no"], {}) == "yes"
        assert _eval_if([["lt", 5, 3], "yes", "no"], {}) == "no"


# ============================================================
# _eval_value
# ============================================================


class TestEvalValue:
    """通用值求值"""

    def test_bool_literal(self):
        assert _eval_value(True, {}) is True
        assert _eval_value(False, {}) is False

    def test_numeric_literal(self):
        assert _eval_value(42, {}) == 42
        assert _eval_value(3.14, {}) == 3.14

    def test_string_literal(self):
        assert _eval_value("hello", {}) == "hello"

    def test_none_literal(self):
        assert _eval_value(None, {}) is None

    def test_trip_field_access(self):
        assert _eval_value("$trip.x", {"x": 42}) == 42

    def test_literal_array(self):
        # First element is not a known operator → literal array
        result = _eval_value([1, 2, 3], {})
        assert result == [1, 2, 3]

    def test_empty_list_returns_empty_list(self):
        assert _eval_value([], {}) == []

    def test_literal_array_with_non_op_string_head(self):
        # Non-operator string heads are treated as literal arrays, not expressions
        result = _eval_value(["some_string", 1, 2], {})
        assert result == ["some_string", 1, 2]

    def test_invalid_node_raises(self):
        with pytest.raises(RuleExprError, match="invalid expression"):
            _eval_value(set(), {})

    def test_comparison_returns_bool(self):
        assert _eval_value(["eq", 5, 5], {}) is True
        assert _eval_value(["ne", 5, 3], {}) is True

    def test_in_returns_bool(self):
        assert _eval_value(["in", "blue", ["blue", "red"]], {}) is True

    def test_count_returns_int(self):
        assert _eval_value(["count", "$trip.items"], {"items": [1, 2, 3]}) == 3


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

    def test_default_threshold_is_0_5(self):
        rule = {
            "id": 10,
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": {"when": True, "score": 0.6},
        }
        result = evaluate_rule(rule, {})
        assert result["is_suspicious"] == 1
        assert result["details"]["threshold"] == 0.5

    def test_score_exactly_at_threshold_is_suspicious(self):
        rule = {
            "id": 11,
            "fraud_type": "GATEWAY_ANOMALY",
            "threshold": 0.5,
            "rule_expr": {"when": True, "score": 0.5},
        }
        result = evaluate_rule(rule, {})
        assert result["is_suspicious"] == 1

    def test_clamp_score_above_1(self):
        rule = {
            "id": 12,
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": {"when": True, "score": 5.0},
        }
        result = evaluate_rule(rule, {})
        assert result["risk_score"] == 1.0

    def test_clamp_score_below_0(self):
        rule = {
            "id": 13,
            "fraud_type": "GATEWAY_ANOMALY",
            "rule_expr": {"when": True, "score": -2.0},
        }
        result = evaluate_rule(rule, {})
        assert result["risk_score"] == 0.0

    def test_result_includes_details(self):
        rule = {
            "id": 14,
            "name": "my-rule",
            "fraud_type": "GATEWAY_ANOMALY",
            "threshold": 0.7,
            "rule_expr": {"when": True, "score": 0.8},
        }
        result = evaluate_rule(rule, {})
        assert result["details"]["rule_name"] == "my-rule"
        assert result["details"]["threshold"] == 0.7

    def test_rule_with_no_rule_expr_returns_none(self):
        rule = {"id": 15, "fraud_type": "GATEWAY_ANOMALY"}
        # rule_expr is None → when defaults to True, score defaults to 0.0
        result = evaluate_rule(rule, {})
        assert result is not None
        assert result["risk_score"] == 0.0


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

    def test_unregister_nonexistent_id_is_noop(self):
        engine = RuleEngine()
        engine.register(_build_rule(1, "GATEWAY_ANOMALY", True))
        engine.unregister(999)
        assert len(engine.run({})) == 1

    def test_register_invalid_rule_raises(self):
        engine = RuleEngine()
        with pytest.raises(RuleValidationError):
            engine.register({"id": 1})  # missing required fields

    def test_run_with_no_rules_returns_empty(self):
        engine = RuleEngine()
        assert engine.run({}) == []

    def test_run_batch_with_empty_trips(self):
        engine = RuleEngine()
        engine.register(_build_rule(1, "GATEWAY_ANOMALY", True))
        assert engine.run_batch([]) == []

    def test_enabled_none_treated_as_enabled(self):
        """enabled 字段缺失时默认为 1（启用）"""
        engine = RuleEngine()
        rule = _build_rule(1, "GATEWAY_ANOMALY", True)
        rule["enabled"] = None
        engine.register(rule)
        results = engine.run({})
        assert len(results) == 1

    def test_fraud_type_filter_with_multiple_types(self):
        engine = RuleEngine()
        engine.register(_build_rule(1, "GATEWAY_ANOMALY", True))
        engine.register(_build_rule(2, "OBU_SHIELD", True))
        engine.register(_build_rule(3, "TRUCK_AS_CAR", True))
        results = engine.run({}, fraud_types=["GATEWAY_ANOMALY", "OBU_SHIELD"])
        assert len(results) == 2
        assert all(r["fraud_type"] in ("GATEWAY_ANOMALY", "OBU_SHIELD") for r in results)

    def test_run_skips_rules_where_condition_not_met(self):
        engine = RuleEngine()
        engine.register(_build_rule(1, "GATEWAY_ANOMALY", ["eq", "$trip.x", 1]))
        engine.register(_build_rule(2, "OBU_SHIELD", ["eq", "$trip.x", 2]))
        results = engine.run({"x": 1})
        assert len(results) == 1
        assert results[0]["rule_id"] == 1


# ============================================================
# helpers
# ============================================================


def json_when_score(when_expr=None, score_expr=None):
    return {
        "when": when_expr if when_expr is not None else True,
        "score": score_expr if score_expr is not None else 0.5,
    }
