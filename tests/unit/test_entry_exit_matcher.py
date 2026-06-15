"""EntryExitMatcher 单元测试 — mock vehicle-ai-service"""
import pytest
from unittest.mock import patch

from apps.api.services.entry_exit_matcher import EntryExitMatcher, compare_trip


class TestEntryExitMatcher:
    def test_compare_match(self, mock_ai_client):
        """测试出入口车辆匹配 — 公共服务返 is_suspicious=False + fingerprint_sim 高"""
        matcher = EntryExitMatcher()
        result = matcher.compare(
            {'image_license': 'http://fake/entry.jpg'},
            {'image_license': 'http://fake/exit.jpg'}
        )
        assert result['_comparison_success'] is True
        assert result['type_match'] is True
        assert result['entry_visual_type'] == 'truck'
        assert result['exit_visual_type'] == 'truck'
        assert mock_ai_client.entry_exit.called

    def test_compare_no_image_urls(self, mock_ai_client):
        """测试缺少图片 URL 时返回空结果 — 不调公共服务"""
        matcher = EntryExitMatcher()
        result = matcher.compare(
            {'image_license': None},
            {'image_license': None}
        )
        assert result['_comparison_success'] is False
        assert result['fingerprint_sim'] == 0.0
        mock_ai_client.entry_exit.assert_not_called()

    def test_compare_service_error_returns_safe_result(self, mock_ai_client):
        """测试公共服务返 error 时返回空结果"""
        mock_ai_client.entry_exit.return_value = {'error': 'service_unavailable', 'detail': 'timeout'}
        matcher = EntryExitMatcher()
        result = matcher.compare(
            {'image_license': 'http://fake/entry.jpg'},
            {'image_license': 'http://fake/exit.jpg'}
        )
        assert result['_comparison_success'] is False
        assert result['fingerprint_sim'] == 0.0
        assert result['is_suspicious'] is False

    def test_compare_type_mismatch_marked_suspicious(self, mock_ai_client):
        """测试车型不一致(type_match=False)时标记可疑"""
        mock_ai_client.entry_exit.return_value = {
            'is_suspicious': True,
            'fraud_type': 'ENTRY_EXIT_MISMATCH',
            'color_match': True,
            'type_match': False,
            'fingerprint_sim': 0.5,
            'entry_color': 'blue',
            'exit_color': 'blue',
            'entry_visual_type': 'truck',
            'exit_visual_type': 'passenger',
            'comparison_success': True,
        }
        matcher = EntryExitMatcher()
        result = matcher.compare(
            {'image_license': 'http://fake/entry.jpg'},
            {'image_license': 'http://fake/exit.jpg'}
        )
        assert result['is_suspicious'] is True
        assert result['fraud_type'] == 'ENTRY_EXIT_MISMATCH'
        assert result['type_match'] is False

    def test_plate_match_consistent(self, mock_ai_client):
        """测试 OCR 识别车牌一致时 plate_match=True，不改变可疑判定"""
        mock_ai_client.recognize_plate.side_effect = [
            {'plate': '京A12345', 'confidence': 0.95},
            {'plate': '京A12345', 'confidence': 0.93},
        ]
        matcher = EntryExitMatcher()
        result = matcher.compare(
            {'image_license': 'http://fake/entry.jpg'},
            {'image_license': 'http://fake/exit.jpg'}
        )
        assert result['plate_match'] is True
        assert result['plate_recognized_entry'] == '京A12345'
        assert result['plate_recognized_exit'] == '京A12345'
        # 视觉比对未可疑，车牌一致 → 仍不可疑
        assert result['is_suspicious'] is False

    def test_plate_mismatch_marks_suspicious(self, mock_ai_client):
        """测试 OCR 识别车牌不一致时标记可疑"""
        mock_ai_client.entry_exit.return_value = {
            'is_suspicious': False,
            'fraud_type': None,
            'color_match': True,
            'type_match': True,
            'fingerprint_sim': 0.92,
            'entry_color': 'blue',
            'exit_color': 'blue',
            'entry_visual_type': 'truck',
            'exit_visual_type': 'truck',
            'comparison_success': True,
        }
        mock_ai_client.recognize_plate.side_effect = [
            {'plate': '京A12345', 'confidence': 0.95},
            {'plate': '沪B67890', 'confidence': 0.93},
        ]
        matcher = EntryExitMatcher()
        result = matcher.compare(
            {'image_license': 'http://fake/entry.jpg'},
            {'image_license': 'http://fake/exit.jpg'}
        )
        assert result['plate_match'] is False
        assert result['is_suspicious'] is True
        assert result['fraud_type'] == 'ENTRY_EXIT_MISMATCH'

    def test_plate_ocr_failure_degrades_gracefully(self, mock_ai_client):
        """测试 OCR 识别失败时退化为纯视觉比对"""
        mock_ai_client.recognize_plate.return_value = {'error': 'service_unavailable'}
        matcher = EntryExitMatcher()
        result = matcher.compare(
            {'image_license': 'http://fake/entry.jpg'},
            {'image_license': 'http://fake/exit.jpg'}
        )
        assert result['plate_match'] is None
        assert result['plate_recognized_entry'] is None
        assert result['plate_recognized_exit'] is None
        # 退化为视觉比对结果
        assert result['_comparison_success'] is True


def test_compare_trip_convenience(mock_ai_client):
    """测试便捷函数 — 走公共服务"""
    result = compare_trip(
        {'image_license': 'http://fake/entry.jpg'},
        {'image_license': 'http://fake/exit.jpg'},
    )
    assert 'is_suspicious' in result
    assert result['_comparison_success'] is True
    mock_ai_client.entry_exit.assert_called_once()
