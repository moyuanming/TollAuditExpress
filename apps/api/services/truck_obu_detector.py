"""
货车套用客车OBU检测服务 — 调用 vehicle-ai-service
检测交易记录为客车(VEHICLETYPE=1)但图片识别为货车的情况
"""

from typing import Dict, Optional

from apps.api.core.logging_config import get_logger
from apps.api.core.vehicle_ai_client import get_client

logger = get_logger(__name__)


class TruckOBUDetector:
    """货车套用客车OBU检测器 — HTTP 客户端封装"""

    def __init__(self, model_path: Optional[str] = None):
        """model_path 参数保留以兼容旧调用,但不再使用(由公共服务托管)"""
        self.model_path = model_path

    def download_image(self, url: str):
        """保留旧接口(内部不再使用,公共服务会自己下载)"""
        raise NotImplementedError(
            "TruckOBUDetector 现在通过 vehicle-ai-service 调用,不再本地下载图片"
        )

    def detect(self, record: Dict) -> Dict:
        """
        检测单条记录是否涉嫌货车套用客车 OBU

        Args:
            record: 包含以下字段的字典:
                - VEHICLETYPE: 交易记录的车辆类型 (1=客车)
                - image_trans: _trans.jpg URL

        Returns:
            检测结果字典(字段与旧实现保持一致):
                - is_suspicious, fraud_type, record_vehicle_type,
                  visual_vehicle_type, llm_verified, confidence
        """
        result = {
            'is_suspicious': False,
            'fraud_type': None,
            'record_vehicle_type': record.get('VEHICLETYPE'),
            'visual_vehicle_type': None,
            'llm_verified': False,
            'confidence': 0.0
        }

        if record.get('VEHICLETYPE') != 1:
            return result

        image_url = record.get('image_trans')
        if not image_url:
            return result

        try:
            response = get_client().truck_obu(image_url, declared_vehicle_type=1)
        except Exception as e:
            logger.error("vehicle-ai-service truck_obu raised for %s: %s", image_url, e)
            return result

        if 'error' in response:
            logger.error("vehicle-ai-service truck_obu failed for %s: %s", image_url, response)
            return result

        return {
            'is_suspicious': bool(response.get('is_suspicious', False)),
            'fraud_type': response.get('fraud_type'),
            'record_vehicle_type': record.get('VEHICLETYPE'),
            'visual_vehicle_type': response.get('visual_vehicle_type'),
            'llm_verified': bool(response.get('llm_verified', False)),
            'confidence': float(response.get('confidence', 0.0)),
        }


def detect_single_record(vehicle_type: int, image_url: str) -> Dict:
    """
    便捷函数：检测单条记录

    Args:
        vehicle_type: 交易记录的车辆类型 (1=客车)
        image_url: _trans.jpg 图片URL

    Returns:
        检测结果字典
    """
    detector = TruckOBUDetector()
    record = {
        'VEHICLETYPE': vehicle_type,
        'image_trans': image_url
    }
    return detector.detect(record)
