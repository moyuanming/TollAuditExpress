"""TripAggregator 单元测试"""
import pytest
from datetime import datetime
from io import BytesIO

from apps.api.services.trip_aggregator import (
    build_image_url, build_gantry_image_url,
    serialize_gantry_records, aggregate_trip, TripAggregator
)


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


class TestBuildGantryImageURL:
    """测试门架图片URL构建 — 优先使用 t_grantry_image 抓拍记录ID"""

    def test_uses_image_id_from_grantry_image(self):
        """有 IMAGE_ID 时使用抓拍记录ID"""
        record = {
            'IMAGE_ID': 'CAPTURE999',  # t_grantry_image.ID
            'ID': 'TX123',             # t_waste_en_ex_gantry.ID (回退)
            'VEHICLEID': '京A12345',
            'VEHICLECOLOR': 1,
        }
        url = build_gantry_image_url(record)
        assert 'pic_id=CAPTURE999' in url
        assert 'TX123' not in url

    def test_falls_back_to_transaction_id(self):
        """无 IMAGE_ID 时回退使用交易记录ID"""
        record = {
            'ID': 'TX456',
            'VEHICLEID': '京B67890',
            'VEHICLECOLOR': 2,
        }
        url = build_gantry_image_url(record)
        assert 'pic_id=TX456' in url

    def test_returns_none_without_required_fields(self):
        assert build_gantry_image_url({}) is None
        assert build_gantry_image_url({'ID': 'X'}) is None
        assert build_gantry_image_url({'ID': 'X', 'VEHICLEID': '京C'}) is None

    def test_url_encodes_plate(self):
        record = {
            'IMAGE_ID': 'IMG001',
            'VEHICLEID': '京A 12345',
            'VEHICLECOLOR': 1,
        }
        url = build_gantry_image_url(record)
        assert 'vchicle=' in url
        # 空格应被编码
        assert ' ' not in url.split('vchicle=')[1].split('&')[0]


class TestSerializeGantryRecords:
    """测试门架记录序列化"""

    def test_serialize_includes_image_id_and_pic_id(self):
        records = [{
            'IMAGE_ID': 'CAP001',
            'ID': 'TX001',
            'STATION_NAME': '测试门架',
            'OCCURTIME': datetime(2025, 6, 15, 8, 30, 0),
            'VEHICLEID': '京A00001',
            'VEHICLECOLOR': 1,
            'VEHICLETYPE': 1,
            'OBUID': 'OBU001',
        }]
        import json
        result = json.loads(serialize_gantry_records(records))
        assert result[0]['pic_id'] == 'CAP001'
        assert 'image_url' in result[0]

    def test_serialize_falls_back_pic_id(self):
        """无 IMAGE_ID 时 pic_id 回退到交易 ID"""
        records = [{
            'ID': 'TX002',
            'STATION_NAME': '门架2',
            'OCCURTIME': datetime(2025, 6, 15, 9, 0, 0),
            'VEHICLEID': '京B00002',
            'VEHICLECOLOR': 2,
            'VEHICLETYPE': 2,
            'OBUID': 'OBU002',
        }]
        import json
        result = json.loads(serialize_gantry_records(records))
        assert result[0]['pic_id'] == 'TX002'


class TestTripAggregator:
    def test_run_detection_with_mocks(self, temp_db, mock_ai_client):
        """测试 _run_detection 在 mock 公共服务和数据库下的完整流程"""
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
        # Model B 始终把识别结果写进 entry_visual_type / exit_visual_type
        assert trip['entry_visual_type'] == 'truck'
        # conftest mock 的 entry_exit 返回 is_suspicious=False,
        # 所以 _run_detection 不会把 audit_status 升级到 SUSPECTED,仍为 PENDING
        assert trip['audit_status'] == 'PENDING'
        # 但 audit_results 仍会写入一条 ENTRY_EXIT_MISMATCH 记录(写库后再判命中)。
        # 注意:get_suspects 会过滤 is_suspicious=0,所以这里直接走原始 SQL 验证。
        from apps.api.database.doris_connection import get_connection
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT fraud_type, is_suspicious, audit_trip_id FROM audit_results"
            )
            rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]['fraud_type'] == 'ENTRY_EXIT_MISMATCH'
        assert rows[0]['is_suspicious'] == 0
        assert rows[0]['audit_trip_id'] == trip_id

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
