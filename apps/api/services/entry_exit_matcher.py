"""
出入口车辆比对服务 — 调用 vehicle-ai-service
比对出入口车辆图片，判断是否为同一辆车
增加车牌 OCR 识别，将车牌一致性作为比对权重
"""


from apps.api.core.logging_config import get_logger
from apps.api.core.vehicle_ai_client import get_client

logger = get_logger(__name__)


def _recognize_plate_safe(image_url: str) -> dict | None:
    """调用车牌 OCR 识别，失败时返回 None（不抛异常）。"""
    if not image_url:
        return None
    try:
        result = get_client().recognize_plate(image_url)
        if isinstance(result, dict) and 'error' not in result and result.get('plate'):
            return result
    except Exception as e:
        logger.warning('recognize_plate failed for %s: %s', image_url, e)
    return None


class EntryExitMatcher:
    """出入口车辆比对器 — HTTP 客户端封装"""

    def __init__(self, model_path: str | None = None):
        """model_path 参数保留以兼容旧调用,但不再使用(由公共服务托管)"""
        self.model_path = model_path

    def download_image(self, url: str):
        """保留旧接口(内部不再使用,公共服务会自己下载)"""
        raise NotImplementedError(
            "EntryExitMatcher 现在通过 vehicle-ai-service 调用,不再本地下载图片"
        )

    def compare(self, entry_record: dict, exit_record: dict) -> dict:
        """
        比对出入口车辆

        Args:
            entry_record: 入口记录 (含 image_license 字段)
            exit_record: 出口记录 (含 image_license 字段)

        Returns:
            比对结果:
                - is_suspicious, fraud_type, color_match, type_match,
                  fingerprint_sim, entry_color, exit_color,
                  entry_visual_type, exit_visual_type,
                  plate_match, plate_recognized_entry, plate_recognized_exit,
                  plate_confidence_entry, plate_confidence_exit,
                  _comparison_success
        """
        result = {
            'is_suspicious': False,
            'fraud_type': None,
            'color_match': True,
            'type_match': True,
            'fingerprint_sim': 0.0,
            'entry_color': None,
            'exit_color': None,
            'entry_visual_type': None,
            'exit_visual_type': None,
            'plate_match': None,
            'plate_recognized_entry': None,
            'plate_recognized_exit': None,
            'plate_confidence_entry': None,
            'plate_confidence_exit': None,
            '_comparison_success': False
        }

        entry_url = entry_record.get('image_license')
        exit_url = exit_record.get('image_license')

        if not entry_url or not exit_url:
            result['fingerprint_sim'] = 0.0
            return result

        response = get_client().entry_exit(entry_url, exit_url)

        if 'error' in response:
            logger.error(
                "vehicle-ai-service entry_exit failed: entry=%s exit=%s err=%s url=%s",
                entry_url, exit_url, response, response.get('url'),
            )
            return result

        result.update({
            'is_suspicious': bool(response.get('is_suspicious', False)),
            'fraud_type': response.get('fraud_type'),
            'color_match': bool(response.get('color_match', True)),
            'type_match': bool(response.get('type_match', True)),
            'fingerprint_sim': float(response.get('fingerprint_sim', 0.0)),
            'entry_color': response.get('entry_color'),
            'exit_color': response.get('exit_color'),
            'entry_visual_type': response.get('entry_visual_type'),
            'exit_visual_type': response.get('exit_visual_type'),
            '_comparison_success': bool(response.get('comparison_success', False)),
        })

        # 车牌 OCR 识别 — 作为独立信号参与判定
        entry_ocr = _recognize_plate_safe(entry_url)
        exit_ocr = _recognize_plate_safe(exit_url)

        if entry_ocr:
            result['plate_recognized_entry'] = entry_ocr.get('plate')
            result['plate_confidence_entry'] = entry_ocr.get('confidence')
        if exit_ocr:
            result['plate_recognized_exit'] = exit_ocr.get('plate')
            result['plate_confidence_exit'] = exit_ocr.get('confidence')

        # 两端都有 OCR 结果时比较车牌一致性
        if entry_ocr and exit_ocr:
            entry_plate = (entry_ocr.get('plate') or '').strip().upper()
            exit_plate = (exit_ocr.get('plate') or '').strip().upper()
            plate_match = entry_plate == exit_plate and entry_plate != ''
            result['plate_match'] = plate_match

            # 车牌不一致 → 加强可疑判定
            if not plate_match:
                if not result['is_suspicious']:
                    result['is_suspicious'] = True
                    if not result['fraud_type']:
                        result['fraud_type'] = 'ENTRY_EXIT_MISMATCH'

        return result


def compare_trip(entry_record: dict, exit_record: dict) -> dict:
    """
    便捷函数：比对出入口记录
    """
    matcher = EntryExitMatcher()
    return matcher.compare(entry_record, exit_record)
