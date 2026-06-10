"""doris_trip_query 单元测试 - 重点覆盖 SQL 构造与 sort 注入防御"""
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from apps.api.services import doris_trip_query as dtq
from apps.api.services.doris_trip_query import (
    query_trips,
    get_trip_detail,
    _build_where_clause,
    _build_having_clause,
    _build_passid_cte,
    SORTABLE_COLUMNS_DORIS,
)


class TestBuildWhereClause:
    def test_no_filters_returns_1_1(self):
        sql, params = _build_where_clause({})
        assert sql == '1=1'
        assert params == []

    def test_vehicle_id_exact(self):
        sql, params = _build_where_clause({'vehicle_id': '京a12345', 'vehicle_id_match': 'exact'})
        assert 't.VEHICLEID = %s' in sql
        assert params == ['京A12345']

    def test_vehicle_id_prefix(self):
        sql, params = _build_where_clause({'vehicle_id': '京A', 'vehicle_id_match': 'prefix'})
        assert 't.VEHICLEID LIKE %s' in sql
        assert params == ['京A%']

    def test_vehicle_id_contains(self):
        sql, params = _build_where_clause({'vehicle_id': '123', 'vehicle_id_match': 'contains'})
        assert 'LIKE %s' in sql
        assert params == ['%123%']

    def test_vehicle_id_invalid_match_mode_falls_back_to_exact(self):
        sql, params = _build_where_clause({'vehicle_id': 'X', 'vehicle_id_match': 'hax'})
        assert 't.VEHICLEID = %s' in sql

    def test_vehicle_id_escapes_wildcards(self):
        sql, params = _build_where_clause({'vehicle_id': 'A%_B', 'vehicle_id_match': 'contains'})
        assert '\\%' in params[0]
        assert '\\_' in params[0]

    def test_obu_id(self):
        sql, params = _build_where_clause({'obu_id': 'OBU001'})
        assert 't.OBUID = %s' in sql
        assert params == ['OBU001']

    def test_vehicle_type_and_color(self):
        sql, params = _build_where_clause({'vehicle_type': '2', 'vehicle_color': '1'})
        assert 't.VEHICLETYPE = %s' in sql
        assert 't.VEHICLECOLOR = %s' in sql
        assert params == [2, 1]

    def test_invalid_vehicle_type_is_ignored(self):
        sql, params = _build_where_clause({'vehicle_type': 'abc'})
        assert 'VEHICLETYPE' not in sql

    def test_time_window_between(self):
        start = datetime(2026, 5, 1)
        end = datetime(2026, 5, 8)
        sql, params = _build_where_clause({'start_time': start, 'end_time': end})
        assert 'BETWEEN %s AND %s' in sql
        assert params == [start, end]

    def test_time_window_only_start(self):
        sql, params = _build_where_clause({'start_time': datetime(2026, 5, 1)})
        assert '>=' in sql
        assert params == [datetime(2026, 5, 1)]


class TestBuildHavingClause:
    def test_no_filters_returns_empty(self):
        sql, params = _build_having_clause({})
        assert sql == ''
        assert params == []

    def test_entry_station(self):
        sql, params = _build_having_clause({'entry_station_name': '北京南'})
        assert 'entry_station_name LIKE %s' in sql
        assert params == ['%北京南%']

    def test_gantry_range(self):
        sql, params = _build_having_clause({'min_gantry_count': '2', 'max_gantry_count': '5'})
        assert 'gantry_count >= %s' in sql
        assert 'gantry_count <= %s' in sql
        assert params == [2, 5]

    def test_invalid_gantry_ignored(self):
        sql, params = _build_having_clause({'min_gantry_count': 'oops'})
        assert 'gantry_count' not in sql


class TestBuildPassidCte:
    def test_cte_structure(self):
        cte = _build_passid_cte('1=1', '')
        assert 'WITH passid_agg AS' in cte
        assert 'GROUP BY t.PASSID' in cte
        assert "LANETYPE='入口'" in cte
        assert "LANETYPE='门架'" in cte

    def test_cte_includes_having_block(self):
        cte = _build_passid_cte('1=1', 'gantry_count >= %s')
        assert 'HAVING gantry_count >= %s' in cte


class TestQueryTrips:
    def test_invalid_order_by_raises(self):
        with pytest.raises(ValueError, match='Invalid order_by'):
            query_trips({'order_by': 'DROP TABLE--'}, limit=10, offset=0)

    def test_sort_allowlist_excludes_risk_score(self):
        assert 'risk_score' not in SORTABLE_COLUMNS_DORIS

    def test_query_executes_against_pymysql(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = {'total': 2}
        fake_cursor.fetchall.return_value = [
            {
                'PASSID': 'P001',
                'entry_time': datetime(2026, 5, 1, 8, 0),
                'entry_station_name': '北京南',
                'entry_vehicle_id': '京A12345',
                'entry_vehicle_color': '1',
                'entry_vehicle_type': 1,
                'entry_obu_id': 'OBU1',
                'exit_time': datetime(2026, 5, 1, 10, 0),
                'exit_station_name': '天津',
                'exit_vehicle_id': '京A12345',
                'exit_vehicle_color': '1',
                'exit_vehicle_type': 1,
                'exit_obu_id': 'OBU1',
                'gantry_count': 3,
            }
        ]
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cursor

        with patch.object(dtq, 'HAS_PYMYSQL', True), \
             patch('apps.api.services.doris_trip_query.pymysql.connect', return_value=fake_conn):
            rows, total = query_trips(
                {'vehicle_id': '京A12345', 'vehicle_id_match': 'exact',
                 'start_time': datetime(2026, 5, 1), 'end_time': datetime(2026, 5, 8),
                 'order_by': 'entry_time', 'order': 'desc'},
                limit=20, offset=0,
            )

        assert total == 2
        assert len(rows) == 1
        assert rows[0]['passid'] == 'P001'
        assert rows[0]['entry_vehicle_id'] == '京A12345'
        assert rows[0]['gantry_count'] == 3

        assert fake_cursor.execute.call_count == 2
        list_sql = fake_cursor.execute.call_args_list[1][0][0]
        assert 'ORDER BY entry_time DESC' in list_sql
        assert 'LIMIT %s OFFSET %s' in list_sql
        assert 'WITH passid_agg AS' in list_sql

    def test_query_returns_empty_when_no_pymysql(self):
        with patch.object(dtq, 'HAS_PYMYSQL', False):
            rows, total = query_trips({}, limit=10, offset=0)
        assert rows == []
        assert total == 0

    def test_query_short_circuits_on_zero_count(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = {'total': 0}
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cursor

        with patch.object(dtq, 'HAS_PYMYSQL', True), \
             patch('apps.api.services.doris_trip_query.pymysql.connect', return_value=fake_conn):
            rows, total = query_trips({}, limit=10, offset=0)

        assert rows == []
        assert total == 0
        assert fake_cursor.execute.call_count == 1

    def test_query_includes_having_when_filter_set(self):
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = {'total': 1}
        fake_cursor.fetchall.return_value = [
            {'PASSID': 'P', 'gantry_count': 2}
        ]
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cursor

        with patch.object(dtq, 'HAS_PYMYSQL', True), \
             patch('apps.api.services.doris_trip_query.pymysql.connect', return_value=fake_conn):
            query_trips({'min_gantry_count': '2', 'order_by': 'gantry_count'}, limit=5, offset=0)

        list_sql = fake_cursor.execute.call_args_list[1][0][0]
        assert 'HAVING' in list_sql
        assert 'ORDER BY gantry_count DESC' in list_sql

    def test_execute_params_match_placeholder_count_with_where_filters(self):
        """回归测试：WHERE 含过滤条件时，count/list 两次 execute 的参数数必须等于 SQL 中 %s 占位符数。"""
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = {'total': 1}
        fake_cursor.fetchall.return_value = [{'PASSID': 'P', 'gantry_count': 1}]
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cursor

        with patch.object(dtq, 'HAS_PYMYSQL', True), \
             patch('apps.api.services.doris_trip_query.pymysql.connect', return_value=fake_conn):
            query_trips(
                {
                    'vehicle_id': '京A12345',
                    'vehicle_id_match': 'exact',
                    'obu_id': 'OBU1',
                    'start_time': datetime(2026, 5, 1),
                    'end_time': datetime(2026, 5, 8),
                    'min_gantry_count': '1',
                    'order_by': 'entry_time',
                },
                limit=10, offset=0,
            )

        assert fake_cursor.execute.call_count == 2
        for call in fake_cursor.execute.call_args_list:
            sql, params = call.args
            placeholders = sql.count('%s')
            assert placeholders == len(params), (
                f"SQL has {placeholders} %s placeholders but execute got {len(params)} params. "
                f"sql={sql!r} params={params!r}"
            )

        count_sql, count_params = fake_cursor.execute.call_args_list[0].args
        list_sql, list_params = fake_cursor.execute.call_args_list[1].args
        assert list_params[-2:] == [10, 0]
        assert len(list_params) == len(count_params) + 2

    def test_row_to_dict_coerces_int_color_to_str(self):
        """回归测试：Doris 端 VEHICLECOLOR 是 TINYINT，返回 int；序列化层必须转 str 才能通过 Pydantic str 字段。"""
        from apps.api.services.doris_trip_query import _row_to_dict
        row = {
            'PASSID': 'P1',
            'entry_vehicle_color': 1,  # int from Doris
            'exit_vehicle_color': 2,
            'gantry_count': 3,
        }
        out = _row_to_dict(row)
        assert out['entry_vehicle_color'] == '1'
        assert isinstance(out['entry_vehicle_color'], str)
        assert out['exit_vehicle_color'] == '2'
        assert isinstance(out['exit_vehicle_color'], str)


class TestGetTripDetail:
    def test_returns_none_when_aggregate_returns_none(self):
        with patch.object(dtq, 'HAS_PYMYSQL', True), \
             patch('apps.api.services.doris_trip_query.aggregate_trip', return_value=None):
            assert get_trip_detail('NONEXIST') is None

    def test_includes_gantry_image_records(self):
        trip = {
            'passid': 'P1',
            'entry_time': '2026-05-01T08:00:00',
            'entry_station_name': 'S1',
            'entry_vehicle_id': '京A12345',
            'entry_vehicle_color': 1,
            'entry_vehicle_type': 1,
            'entry_obu_id': 'OBU1',
            'entry_lane_id': 'L1',
            'entry_image_license': 'http://x/lic.jpg',
            'entry_image_trans': 'http://x/trans.jpg',
            'exit_time': '2026-05-01T10:00:00',
            'exit_station_name': 'S2',
            'exit_vehicle_id': '京A12345',
            'exit_vehicle_color': 1,
            'exit_vehicle_type': 1,
            'exit_obu_id': 'OBU1',
            'exit_lane_id': 'L2',
            'exit_image_license': 'http://x/lic2.jpg',
            'exit_image_trans': 'http://x/trans2.jpg',
            'gantry_count': 1,
            'gantry_records': '[]',
        }
        with patch.object(dtq, 'HAS_PYMYSQL', True), \
             patch('apps.api.services.doris_trip_query.aggregate_trip', return_value=trip), \
             patch('apps.api.services.doris_trip_query.get_gantry_images_by_vehicle', return_value=[]):
            detail = get_trip_detail('P1')

        assert detail is not None
        assert detail['passid'] == 'P1'
        assert detail['gantry_records'] == '[]'
        assert detail['gantry_image_records'] is not None
        assert 'audit_results' not in detail

    def test_returns_none_when_passid_empty(self):
        assert get_trip_detail('') is None
        assert get_trip_detail(None) is None
