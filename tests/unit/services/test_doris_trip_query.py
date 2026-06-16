"""doris_trip_query 单元测试 — Doris行程查询

行为契约:
  - _normalize_vehicle_id: 清理车牌输入
  - _build_where_clause: 构造WHERE子句(过滤原始记录)
  - _build_having_clause: 构造HAVING子句(聚合后过滤)
  - _build_passid_cte: 构造CTE SQL
  - _format_time: 时间格式化
  - _row_to_dict: 行序列化
  - query_trips: 按PASSID聚合查询行程
  - get_trip_detail: 获取单个行程详情
  - find_passenger_obu_candidates_doris: 筛选客车OBU候选
  - _rows_to_candidate_trips: 扁平行按PASSID分组
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.api.services.doris_trip_query import (
    SORTABLE_COLUMNS_DORIS,
    VEHICLE_ID_MATCH_MODES_DORIS,
    _build_having_clause,
    _build_passid_cte,
    _build_where_clause,
    _format_time,
    _normalize_vehicle_id,
    _row_to_dict,
    _rows_to_candidate_trips,
    find_passenger_obu_candidates_doris,
    get_trip_detail,
    query_trips,
)

# ============================================================
# _normalize_vehicle_id
# ============================================================


class TestNormalizeVehicleId:
    def test_strips_whitespace_and_uppercases(self):
        assert _normalize_vehicle_id("  京a12345  ") == "京A12345"

    def test_returns_empty_for_none(self):
        assert _normalize_vehicle_id(None) == ""

    def test_returns_empty_for_empty_string(self):
        assert _normalize_vehicle_id("") == ""

    def test_already_normalized(self):
        assert _normalize_vehicle_id("京A12345") == "京A12345"


# ============================================================
# _build_where_clause
# ============================================================


class TestBuildWhereClause:
    def test_empty_filters_returns_1_equals_1(self):
        sql, params = _build_where_clause({})
        assert sql == "1=1"
        assert params == []

    def test_exact_vehicle_id_match(self):
        sql, params = _build_where_clause({"vehicle_id": "京A12345"})
        assert "t.VEHICLEID = %s" in sql
        assert "京A12345" in params

    def test_prefix_vehicle_id_match(self):
        sql, params = _build_where_clause({"vehicle_id": "京A", "vehicle_id_match": "prefix"})
        assert "LIKE %s" in sql
        assert params[0] == "京A%"

    def test_contains_vehicle_id_match(self):
        sql, params = _build_where_clause({"vehicle_id": "A12", "vehicle_id_match": "contains"})
        assert "LIKE %s" in sql
        assert params[0] == "%A12%"

    def test_invalid_match_mode_defaults_to_exact(self):
        sql, params = _build_where_clause({"vehicle_id": "京A1", "vehicle_id_match": "invalid"})
        assert "t.VEHICLEID = %s" in sql

    def test_obu_id_filter(self):
        sql, params = _build_where_clause({"obu_id": "OBU001"})
        assert "t.OBUID = %s" in sql
        assert "OBU001" in params

    def test_vehicle_type_filter(self):
        sql, params = _build_where_clause({"vehicle_type": 1})
        assert "t.VEHICLETYPE = %s" in sql
        assert 1 in params

    def test_vehicle_type_string_converted(self):
        sql, params = _build_where_clause({"vehicle_type": "2"})
        assert "t.VEHICLETYPE = %s" in sql
        assert 2 in params

    def test_vehicle_type_invalid_ignored(self):
        sql, params = _build_where_clause({"vehicle_type": "not-int"})
        assert "VEHICLETYPE" not in sql

    def test_vehicle_color_filter(self):
        sql, params = _build_where_clause({"vehicle_color": 1})
        assert "t.VEHICLECOLOR = %s" in sql

    def test_time_range_filter(self):
        sql, params = _build_where_clause(
            {
                "start_time": "2026-06-01",
                "end_time": "2026-06-30",
            }
        )
        assert "BETWEEN %s AND %s" in sql
        assert "2026-06-01" in params
        assert "2026-06-30" in params

    def test_start_time_only_filter(self):
        sql, params = _build_where_clause({"start_time": "2026-06-01"})
        assert "OCCURTIME >= %s" in sql

    def test_end_time_only_filter(self):
        sql, params = _build_where_clause({"end_time": "2026-06-30"})
        assert "OCCURTIME <= %s" in sql

    def test_combined_filters(self):
        sql, params = _build_where_clause(
            {
                "vehicle_id": "京A1",
                "obu_id": "OBU1",
                "start_time": "2026-06-01",
                "end_time": "2026-06-30",
            }
        )
        assert "AND" in sql
        assert len(params) >= 4

    def test_vehicle_id_special_chars_escaped(self):
        sql, params = _build_where_clause({"vehicle_id": "京%A_"})
        # Should escape % and _ for LIKE
        assert "VEHICLEID = %s" in sql


# ============================================================
# _build_having_clause
# ============================================================


class TestBuildHavingClause:
    def test_empty_filters_returns_empty(self):
        sql, params = _build_having_clause({})
        assert sql == ""
        assert params == []

    def test_entry_station_filter(self):
        sql, params = _build_having_clause({"entry_station_name": "站A"})
        assert "entry_station_name LIKE %s" in sql
        assert params[0] == "%站A%"

    def test_exit_station_filter(self):
        sql, params = _build_having_clause({"exit_station_name": "站B"})
        assert "exit_station_name LIKE %s" in sql
        assert params[0] == "%站B%"

    def test_min_gantry_count_filter(self):
        sql, params = _build_having_clause({"min_gantry_count": 3})
        assert "gantry_count >= %s" in sql
        assert 3 in params

    def test_max_gantry_count_filter(self):
        sql, params = _build_having_clause({"max_gantry_count": 10})
        assert "gantry_count <= %s" in sql
        assert 10 in params

    def test_invalid_gantry_count_ignored(self):
        sql, params = _build_having_clause({"min_gantry_count": "not-int"})
        assert "gantry_count" not in sql

    def test_combined_having_filters(self):
        sql, params = _build_having_clause(
            {
                "entry_station_name": "站A",
                "min_gantry_count": 2,
            }
        )
        assert "AND" in sql
        assert len(params) == 2


# ============================================================
# _build_passid_cte
# ============================================================


class TestBuildPassidCte:
    def test_generates_cte_with_where_and_no_having(self):
        cte = _build_passid_cte("t.VEHICLEID = %s", "")
        assert "WITH passid_agg AS" in cte
        assert "t.VEHICLEID = %s" in cte
        assert "HAVING" not in cte

    def test_generates_cte_with_having(self):
        cte = _build_passid_cte("1=1", "gantry_count >= %s")
        assert "HAVING gantry_count >= %s" in cte


# ============================================================
# _format_time
# ============================================================


class TestFormatTime:
    def test_datetime_to_isoformat(self):
        dt = datetime(2026, 6, 14, 10, 30, 0)
        assert _format_time(dt) == "2026-06-14T10:30:00"

    def test_none_returns_none(self):
        assert _format_time(None) is None

    def test_string_returns_string(self):
        assert _format_time("2026-06-14") == "2026-06-14"

    def test_int_returns_string(self):
        assert _format_time(123) == "123"


# ============================================================
# _row_to_dict
# ============================================================


class TestRowToDict:
    def test_converts_row_to_dict(self):
        row = {
            "PASSID": "PASS1",
            "entry_time": datetime(2026, 6, 14, 10, 0, 0),
            "entry_station_name": "入口站",
            "entry_vehicle_id": "京A1",
            "entry_vehicle_color": 1,
            "entry_vehicle_type": 1,
            "entry_obu_id": "OBU1",
            "exit_time": datetime(2026, 6, 14, 12, 0, 0),
            "exit_station_name": "出口站",
            "exit_vehicle_id": "京A1",
            "exit_vehicle_color": 2,
            "exit_vehicle_type": 1,
            "exit_obu_id": "OBU1",
            "gantry_count": 3,
        }
        result = _row_to_dict(row)
        assert result["passid"] == "PASS1"
        assert result["entry_time"] == "2026-06-14T10:00:00"
        assert result["exit_time"] == "2026-06-14T12:00:00"
        assert result["gantry_count"] == 3
        assert result["entry_vehicle_color"] == "1"

    def test_handles_null_values(self):
        row = {
            "PASSID": "PASS2",
            "entry_time": None,
            "entry_station_name": None,
            "entry_vehicle_id": None,
            "entry_vehicle_color": None,
            "entry_vehicle_type": None,
            "entry_obu_id": None,
            "exit_time": None,
            "exit_station_name": None,
            "exit_vehicle_id": None,
            "exit_vehicle_color": None,
            "exit_vehicle_type": None,
            "exit_obu_id": None,
            "gantry_count": None,
        }
        result = _row_to_dict(row)
        assert result["entry_time"] is None
        assert result["gantry_count"] == 0


# ============================================================
# query_trips
# ============================================================


class TestQueryTrips:
    @patch("apps.api.services.doris_trip_query.HAS_PYMYSQL", False)
    def test_returns_empty_when_no_pymysql(self):
        rows, total = query_trips({})
        assert rows == []
        assert total == 0

    def test_raises_on_invalid_order_by(self):
        with pytest.raises(ValueError, match="Invalid order_by"):
            query_trips({"order_by": "invalid_column"})

    @patch("apps.api.services.doris_trip_query.pymysql")
    @patch("apps.api.services.doris_trip_query.HAS_PYMYSQL", True)
    def test_returns_empty_when_total_zero(self, mock_pymysql):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymysql.connect.return_value = mock_conn
        mock_pymysql.cursors.DictCursor = "DictCursor"
        mock_cursor.fetchone.return_value = {"total": 0}

        rows, total = query_trips({"order_by": "entry_time"})
        assert rows == []
        assert total == 0

    @patch("apps.api.services.doris_trip_query.pymysql")
    @patch("apps.api.services.doris_trip_query.HAS_PYMYSQL", True)
    def test_returns_rows_and_total(self, mock_pymysql):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymysql.connect.return_value = mock_conn
        mock_pymysql.cursors.DictCursor = "DictCursor"

        # First call (count), second call (list)
        mock_cursor.fetchone.return_value = {"total": 2}
        mock_cursor.fetchall.return_value = [
            {
                "PASSID": "P1",
                "entry_time": "2026-06-14",
                "entry_station_name": "站1",
                "entry_vehicle_id": "京A1",
                "entry_vehicle_color": 1,
                "entry_vehicle_type": 1,
                "entry_obu_id": None,
                "exit_time": "2026-06-14",
                "exit_station_name": "站2",
                "exit_vehicle_id": "京A1",
                "exit_vehicle_color": 1,
                "exit_vehicle_type": 1,
                "exit_obu_id": None,
                "gantry_count": 2,
            },
            {
                "PASSID": "P2",
                "entry_time": "2026-06-15",
                "entry_station_name": "站3",
                "entry_vehicle_id": "京B1",
                "entry_vehicle_color": 2,
                "entry_vehicle_type": 2,
                "entry_obu_id": None,
                "exit_time": "2026-06-15",
                "exit_station_name": "站4",
                "exit_vehicle_id": "京B1",
                "exit_vehicle_color": 2,
                "exit_vehicle_type": 2,
                "exit_obu_id": None,
                "gantry_count": 0,
            },
        ]

        rows, total = query_trips({"order_by": "entry_time"})
        assert total == 2
        assert len(rows) == 2
        assert rows[0]["passid"] == "P1"

    def test_sortable_columns_whitelist(self):
        assert "entry_time" in SORTABLE_COLUMNS_DORIS
        assert "exit_time" in SORTABLE_COLUMNS_DORIS
        assert "gantry_count" in SORTABLE_COLUMNS_DORIS
        assert "invalid" not in SORTABLE_COLUMNS_DORIS

    def test_vehicle_id_match_modes_whitelist(self):
        assert "exact" in VEHICLE_ID_MATCH_MODES_DORIS
        assert "prefix" in VEHICLE_ID_MATCH_MODES_DORIS
        assert "contains" in VEHICLE_ID_MATCH_MODES_DORIS


# ============================================================
# get_trip_detail
# ============================================================


class TestGetTripDetail:
    def test_returns_none_for_empty_passid(self):
        assert get_trip_detail("") is None

    @patch("apps.api.services.doris_trip_query.HAS_PYMYSQL", False)
    def test_returns_none_when_no_pymysql(self):
        assert get_trip_detail("PASS1") is None

    @patch("apps.api.services.doris_trip_query.aggregate_trip", return_value=None)
    @patch("apps.api.services.doris_trip_query.get_records_by_passid", return_value=[])
    def test_returns_none_when_no_records(self, mock_records, mock_agg):
        result = get_trip_detail("PASS_EMPTY")
        assert result is None

    @patch("apps.api.services.doris_trip_query.get_gantry_images_by_vehicle", return_value=[])
    @patch("apps.api.services.doris_trip_query.aggregate_trip")
    def test_returns_detail_from_aggregate_trip(self, mock_agg, mock_gantry):
        mock_agg.return_value = {
            "passid": "PASS1",
            "entry_time": "2026-06-14T10:00:00",
            "exit_time": "2026-06-14T12:00:00",
            "entry_station_name": "入口站",
            "exit_station_name": "出口站",
            "entry_vehicle_id": "京A1",
            "exit_vehicle_id": "京A1",
            "entry_vehicle_color": 1,
            "exit_vehicle_color": 1,
            "entry_vehicle_type": 1,
            "exit_vehicle_type": 1,
            "entry_obu_id": "OBU1",
            "exit_obu_id": "OBU1",
            "entry_lane_id": "L1",
            "exit_lane_id": "L2",
            "entry_image_license": "http://x/e.jpg",
            "entry_image_trans": "http://x/et.jpg",
            "exit_image_license": "http://x/x.jpg",
            "exit_image_trans": "http://x/xt.jpg",
            "gantry_count": 1,
            "gantry_records": "[]",
        }

        result = get_trip_detail("PASS1")
        assert result is not None
        assert result["passid"] == "PASS1"
        assert result["entry_time"] == "2026-06-14T10:00:00"
        assert result["exit_time"] == "2026-06-14T12:00:00"
        assert result["entry_station_name"] == "入口站"
        assert result["exit_station_name"] == "出口站"
        assert result["gantry_count"] == 1

    @patch("apps.api.services.doris_trip_query.get_gantry_images_by_vehicle", return_value=[])
    @patch("apps.api.services.doris_trip_query.aggregate_trip", return_value=None)
    @patch("apps.api.services.doris_trip_query.get_records_by_passid")
    def test_fallback_to_records_when_aggregate_fails(self, mock_records, mock_agg, mock_gantry):
        mock_records.return_value = [
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
            },
            {
                "LANETYPE": "出口",
                "OCCURTIME": "2026-06-14 12:00:00",
                "STATION_NAME": "出口站",
                "VEHICLEID": "京A1",
                "VEHICLECOLOR": 1,
                "VEHICLETYPE": 1,
                "OBUID": "OBU1",
                "IPADDRESS": "10.0.0.2",
                "LANE_ID": "L2",
                "ID": "R2",
            },
        ]

        result = get_trip_detail("PASS_FALLBACK")
        assert result is not None
        assert result["passid"] == "PASS_FALLBACK"
        assert result["entry_station_name"] == "入口站"
        assert result["exit_station_name"] == "出口站"


# ============================================================
# find_passenger_obu_candidates_doris
# ============================================================


class TestFindPassengerObuCandidatesDoris:
    @patch("apps.api.services.doris_trip_query.HAS_PYMYSQL", False)
    def test_returns_empty_when_no_pymysql(self):
        assert find_passenger_obu_candidates_doris("2026-06-01", "2026-06-30") == []

    @patch("apps.api.services.doris_trip_query.pymysql")
    @patch("apps.api.services.doris_trip_query.HAS_PYMYSQL", True)
    def test_returns_candidate_trips(self, mock_pymysql):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pymysql.connect.return_value = mock_conn
        mock_pymysql.cursors.DictCursor = "DictCursor"
        mock_cursor.fetchall.return_value = [
            {
                "PASSID": "P1",
                "LANETYPE": "入口",
                "VEHICLETYPE": 1,
                "VEHICLEID": "川A1",
                "VEHICLECOLOR": 1,
                "OBUID": "OBU1",
                "MEDIATYPE": 1,
                "STATION_NAME": "站1",
                "LANE_ID": "L1",
                "OCCURTIME": "2026-06-14 10:00:00",
                "ID": "R1",
                "STATION_ID": "S1",
                "IPADDRESS": "10.0.0.1",
            },
            {
                "PASSID": "P1",
                "LANETYPE": "出口",
                "VEHICLETYPE": 1,
                "VEHICLEID": "川A1",
                "VEHICLECOLOR": 1,
                "OBUID": "OBU1",
                "MEDIATYPE": 1,
                "STATION_NAME": "站2",
                "LANE_ID": "L2",
                "OCCURTIME": "2026-06-14 12:00:00",
                "ID": "R2",
                "STATION_ID": "S2",
                "IPADDRESS": "10.0.0.2",
            },
        ]

        result = find_passenger_obu_candidates_doris("2026-06-01", "2026-06-30")
        assert len(result) == 1
        assert result[0]["passid"] == "P1"
        assert result[0]["entry_station_name"] == "站1"
        assert result[0]["exit_station_name"] == "站2"


# ============================================================
# _rows_to_candidate_trips
# ============================================================


class TestRowsToCandidateTrips:
    def test_groups_by_passid(self):
        rows = [
            {
                "PASSID": "P1",
                "LANETYPE": "入口",
                "VEHICLETYPE": 1,
                "VEHICLEID": "川A1",
                "VEHICLECOLOR": 1,
                "OBUID": "OBU1",
                "MEDIATYPE": 1,
                "STATION_NAME": "站1",
                "LANE_ID": "L1",
                "OCCURTIME": "2026-06-14 10:00:00",
                "ID": "R1",
                "STATION_ID": "S1",
                "IPADDRESS": "10.0.0.1",
            },
            {
                "PASSID": "P1",
                "LANETYPE": "出口",
                "VEHICLETYPE": 1,
                "VEHICLEID": "川A1",
                "VEHICLECOLOR": 1,
                "OBUID": "OBU1",
                "MEDIATYPE": 1,
                "STATION_NAME": "站2",
                "LANE_ID": "L2",
                "OCCURTIME": "2026-06-14 12:00:00",
                "ID": "R2",
                "STATION_ID": "S2",
                "IPADDRESS": "10.0.0.2",
            },
        ]
        trips = _rows_to_candidate_trips(rows)
        assert len(trips) == 1
        assert trips[0]["passid"] == "P1"
        assert trips[0]["entry_vehicle_id"] == "川A1"
        assert trips[0]["exit_vehicle_id"] == "川A1"

    def test_handles_entry_only(self):
        rows = [
            {
                "PASSID": "P2",
                "LANETYPE": "入口",
                "VEHICLETYPE": 1,
                "VEHICLEID": "川B1",
                "VEHICLECOLOR": 1,
                "OBUID": "OBU2",
                "MEDIATYPE": 1,
                "STATION_NAME": "站1",
                "LANE_ID": "L1",
                "OCCURTIME": "2026-06-14 10:00:00",
                "ID": "R1",
                "STATION_ID": "S1",
                "IPADDRESS": "10.0.0.1",
            },
        ]
        trips = _rows_to_candidate_trips(rows)
        assert len(trips) == 1
        assert trips[0]["entry_station_name"] == "站1"
        assert trips[0]["exit_station_name"] is None

    def test_handles_empty_rows(self):
        trips = _rows_to_candidate_trips([])
        assert trips == []

    def test_multiple_passids(self):
        rows = [
            {
                "PASSID": "P1",
                "LANETYPE": "入口",
                "VEHICLETYPE": 1,
                "VEHICLEID": "川A1",
                "VEHICLECOLOR": 1,
                "OBUID": "OBU1",
                "MEDIATYPE": 1,
                "STATION_NAME": "站1",
                "LANE_ID": "L1",
                "OCCURTIME": "2026-06-14 10:00:00",
                "ID": "R1",
                "STATION_ID": "S1",
                "IPADDRESS": "10.0.0.1",
            },
            {
                "PASSID": "P1",
                "LANETYPE": "出口",
                "VEHICLETYPE": 1,
                "VEHICLEID": "川A1",
                "VEHICLECOLOR": 1,
                "OBUID": "OBU1",
                "MEDIATYPE": 1,
                "STATION_NAME": "站2",
                "LANE_ID": "L2",
                "OCCURTIME": "2026-06-14 12:00:00",
                "ID": "R2",
                "STATION_ID": "S2",
                "IPADDRESS": "10.0.0.2",
            },
            {
                "PASSID": "P2",
                "LANETYPE": "入口",
                "VEHICLETYPE": 1,
                "VEHICLEID": "川B1",
                "VEHICLECOLOR": 2,
                "OBUID": "OBU2",
                "MEDIATYPE": 1,
                "STATION_NAME": "站3",
                "LANE_ID": "L3",
                "OCCURTIME": "2026-06-14 11:00:00",
                "ID": "R3",
                "STATION_ID": "S3",
                "IPADDRESS": "10.0.0.3",
            },
            {
                "PASSID": "P2",
                "LANETYPE": "出口",
                "VEHICLETYPE": 1,
                "VEHICLEID": "川B1",
                "VEHICLECOLOR": 2,
                "OBUID": "OBU2",
                "MEDIATYPE": 1,
                "STATION_NAME": "站4",
                "LANE_ID": "L4",
                "OCCURTIME": "2026-06-14 13:00:00",
                "ID": "R4",
                "STATION_ID": "S4",
                "IPADDRESS": "10.0.0.4",
            },
        ]
        trips = _rows_to_candidate_trips(rows)
        assert len(trips) == 2
        passids = {t["passid"] for t in trips}
        assert passids == {"P1", "P2"}
