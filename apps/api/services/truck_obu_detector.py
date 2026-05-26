"""
货车套用客车OBU检测服务
检测交易记录为客车(VEHICLETYPE=1)但图片识别为货车的情况
适配自 getmoveobu/audit/services/truck_obu_detector.py
"""

import sys
import os
from typing import Dict, Optional

# 添加 getmoveobu 路径以复用 ML 模型
GETMOVEOBU_PATH = '/Users/moyuanming/getmoveobu'
if GETMOVEOBU_PATH not in sys.path:
    sys.path.insert(0, GETMOVEOBU_PATH)

try:
    import requests
    from io import BytesIO
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from apps.api.core.ml.vehicle_classifier import VehicleClassifier


class TruckOBUDetector:
    """货车套用客车OBU检测器"""

    def __init__(self, model_path: str = None):
        if model_path is None:
            model_path = os.path.join(GETMOVEOBU_PATH, 'best_model.pth')
        self.classifier = VehicleClassifier(model_path)

    def download_image(self, url: str) -> Optional[BytesIO]:
        """下载图片"""
        if not HAS_REQUESTS:
            return None

        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200 and 'image' in response.headers.get('Content-Type', ''):
                return BytesIO(response.content)
        except Exception:
            pass
        return None

    def detect(self, record: Dict) -> Dict:
        """
        检测单条记录是否涉嫌货车套用客车OBU

        Args:
            record: 包含以下字段的字典:
                - VEHICLETYPE: 交易记录的车辆类型 (1=客车)
                - image_trans: _trans.jpg URL

        Returns:
            检测结果字典:
                - is_suspicious: 是否可疑
                - fraud_type: 逃费类型
                - record_vehicle_type: 交易记录车型
                - visual_vehicle_type: 视觉识别车型
                - confidence: 识别置信度
        """
        result = {
            'is_suspicious': False,
            'fraud_type': None,
            'record_vehicle_type': record.get('VEHICLETYPE'),
            'visual_vehicle_type': None,
            'confidence': 0.0
        }

        # 只检测交易记录为客车的(VEHICLETYPE=1)
        if record.get('VEHICLETYPE') != 1:
            return result

        image_url = record.get('image_trans')
        if not image_url:
            return result

        # 下载图片
        image_io = self.download_image(image_url)
        if not image_io:
            return result

        # 视觉模型识别
        try:
            classify_result = self.classifier.classify(image_io)
            if classify_result and len(classify_result) > 0:
                visual_class = classify_result[0]['class']
                confidence = classify_result[0]['confidence']
                result['visual_vehicle_type'] = visual_class
                result['confidence'] = confidence

                # 交易记录=客车 但 视觉识别=货车 → 可疑
                if visual_class == 'truck' and confidence >= 0.8:
                    result['is_suspicious'] = True
                    result['fraud_type'] = 'TRUCK_USES_PASSENGER_OBU'
        except Exception:
            pass

        return result


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
