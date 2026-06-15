"""
车辆双图比对业务封装：手动触发 vehicle-ai-service 对出入口车牌特写做"同一辆车"判定。

调用方不变：
    compare_vehicles_by_passid(passid) -> Dict
业务编排：
    - 入/出口图片 URL 取自 trip_aggregator.aggregate_trip(passid)
    - 入/出口车牌/OBU 取自同一个 trip dict
    - 视觉信号（颜色/车型/fingerprint_sim）取自 audit_results 表
    - 车牌 OCR 信号取自 recognize_plate 接口
    - 缺任一图片 URL → 400（image_url_missing）
    - 调公共服务失败 → service_unavailable，不抛异常
    - 元数据完整时优先走侧车的分档裁决，完全省去 LLM
"""

from typing import Any, Dict, Optional

from apps.api.core.logging_config import get_logger
from apps.api.core.vehicle_ai_client import get_client
from apps.api.database.repositories.audit_repository import AuditRepository
from apps.api.services.trip_aggregator import aggregate_trip

logger = get_logger(__name__)


def _missing_image_error(missing_field: str) -> Dict[str, Any]:
    return {
        'error': 'image_url_missing',
        'field': missing_field,
    }


def _unavailable_error(detail: str) -> Dict[str, Any]:
    return {
        'error': 'service_unavailable',
        'detail': detail,
    }


def _fetch_visual_features(passid: str) -> Dict[str, Any]:
    """从 audit_results 拉视觉信号，失败/缺失时返回空 dict（走 LLM 回退）。"""
    try:
        row = AuditRepository().get_visual_features_by_passid(passid)
    except Exception as e:
        logger.warning('visual_features lookup failed for %s: %s', passid, e)
        return {}
    if not row:
        return {}
    return {
        'entry_color': row.get('entry_color'),
        'exit_color': row.get('exit_color'),
        'entry_visual_type': row.get('entry_visual_type'),
        'exit_visual_type': row.get('exit_visual_type'),
        'fingerprint_sim': row.get('fingerprint_sim'),
    }


def _recognize_plate_safe(image_url: str) -> Optional[Dict]:
    """调用车牌 OCR 识别，失败时返回 None。"""
    if not image_url:
        return None
    try:
        result = get_client().recognize_plate(image_url)
        if isinstance(result, dict) and 'error' not in result and result.get('plate'):
            return result
    except Exception as e:
        logger.warning('recognize_plate failed for %s: %s', image_url, e)
    return None


def compare_vehicles_by_passid(passid: str) -> Dict[str, Any]:
    """按 passid 取行程后，把图片 URL + 元数据 + 车牌 OCR 信号透传给 vehicle-ai-service。

    Returns:
        成功：{'passid', 'is_same_vehicle', 'confidence', 'reason',
              'entry_image_url', 'exit_image_url', 'model', 'elapsed_ms',
              'plate_match', 'plate_recognized_entry', 'plate_recognized_exit'}
        失败：{'error': 'trip_not_found'|'image_url_missing'|'service_unavailable'|
                       'parse_error', ...}
    """
    if not passid:
        return _missing_image_error('passid')

    trip = aggregate_trip(passid)
    if not trip:
        return {'error': 'trip_not_found'}

    entry_url = trip.get('entry_image_license')
    exit_url = trip.get('exit_image_license')

    if not entry_url:
        return _missing_image_error('entry_image_license')
    if not exit_url:
        return _missing_image_error('exit_image_license')

    visual = _fetch_visual_features(passid)

    # 车牌 OCR 识别
    entry_ocr = _recognize_plate_safe(entry_url)
    exit_ocr = _recognize_plate_safe(exit_url)

    entry_plate_ocr = None
    exit_plate_ocr = None
    plate_match = None
    if entry_ocr:
        entry_plate_ocr = entry_ocr.get('plate')
    if exit_ocr:
        exit_plate_ocr = exit_ocr.get('plate')
    if entry_plate_ocr and exit_plate_ocr:
        plate_match = (entry_plate_ocr or '').strip().upper() == (exit_plate_ocr or '').strip().upper()

    try:
        result = get_client().compare(
            entry_url,
            exit_url,
            entry_vehicle_id=trip.get('entry_vehicle_id'),
            exit_vehicle_id=trip.get('exit_vehicle_id'),
            entry_obu_id=trip.get('entry_obu_id'),
            exit_obu_id=trip.get('exit_obu_id'),
            entry_color=visual.get('entry_color'),
            exit_color=visual.get('exit_color'),
            entry_visual_type=visual.get('entry_visual_type'),
            exit_visual_type=visual.get('exit_visual_type'),
            fingerprint_sim=visual.get('fingerprint_sim'),
            entry_plate_ocr=entry_plate_ocr,
            exit_plate_ocr=exit_plate_ocr,
            plate_match=plate_match,
        )
    except Exception as e:
        logger.warning('compare service raised for %s: %s', passid, e)
        return _unavailable_error(str(e))

    if 'error' in result:
        if result['error'] in ('image_url_missing',):
            return result
        return _unavailable_error(result.get('detail', result['error']))

    missing = [k for k in ('is_same_vehicle', 'confidence', 'reason', 'model') if k not in result]
    if missing:
        return {
            'error': 'parse_error',
            'detail': f'missing fields: {missing}',
        }

    return {
        'passid': passid,
        'is_same_vehicle': bool(result['is_same_vehicle']),
        'confidence': float(result['confidence']),
        'reason': str(result.get('reason', '')),
        'entry_image_url': entry_url,
        'exit_image_url': exit_url,
        'model': str(result.get('model', '')),
        'elapsed_ms': int(result.get('elapsed_ms', 0)),
        'plate_match': plate_match,
        'plate_recognized_entry': entry_plate_ocr,
        'plate_recognized_exit': exit_plate_ocr,
    }
