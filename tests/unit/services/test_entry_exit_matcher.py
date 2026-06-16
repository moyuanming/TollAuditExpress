"""EntryExitMatcher 单元测试 — 出入口车辆比对服务

测试范围：
  - EntryExitMatcher.compare() 核心比对逻辑
  - compare_trip() 便捷函数
  - EntryExitMatcher.download_image() 废弃接口
  - _recognize_plate_safe() 车牌 OCR 安全包装
  - 车牌不一致时加强可疑判定
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.api.services.entry_exit_matcher import (
    EntryExitMatcher,
    _recognize_plate_safe,
    compare_trip,
)

# ============================================================
# EntryExitMatcher.download_image — 废弃接口
# ============================================================


class TestDownloadImageDeprecated:
    """download_image 应抛 NotImplementedError"""

    def test_download_image_raises_not_implemented(self):
        matcher = EntryExitMatcher()
        with pytest.raises(NotImplementedError, match="vehicle-ai-service"):
            matcher.download_image("http://example.com/img.jpg")


# ============================================================
# EntryExitMatcher.compare — 核心比对
# ============================================================


class TestCompareNoImageUrls:
    """缺少图片 URL 时返回默认结果"""

    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_returns_default_when_entry_url_missing(self, mock_get_client):
        matcher = EntryExitMatcher()
        result = matcher.compare({}, {"image_license": "http://exit.jpg"})
        assert result["is_suspicious"] is False
        assert result["fingerprint_sim"] == 0.0
        assert result["_comparison_success"] is False
        # get_client 不应被调用
        mock_get_client.assert_not_called()

    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_returns_default_when_exit_url_missing(self, mock_get_client):
        matcher = EntryExitMatcher()
        result = matcher.compare({"image_license": "http://entry.jpg"}, {})
        assert result["is_suspicious"] is False
        assert result["fingerprint_sim"] == 0.0
        assert result["_comparison_success"] is False

    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_returns_default_when_both_urls_missing(self, mock_get_client):
        matcher = EntryExitMatcher()
        result = matcher.compare({}, {})
        assert result["is_suspicious"] is False
        assert result["fingerprint_sim"] == 0.0

    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_returns_default_when_entry_url_is_none(self, mock_get_client):
        matcher = EntryExitMatcher()
        result = matcher.compare({"image_license": None}, {"image_license": "http://exit.jpg"})
        assert result["is_suspicious"] is False

    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_returns_default_when_exit_url_is_empty_string(self, mock_get_client):
        matcher = EntryExitMatcher()
        result = matcher.compare({"image_license": "http://entry.jpg"}, {"image_license": ""})
        assert result["is_suspicious"] is False


class TestCompareServiceError:
    """vehicle-ai-service 返回错误时的处理"""

    @patch("apps.api.services.entry_exit_matcher._recognize_plate_safe", return_value=None)
    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_returns_default_on_service_error(self, mock_get_client, mock_ocr):
        fake_client = MagicMock()
        fake_client.entry_exit.return_value = {"error": "service_unavailable", "detail": "timeout"}
        mock_get_client.return_value = fake_client

        matcher = EntryExitMatcher()
        result = matcher.compare(
            {"image_license": "http://entry.jpg"},
            {"image_license": "http://exit.jpg"},
        )
        assert result["is_suspicious"] is False
        assert result["_comparison_success"] is False
        assert result["fingerprint_sim"] == 0.0


class TestCompareSuccess:
    """vehicle-ai-service 正常返回时的处理"""

    @patch("apps.api.services.entry_exit_matcher._recognize_plate_safe", return_value=None)
    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_returns_success_fields_on_normal_response(self, mock_get_client, mock_ocr):
        fake_client = MagicMock()
        fake_client.entry_exit.return_value = {
            "is_suspicious": True,
            "fraud_type": "ENTRY_EXIT_MISMATCH",
            "color_match": False,
            "type_match": True,
            "fingerprint_sim": 0.85,
            "entry_color": "blue",
            "exit_color": "red",
            "entry_visual_type": "truck",
            "exit_visual_type": "car",
            "comparison_success": True,
        }
        mock_get_client.return_value = fake_client

        matcher = EntryExitMatcher()
        result = matcher.compare(
            {"image_license": "http://entry.jpg"},
            {"image_license": "http://exit.jpg"},
        )
        assert result["is_suspicious"] is True
        assert result["fraud_type"] == "ENTRY_EXIT_MISMATCH"
        assert result["color_match"] is False
        assert result["type_match"] is True
        assert result["fingerprint_sim"] == pytest.approx(0.85)
        assert result["entry_color"] == "blue"
        assert result["exit_color"] == "red"
        assert result["entry_visual_type"] == "truck"
        assert result["exit_visual_type"] == "car"
        assert result["_comparison_success"] is True

    @patch("apps.api.services.entry_exit_matcher._recognize_plate_safe", return_value=None)
    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_defaults_when_response_missing_optional_fields(self, mock_get_client, mock_ocr):
        fake_client = MagicMock()
        fake_client.entry_exit.return_value = {
            "comparison_success": True,
        }
        mock_get_client.return_value = fake_client

        matcher = EntryExitMatcher()
        result = matcher.compare(
            {"image_license": "http://entry.jpg"},
            {"image_license": "http://exit.jpg"},
        )
        assert result["is_suspicious"] is False
        assert result["fraud_type"] is None
        assert result["color_match"] is True
        assert result["type_match"] is True
        assert result["fingerprint_sim"] == 0.0
        assert result["_comparison_success"] is True

    @patch("apps.api.services.entry_exit_matcher._recognize_plate_safe", return_value=None)
    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_passes_correct_urls_to_entry_exit(self, mock_get_client, mock_ocr):
        fake_client = MagicMock()
        fake_client.entry_exit.return_value = {"comparison_success": True}
        mock_get_client.return_value = fake_client

        matcher = EntryExitMatcher()
        matcher.compare(
            {"image_license": "http://entry.jpg"},
            {"image_license": "http://exit.jpg"},
        )
        fake_client.entry_exit.assert_called_once_with("http://entry.jpg", "http://exit.jpg")


class TestComparePlateOcr:
    """车牌 OCR 识别与一致性判定"""

    @patch("apps.api.services.entry_exit_matcher._recognize_plate_safe")
    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_populates_plate_ocr_results(self, mock_get_client, mock_ocr):
        fake_client = MagicMock()
        fake_client.entry_exit.return_value = {
            "is_suspicious": False,
            "color_match": True,
            "type_match": True,
            "fingerprint_sim": 0.9,
            "comparison_success": True,
        }
        mock_get_client.return_value = fake_client

        entry_url = "http://entry.jpg"
        exit_url = "http://exit.jpg"
        mock_ocr.side_effect = lambda url: (
            {"plate": "京A12345", "confidence": 0.95}
            if url == entry_url
            else {"plate": "京A12345", "confidence": 0.93}
            if url == exit_url
            else None
        )

        matcher = EntryExitMatcher()
        result = matcher.compare({"image_license": entry_url}, {"image_license": exit_url})
        assert result["plate_recognized_entry"] == "京A12345"
        assert result["plate_recognized_exit"] == "京A12345"
        assert result["plate_confidence_entry"] == 0.95
        assert result["plate_confidence_exit"] == 0.93
        assert result["plate_match"] is True

    @patch("apps.api.services.entry_exit_matcher._recognize_plate_safe")
    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_plate_mismatch_sets_suspicious_and_fraud_type(self, mock_get_client, mock_ocr):
        fake_client = MagicMock()
        fake_client.entry_exit.return_value = {
            "is_suspicious": False,
            "color_match": True,
            "type_match": True,
            "fingerprint_sim": 0.9,
            "comparison_success": True,
        }
        mock_get_client.return_value = fake_client

        entry_url = "http://entry.jpg"
        exit_url = "http://exit.jpg"
        mock_ocr.side_effect = lambda url: (
            {"plate": "京A12345", "confidence": 0.95}
            if url == entry_url
            else {"plate": "京B99999", "confidence": 0.93}
            if url == exit_url
            else None
        )

        matcher = EntryExitMatcher()
        result = matcher.compare({"image_license": entry_url}, {"image_license": exit_url})
        assert result["plate_match"] is False
        assert result["is_suspicious"] is True
        assert result["fraud_type"] == "ENTRY_EXIT_MISMATCH"

    @patch("apps.api.services.entry_exit_matcher._recognize_plate_safe")
    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_plate_mismatch_does_not_override_existing_fraud_type(self, mock_get_client, mock_ocr):
        fake_client = MagicMock()
        fake_client.entry_exit.return_value = {
            "is_suspicious": True,
            "fraud_type": "VEHICLE_TYPE_DOWNGRADE",
            "color_match": False,
            "type_match": False,
            "fingerprint_sim": 0.3,
            "comparison_success": True,
        }
        mock_get_client.return_value = fake_client

        entry_url = "http://entry.jpg"
        exit_url = "http://exit.jpg"
        mock_ocr.side_effect = lambda url: (
            {"plate": "京A12345", "confidence": 0.95}
            if url == entry_url
            else {"plate": "京B99999", "confidence": 0.93}
            if url == exit_url
            else None
        )

        matcher = EntryExitMatcher()
        result = matcher.compare({"image_license": entry_url}, {"image_license": exit_url})
        assert result["plate_match"] is False
        assert result["is_suspicious"] is True
        # 已有 fraud_type，不应被覆盖
        assert result["fraud_type"] == "VEHICLE_TYPE_DOWNGRADE"

    @patch("apps.api.services.entry_exit_matcher._recognize_plate_safe")
    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_plate_match_case_insensitive_and_whitespace_stripped(self, mock_get_client, mock_ocr):
        fake_client = MagicMock()
        fake_client.entry_exit.return_value = {
            "is_suspicious": False,
            "color_match": True,
            "type_match": True,
            "fingerprint_sim": 0.9,
            "comparison_success": True,
        }
        mock_get_client.return_value = fake_client

        entry_url = "http://entry.jpg"
        exit_url = "http://exit.jpg"
        mock_ocr.side_effect = lambda url: (
            {"plate": "  京a12345  ", "confidence": 0.95}
            if url == entry_url
            else {"plate": "京A12345", "confidence": 0.93}
            if url == exit_url
            else None
        )

        matcher = EntryExitMatcher()
        result = matcher.compare({"image_license": entry_url}, {"image_license": exit_url})
        assert result["plate_match"] is True

    @patch("apps.api.services.entry_exit_matcher._recognize_plate_safe")
    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_only_entry_ocr_populates_entry_fields(self, mock_get_client, mock_ocr):
        fake_client = MagicMock()
        fake_client.entry_exit.return_value = {
            "is_suspicious": False,
            "color_match": True,
            "type_match": True,
            "fingerprint_sim": 0.9,
            "comparison_success": True,
        }
        mock_get_client.return_value = fake_client

        entry_url = "http://entry.jpg"
        exit_url = "http://exit.jpg"
        mock_ocr.side_effect = lambda url: ({"plate": "京A12345", "confidence": 0.95} if url == entry_url else None)

        matcher = EntryExitMatcher()
        result = matcher.compare({"image_license": entry_url}, {"image_license": exit_url})
        assert result["plate_recognized_entry"] == "京A12345"
        assert result["plate_recognized_exit"] is None
        assert result["plate_match"] is None

    @patch("apps.api.services.entry_exit_matcher._recognize_plate_safe")
    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_compare_empty_plate_string_treated_as_no_match(self, mock_get_client, mock_ocr):
        fake_client = MagicMock()
        fake_client.entry_exit.return_value = {
            "is_suspicious": False,
            "color_match": True,
            "type_match": True,
            "fingerprint_sim": 0.9,
            "comparison_success": True,
        }
        mock_get_client.return_value = fake_client

        entry_url = "http://entry.jpg"
        exit_url = "http://exit.jpg"
        mock_ocr.side_effect = lambda url: (
            {"plate": "", "confidence": 0.1}
            if url == entry_url
            else {"plate": "", "confidence": 0.1}
            if url == exit_url
            else None
        )

        matcher = EntryExitMatcher()
        result = matcher.compare({"image_license": entry_url}, {"image_license": exit_url})
        # Both empty strings → plate_match should be False (empty string treated as no plate)
        assert result["plate_match"] is False


# ============================================================
# _recognize_plate_safe
# ============================================================


class TestRecognizePlateSafe:
    """_recognize_plate_safe — 安全车牌 OCR 包装"""

    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_returns_none_on_empty_url(self, mock_get_client):
        result = _recognize_plate_safe("")
        assert result is None
        mock_get_client.assert_not_called()

    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_returns_none_on_none_url(self, mock_get_client):
        result = _recognize_plate_safe(None)
        assert result is None
        mock_get_client.assert_not_called()

    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_returns_result_on_success(self, mock_get_client):
        fake_client = MagicMock()
        fake_client.recognize_plate.return_value = {"plate": "京A12345", "confidence": 0.95}
        mock_get_client.return_value = fake_client

        result = _recognize_plate_safe("http://img.jpg")
        assert result == {"plate": "京A12345", "confidence": 0.95}

    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_returns_none_when_result_has_error_key(self, mock_get_client):
        fake_client = MagicMock()
        fake_client.recognize_plate.return_value = {"error": "timeout"}
        mock_get_client.return_value = fake_client

        result = _recognize_plate_safe("http://img.jpg")
        assert result is None

    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_returns_none_when_result_has_no_plate(self, mock_get_client):
        fake_client = MagicMock()
        fake_client.recognize_plate.return_value = {"confidence": 0.5}
        mock_get_client.return_value = fake_client

        result = _recognize_plate_safe("http://img.jpg")
        assert result is None

    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_returns_none_when_result_is_not_dict(self, mock_get_client):
        fake_client = MagicMock()
        fake_client.recognize_plate.return_value = "not a dict"
        mock_get_client.return_value = fake_client

        result = _recognize_plate_safe("http://img.jpg")
        assert result is None

    @patch("apps.api.services.entry_exit_matcher.get_client")
    def test_returns_none_on_exception(self, mock_get_client):
        fake_client = MagicMock()
        fake_client.recognize_plate.side_effect = RuntimeError("service down")
        mock_get_client.return_value = fake_client

        result = _recognize_plate_safe("http://img.jpg")
        assert result is None


# ============================================================
# compare_trip 便捷函数
# ============================================================


class TestCompareTripConvenienceFunction:
    """compare_trip() 应委托 EntryExitMatcher.compare()"""

    @patch.object(EntryExitMatcher, "compare")
    def test_compare_trip_delegates_to_matcher_compare(self, mock_compare):
        expected = {"is_suspicious": False, "_comparison_success": True}
        mock_compare.return_value = expected

        entry = {"image_license": "http://entry.jpg"}
        exit_rec = {"image_license": "http://exit.jpg"}
        result = compare_trip(entry, exit_rec)
        assert result == expected
        mock_compare.assert_called_once_with(entry, exit_rec)


# ============================================================
# EntryExitMatcher.__init__
# ============================================================


class TestEntryExitMatcherInit:
    """构造函数行为"""

    def test_init_stores_model_path(self):
        matcher = EntryExitMatcher(model_path="/some/path")
        assert matcher.model_path == "/some/path"

    def test_init_default_model_path_is_none(self):
        matcher = EntryExitMatcher()
        assert matcher.model_path is None
