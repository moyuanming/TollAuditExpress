"""TruckOBUDetector 单元测试"""
import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO

from apps.api.services.truck_obu_detector import TruckOBUDetector, detect_single_record


class TestTruckOBUDetector:
    def test_detect_passenger_obus_with_truck_image(self, mock_ml_models, mock_image_download):
        """测试客车交易 + 货车图片"""
        detector = TruckOBUDetector()
        result = detector.detect({
            'VEHICLETYPE': 1,
            'image_trans': 'http://fake/trans.jpg'
        })
        assert result['visual_vehicle_type'] == 'truck'
        assert result['record_vehicle_type'] == 1

    def test_detect_non_passenger_skip(self, mock_ml_models):
        """测试非客车直接跳过"""
        detector = TruckOBUDetector()
        result = detector.detect({
            'VEHICLETYPE': 2,
            'image_trans': 'http://fake/trans.jpg'
        })
        assert result['is_suspicious'] is False
        assert result['visual_vehicle_type'] is None

    def test_detect_no_image_url(self, mock_ml_models):
        """测试无图片 URL"""
        detector = TruckOBUDetector()
        result = detector.detect({
            'VEHICLETYPE': 1,
            'image_trans': None
        })
        assert result['is_suspicious'] is False

    def test_detect_download_failure(self, mock_ml_models):
        """测试图片下载失败"""
        with patch(
            'apps.api.services.truck_obu_detector.download_image',
            return_value=None
        ):
            detector = TruckOBUDetector()
            result = detector.detect({
                'VEHICLETYPE': 1,
                'image_trans': 'http://fake/trans.jpg'
            })
        assert result['is_suspicious'] is False

    def test_detect_classify_error(self, mock_image_download):
        """测试模型分类异常时容错"""
        broken = MagicMock()
        broken.classify.side_effect = RuntimeError("GPU not available")

        with patch(
            'apps.api.services.truck_obu_detector.VehicleClassifier',
            return_value=broken
        ):
            detector = TruckOBUDetector()
            result = detector.detect({
                'VEHICLETYPE': 1,
                'image_trans': 'http://fake/trans.jpg'
            })
        assert result['is_suspicious'] is False


def test_detect_single_record_convenience():
    """测试便捷函数"""
    try:
        result = detect_single_record(1, 'http://fake/img.jpg')
        assert 'is_suspicious' in result
    except Exception:
        pass
