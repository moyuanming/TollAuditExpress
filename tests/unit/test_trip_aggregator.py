"""TripAggregator 单元测试"""
import pytest
from datetime import datetime
from io import BytesIO

from apps.api.services.trip_aggregator import build_image_url, aggregate_trip, TripAggregator


class TestBuildImageURL:
    def test_build_url_with_datetime(self):
        record = {
            'OCCURTIME': datetime(2025, 6, 15, 8, 30, 0),
            'IPADDRESS': '10.0.0.1',
            'LANE_ID': 'L001',
            'ID': 'IMG123'
        }
        url = build_image_url(record, '_license.jpg')
        assert url == 'http://10.0.0.1/img/data/L001/20250615/IMG123_license.jpg'

    def test_build_url_with_string_date(self):
        record = {
            'OCCURTIME': '2025-06-15 08:30:00',
            'IPADDRESS': '10.0.0.1',
            'LANE_ID': 'L001',
            'ID': 'IMG123'
        }
        url = build_image_url(record, '_trans.jpg')
        assert url == 'http://10.0.0.1/img/data/L001/20250615/IMG123_trans.jpg'

    def test_build_url_empty_occur_time(self):
        record = {
            'OCCURTIME': None,
            'IPADDRESS': '10.0.0.1',
            'LANE_ID': 'L001',
            'ID': 'IMG123'
        }
        url = build_image_url(record)
        assert 'IMG123_license.jpg' in url


class TestTripAggregator:
    def test_run_detection_with_mocks(self, temp_db, mock_ml_models, mock_image_download, monkeypatch):
        """测试 _run_detection 在 mock 模型和数据库下的完整流程"""
        from apps.api.database.repositories.trip_repository import TripRepository

        repo = TripRepository()
        trip_id = repo.save_trip({
            'passid': 'TEST001',
            'entry_time': '2025-06-15 08:00:00',
            'exit_time': '2025-06-15 10:00:00',
            'entry_vehicle_type': 1,
            'entry_image_trans': 'http://fake/img.jpg',
            'entry_image_license': 'http://fake/license.jpg',
            'exit_image_license': 'http://fake/exit_license.jpg',
            'gantry_count': 3
        })

        trip_data = {
            'passid': 'TEST001',
            'entry_vehicle_type': 1,
            'entry_image_trans': 'http://fake/img.jpg',
            'entry_image_license': 'http://fake/license.jpg',
            'exit_image_license': 'http://fake/exit_license.jpg',
        }

        aggregator = TripAggregator()
        aggregator._run_detection(trip_data, trip_id)

        trip = repo.get_trip_detail('TEST001')
        assert trip is not None
        assert trip['entry_visual_type'] == 'truck'
        assert trip['audit_status'] == 'SUSPECTED'
        assert trip['risk_score'] > 0

    def test_run_detection_no_images(self, temp_db, monkeypatch):
        """测试无图片时不崩溃"""
        from apps.api.database.repositories.trip_repository import TripRepository

        repo = TripRepository()
        trip_id = repo.save_trip({
            'passid': 'TEST002',
            'entry_time': '2025-06-15 08:00:00',
        })

        trip_data = {'passid': 'TEST002'}

        aggregator = TripAggregator()
        aggregator._run_detection(trip_data, trip_id)

        trip = repo.get_trip_detail('TEST002')
        assert trip['audit_status'] == 'PENDING'


def test_aggregate_trip_no_records(monkeypatch):
    """测试无记录时返回 None"""
    def mock_get_records(passid):
        return []
    monkeypatch.setattr(
        'apps.api.services.trip_aggregator.get_records_by_passid',
        mock_get_records
    )
    result = aggregate_trip('NONEXISTENT')
    assert result is None


def test_aggregate_trip_missing_entry_exit(monkeypatch):
    """测试缺少入口/出口记录时返回 None"""
    def mock_get_records(passid):
        return [{'LANETYPE': '门架', 'OCCURTIME': datetime(2025, 6, 15, 8, 30)}]
    monkeypatch.setattr(
        'apps.api.services.trip_aggregator.get_records_by_passid',
        mock_get_records
    )
    result = aggregate_trip('PARTIAL')
    assert result is None
