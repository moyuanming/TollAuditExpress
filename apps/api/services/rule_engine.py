"""RuleEngine 骨架 — 阶段 1 MVP

JSON s-expression DSL:
  when:  ["and", ["eq", "$trip.field", value], ["gt", "$trip.field", 3]]
  score: ["add", ["mul", "$trip.field", 0.3], 0.5]

安全设计：完全白名单的操作符 + 字段访问（$trip.field），禁止 eval / import / 函数调用。
所有求值通过自实现的 AST 解释器完成。

Rule schema:
  {
    "id": int,
    "name": str,
    "fraud_type": str,         # 必须在 ALLOWED_FRAUD_TYPES
    "threshold": float,         # [0, 1]，可选，默认 0.5
    "dry_run": int,             # 0/1，可选
    "enabled": int,             # 0/1，可选，默认 1
    "rule_expr": {
        "when":  <expr>,
        "score": <expr>
    }
  }
"""

from typing import Any, Dict, List, Optional

ALLOWED_FRAUD_TYPES = frozenset(
    [
        "TRUCK_AS_CAR",
        "ENTRY_EXIT_MISMATCH",
        "GATEWAY_ANOMALY",
        "VEHICLE_TYPE_DOWNGRADE",
        "SAME_PLATE_DIFF_VEHICLE",
        "OBU_UNBIND",
        "OBU_SHIELD",
    ]
)

_ALLOWED_OPS = frozenset(
    [
        "and",
        "or",
        "not",
        "eq",
        "ne",
        "gt",
        "lt",
        "gte",
        "lte",
        "in",
        "add",
        "sub",
        "mul",
        "div",
        "count",
        "if",
    ]
)

_FORBIDDEN_TOKENS = frozenset(
    [
        "__import__",
        "eval",
        "exec",
        "compile",
        "globals",
        "locals",
        "getattr",
        "setattr",
        "delattr",
        "open",
        "call",
        "lambda",
    ]
)


class RuleValidationError(ValueError):
    """规则结构不合法"""


class RuleExprError(ValueError):
    """表达式求值失败（语法错误、未知操作符、非法字段访问）"""


# ============================================================
# validation
# ============================================================


def validate_rule(rule: Any) -> None:
    """校验规则结构；不合法抛出 RuleValidationError。"""
    if not isinstance(rule, dict):
        raise RuleValidationError(f"rule must be a dict, got {type(rule).__name__}")

    required = ("id", "name", "fraud_type", "rule_expr")
    for key in required:
        if key not in rule:
            raise RuleValidationError(f"missing required field: {key}")

    fraud_type = rule["fraud_type"]
    if fraud_type not in ALLOWED_FRAUD_TYPES:
        raise RuleValidationError(f"unsupported fraud_type: {fraud_type}")

    if "threshold" in rule:
        threshold = rule["threshold"]
        if not isinstance(threshold, (int, float)) or not (0.0 <= threshold <= 1.0):
            raise RuleValidationError(f"threshold must be in [0, 1], got {threshold!r}")

    rule_expr = rule["rule_expr"]
    if not isinstance(rule_expr, dict):
        raise RuleValidationError("rule_expr must be a dict")
    if "when" not in rule_expr and "score" not in rule_expr:
        raise RuleValidationError("rule_expr must contain 'when' or 'score'")

    if "when" in rule_expr:
        _check_expr_shape(rule_expr["when"], context="when")
    if "score" in rule_expr:
        _check_expr_shape(rule_expr["score"], context="score")


def _check_expr_shape(expr: Any, context: str) -> None:
    """静态检查表达式结构：操作符白名单 + 嵌套合法性。"""
    if isinstance(expr, bool):
        return
    if isinstance(expr, (int, float)):
        return
    if isinstance(expr, str):
        if expr.startswith("$trip.") or expr == "$trip":
            return
        return
    if isinstance(expr, list):
        if not expr:
            raise RuleExprError(f"{context}: empty expression")
        head = expr[0]
        if not isinstance(head, str):
            raise RuleExprError(f"{context}: operator must be str, got {type(head).__name__}")
        if head in _FORBIDDEN_TOKENS:
            raise RuleExprError(f"{context}: forbidden token: {head}")
        if head not in _ALLOWED_OPS:
            raise RuleExprError(f"{context}: unknown operator: {head}")
        for child in expr[1:]:
            _check_expr_shape(child, context=context)
        return
    raise RuleExprError(f"{context}: unsupported expression node: {type(expr).__name__}")


# ============================================================
# field access
# ============================================================


def _resolve_field(path: str, trip: Dict[str, Any]) -> Any:
    """$trip.foo.bar → trip['foo']['bar']；路径必须以 $trip 开头。"""
    if not isinstance(path, str) or not path.startswith("$trip"):
        raise RuleExprError(f"field path must start with $trip, got {path!r}")
    parts = path.split(".")
    if parts[0] != "$trip" or len(parts) < 2:
        raise RuleExprError(f"invalid field path: {path!r}")
    cursor: Any = trip
    for p in parts[1:]:
        if isinstance(cursor, dict):
            cursor = cursor.get(p)
        else:
            cursor = None
        if cursor is None:
            return None
    return cursor


# ============================================================
# boolean expression evaluation
# ============================================================


def evaluate_condition(expr: Any, trip: Dict[str, Any]) -> bool:
    """求值 when 表达式，返回 True / False。"""
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, (int, float)):
        return bool(expr)
    if isinstance(expr, str):
        if expr.startswith("$trip."):
            value = _resolve_field(expr, trip)
            return bool(value)
        return bool(expr)
    if isinstance(expr, list) and expr:
        head = expr[0]
        if head in _FORBIDDEN_TOKENS or head not in _ALLOWED_OPS:
            raise RuleExprError(f"unknown/forbidden operator: {head}")
        if head == "and":
            return all(evaluate_condition(c, trip) for c in expr[1:])
        if head == "or":
            return any(evaluate_condition(c, trip) for c in expr[1:])
        if head == "not":
            if len(expr) != 2:
                raise RuleExprError("not takes exactly 1 argument")
            return not evaluate_condition(expr[1], trip)
        if head in ("eq", "ne", "gt", "lt", "gte", "lte"):
            return _eval_comparison(head, expr[1:], trip)
        if head == "in":
            return _eval_in(expr[1:], trip)
        if head == "count":
            value = _eval_count(expr[1:], trip)
            return bool(value)
    raise RuleExprError(f"invalid condition expression: {expr!r}")


def _eval_comparison(op: str, args: List[Any], trip: Dict[str, Any]) -> bool:
    if len(args) != 2:
        raise RuleExprError(f"{op} takes exactly 2 arguments")
    left = _eval_value(args[0], trip)
    right = _eval_value(args[1], trip)
    if left is None or right is None:
        if left is None and right is None:
            return op == "eq"
        return op == "ne" and left is not right
    try:
        if op == "eq":
            return left == right
        if op == "ne":
            return left != right
        if op == "gt":
            return left > right
        if op == "lt":
            return left < right
        if op == "gte":
            return left >= right
        if op == "lte":
            return left <= right
    except TypeError as e:
        raise RuleExprError(f"{op} comparison failed: {e}") from e
    return False


def _eval_in(args: List[Any], trip: Dict[str, Any]) -> bool:
    if len(args) != 2:
        raise RuleExprError("in takes exactly 2 arguments")
    needle = _eval_value(args[0], trip)
    haystack = _eval_value(args[1], trip)
    if haystack is None:
        return False
    if needle is None:
        return None in (haystack if isinstance(haystack, (list, tuple, set)) else [haystack])
    try:
        return needle in haystack
    except TypeError:
        return False


def _eval_count(args: List[Any], trip: Dict[str, Any]) -> int:
    if len(args) != 1:
        raise RuleExprError("count takes exactly 1 argument")
    value = _eval_value(args[0], trip)
    if value is None:
        return 0
    if isinstance(value, (list, tuple, set, dict, str)):
        return len(value)
    raise RuleExprError(f"count requires collection, got {type(value).__name__}")


# ============================================================
# numeric expression evaluation
# ============================================================


def evaluate_score(expr: Any, trip: Dict[str, Any]) -> float:
    """求值 score 表达式，返回原始 float（不限幅）。

    限幅由 evaluate_rule 在阈值比对前统一处理，确保 DSL 内部可访问任意数值。
    """
    raw = _eval_value(expr, trip)
    try:
        return float(raw if raw is not None else 0.0)
    except (TypeError, ValueError) as e:
        raise RuleExprError(f"score must be numeric, got {expr!r}") from e


def _eval_value(node: Any, trip: Dict[str, Any]) -> Any:
    """通用值求值：literal / $trip.field / 嵌套算术 / count / if。

    列表节点歧义消解：首元素为已知操作符 → 表达式；否则 → 字面量数组。
    """
    if isinstance(node, bool):
        return node
    if isinstance(node, (int, float)):
        return node
    if isinstance(node, str):
        if node.startswith("$trip."):
            return _resolve_field(node, trip)
        return node
    if node is None:
        return None
    if isinstance(node, list) and node:
        head = node[0]
        # 字面量数组：首元素不是已知操作符（典型用于 in 右侧 / 函数参数）
        if not isinstance(head, str) or head not in _ALLOWED_OPS:
            return [_eval_value(item, trip) for item in node]
        if head in _FORBIDDEN_TOKENS:
            raise RuleExprError(f"forbidden operator: {head}")
        if head in ("and", "or", "not"):
            return evaluate_condition(node, trip)
        if head in ("eq", "ne", "gt", "lt", "gte", "lte"):
            return _eval_comparison(head, node[1:], trip)
        if head == "in":
            return _eval_in(node[1:], trip)
        if head == "count":
            return _eval_count(node[1:], trip)
        if head in ("add", "sub", "mul", "div"):
            return _eval_arithmetic(head, node[1:], trip)
        if head == "if":
            return _eval_if(node[1:], trip)
    if isinstance(node, list):
        return [_eval_value(item, trip) for item in node]
    raise RuleExprError(f"invalid expression: {node!r}")


def _eval_arithmetic(op: str, args: List[Any], trip: Dict[str, Any]) -> float:
    if len(args) < 2:
        raise RuleExprError(f"{op} takes at least 2 arguments")
    values = [_eval_value(a, trip) for a in args]
    result: float = float(values[0]) if values[0] is not None else 0.0
    for v in values[1:]:
        n = float(v) if v is not None else 0.0
        if op == "add":
            result = result + n
        elif op == "sub":
            result = result - n
        elif op == "mul":
            result = result * n
        elif op == "div":
            if n == 0:
                raise RuleExprError("division by zero")
            result = result / n
    return result


def _eval_if(args: List[Any], trip: Dict[str, Any]) -> Any:
    if len(args) != 3:
        raise RuleExprError("if takes exactly 3 arguments")
    cond = evaluate_condition(args[0], trip)
    return _eval_value(args[1] if cond else args[2], trip)


# ============================================================
# full rule evaluation
# ============================================================


def evaluate_rule(rule: Dict[str, Any], trip: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """评估规则：当 when 为真时返回 result dict，否则 None。"""
    rule_expr = rule.get("rule_expr") or {}
    when_expr = rule_expr.get("when", True)
    score_expr = rule_expr.get("score", 0.0)

    if not evaluate_condition(when_expr, trip):
        return None

    risk_score = evaluate_score(score_expr, trip)
    # 限幅在阈值比对前完成，防止超界分值污染排序
    if risk_score < 0.0:
        risk_score = 0.0
    elif risk_score > 1.0:
        risk_score = 1.0
    threshold = float(rule.get("threshold", 0.5))
    dry_run = int(rule.get("dry_run", 0) or 0)

    is_suspicious = 0 if dry_run else (1 if risk_score >= threshold else 0)

    return {
        "rule_id": rule.get("id"),
        "fraud_type": rule.get("fraud_type"),
        "risk_score": risk_score,
        "is_suspicious": is_suspicious,
        "dry_run": dry_run,
        "details": {
            "rule_name": rule.get("name"),
            "threshold": threshold,
        },
    }


# ============================================================
# RuleEngine class
# ============================================================


class RuleEngine:
    """注册规则 + 批量执行。"""

    def __init__(self) -> None:
        self._rules: List[Dict[str, Any]] = []

    def register(self, rule: Dict[str, Any]) -> None:
        validate_rule(rule)
        self._rules.append(rule)

    def unregister(self, rule_id: int) -> None:
        self._rules = [r for r in self._rules if r.get("id") != rule_id]

    def load_from_dicts(self, rules: List[Dict[str, Any]]) -> None:
        for r in rules:
            self.register(r)

    def run(
        self,
        trip: Dict[str, Any],
        fraud_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for rule in self._rules:
            enabled = rule.get("enabled")
            if enabled is None:
                enabled = 1
            if int(enabled) == 0:
                continue
            if fraud_types is not None and rule.get("fraud_type") not in fraud_types:
                continue
            result = evaluate_rule(rule, trip)
            if result is not None:
                results.append(result)
        return results

    def run_batch(
        self,
        trips: List[Dict[str, Any]],
        fraud_types: Optional[List[str]] = None,
    ) -> List[List[Dict[str, Any]]]:
        return [self.run(trip, fraud_types=fraud_types) for trip in trips]
