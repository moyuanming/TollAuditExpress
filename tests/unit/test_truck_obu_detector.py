"""TruckOBUDetector 单元测试 — mock vehicle-ai-service"""
import pytest
from unittest.mock import patch, MagicMock

from apps.api.services.truck_obu_detector import TruckOBUDetector, detect_single_record


class TestTruckOBUDetector:
    def test_detect_passenger_obus_with_truck_image(self, mock_ai_client):
        """测试客车交易 + 货车图片 — 公共服务返回 visual_vehicle_type=truck 时标记可疑"""
        detector = TruckOBUDetector()
        result = detector.detect({
            'VEHICLETYPE': 1,
            'image_trans': 'http://fake/trans.jpg'
        })
        assert result['visual_vehicle_type'] == 'truck'
        assert result['record_vehicle_type'] == 1
        assert result['is_suspicious'] is True
        assert mock_ai_client.truck_obu.called

    def test_detect_non_passenger_skip(self, mock_ai_client):
        """测试非客车直接跳过 — 不调公共服务"""
        detector = TruckOBUDetector()
        result = detector.detect({
            'VEHICLETYPE': 2,
            'image_trans': 'http://fake/trans.jpg'
        })
        assert result['is_suspicious'] is False
        assert result['visual_vehicle_type'] is None
        mock_ai_client.truck_obu.assert_not_called()

    def test_detect_no_image_url(self, mock_ai_client):
        """测试无图片 URL"""
        detector = TruckOBUDetector()
        result = detector.detect({
            'VEHICLETYPE': 1,
            'image_trans': None
        })
        assert result['is_suspicious'] is False
        mock_ai_client.truck_obu.assert_not_called()

    def test_detect_service_error_returns_safe_result(self, mock_ai_client):
        """测试公共服务返回 error 时返回空结果(不抛异常)"""
        mock_ai_client.truck_obu.return_value = {'error': 'service_unavailable', 'detail': 'timeout'}
        detector = TruckOBUDetector()
        result = detector.detect({
            'VEHICLETYPE': 1,
            'image_trans': 'http://fake/trans.jpg'
        })
        assert result['is_suspicious'] is False
        assert result['visual_vehicle_type'] is None
        assert result['confidence'] == 0.0

    def test_detect_service_raises_returns_safe_result(self, mock_ai_client):
        """测试公共服务抛异常时返回空结果"""
        mock_ai_client.truck_obu.side_effect = RuntimeError("service down")
        detector = TruckOBUDetector()
        result = detector.detect({
            'VEHICLETYPE': 1,
            'image_trans': 'http://fake/trans.jpg'
        })
        assert result['is_suspicious'] is False
        assert result['visual_vehicle_type'] is None


def test_detect_single_record_convenience(mock_ai_client):
    """测试便捷函数 — 走公共服务,断言返回字典"""
    result = detect_single_record(1, 'http://fake/img.jpg')
    assert 'is_suspicious' in result
    assert result['visual_vehicle_type'] == 'truck'
    mock_ai_client.truck_obu.assert_called_once()
