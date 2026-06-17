"""批量 AI 复核可疑车辆（走 vehicle-ai-service 公共服务）。

后台调度（AI_VERIFY task_type）和 trip_aggregator 检测完可疑记录后都用这个入口。
并发：ThreadPoolExecutor + max_workers 上限避免打爆公共服务。

注：函数/日志关键字从 llm_* 改为 ai_verify_*；audit_results 表字段
(llm_is_same_vehicle / llm_confidence / llm_reason / llm_model / llm_checked_at)
保留原名，留待后续 schema 迁移统一改 ai_verify_*。
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from apps.api.core.logging_config import get_logger
from apps.api.database.repositories.audit_repository import AuditRepository
from apps.api.services.vehicle_comparator import compare_vehicles_by_passid

logger = get_logger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _process_one(row: dict[str, Any]) -> tuple[str, str | None]:
    """单条处理：调公共服务比对，OK 则写库。返回 (status, error_code)。
    status ∈ {'ok', 'skipped'}; error_code 仅 skipped 时有值。
    """
    passid = row.get('passid')
    suspect_id = row.get('id')
    if not passid or suspect_id is None:
        return 'skipped', 'missing_passid_or_id'

    try:
        result = compare_vehicles_by_passid(passid)
    except Exception as e:
        logger.error("ai_verify_batch: compare_vehicles_by_passid(%s) raised: %s", passid, e)
        return 'skipped', f"exception:{e}"

    if not isinstance(result, dict) or 'error' in result:
        err_code = (result or {}).get('error') if isinstance(result, dict) else 'no_result'
        logger.info("ai_verify_batch: skip suspect_id=%s passid=%s reason=%s",
                    suspect_id, passid, err_code)
        return 'skipped', err_code

    required = ('is_same_vehicle', 'confidence', 'reason')
    missing = [k for k in required if k not in result]
    if missing:
        logger.warning("ai_verify_batch: incomplete verdict for suspect_id=%s missing=%s",
                       suspect_id, missing)
        return 'skipped', f"incomplete:{missing}"

    AuditRepository().update_llm_verdict(
        suspect_id,
        is_same=bool(result['is_same_vehicle']),
        confidence=float(result['confidence']),
        reason=str(result.get('reason', '')),
        model=str(result.get('model', '')),
        checked_at=_iso_now(),
    )
    return 'ok', None


def run_ai_verify_batch_for_suspects(limit: int = 50, max_workers: int = 4) -> dict[str, Any]:
    """取最多 limit 条待 AI 复核记录，并发跑公共服务写回。

    Returns:
        {'processed': N, 'succeeded': M, 'skipped': K, 'errors': [str, ...]}
        errors 收集形如 "passid: error_code" 的简记，便于日志/监控。
    """
    rows = AuditRepository().get_pending_llm_suspects(limit=limit)
    if not rows:
        return {'processed': 0, 'succeeded': 0, 'skipped': 0, 'errors': []}

    statuses: list[str] = []
    errors: list[str] = []
    workers = max(1, min(max_workers, len(rows)))

    def _wrap(row: dict[str, Any]) -> str:
        status, err_code = _process_one(row)
        if status == 'skipped' and err_code:
            passid = row.get('passid') or f"id={row.get('id')}"
            errors.append(f"{passid}: {err_code}")
        return status

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for status in pool.map(_wrap, rows):
            statuses.append(status)

    return {
        'processed': len(rows),
        'succeeded': statuses.count('ok'),
        'skipped': statuses.count('skipped'),
        'errors': errors,
    }
