"""
车辆双图比对业务封装：手动触发 MaaS 对出入口车牌特写做"同一辆车"判定。

设计原则：
- 入口/出口图片 URL 取自 trip_aggregator.aggregate_trip(passid) 的
  entry_image_license / exit_image_license（Doris 已 join 出的完整 URL）。
- 缺任一图片 URL → 400（image_url_missing）。
- 调 MaaS 前先把图片下载到本地临时 jpg，函数返回前清理。
- 任何 MaaS 异常 / 解析失败都翻译为 error dict，路由层映射到 502。
"""

import os
import time
import tempfile
from typing import Any, Dict

from apps.api.core.logging_config import get_logger
from apps.api.services.image_utils import download_images_parallel
from apps.api.services.trip_aggregator import aggregate_trip

logger = get_logger(__name__)


def _missing_image_error(missing_field: str) -> Dict[str, Any]:
    return {
        'error': 'image_url_missing',
        'field': missing_field,
    }


def _unavailable_error(detail: str) -> Dict[str, Any]:
    return {
        'error': 'maas_unavailable',
        'detail': detail,
    }


def _parse_error(detail: str) -> Dict[str, Any]:
    return {
        'error': 'parse_error',
        'detail': detail,
    }


def _write_temp_image(url: str, url_to_bytes: Dict[str, Any]) -> str:
    """从 url_to_bytes 取出 url 对应 BytesIO，写到 NamedTemporaryFile(jpg)，返回路径。"""
    image_io = url_to_bytes.get(url)
    if image_io is None:
        raise ValueError(f"image not downloaded: {url}")
    image_io.seek(0)
    tmp = tempfile.NamedTemporaryFile(prefix='maas-', suffix='.jpg', delete=False)
    try:
        tmp.write(image_io.getvalue())
        tmp.flush()
    finally:
        tmp.close()
    return tmp.name


def compare_vehicles_by_passid(passid: str) -> Dict[str, Any]:
    """按 passid 取行程后，并行下载出入口车牌图，调 MaaS 双图比对。

    Returns:
        成功：{'passid', 'is_same_vehicle', 'confidence', 'reason',
              'entry_image_url', 'exit_image_url', 'model', 'elapsed_ms'}
        失败：{'error': 'trip_not_found'|'image_url_missing'|'image_download_failed'|
                       'maas_unavailable'|'parse_error', ...}
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

    started = time.monotonic()
    url_to_bytes = download_images_parallel([entry_url, exit_url])
    if url_to_bytes.get(entry_url) is None or url_to_bytes.get(exit_url) is None:
        return {
            'error': 'image_download_failed',
            'entry_ok': url_to_bytes.get(entry_url) is not None,
            'exit_ok': url_to_bytes.get(exit_url) is not None,
        }

    tmp_paths = []
    try:
        tmp_a = _write_temp_image(entry_url, url_to_bytes)
        tmp_b = _write_temp_image(exit_url, url_to_bytes)
        tmp_paths = [tmp_a, tmp_b]
    except Exception as e:
        for p in tmp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass
        logger.error("vehicle_comparator: write temp file failed for %s: %s", passid, e)
        return _unavailable_error(f"temp file write failed: {e}")

    try:
        from apps.api.LLM.Maas import compare_vehicles
        result = compare_vehicles(tmp_paths[0], tmp_paths[1])
    except Exception as e:
        logger.error("vehicle_comparator: MaaS call failed for %s: %s", passid, e)
        return _unavailable_error(str(e))
    finally:
        for p in tmp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass

    if not result:
        return _unavailable_error("empty result from MaaS")

    missing = [k for k in ('is_same_vehicle', 'confidence', 'reason') if k not in result]
    if missing:
        return _parse_error(f"missing fields: {missing}")

    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        'passid': passid,
        'is_same_vehicle': bool(result['is_same_vehicle']),
        'confidence': float(result['confidence']),
        'reason': str(result.get('reason', '')),
        'entry_image_url': entry_url,
        'exit_image_url': exit_url,
        'model': str(result.get('model', '')),
        'elapsed_ms': elapsed_ms,
    }
