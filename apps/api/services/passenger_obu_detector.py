"""客车 OBU 监测 — 元数据预筛 + 图片识别 + LLM 复核

命中规则(任一侧):
  1. vehicle_type == 1              (申报为客车)
  2. vehicle_id NOT LIKE '新A%'     (非新 A 开头)
  3. 已有 visual_type 不是货车       (SQL 预筛通过) — 可选优化
  4. 调 vehicle-ai-service.truck_obu() 命中(is_suspicious=True)

LLM 复核契约由 vehicle-ai-service.truck_obu() 端点内部保证:
- AI service 修复了「ML 高自信漏调 LLM」BUG,现在 is_truck=True 时总是调 LLM。
- LLM 失败时 AI service 返回 is_suspicious=True + llm_verified=False(fail-open),
  我方仍按 is_suspicious 写嫌疑行,便于审计追溯与 disagreement 上报。
"""

from typing import Any

from apps.api.core.logging_config import get_logger
from apps.api.core.vehicle_ai_client import get_client

logger = get_logger(__name__)

FRAUD_TYPE = "PASSENGER_USES_TRUCK_OBU_NON_NEW_A"
DECLARED_VEHICLE_TYPE = 1
NON_NEW_A_PREFIX = "新A"
# 视觉识别为货车的类型集合(visual_type 字段是字符串)
TRUCK_VISUAL_TYPES = frozenset({"14", "15", "16", "truck"})

# llm_call_status 取值与严重度排序
# (越往后越严重,聚合时取 max,便于运维一眼看出"最坏情况")
LLM_CALL_STATUS_CALLED_CONFIRMED = "called_confirmed"
LLM_CALL_STATUS_CALLED_REJECTED = "called_rejected"
LLM_CALL_STATUS_NOT_CALLED = "not_called"
LLM_CALL_STATUS_SERVICE_ERROR = "service_error"
_LLM_STATUS_SEVERITY = {
    LLM_CALL_STATUS_CALLED_CONFIRMED: 1,
    LLM_CALL_STATUS_NOT_CALLED: 2,
    LLM_CALL_STATUS_CALLED_REJECTED: 3,
    LLM_CALL_STATUS_SERVICE_ERROR: 4,
}


def _worst_llm_call_status(*statuses: str | None) -> str | None:
    candidates = [s for s in statuses if s]
    if not candidates:
        return None
    return max(candidates, key=lambda s: _LLM_STATUS_SEVERITY.get(s, 0))


def detect_trip(trip: dict[str, Any]) -> dict[str, Any] | None:
    """返回 None 表示未命中;否则返回完整命中细节。

    details 字段(source_side / entry_visual_type / llm_verified / llm_confidence /
    visual_vehicle_type / rule_version / llm_call_status)在 task_executor 落
    audit_results.details 时会被使用。
    """
    sides: list[dict[str, Any]] = []
    for side, vtype_key, vid_key, vt_key, img_key, obu_key, mtype_key in _SIDE_KEYS:
        hit = _side_check(trip, side, vtype_key, vid_key, vt_key, img_key, obu_key, mtype_key)
        if hit:
            sides.append(hit)

    if not sides:
        return None

    source_side = "BOTH" if len(sides) == 2 else sides[0]["side"].upper()
    primary = sides[0]
    return {
        "fraud_type": FRAUD_TYPE,
        "source_side": source_side,
        "entry_vehicle_type": trip.get("entry_vehicle_type"),
        "exit_vehicle_type": trip.get("exit_vehicle_type"),
        "entry_obu_id": trip.get("entry_obu_id"),
        "exit_obu_id": trip.get("exit_obu_id"),
        "entry_image_trans": trip.get("entry_image_trans"),
        "exit_image_trans": trip.get("exit_image_trans"),
        "entry_visual_type": trip.get("entry_visual_type"),
        "exit_visual_type": trip.get("exit_visual_type"),
        "llm_verified": all(s["llm_verified"] for s in sides),
        "llm_confidence": sum(s["confidence"] for s in sides) / len(sides),
        "visual_vehicle_type": primary["visual_vehicle_type"],
        "risk_score": 0.95 if source_side == "BOTH" else 0.85,
        "llm_call_status": _worst_llm_call_status(*(s.get("llm_call_status") for s in sides)),
    }


_SIDE_KEYS = (
    (
        "entry",
        "entry_vehicle_type",
        "entry_vehicle_id",
        "entry_visual_type",
        "entry_image_trans",
        "entry_obu_id",
        "entry_media_type",
    ),
    (
        "exit",
        "exit_vehicle_type",
        "exit_vehicle_id",
        "exit_visual_type",
        "exit_image_trans",
        "exit_obu_id",
        "exit_media_type",
    ),
)


def _side_check(
    trip,
    side,
    vtype_key,
    vid_key,
    vt_key,
    img_key,
    obu_key,
    mtype_key,
) -> dict[str, Any] | None:
    if trip.get(vtype_key) != DECLARED_VEHICLE_TYPE:
        return None
    vid = trip.get(vid_key)
    if not vid or str(vid).startswith(NON_NEW_A_PREFIX):
        return None
    # 优化:若 visual_type 已有值且不是货车,直接跳过(免一次模型调用)
    existing_vt = trip.get(vt_key)
    if existing_vt and existing_vt not in TRUCK_VISUAL_TYPES:
        return None
    image_url = trip.get(img_key)
    if not image_url:
        return None

    passid = trip.get("passid")

    # 调 vehicle-ai-service(同步阻塞,失败/超时返回 None)
    try:
        resp = get_client().truck_obu(
            image_url,
            declared_vehicle_type=DECLARED_VEHICLE_TYPE,
        )
    except Exception as e:
        logger.error(
            "vehicle-ai-service truck_obu raised: passid=%s side=%s image=%s error=%s",
            passid,
            side,
            image_url,
            e,
        )
        return None
    if "error" in resp:
        logger.error(
            "vehicle-ai-service truck_obu failed: passid=%s side=%s image=%s resp=%s",
            passid,
            side,
            image_url,
            resp,
        )
        return None
    # AI service 现在总是调 LLM(is_truck=True 时);fail-open(MaaS 抖动)时
    # 仍返回 is_suspicious=True + llm_verified=False,主项目按 is_suspicious 写嫌疑行,
    # llm_verified 字段透传供审计追溯与 disagreement_store 比对。
    if not resp.get("is_suspicious"):
        return None
    llm_verified = bool(resp.get("llm_verified"))
    return {
        "side": side,
        "llm_verified": llm_verified,
        "confidence": float(resp.get("confidence", 0.0)),
        "visual_vehicle_type": resp.get("visual_vehicle_type"),
        "image_url": image_url,
        "obu_id": trip.get(obu_key),
        "media_type": trip.get(mtype_key),
        "llm_call_status": (LLM_CALL_STATUS_CALLED_CONFIRMED if llm_verified else LLM_CALL_STATUS_CALLED_REJECTED),
    }
