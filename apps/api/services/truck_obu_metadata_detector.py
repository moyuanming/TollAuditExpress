"""货车 OBU 监测器（纯元数据规则）

判断条件:entry/exit 任一侧满足
  1. vehicle_type ∈ {14, 15, 16}（货车）
  2. media_type == 1（OBU 介质）
  3. vehicle_id NOT LIKE '新A%'（非新A 开头）

输出:fraud_type=TRUCK_USES_TRUCK_OBU_NON_NEW_A,
     source_side 标识命中侧（ENTRY / EXIT / BOTH）,
     risk_score 固定 0.85（纯规则命中,置信度高）。
"""

from typing import Optional, Dict, Any

TRUCK_VEHICLE_TYPES = frozenset({14, 15, 16})
OBU_MEDIA_TYPE = 1
NON_NEW_A_PREFIX = "新A"

FRAUD_TYPE = "TRUCK_USES_TRUCK_OBU_NON_NEW_A"
DEFAULT_RISK_SCORE = 0.85


def detect_trip(trip: dict) -> Optional[Dict[str, Any]]:
    """返回 None 表示未命中；否则返回结果 dict（含 source_side / risk_score）。"""
    entry_match = _side_match(
        trip.get('entry_vehicle_type'),
        trip.get('entry_media_type'),
        trip.get('entry_vehicle_id'),
    )
    exit_match = _side_match(
        trip.get('exit_vehicle_type'),
        trip.get('exit_media_type'),
        trip.get('exit_vehicle_id'),
    )
    if not (entry_match or exit_match):
        return None
    if entry_match and exit_match:
        source_side = 'BOTH'
    elif entry_match:
        source_side = 'ENTRY'
    else:
        source_side = 'EXIT'
    return {
        'fraud_type': FRAUD_TYPE,
        'source_side': source_side,
        'entry_vehicle_type': trip.get('entry_vehicle_type'),
        'exit_vehicle_type': trip.get('exit_vehicle_type'),
        'entry_media_type': trip.get('entry_media_type'),
        'exit_media_type': trip.get('exit_media_type'),
        'entry_obu_id': trip.get('entry_obu_id'),
        'exit_obu_id': trip.get('exit_obu_id'),
        'risk_score': DEFAULT_RISK_SCORE,
    }


def _side_match(vehicle_type, media_type, vehicle_id) -> bool:
    if vehicle_type not in TRUCK_VEHICLE_TYPES:
        return False
    if media_type != OBU_MEDIA_TYPE:
        return False
    if not vehicle_id:
        return False
    return not str(vehicle_id).startswith(NON_NEW_A_PREFIX)
