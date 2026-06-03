"""
货车套用客车OBU检测服务
检测交易记录为客车(VEHICLETYPE=1)但图片识别为货车的情况
"""

import os
from io import BytesIO
from typing import Dict, Optional

from apps.api.core.config import MODEL_PATH, TRUCK_OBU_CONFIDENCE_THRESHOLD
from apps.api.services.image_utils import download_image
from apps.api.core.logging_config import get_logger

from apps.api.core.ml.vehicle_classifier import VehicleClassifier

logger = get_logger(__name__)


class TruckOBUDetector:
    """货车套用客车OBU检测器"""

    def __init__(self, model_path: str = None):
        if model_path is None:
            model_path = MODEL_PATH
        self.classifier = VehicleClassifier(model_path)

    def download_image(self, url: str) -> Optional[BytesIO]:
        """下载图片"""
        return download_image(url)

    def _verify_with_llm(self, image_bytes: BytesIO) -> Optional[int]:
        """使用大模型二次验证
        
        Args:
            image_bytes: 图片字节数据
            
        Returns:
            1: 是货车, 0: 不是货车, None: 验证失败
        """
        try:
            from apps.api.LLM.ZhiPu import detect_truck
            import tempfile
            
            # 保存临时文件用于LLM检测
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp.write(image_bytes.getvalue())
                tmp_path = tmp.name
            
            try:
                result = detect_truck(tmp_path)
                return result
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            logger.warning("LLM验证失败: %s", e)
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
                - llm_verified: 是否经过LLM二次确认
                - confidence: 识别置信度
        """
        result = {
            'is_suspicious': False,
            'fraud_type': None,
            'record_vehicle_type': record.get('VEHICLETYPE'),
            'visual_vehicle_type': None,
            'llm_verified': False,
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

                # 模型识别为货车且置信度高
                if visual_class == 'truck' and confidence >= TRUCK_OBU_CONFIDENCE_THRESHOLD:
                    # 使用大模型二次确认
                    image_io.seek(0)
                    llm_result = self._verify_with_llm(image_io)
                    
                    if llm_result == 1:
                        # 大模型也确认为货车 → 可疑（货套客）
                        result['is_suspicious'] = True
                        result['fraud_type'] = 'TRUCK_USES_PASSENGER_OBU'
                        result['llm_verified'] = True
                    elif llm_result == 0:
                        # 大模型否定 → 不是货套客
                        result['is_suspicious'] = False
                        result['llm_verified'] = True
                    # llm_result == None 时保持不确定状态
                        
        except Exception as e:
            logger.error("VehicleClassifier error for %s: %s", record.get('image_trans', 'unknown'), e)

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
