"""客车 OBU 监测 — 元数据预筛 + 图片识别 + LLM 复核

命中规则(任一侧):
  1. vehicle_type == 1              (申报为客车)
  2. vehicle_id NOT LIKE '新A%'     (非新 A 开头)
  3. 已有 visual_type 不是货车       (SQL 预筛通过) — 可选优化
  4. 调 vehicle-ai-service.truck_obu() 命中 + llm_verified=True
"""

from typing import Any, Dict, List, Optional

from apps.api.core.vehicle_ai_client import get_client
from apps.api.core.logging_config import get_logger

logger = get_logger(__name__)

FRAUD_TYPE = "PASSENGER_USES_TRUCK_OBU_NON_NEW_A"
DECLARED_VEHICLE_TYPE = 1
NON_NEW_A_PREFIX = "新A"
# 视觉识别为货车的类型集合(visual_type 字段是字符串)
TRUCK_VISUAL_TYPES = frozenset({"14", "15", "16", "truck"})


def detect_trip(trip: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """返回 None 表示未命中;否则返回完整命中细节。

    details 字段(source_side / entry_visual_type / llm_verified / llm_confidence /
    visual_vehicle_type / rule_version)在 task_executor 落 audit_results.details 时会被使用。
    """
    sides: List[Dict[str, Any]] = []
    for side, vtype_key, vid_key, vt_key, img_key, obu_key, mtype_key in _SIDE_KEYS:
        hit = _side_check(
            trip, side, vtype_key, vid_key, vt_key, img_key, obu_key, mtype_key
        )
        if hit:
            sides.append(hit)

    if not sides:
        return None

    source_side = 'BOTH' if len(sides) == 2 else sides[0]['side'].upper()
    primary = sides[0]
    return {
        'fraud_type': FRAUD_TYPE,
        'source_side': source_side,
        'entry_vehicle_type': trip.get('entry_vehicle_type'),
        'exit_vehicle_type': trip.get('exit_vehicle_type'),
        'entry_obu_id': trip.get('entry_obu_id'),
        'exit_obu_id': trip.get('exit_obu_id'),
        'entry_image_trans': trip.get('entry_image_trans'),
        'exit_image_trans': trip.get('exit_image_trans'),
        'entry_visual_type': trip.get('entry_visual_type'),
        'exit_visual_type': trip.get('exit_visual_type'),
        'llm_verified': all(s['llm_verified'] for s in sides),
        'llm_confidence': sum(s['confidence'] for s in sides) / len(sides),
        'visual_vehicle_type': primary['visual_vehicle_type'],
        'risk_score': 0.95 if source_side == 'BOTH' else 0.85,
    }


_SIDE_KEYS = (
    ('entry', 'entry_vehicle_type', 'entry_vehicle_id', 'entry_visual_type',
     'entry_image_trans', 'entry_obu_id', 'entry_media_type'),
    ('exit',  'exit_vehicle_type',  'exit_vehicle_id',  'exit_visual_type',
     'exit_image_trans',  'exit_obu_id',  'exit_media_type'),
)


def _side_check(
    trip, side, vtype_key, vid_key, vt_key, img_key, obu_key, mtype_key,
) -> Optional[Dict[str, Any]]:
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

    # 调 vehicle-ai-service(同步阻塞,失败/超时返回 None)
    try:
        resp = get_client().truck_obu(
            image_url, declared_vehicle_type=DECLARED_VEHICLE_TYPE,
        )
    except Exception as e:
        logger.error("vehicle-ai-service truck_obu raised for %s: %s", image_url, e)
        return None
    if 'error' in resp:
        logger.error("vehicle-ai-service truck_obu failed for %s: %s", image_url, resp)
        return None
    if not resp.get('is_suspicious'):
        return None
    if not resp.get('llm_verified'):
        return None
    return {
        'side': side,
        'llm_verified': bool(resp.get('llm_verified')),
        'confidence': float(resp.get('confidence', 0.0)),
        'visual_vehicle_type': resp.get('visual_vehicle_type'),
        'image_url': image_url,
        'obu_id': trip.get(obu_key),
        'media_type': trip.get(mtype_key),
    }
