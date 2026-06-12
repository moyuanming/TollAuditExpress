"""
出入口车辆比对服务 — 调用 vehicle-ai-service
比对出入口车辆图片，判断是否为同一辆车
"""

from typing import Dict, Optional

from apps.api.core.logging_config import get_logger
from apps.api.core.vehicle_ai_client import get_client

logger = get_logger(__name__)


class EntryExitMatcher:
    """出入口车辆比对器 — HTTP 客户端封装"""

    def __init__(self, model_path: Optional[str] = None):
        """model_path 参数保留以兼容旧调用,但不再使用(由公共服务托管)"""
        self.model_path = model_path

    def download_image(self, url: str):
        """保留旧接口(内部不再使用,公共服务会自己下载)"""
        raise NotImplementedError(
            "EntryExitMatcher 现在通过 vehicle-ai-service 调用,不再本地下载图片"
        )

    def compare(self, entry_record: Dict, exit_record: Dict) -> Dict:
        """
        比对出入口车辆

        Args:
            entry_record: 入口记录 (含 image_license 字段)
            exit_record: 出口记录 (含 image_license 字段)

        Returns:
            比对结果(字段与旧实现保持一致):
                - is_suspicious, fraud_type, color_match, type_match,
                  fingerprint_sim, entry_color, exit_color,
                  entry_visual_type, exit_visual_type,
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

        return {
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
        }


def compare_trip(entry_record: Dict, exit_record: Dict) -> Dict:
    """
    便捷函数：比对出入口记录
    """
    matcher = EntryExitMatcher()
    return matcher.compare(entry_record, exit_record)
