"""规则管理 API 路由 — Phase 1 MVP"""

from fastapi import APIRouter, HTTPException
from typing import Optional

from apps.api.core.logging_config import get_logger
from apps.api.database.repositories.rule_repository import RuleRepository
from apps.api.services.rule_engine import validate_rule, RuleValidationError
from apps.api.models.schemas import (
    DetectionRuleCreate,
    DetectionRuleUpdate,
    DetectionRuleResponse,
    DetectionRuleListResponse,
)

logger = get_logger(__name__)

router = APIRouter()


def _repo() -> RuleRepository:
    return RuleRepository()


def _to_response(rule: dict) -> DetectionRuleResponse:
    import json
    rule_expr = rule.get("rule_expr", "{}")
    if isinstance(rule_expr, dict):
        rule_expr = json.dumps(rule_expr, ensure_ascii=False)
    return DetectionRuleResponse(
        id=rule["id"],
        name=rule["name"],
        fraud_type=rule["fraud_type"],
        severity=rule.get("severity", 2),
        description=rule.get("description"),
        rule_expr=rule_expr,
        threshold=float(rule.get("threshold", 0.5)),
        dry_run=int(rule.get("dry_run", 0)),
        enabled=int(rule.get("enabled", 1)),
        source=rule.get("source", "manual"),
        created_at=str(rule["created_at"]) if rule.get("created_at") else None,
        updated_at=str(rule["updated_at"]) if rule.get("updated_at") else None,
    )


@router.get("/rules", response_model=DetectionRuleListResponse)
async def list_rules(
    fraud_type: Optional[str] = None,
    enabled: Optional[int] = None,
):
    repo = _repo()
    rules = repo.list_rules(enabled_only=(enabled == 1) if enabled is not None else False)
    if fraud_type:
        rules = [r for r in rules if r.get("fraud_type") == fraud_type]
    return DetectionRuleListResponse(
        rules=[_to_response(r).dict() for r in rules],
        total=len(rules),
    )


@router.get("/rules/{rule_id}", response_model=DetectionRuleResponse)
async def get_rule(rule_id: int):
    repo = _repo()
    rule = repo.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return _to_response(rule)


@router.post("/rules", status_code=201, response_model=DetectionRuleResponse)
async def create_rule(data: DetectionRuleCreate):
    import json

    rule_dict = data.dict()
    rule_expr = rule_dict.pop("rule_expr")

    try:
        validate_rule({
            "id": 0,
            "name": data.name,
            "fraud_type": data.fraud_type,
            "rule_expr": rule_expr,
            "threshold": data.threshold,
        })
    except RuleValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo = _repo()
    rule_id = repo.create_rule({**rule_dict, "rule_expr": json.dumps(rule_expr, ensure_ascii=False)})
    # Doris read-after-write 延迟：短暂等待后重试读取
    import time
    for attempt in range(3):
        rule = repo.get_rule(rule_id)
        if rule:
            return _to_response(rule)
        time.sleep(0.2)
    # 读取失败则基于请求数据构建响应
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    return _to_response({
        "id": rule_id, "name": data.name, "fraud_type": data.fraud_type,
        "severity": data.severity, "description": data.description,
        "rule_expr": json.dumps(rule_expr, ensure_ascii=False),
        "threshold": data.threshold, "dry_run": data.dry_run,
        "enabled": 1, "source": data.source or "manual",
        "created_at": now, "updated_at": now,
    })


@router.put("/rules/{rule_id}", response_model=DetectionRuleResponse)
async def update_rule(rule_id: int, data: DetectionRuleUpdate):
    import json

    updates = data.dict(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    repo = _repo()
    existing = repo.get_rule(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")

    if "rule_expr" in updates:
        rule_expr = updates.pop("rule_expr")
        try:
            validate_rule({
                "id": rule_id,
                "name": existing["name"],
                "fraud_type": existing["fraud_type"],
                "rule_expr": rule_expr,
                "threshold": existing.get("threshold", 0.5),
            })
        except RuleValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))
        updates["rule_expr"] = json.dumps(rule_expr, ensure_ascii=False)

    ok = repo.update_rule(rule_id, updates)
    if not ok:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Doris read-after-write 延迟：基于 existing + updates 构建响应
    for key, value in updates.items():
        if key == "rule_expr":
            existing[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value
        else:
            existing[key] = value
    from datetime import datetime, timezone, timedelta
    existing["updated_at"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    return _to_response(existing)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int):
    repo = _repo()
    ok = repo.delete_rule(rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"deleted": True}


@router.patch("/rules/{rule_id}/toggle")
async def toggle_rule(rule_id: int, enabled: int):
    repo = _repo()
    existing = repo.get_rule(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")
    ok = repo.toggle_enabled(rule_id, enabled)
    if not ok:
        raise HTTPException(status_code=404, detail="Rule not found")
    # Doris UNIQUE KEY merge-on-write 存在 read-after-write 延迟，
    # 直接基于请求参数构建响应而非重新从 DB 读取
    existing["enabled"] = 1 if enabled else 0
    from datetime import datetime, timezone, timedelta
    existing["updated_at"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    return _to_response(existing).dict()


@router.patch("/rules/{rule_id}/dry-run")
async def set_dry_run(rule_id: int, dry_run: int):
    repo = _repo()
    existing = repo.get_rule(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")
    ok = repo.set_dry_run(rule_id, dry_run)
    if not ok:
        raise HTTPException(status_code=404, detail="Rule not found")
    existing["dry_run"] = 1 if dry_run else 0
    from datetime import datetime, timezone, timedelta
    existing["updated_at"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    return _to_response(existing).dict()
