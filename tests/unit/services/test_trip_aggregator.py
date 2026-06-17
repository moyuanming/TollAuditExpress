"""trip_aggregator 单元测试 — 行程聚合服务

行为契约:
  - build_image_url: 从记录构建入口/出口图片URL
  - build_gantry_image_url: 从记录构建门架图片URL(查询式)
  - get_gantry_image_match: 查询匹配的门架抓拍图片记录
  - get_gantry_images_by_vehicle: 查询时间范围内门架抓拍图片
  - serialize_gantry_image_records / serialize_gantry_records: 序列化
  - get_records_by_passid: 获取同一PASSID的所有记录
  - aggregate_trip: 聚合单个行程(入口+出口+门架)
  - get_recent_passids: 获取最近的PASSID列表
  - TripAggregator.aggregate_recent_trips: 聚合最近行程并可选执行视觉检测
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from apps.api.services.trip_aggregator import (
    GANTRY_IMAGE_BASE,
    TripAggregator,
    aggregate_trip,
    build_gantry_image_url,
    build_image_url,
    get_gantry_image_match,
    get_gantry_images_by_vehicle,
    get_recent_passids,
    get_records_by_passid,
    serialize_gantry_image_records,
    serialize_gantry_records,
)

# ============================================================
# build_image_url
# ============================================================


class TestBuildImageUrl:
    def test_builds_url_with_datetime_occurtime(self):
        record = {
            "IPADDRESS": "10.0.0.1",
            "LANE_ID": "L001",
            "OCCURTIME": datetime(2026, 6, 14, 10, 30, 0),
            "ID": "REC001",
        }
        url = build_image_url(record)
        assert url == "http://10.0.0.1/img/data/L001/20260614/REC001_license.jpg"

    def test_builds_url_with_string_occurtime(self):
        record = {
            "IPADDRESS": "10.0.0.2",
            "LANE_ID": "L002",
            "OCCURTIME": "2026-06-15 08:00:00",
            "ID": "REC002",
        }
        url = build_image_url(record)
        assert url == "http://10.0.0.2/img/data/L002/20260615/REC002_license.jpg"

    def test_builds_url_with_custom_suffix(self):
        record = {
            "IPADDRESS": "10.0.0.1",
            "LANE_ID": "L001",
            "OCCURTIME": datetime(2026, 1, 1),
            "ID": "REC003",
        }
        url = build_image_url(record, "_trans.jpg")
        assert url == "http://10.0.0.1/img/data/L001/20260101/REC003_trans.jpg"

    def test_handles_missing_occurtime(self):
        record = {"IPADDRESS": "10.0.0.1", "LANE_ID": "L001", "OCCURTIME": None, "ID": "REC004"}
        url = build_image_url(record)
        assert "REC004_license.jpg" in url

    def test_handles_empty_occurtime(self):
        record = {"IPADDRESS": "10.0.0.1", "LANE_ID": "L001", "OCCURTIME": "", "ID": "REC005"}
        url = build_image_url(record)
        assert "REC005_license.jpg" in url


# ============================================================
# build_gantry_image_url
# ============================================================


class TestBuildGantryImageUrl:
    def test_builds_url_with_image_id(self):
        record = {"IMAGE_ID": "IMG123", "VEHICLEID": "京A12345", "VEHICLECOLOR": 1}
        url = build_gantry_image_url(record)
        assert GANTRY_IMAGE_BASE in url
        assert "pic_id=IMG123" in url
        assert "vchicle=" in url
        assert "vehicle_color=1" in url

    def test_falls_back_to_id_when_no_image_id(self):
        record = {"ID": "REC999", "VEHICLEID": "川B99999", "VEHICLECOLOR": 2}
        url = build_gantry_image_url(record)
        assert "pic_id=REC999" in url

    def test_returns_none_when_missing_plate(self):
        record = {"IMAGE_ID": "IMG123", "VEHICLECOLOR": 1}
        assert build_gantry_image_url(record) is None

    def test_returns_none_when_missing_color(self):
        record = {"IMAGE_ID": "IMG123", "VEHICLEID": "京A12345"}
        # VEHICLECOLOR is not set → None
        assert build_gantry_image_url(record) is None

    def test_returns_none_when_missing_pic_id(self):
        record = {"VEHICLEID": "京A12345", "VEHICLECOLOR": 1}
        assert build_gantry_image_url(record) is None

    def test_url_encodes_vehicle_id(self):
        record = {"IMAGE_ID": "IMG1", "VEHICLEID": "京A+123", "VEHICLECOLOR": 1}
        url = build_gantry_image_url(record)
        assert url is not None
        # Should contain URL-encoded plate
        assert "vchicle=" in url


# ============================================================
# get_gantry_image_match
# ============================================================


class TestGetGantryImageMatch:
    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", False)
    def test_returns_none_when_no_pymysql(self):
        record = {"STATION_ID": "S1", "VEHICLEID": "京A1", "OCCURTIME": "2026-06-14 10:00:00"}
        assert get_gantry_image_match(record) is None

    @patch("apps.api.services.trip_aggregator.pymysql")
    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", True)
    def test_returns_image_id_on_match(self, mock_pymysql):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymysql.connect.return_value = mock_conn
        mock_pymysql.cursors.DictCursor = "DictCursor"
        mock_cursor.fetchone.return_value = {"ID": 42}

        record = {"STATION_ID": "S1", "VEHICLEID": "京A1", "OCCURTIME": "2026-06-14 10:00:00"}
        result = get_gantry_image_match(record)
        assert result == 42

    @patch("apps.api.services.trip_aggregator.pymysql")
    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", True)
    def test_returns_none_when_no_match(self, mock_pymysql):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymysql.connect.return_value = mock_conn
        mock_pymysql.cursors.DictCursor = "DictCursor"
        mock_cursor.fetchone.return_value = None

        record = {"STATION_ID": "S1", "VEHICLEID": "京A1", "OCCURTIME": "2026-06-14 10:00:00"}
        assert get_gantry_image_match(record) is None

    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", True)
    def test_returns_none_when_missing_required_fields(self):
        assert get_gantry_image_match({}) is None
        assert get_gantry_image_match({"STATION_ID": "S1"}) is None
        assert get_gantry_image_match({"STATION_ID": "S1", "VEHICLEID": "京A1"}) is None


# ============================================================
# get_gantry_images_by_vehicle
# ============================================================


class TestGetGantryImagesByVehicle:
    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", False)
    def test_returns_empty_when_no_pymysql(self):
        assert get_gantry_images_by_vehicle("京A1", "2026-06-14", "2026-06-15") == []

    def test_returns_empty_when_missing_vehicle_id(self):
        assert get_gantry_images_by_vehicle("", "2026-06-14", "2026-06-15") == []

    def test_returns_empty_when_missing_times(self):
        assert get_gantry_images_by_vehicle("京A1", None, None) == []

    @patch("apps.api.services.trip_aggregator.pymysql")
    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", True)
    def test_returns_records_on_success(self, mock_pymysql):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymysql.connect.return_value = mock_conn
        mock_pymysql.cursors.DictCursor = "DictCursor"
        mock_cursor.fetchall.return_value = [
            {"ID": 1, "GRANTRY_ID": "G1", "VEHICLEID": "京A1", "VEHICLECOLOR": 1, "CAPTURETIME": "2026-06-14 10:00:00"},
        ]

        result = get_gantry_images_by_vehicle("京A1", "2026-06-14", "2026-06-15")
        assert len(result) == 1
        assert result[0]["ID"] == 1

    @patch("apps.api.services.trip_aggregator.pymysql")
    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", True)
    def test_returns_empty_on_db_error(self, mock_pymysql):
        mock_pymysql.connect.side_effect = Exception("connection failed")

        result = get_gantry_images_by_vehicle("京A1", "2026-06-14", "2026-06-15")
        assert result == []

    @patch("apps.api.services.trip_aggregator.pymysql")
    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", True)
    def test_passes_connect_and_read_timeout_to_pymysql(self, mock_pymysql):
        """回归测试:pymysql.connect 必须带 connect_timeout/read_timeout。

        背景:源库 dwd_tolldata 是远端只读实例,网络抖动或防火墙重置时
        pymysql 默认无超时会让 audit/suspect/{id} endpoint 同步 hang,
        前端 fetch 永远 pending → UI 一直转 spinner("卡住")。
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymysql.connect.return_value = mock_conn
        mock_pymysql.cursors.DictCursor = "DictCursor"
        mock_cursor.fetchall.return_value = []

        get_gantry_images_by_vehicle("京A1", "2026-06-14", "2026-06-15")

        mock_pymysql.connect.assert_called_once()
        call_kwargs = mock_pymysql.connect.call_args.kwargs
        assert (
            "connect_timeout" in call_kwargs
        ), "pymysql.connect 缺少 connect_timeout,源库不可达时会 hang 整个 endpoint"
        assert "read_timeout" in call_kwargs, "pymysql.connect 缺少 read_timeout,慢查询会 hang 整个 endpoint"
        assert call_kwargs["connect_timeout"] > 0
        assert call_kwargs["read_timeout"] > 0

    @patch("apps.api.services.trip_aggregator.pymysql")
    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", True)
    def test_query_includes_limit_to_bound_response_size(self, mock_pymysql):
        """SQL must include LIMIT and the limit value must be in the params,
        so a busy vehicle cannot return thousands of rows that hang the UI
        when the OBU monitor detail panel is opened."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymysql.connect.return_value = mock_conn
        mock_pymysql.cursors.DictCursor = "DictCursor"
        mock_cursor.fetchall.return_value = []

        get_gantry_images_by_vehicle("京A1", "2026-06-14", "2026-06-15")

        mock_cursor.execute.assert_called_once()
        sql, params = mock_cursor.execute.call_args.args
        assert "LIMIT" in sql.upper(), f"SQL must include LIMIT to bound response size. Got: {sql}"
        assert 200 in params, f"params must include a limit value (200). Got: {params}"


# ============================================================
# serialize_gantry_image_records / serialize_gantry_records
# ============================================================


class TestSerializeGantryImageRecords:
    def test_serializes_records_to_json(self):
        records = [
            {
                "ID": 1,
                "GRANTRY_ID": "G1",
                "STATION_NAME": "站1",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "CAPTURETIME": datetime(2026, 6, 14, 10, 0, 0),
            },
        ]
        result = serialize_gantry_image_records(records)
        items = json.loads(result)
        assert len(items) == 1
        assert items[0]["pic_id"] == 1
        assert items[0]["station_name"] == "站1"
        assert items[0]["occur_time"] == "2026-06-14T10:00:00"

    def test_uses_grantry_id_when_no_station_name(self):
        records = [
            {
                "ID": 2,
                "GRANTRY_ID": "G2",
                "STATION_NAME": None,
                "VEHICLEID": "京A2",
                "VEHICLECOLOR": 1,
                "CAPTURETIME": "2026-06-14 10:00:00",
            },
        ]
        result = serialize_gantry_image_records(records)
        items = json.loads(result)
        assert items[0]["station_name"] == "G2"

    def test_empty_records_returns_empty_json_array(self):
        result = serialize_gantry_image_records([])
        assert json.loads(result) == []


class TestSerializeGantryRecords:
    def test_serializes_gantry_records_with_image_id(self):
        records = [
            {
                "IMAGE_ID": 10,
                "ID": 5,
                "STATION_NAME": "门架1",
                "OCCURTIME": datetime(2026, 6, 14, 11, 0, 0),
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
            },
        ]
        result = serialize_gantry_records(records)
        items = json.loads(result)
        assert len(items) == 1
        assert items[0]["pic_id"] == 10  # IMAGE_ID takes priority
        assert items[0]["station_name"] == "门架1"
        assert items[0]["vehicle_id"] == "京A1"

    def test_falls_back_to_id_when_no_image_id(self):
        records = [
            {
                "ID": 5,
                "STATION_NAME": "门架2",
                "OCCURTIME": "2026-06-14 11:00:00",
                "VEHICLEID": "京A2",
                "VEHICLECOLOR": 2,
                "VEHICLETYPE": 2,
                "OBUID": "OBU2",
            },
        ]
        result = serialize_gantry_records(records)
        items = json.loads(result)
        assert items[0]["pic_id"] == 5


# ============================================================
# get_records_by_passid
# ============================================================


class TestGetRecordsByPassid:
    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", False)
    def test_returns_empty_when_no_pymysql(self):
        assert get_records_by_passid("PASS1") == []

    @patch("apps.api.services.trip_aggregator.pymysql")
    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", True)
    def test_returns_records_on_success(self, mock_pymysql):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymysql.connect.return_value = mock_conn
        mock_pymysql.cursors.DictCursor = "DictCursor"
        mock_cursor.fetchall.return_value = [
            {"PASSID": "PASS1", "LANETYPE": "入口", "OCCURTIME": "2026-06-14 10:00:00"},
            {"PASSID": "PASS1", "LANETYPE": "出口", "OCCURTIME": "2026-06-14 12:00:00"},
        ]

        result = get_records_by_passid("PASS1")
        assert len(result) == 2
        mock_cursor.close.assert_called()
        mock_conn.close.assert_called()


# ============================================================
# aggregate_trip
# ============================================================


class TestAggregateTrip:
    @patch("apps.api.services.trip_aggregator.get_records_by_passid", return_value=[])
    def test_returns_none_when_no_records(self, mock_get):
        assert aggregate_trip("PASS_EMPTY") is None

    @patch("apps.api.services.trip_aggregator.get_gantry_image_match", return_value=None)
    @patch("apps.api.services.trip_aggregator.get_records_by_passid")
    def test_returns_none_when_missing_entry(self, mock_get, mock_match):
        mock_get.return_value = [
            {
                "LANETYPE": "出口",
                "OCCURTIME": "2026-06-14 12:00:00",
                "STATION_NAME": "出口站",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
                "IPADDRESS": "10.0.0.1",
                "LANE_ID": "L1",
                "ID": "R1",
                "MEDIATYPE": 1,
            },
        ]
        assert aggregate_trip("PASS_NO_ENTRY") is None

    @patch("apps.api.services.trip_aggregator.get_gantry_image_match", return_value=None)
    @patch("apps.api.services.trip_aggregator.get_records_by_passid")
    def test_returns_none_when_missing_exit(self, mock_get, mock_match):
        mock_get.return_value = [
            {
                "LANETYPE": "入口",
                "OCCURTIME": "2026-06-14 10:00:00",
                "STATION_NAME": "入口站",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
                "IPADDRESS": "10.0.0.1",
                "LANE_ID": "L1",
                "ID": "R1",
                "MEDIATYPE": 1,
            },
        ]
        assert aggregate_trip("PASS_NO_EXIT") is None

    @patch("apps.api.services.trip_aggregator.get_gantry_image_match", return_value=None)
    @patch("apps.api.services.trip_aggregator.get_records_by_passid")
    def test_aggregates_entry_exit_gantry(self, mock_get, mock_match):
        mock_get.return_value = [
            {
                "LANETYPE": "入口",
                "OCCURTIME": datetime(2026, 6, 14, 10, 0, 0),
                "STATION_NAME": "入口站",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
                "IPADDRESS": "10.0.0.1",
                "LANE_ID": "L1",
                "ID": "R1",
                "MEDIATYPE": 1,
            },
            {
                "LANETYPE": "门架",
                "OCCURTIME": datetime(2026, 6, 14, 11, 0, 0),
                "STATION_NAME": "门架站",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
                "IPADDRESS": "10.0.0.2",
                "LANE_ID": "L2",
                "ID": "R2",
                "MEDIATYPE": 1,
                "STATION_ID": "S1",
            },
            {
                "LANETYPE": "出口",
                "OCCURTIME": datetime(2026, 6, 14, 12, 0, 0),
                "STATION_NAME": "出口站",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
                "IPADDRESS": "10.0.0.3",
                "LANE_ID": "L3",
                "ID": "R3",
                "MEDIATYPE": 1,
            },
        ]

        result = aggregate_trip("PASS_FULL")
        assert result is not None
        assert result["passid"] == "PASS_FULL"
        assert result["entry_time"] == "2026-06-14T10:00:00"
        assert result["exit_time"] == "2026-06-14T12:00:00"
        assert result["entry_station_name"] == "入口站"
        assert result["exit_station_name"] == "出口站"
        assert result["gantry_count"] == 1
        assert result["entry_vehicle_id"] == "京A1"
        assert result["exit_vehicle_id"] == "京A1"

    @patch("apps.api.services.trip_aggregator.get_gantry_image_match", return_value=99)
    @patch("apps.api.services.trip_aggregator.get_records_by_passid")
    def test_gantry_image_match_sets_image_id(self, mock_get, mock_match):
        mock_get.return_value = [
            {
                "LANETYPE": "入口",
                "OCCURTIME": "2026-06-14 10:00:00",
                "STATION_NAME": "入口站",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
                "IPADDRESS": "10.0.0.1",
                "LANE_ID": "L1",
                "ID": "R1",
                "MEDIATYPE": 1,
            },
            {
                "LANETYPE": "门架",
                "OCCURTIME": "2026-06-14 11:00:00",
                "STATION_NAME": "门架站",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
                "IPADDRESS": "10.0.0.2",
                "LANE_ID": "L2",
                "ID": "R2",
                "MEDIATYPE": 1,
                "STATION_ID": "S1",
            },
            {
                "LANETYPE": "出口",
                "OCCURTIME": "2026-06-14 12:00:00",
                "STATION_NAME": "出口站",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
                "IPADDRESS": "10.0.0.3",
                "LANE_ID": "L3",
                "ID": "R3",
                "MEDIATYPE": 1,
            },
        ]

        result = aggregate_trip("PASS_IMG")
        assert result is not None
        # gantry_records should contain IMAGE_ID=99
        gantry_data = json.loads(result["gantry_records"])
        assert len(gantry_data) == 1
        assert gantry_data[0]["pic_id"] == 99

    @patch("apps.api.services.trip_aggregator.get_gantry_image_match", side_effect=Exception("db error"))
    @patch("apps.api.services.trip_aggregator.get_records_by_passid")
    def test_gantry_image_match_exception_sets_none_image_id(self, mock_get, mock_match):
        mock_get.return_value = [
            {
                "LANETYPE": "入口",
                "OCCURTIME": "2026-06-14 10:00:00",
                "STATION_NAME": "入口站",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
                "IPADDRESS": "10.0.0.1",
                "LANE_ID": "L1",
                "ID": "R1",
                "MEDIATYPE": 1,
            },
            {
                "LANETYPE": "门架",
                "OCCURTIME": "2026-06-14 11:00:00",
                "STATION_NAME": "门架站",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
                "IPADDRESS": "10.0.0.2",
                "LANE_ID": "L2",
                "ID": "R2",
                "MEDIATYPE": 1,
                "STATION_ID": "S1",
            },
            {
                "LANETYPE": "出口",
                "OCCURTIME": "2026-06-14 12:00:00",
                "STATION_NAME": "出口站",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
                "IPADDRESS": "10.0.0.3",
                "LANE_ID": "L3",
                "ID": "R3",
                "MEDIATYPE": 1,
            },
        ]

        result = aggregate_trip("PASS_EXC")
        assert result is not None
        # Should not crash; gantry IMAGE_ID set to None
        gantry_data = json.loads(result["gantry_records"])
        assert gantry_data[0]["pic_id"] == "R2"  # Falls back to ID


# ============================================================
# get_recent_passids
# ============================================================


class TestGetRecentPassids:
    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", False)
    def test_returns_empty_when_no_pymysql(self):
        assert get_recent_passids() == []

    @patch("apps.api.services.trip_aggregator.pymysql")
    @patch("apps.api.services.trip_aggregator.HAS_PYMYSQL", True)
    def test_returns_passid_list(self, mock_pymysql):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymysql.connect.return_value = mock_conn
        mock_pymysql.cursors.DictCursor = "DictCursor"
        mock_cursor.fetchall.return_value = [
            {"PASSID": "PASS1"},
            {"PASSID": "PASS2"},
        ]

        result = get_recent_passids(days=7, limit=100)
        assert result == ["PASS1", "PASS2"]


# ============================================================
# TripAggregator
# ============================================================


class TestTripAggregator:
    @patch("apps.api.services.trip_aggregator.get_recent_passids", return_value=[])
    def test_aggregate_recent_trips_no_passids(self, mock_passids):
        agg = TripAggregator()
        count = agg.aggregate_recent_trips(days=7, limit=100)
        assert count == 0

    @patch("apps.api.services.trip_aggregator.aggregate_trip", return_value=None)
    @patch("apps.api.services.trip_aggregator.get_recent_passids", return_value=["PASS1", "PASS2"])
    def test_aggregate_recent_trips_no_trip_data(self, mock_passids, mock_agg):
        with patch("apps.api.database.repositories.trip_repository.TripRepository"):
            agg = TripAggregator()
            count = agg.aggregate_recent_trips(days=7, limit=100, run_detection=False)
            assert count == 0

    @patch("apps.api.services.trip_aggregator.aggregate_trip")
    @patch("apps.api.services.trip_aggregator.get_recent_passids", return_value=["PASS1"])
    def test_aggregate_recent_trips_saves_and_counts(self, mock_passids, mock_agg):
        mock_agg.return_value = {
            "passid": "PASS1",
            "entry_time": "2026-06-14T10:00:00",
            "exit_time": "2026-06-14T12:00:00",
            "entry_station_name": "入口站",
            "exit_station_name": "出口站",
            "entry_vehicle_id": "京A1",
            "exit_vehicle_id": "京A1",
            "entry_vehicle_type": 1,
            "exit_vehicle_type": 1,
            "entry_vehicle_color": 1,
            "exit_vehicle_color": 1,
            "entry_obu_id": "OBU1",
            "exit_obu_id": "OBU1",
            "entry_media_type": 1,
            "exit_media_type": 1,
            "entry_image_license": "http://x/entry.jpg",
            "entry_image_trans": "http://x/entry_t.jpg",
            "exit_image_license": "http://x/exit.jpg",
            "exit_image_trans": "http://x/exit_t.jpg",
            "gantry_count": 0,
            "gantry_records": "[]",
        }

        mock_repo = MagicMock()
        mock_repo.save_trip.return_value = 1

        with patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo):
            agg = TripAggregator()
            count = agg.aggregate_recent_trips(days=7, limit=100, run_detection=False)
            assert count == 1
            mock_repo.save_trip.assert_called_once()

    @patch("apps.api.services.trip_aggregator.aggregate_trip")
    @patch("apps.api.services.trip_aggregator.get_recent_passids", return_value=["PASS1"])
    def test_aggregate_recent_trips_calls_on_progress(self, mock_passids, mock_agg):
        mock_agg.return_value = {
            "passid": "PASS1",
            "entry_time": "2026-06-14T10:00:00",
            "exit_time": "2026-06-14T12:00:00",
            "entry_station_name": "入口站",
            "exit_station_name": "出口站",
            "entry_vehicle_id": "京A1",
            "exit_vehicle_id": "京A1",
            "entry_vehicle_type": 1,
            "exit_vehicle_type": 1,
            "entry_vehicle_color": 1,
            "exit_vehicle_color": 1,
            "entry_obu_id": "OBU1",
            "exit_obu_id": "OBU1",
            "entry_media_type": 1,
            "exit_media_type": 1,
            "entry_image_license": "http://x/entry.jpg",
            "entry_image_trans": "http://x/entry_t.jpg",
            "exit_image_license": "http://x/exit.jpg",
            "exit_image_trans": "http://x/exit_t.jpg",
            "gantry_count": 0,
            "gantry_records": "[]",
        }

        mock_repo = MagicMock()
        mock_repo.save_trip.return_value = 1
        progress_calls = []

        def on_progress(info):
            progress_calls.append(info)

        with patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo):
            agg = TripAggregator()
            agg.aggregate_recent_trips(days=7, limit=100, on_progress=on_progress, run_detection=False)

        assert len(progress_calls) == 1
        assert progress_calls[0]["passid"] == "PASS1"
        assert progress_calls[0]["count"] == 1

    @patch("apps.api.services.trip_aggregator.aggregate_trip")
    @patch("apps.api.services.trip_aggregator.get_recent_passids", return_value=["PASS1"])
    def test_run_detection_with_suspicious_result(self, mock_passids, mock_agg):
        trip_data = {
            "passid": "PASS1",
            "entry_image_license": "http://x/entry.jpg",
            "exit_image_license": "http://x/exit.jpg",
        }
        mock_agg.return_value = trip_data

        mock_repo = MagicMock()
        mock_repo.save_trip.return_value = 1

        mock_matcher = MagicMock()
        mock_matcher.compare.return_value = {
            "_comparison_success": True,
            "is_suspicious": True,
            "fingerprint_sim": 0.3,
            "entry_visual_type": "truck",
            "exit_visual_type": "car",
            "entry_color": "blue",
            "exit_color": "red",
        }

        with (
            patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo),
            patch.object(TripAggregator, "_get_entry_exit_matcher", return_value=mock_matcher),
            patch.object(TripAggregator, "_schedule_llm_verification_async"),
        ):
            agg = TripAggregator()
            count = agg.aggregate_recent_trips(days=7, limit=100, run_detection=True)
            assert count == 1
            mock_repo.save_trip_with_detection_results.assert_called_once()

    @patch("apps.api.services.trip_aggregator.aggregate_trip")
    @patch("apps.api.services.trip_aggregator.get_recent_passids", return_value=["PASS1"])
    def test_run_detection_exception_does_not_crash(self, mock_passids, mock_agg):
        trip_data = {
            "passid": "PASS1",
            "entry_image_license": "http://x/entry.jpg",
            "exit_image_license": "http://x/exit.jpg",
        }
        mock_agg.return_value = trip_data

        mock_repo = MagicMock()
        mock_repo.save_trip.return_value = 1

        mock_matcher = MagicMock()
        mock_matcher.compare.side_effect = RuntimeError("vision service down")

        with (
            patch("apps.api.database.repositories.trip_repository.TripRepository", return_value=mock_repo),
            patch.object(TripAggregator, "_get_entry_exit_matcher", return_value=mock_matcher),
        ):
            agg = TripAggregator()
            # Should not raise, detection error is caught
            count = agg.aggregate_recent_trips(days=7, limit=100, run_detection=True)
            assert count == 1

    def test_schedule_llm_verification_skips_empty_passid(self):
        agg = TripAggregator()
        # Should return immediately without error
        agg._schedule_llm_verification_async(None)
        agg._schedule_llm_verification_async("")
