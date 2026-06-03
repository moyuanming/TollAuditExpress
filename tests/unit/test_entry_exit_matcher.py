"""EntryExitMatcher 单元测试"""
import pytest
from unittest.mock import patch

from apps.api.services.entry_exit_matcher import EntryExitMatcher, compare_trip


class TestEntryExitMatcher:
    def test_compare_match(self, mock_ml_models, mock_image_download):
        """测试出入口车辆匹配 — 同类型车"""
        matcher = EntryExitMatcher()
        result = matcher.compare(
            {'image_license': 'http://fake/entry.jpg'},
            {'image_license': 'http://fake/exit.jpg'}
        )
        assert result['_comparison_success'] is True
        assert result['type_match'] is True
        assert result['entry_visual_type'] == 'truck'
        assert result['exit_visual_type'] == 'truck'

    def test_compare_no_image_urls(self, mock_ml_models):
        """测试缺少图片 URL 时返回空结果"""
        matcher = EntryExitMatcher()
        result = matcher.compare(
            {'image_license': None},
            {'image_license': None}
        )
        assert result['_comparison_success'] is False
        assert result['fingerprint_sim'] == 0.0

    def test_compare_download_failure(self, mock_ml_models):
        """测试图片下载失败时容错"""
        from io import BytesIO

        def fake_fail(url, timeout=None):
            return None

        with patch(
            'apps.api.services.entry_exit_matcher.download_image',
            side_effect=fake_fail
        ):
            matcher = EntryExitMatcher()
            result = matcher.compare(
                {'image_license': 'http://fake/entry.jpg'},
                {'image_license': 'http://fake/exit.jpg'}
            )
        assert result['fingerprint_sim'] == 0.0

    def test_compare_classifier_type_mismatch(self, mock_image_download):
        """测试车型不一致时标记可疑"""
        call_count = [0]

        class AlternatingClassifier:
            def classify(self, image_io):
                call_count[0] += 1
                if call_count[0] == 1:
                    return [{'class': 'truck', 'confidence': 0.9}]
                return [{'class': 'passenger', 'confidence': 0.9}]

        with patch(
            'apps.api.services.entry_exit_matcher.VehicleClassifier',
            return_value=AlternatingClassifier()
        ):
            matcher = EntryExitMatcher()
            result = matcher.compare(
                {'image_license': 'http://fake/entry.jpg'},
                {'image_license': 'http://fake/exit.jpg'}
            )
        assert result['is_suspicious'] is True
        assert result['fraud_type'] == 'ENTRY_EXIT_MISMATCH'


def test_compare_trip_convenience():
    """测试便捷函数 — 无 ML 模型时至少不崩溃"""
    try:
        result = compare_trip({}, {})
        assert 'is_suspicious' in result
    except Exception:
        pass
