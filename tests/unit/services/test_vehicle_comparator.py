"""VehicleComparator 单元测试 — 车辆双图比对业务封装

测试范围：
  - compare_vehicles_by_passid() 核心比对编排逻辑
  - _missing_image_error() / _unavailable_error() 错误构造
  - _fetch_visual_features() 视觉信号获取
  - _recognize_plate_safe() 车牌 OCR 安全包装
  - 各类异常/缺失场景
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.api.services.vehicle_comparator import (
    _fetch_visual_features,
    _missing_image_error,
    _recognize_plate_safe,
    _unavailable_error,
    compare_vehicles_by_passid,
)

# ============================================================
# _missing_image_error / _unavailable_error
# ============================================================


class TestMissingImageError:
    def test_returns_error_dict_with_field(self):
        result = _missing_image_error("entry_image_license")
        assert result["error"] == "image_url_missing"
        assert result["field"] == "entry_image_license"


class TestUnavailableError:
    def test_returns_error_dict_with_detail(self):
        result = _unavailable_error("timeout after 10s")
        assert result["error"] == "service_unavailable"
        assert result["detail"] == "timeout after 10s"


# ============================================================
# _fetch_visual_features
# ============================================================


class TestFetchVisualFeatures:
    """视觉信号获取 — 从 audit_results 拉取"""

    @patch("apps.api.services.vehicle_comparator.AuditRepository")
    def test_returns_features_when_row_found(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.get_visual_features_by_passid.return_value = {
            "entry_color": "blue",
            "exit_color": "red",
            "entry_visual_type": "truck",
            "exit_visual_type": "car",
            "fingerprint_sim": 0.85,
        }
        mock_repo_cls.return_value = mock_repo

        result = _fetch_visual_features("PASS123")
        assert result["entry_color"] == "blue"
        assert result["exit_color"] == "red"
        assert result["fingerprint_sim"] == 0.85

    @patch("apps.api.services.vehicle_comparator.AuditRepository")
    def test_returns_empty_dict_when_no_row(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.get_visual_features_by_passid.return_value = None
        mock_repo_cls.return_value = mock_repo

        result = _fetch_visual_features("PASS123")
        assert result == {}

    @patch("apps.api.services.vehicle_comparator.AuditRepository")
    def test_returns_empty_dict_on_exception(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.get_visual_features_by_passid.side_effect = RuntimeError("db down")
        mock_repo_cls.return_value = mock_repo

        result = _fetch_visual_features("PASS123")
        assert result == {}


# ============================================================
# _recognize_plate_safe
# ============================================================


class TestRecognizePlateSafe:
    """车牌 OCR 安全包装"""

    @patch("apps.api.services.vehicle_comparator.get_client")
    def test_returns_none_on_empty_url(self, mock_get_client):
        result = _recognize_plate_safe("")
        assert result is None
        mock_get_client.assert_not_called()

    @patch("apps.api.services.vehicle_comparator.get_client")
    def test_returns_none_on_none_url(self, mock_get_client):
        result = _recognize_plate_safe(None)
        assert result is None
        mock_get_client.assert_not_called()

    @patch("apps.api.services.vehicle_comparator.get_client")
    def test_returns_result_on_success(self, mock_get_client):
        fake_client = MagicMock()
        fake_client.recognize_plate.return_value = {"plate": "京A12345", "confidence": 0.95}
        mock_get_client.return_value = fake_client

        result = _recognize_plate_safe("http://img.jpg")
        assert result == {"plate": "京A12345", "confidence": 0.95}

    @patch("apps.api.services.vehicle_comparator.get_client")
    def test_returns_none_when_result_has_error(self, mock_get_client):
        fake_client = MagicMock()
        fake_client.recognize_plate.return_value = {"error": "timeout"}
        mock_get_client.return_value = fake_client

        result = _recognize_plate_safe("http://img.jpg")
        assert result is None

    @patch("apps.api.services.vehicle_comparator.get_client")
    def test_returns_none_when_no_plate_in_result(self, mock_get_client):
        fake_client = MagicMock()
        fake_client.recognize_plate.return_value = {"confidence": 0.5}
        mock_get_client.return_value = fake_client

        result = _recognize_plate_safe("http://img.jpg")
        assert result is None

    @patch("apps.api.services.vehicle_comparator.get_client")
    def test_returns_none_on_exception(self, mock_get_client):
        fake_client = MagicMock()
        fake_client.recognize_plate.side_effect = RuntimeError("service down")
        mock_get_client.return_value = fake_client

        result = _recognize_plate_safe("http://img.jpg")
        assert result is None


# ============================================================
# compare_vehicles_by_passid — 输入校验
# ============================================================


class TestCompareVehiclesByPassidInputValidation:
    """输入校验 — passid 缺失 / trip 不存在"""

    def test_returns_error_on_empty_passid(self):
        result = compare_vehicles_by_passid("")
        assert result["error"] == "image_url_missing"
        assert result["field"] == "passid"

    @patch("apps.api.services.vehicle_comparator.aggregate_trip", return_value=None)
    def test_returns_error_when_trip_not_found(self, mock_agg):
        result = compare_vehicles_by_passid("NONEXISTENT")
        assert result["error"] == "trip_not_found"

    @patch("apps.api.services.vehicle_comparator.aggregate_trip")
    def test_returns_error_when_entry_image_missing(self, mock_agg):
        mock_agg.return_value = {
            "exit_image_license": "http://exit.jpg",
        }
        result = compare_vehicles_by_passid("PASS123")
        assert result["error"] == "image_url_missing"
        assert result["field"] == "entry_image_license"

    @patch("apps.api.services.vehicle_comparator.aggregate_trip")
    def test_returns_error_when_exit_image_missing(self, mock_agg):
        mock_agg.return_value = {
            "entry_image_license": "http://entry.jpg",
        }
        result = compare_vehicles_by_passid("PASS123")
        assert result["error"] == "image_url_missing"
        assert result["field"] == "exit_image_license"


# ============================================================
# compare_vehicles_by_passid — 服务调用
# ============================================================


class TestCompareVehiclesByPassidServiceCall:
    """正常服务调用场景"""

    @patch("apps.api.services.vehicle_comparator._recognize_plate_safe", return_value=None)
    @patch("apps.api.services.vehicle_comparator._fetch_visual_features", return_value={})
    @patch("apps.api.services.vehicle_comparator.get_client")
    @patch("apps.api.services.vehicle_comparator.aggregate_trip")
    def test_returns_success_on_normal_response(self, mock_agg, mock_get_client, mock_visual, mock_ocr):
        mock_agg.return_value = {
            "entry_image_license": "http://entry.jpg",
            "exit_image_license": "http://exit.jpg",
            "entry_vehicle_id": "京A12345",
            "exit_vehicle_id": "京A12345",
            "entry_obu_id": "OBU001",
            "exit_obu_id": "OBU001",
        }

        fake_client = MagicMock()
        fake_client.compare.return_value = {
            "is_same_vehicle": True,
            "confidence": 0.92,
            "reason": "车牌号一致",
            "model": "qwen2.5-vl-72b",
            "elapsed_ms": 150,
        }
        mock_get_client.return_value = fake_client

        result = compare_vehicles_by_passid("PASS123")
        assert result["passid"] == "PASS123"
        assert result["is_same_vehicle"] is True
        assert result["confidence"] == pytest.approx(0.92)
        assert result["reason"] == "车牌号一致"
        assert result["model"] == "qwen2.5-vl-72b"
        assert result["entry_image_url"] == "http://entry.jpg"
        assert result["exit_image_url"] == "http://exit.jpg"
        assert result["elapsed_ms"] == 150

    @patch("apps.api.services.vehicle_comparator._recognize_plate_safe", return_value=None)
    @patch("apps.api.services.vehicle_comparator._fetch_visual_features", return_value={})
    @patch("apps.api.services.vehicle_comparator.get_client")
    @patch("apps.api.services.vehicle_comparator.aggregate_trip")
    def test_passes_visual_features_and_metadata_to_compare(self, mock_agg, mock_get_client, mock_visual, mock_ocr):
        mock_agg.return_value = {
            "entry_image_license": "http://entry.jpg",
            "exit_image_license": "http://exit.jpg",
            "entry_vehicle_id": "京A12345",
            "exit_vehicle_id": "京A12345",
            "entry_obu_id": "OBU001",
            "exit_obu_id": "OBU001",
        }
        mock_visual.return_value = {
            "entry_color": "blue",
            "exit_color": "red",
            "entry_visual_type": "truck",
            "exit_visual_type": "car",
            "fingerprint_sim": 0.85,
        }

        fake_client = MagicMock()
        fake_client.compare.return_value = {
            "is_same_vehicle": False,
            "confidence": 0.3,
            "reason": "颜色不一致",
            "model": "rule-based",
        }
        mock_get_client.return_value = fake_client

        compare_vehicles_by_passid("PASS123")
        call_kwargs = fake_client.compare.call_args
        assert call_kwargs[1]["entry_color"] == "blue"
        assert call_kwargs[1]["exit_color"] == "red"
        assert call_kwargs[1]["fingerprint_sim"] == 0.85


# ============================================================
# compare_vehicles_by_passid — 车牌 OCR
# ============================================================


class TestCompareVehiclesByPassidPlateOcr:
    """车牌 OCR 信号透传"""

    @patch("apps.api.services.vehicle_comparator._fetch_visual_features", return_value={})
    @patch("apps.api.services.vehicle_comparator._recognize_plate_safe")
    @patch("apps.api.services.vehicle_comparator.get_client")
    @patch("apps.api.services.vehicle_comparator.aggregate_trip")
    def test_plate_ocr_results_passed_to_compare_and_response(self, mock_agg, mock_get_client, mock_ocr, mock_visual):
        mock_agg.return_value = {
            "entry_image_license": "http://entry.jpg",
            "exit_image_license": "http://exit.jpg",
            "entry_vehicle_id": "京A12345",
            "exit_vehicle_id": "京A12345",
        }

        mock_ocr.side_effect = lambda url: (
            {"plate": "京A12345", "confidence": 0.95}
            if "entry" in url
            else {"plate": "京A12345", "confidence": 0.93}
            if "exit" in url
            else None
        )

        fake_client = MagicMock()
        fake_client.compare.return_value = {
            "is_same_vehicle": True,
            "confidence": 0.95,
            "reason": "plate match",
            "model": "rule-based",
        }
        mock_get_client.return_value = fake_client

        result = compare_vehicles_by_passid("PASS123")
        assert result["plate_match"] is True
        assert result["plate_recognized_entry"] == "京A12345"
        assert result["plate_recognized_exit"] == "京A12345"

    @patch("apps.api.services.vehicle_comparator._fetch_visual_features", return_value={})
    @patch("apps.api.services.vehicle_comparator._recognize_plate_safe", return_value=None)
    @patch("apps.api.services.vehicle_comparator.get_client")
    @patch("apps.api.services.vehicle_comparator.aggregate_trip")
    def test_plate_match_none_when_no_ocr_results(self, mock_agg, mock_get_client, mock_ocr, mock_visual):
        mock_agg.return_value = {
            "entry_image_license": "http://entry.jpg",
            "exit_image_license": "http://exit.jpg",
        }

        fake_client = MagicMock()
        fake_client.compare.return_value = {
            "is_same_vehicle": True,
            "confidence": 0.9,
            "reason": "visual match",
            "model": "rule-based",
        }
        mock_get_client.return_value = fake_client

        result = compare_vehicles_by_passid("PASS123")
        assert result["plate_match"] is None
        assert result["plate_recognized_entry"] is None
        assert result["plate_recognized_exit"] is None


# ============================================================
# compare_vehicles_by_passid — 异常处理
# ============================================================


class TestCompareVehiclesByPassidErrorHandling:
    """各类异常/错误场景"""

    @patch("apps.api.services.vehicle_comparator._recognize_plate_safe", return_value=None)
    @patch("apps.api.services.vehicle_comparator._fetch_visual_features", return_value={})
    @patch("apps.api.services.vehicle_comparator.get_client")
    @patch("apps.api.services.vehicle_comparator.aggregate_trip")
    def test_returns_unavailable_on_compare_exception(self, mock_agg, mock_get_client, mock_visual, mock_ocr):
        mock_agg.return_value = {
            "entry_image_license": "http://entry.jpg",
            "exit_image_license": "http://exit.jpg",
        }

        fake_client = MagicMock()
        fake_client.compare.side_effect = RuntimeError("service down")
        mock_get_client.return_value = fake_client

        result = compare_vehicles_by_passid("PASS123")
        assert result["error"] == "service_unavailable"

    @patch("apps.api.services.vehicle_comparator._recognize_plate_safe", return_value=None)
    @patch("apps.api.services.vehicle_comparator._fetch_visual_features", return_value={})
    @patch("apps.api.services.vehicle_comparator.get_client")
    @patch("apps.api.services.vehicle_comparator.aggregate_trip")
    def test_returns_unavailable_on_service_error_in_response(self, mock_agg, mock_get_client, mock_visual, mock_ocr):
        mock_agg.return_value = {
            "entry_image_license": "http://entry.jpg",
            "exit_image_license": "http://exit.jpg",
        }

        fake_client = MagicMock()
        fake_client.compare.return_value = {
            "error": "model_not_found",
            "detail": "model xyz not available",
        }
        mock_get_client.return_value = fake_client

        result = compare_vehicles_by_passid("PASS123")
        assert result["error"] == "service_unavailable"

    @patch("apps.api.services.vehicle_comparator._recognize_plate_safe", return_value=None)
    @patch("apps.api.services.vehicle_comparator._fetch_visual_features", return_value={})
    @patch("apps.api.services.vehicle_comparator.get_client")
    @patch("apps.api.services.vehicle_comparator.aggregate_trip")
    def test_passes_through_image_url_missing_error(self, mock_agg, mock_get_client, mock_visual, mock_ocr):
        mock_agg.return_value = {
            "entry_image_license": "http://entry.jpg",
            "exit_image_license": "http://exit.jpg",
        }

        fake_client = MagicMock()
        fake_client.compare.return_value = {
            "error": "image_url_missing",
            "field": "image_url_a",
        }
        mock_get_client.return_value = fake_client

        result = compare_vehicles_by_passid("PASS123")
        assert result["error"] == "image_url_missing"

    @patch("apps.api.services.vehicle_comparator._recognize_plate_safe", return_value=None)
    @patch("apps.api.services.vehicle_comparator._fetch_visual_features", return_value={})
    @patch("apps.api.services.vehicle_comparator.get_client")
    @patch("apps.api.services.vehicle_comparator.aggregate_trip")
    def test_returns_parse_error_on_missing_required_fields(self, mock_agg, mock_get_client, mock_visual, mock_ocr):
        mock_agg.return_value = {
            "entry_image_license": "http://entry.jpg",
            "exit_image_license": "http://exit.jpg",
        }

        fake_client = MagicMock()
        fake_client.compare.return_value = {
            "is_same_vehicle": True,
            # missing: confidence, reason, model
        }
        mock_get_client.return_value = fake_client

        result = compare_vehicles_by_passid("PASS123")
        assert result["error"] == "parse_error"
        assert "confidence" in result["detail"] or "missing" in result["detail"]

    @patch("apps.api.services.vehicle_comparator._recognize_plate_safe", return_value=None)
    @patch("apps.api.services.vehicle_comparator._fetch_visual_features", return_value={})
    @patch("apps.api.services.vehicle_comparator.get_client")
    @patch("apps.api.services.vehicle_comparator.aggregate_trip")
    def test_coerces_types_in_success_response(self, mock_agg, mock_get_client, mock_visual, mock_ocr):
        mock_agg.return_value = {
            "entry_image_license": "http://entry.jpg",
            "exit_image_license": "http://exit.jpg",
        }

        fake_client = MagicMock()
        fake_client.compare.return_value = {
            "is_same_vehicle": 1,
            "confidence": "0.92",
            "reason": "match",
            "model": "rule-based",
            "elapsed_ms": "150",
        }
        mock_get_client.return_value = fake_client

        result = compare_vehicles_by_passid("PASS123")
        assert isinstance(result["is_same_vehicle"], bool)
        assert isinstance(result["confidence"], float)
        assert isinstance(result["elapsed_ms"], int)
