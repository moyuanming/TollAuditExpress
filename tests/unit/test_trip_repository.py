"""任意车辆查询仓储层单元测试 — 覆盖 _build_where、get_trip_detail_with_results"""

import pytest


@pytest.fixture
def repo_client(temp_db):
    from apps.api.database.repositories.trip_repository import (
        TripRepository, _build_where, _resolve_order, VEHICLE_TYPE_VALUES,
    )
    return {
        "TripRepository": TripRepository,
        "_build_where": _build_where,
        "_resolve_order": _resolve_order,
    }


def _seed_trip(repo, **overrides):
    """插入一条最小可用的 trip。"""
    base = {
        "passid": "TRIP_BASE",
        "entry_time": "2025-06-15 08:00:00",
        "exit_time": "2025-06-15 12:00:00",
        "entry_station_name": "入口A",
        "exit_station_name": "出口B",
        "entry_vehicle_id": "川A00001",
        "exit_vehicle_id": "川A00001",
        "entry_vehicle_type": 1,
        "exit_vehicle_type": 1,
        "entry_vehicle_color": 1,
        "exit_vehicle_color": 1,
        "entry_obu_id": "OBU0001",
        "exit_obu_id": "OBU0001",
        "audit_status": "PENDING",
        "risk_score": 0.0,
        "gantry_count": 0,
    }
    base.update(overrides)
    return repo.save_trip(base)


class TestBuildWhereHelpers:
    def test_empty_filters_returns_empty_where(self, repo_client):
        where, params = repo_client["_build_where"]({})
        assert where == ""
        assert params == []

    def test_plate_exact_match_uses_eq(self, repo_client):
        where, params = repo_client["_build_where"](
            {"entry_vehicle_id": "川A12345", "vehicle_id_match": "exact"}
        )
        assert "entry_vehicle_id = %s" in where
        assert params == ["川A12345"]

    def test_plate_prefix_uses_like(self, repo_client):
        where, params = repo_client["_build_where"](
            {"entry_vehicle_id": "川A", "vehicle_id_match": "prefix"}
        )
        assert "entry_vehicle_id LIKE %s" in where
        assert params == ["川A%"]

    def test_plate_contains_uses_like_with_wildcards(self, repo_client):
        where, params = repo_client["_build_where"](
            {"entry_vehicle_id": "A12", "vehicle_id_match": "contains"}
        )
        assert "entry_vehicle_id LIKE %s" in where
        assert params == ["%A12%"]

    def test_vehicle_id_or_clause(self, repo_client):
        where, params = repo_client["_build_where"]({"vehicle_id": "川Z"})
        assert "OR" in where
        # exact 是默认值
        assert "川Z" in params
        assert len(params) == 2  # 各出现一次

    def test_vehicle_type_validated_against_allowed_set(self, repo_client):
        # 3 不在 VEHICLE_TYPE_VALUES 中，应跳过该条件
        where, params = repo_client["_build_where"]({"vehicle_type": 99})
        assert where == ""
        assert params == []

    def test_risk_score_range(self, repo_client):
        where, params = repo_client["_build_where"](
            {"min_risk_score": 0.3, "max_risk_score": 0.8}
        )
        assert "risk_score >= %s" in where
        assert "risk_score <= %s" in where
        assert 0.3 in params and 0.8 in params

    def test_gantry_count_range(self, repo_client):
        where, params = repo_client["_build_where"](
            {"min_gantry_count": 2, "max_gantry_count": 5}
        )
        assert "gantry_count >= %s" in where
        assert "gantry_count <= %s" in where

    def test_audit_status_overrides_legacy_status(self, repo_client):
        where, params = repo_client["_build_where"]({"status": "PENDING", "audit_status": "SUSPECTED"})
        assert "audit_status = %s" in where
        # audit_status 应覆盖 status，只有一个 ?，值为 SUSPECTED
        assert where.count("%s") == 1
        assert params == ["SUSPECTED"]


class TestResolveOrder:
    def test_default_is_entry_time_desc(self, repo_client):
        order = repo_client["_resolve_order"]({})
        assert order == " ORDER BY entry_time DESC"

    def test_risk_score_asc_allowed(self, repo_client):
        order = repo_client["_resolve_order"]({"order_by": "risk_score", "order": "asc"})
        assert order == " ORDER BY risk_score ASC"

    def test_invalid_order_by_falls_back_to_default(self, repo_client):
        order = repo_client["_resolve_order"]({"order_by": "evil;DROP TABLE audit_trips--"})
        assert "entry_time" in order
        assert "DROP" not in order

    def test_invalid_order_falls_back_to_desc(self, repo_client):
        order = repo_client["_resolve_order"]({"order": "sideways"})
        assert "DESC" in order


class TestGetTripsWithFilters:
    def test_filter_by_entry_vehicle_id(self, repo_client):
        repo = repo_client["TripRepository"]()
        _seed_trip(repo, passid="T1", entry_vehicle_id="川A11111", risk_score=0.5)
        _seed_trip(repo, passid="T2", entry_vehicle_id="川B22222", risk_score=0.5)
        rows = repo.get_trips(entry_vehicle_id="川A11111")
        assert len(rows) == 1
        assert rows[0]["passid"] == "T1"

    def test_vehicle_id_match_either_entry_or_exit(self, repo_client):
        repo = repo_client["TripRepository"]()
        _seed_trip(repo, passid="E1", entry_vehicle_id="川X99999", exit_vehicle_id="川X99999")
        _seed_trip(repo, passid="E2", entry_vehicle_id="川X99999", exit_vehicle_id="川Y88888")
        _seed_trip(repo, passid="E3", entry_vehicle_id="川Y88888", exit_vehicle_id="川Y88888")
        # 精确匹配 vehicle_id 入口或出口任一
        rows = repo.get_trips(vehicle_id="川X99999")
        passids = {r["passid"] for r in rows}
        assert passids == {"E1", "E2"}

    def test_prefix_match(self, repo_client):
        repo = repo_client["TripRepository"]()
        _seed_trip(repo, passid="P1", entry_vehicle_id="川AAA001")
        _seed_trip(repo, passid="P2", entry_vehicle_id="川AAA002")
        _seed_trip(repo, passid="P3", entry_vehicle_id="川BBB003")
        rows = repo.get_trips(entry_vehicle_id="川AAA", vehicle_id_match="prefix")
        passids = {r["passid"] for r in rows}
        assert passids == {"P1", "P2"}

    def test_risk_score_range_filters(self, repo_client):
        repo = repo_client["TripRepository"]()
        _seed_trip(repo, passid="R1", risk_score=0.3)
        _seed_trip(repo, passid="R2", risk_score=0.7)
        _seed_trip(repo, passid="R3", risk_score=0.95)
        rows = repo.get_trips(min_risk_score=0.6, max_risk_score=0.9)
        passids = {r["passid"] for r in rows}
        assert passids == {"R2"}

    def test_time_window(self, repo_client):
        repo = repo_client["TripRepository"]()
        _seed_trip(repo, passid="W1", entry_time="2025-06-10 08:00:00")
        _seed_trip(repo, passid="W2", entry_time="2025-06-15 08:00:00")
        _seed_trip(repo, passid="W3", entry_time="2025-06-20 08:00:00")
        rows = repo.get_trips(start_time="2025-06-12", end_time="2025-06-18")
        passids = {r["passid"] for r in rows}
        assert passids == {"W2"}

    def test_order_by_risk_score(self, repo_client):
        repo = repo_client["TripRepository"]()
        _seed_trip(repo, passid="O1", risk_score=0.9)
        _seed_trip(repo, passid="O2", risk_score=0.1)
        _seed_trip(repo, passid="O3", risk_score=0.5)
        rows = repo.get_trips(order_by="risk_score", order="asc")
        assert [r["passid"] for r in rows] == ["O2", "O3", "O1"]

    def test_get_total_count_matches(self, repo_client):
        repo = repo_client["TripRepository"]()
        for i in range(5):
            _seed_trip(repo, passid=f"C{i}", entry_vehicle_id="川C00000")
        total = repo.get_total_count(entry_vehicle_id="川C00000")
        assert total == 5


class TestGetTripDetailWithResults:
    def test_returns_none_for_missing_trip(self, repo_client):
        repo = repo_client["TripRepository"]()
        trip, results = repo.get_trip_detail_with_results("DOES_NOT_EXIST")
        assert trip is None
        assert results == []

    def test_returns_trip_with_empty_results(self, repo_client):
        repo = repo_client["TripRepository"]()
        _seed_trip(repo, passid="TR_EMPTY")
        trip, results = repo.get_trip_detail_with_results("TR_EMPTY")
        assert trip is not None
        assert trip["passid"] == "TR_EMPTY"
        assert results == []

    def test_returns_trip_with_associated_results(self, repo_client):
        from apps.api.database.repositories.audit_repository import AuditRepository
        repo = repo_client["TripRepository"]()
        trip_id = _seed_trip(repo, passid="TR_RES")
        audit_repo = AuditRepository()
        audit_repo.save_result({
            "audit_trip_id": trip_id,
            "fraud_type": "TRUCK_USES_PASSENGER_OBU",
            "is_suspicious": 1,
            "risk_score": 0.85,
            "details": '{"x": 1}',
            "process_status": "UNPROCESSED",
        })

        trip, results = repo.get_trip_detail_with_results("TR_RES")
        assert trip["passid"] == "TR_RES"
        assert len(results) == 1
        r = results[0]
        # JOIN 应把所有 SuspectResponse 需要的字段带回来
        for f in ["passid", "entry_time", "exit_time", "entry_station_name",
                  "entry_vehicle_id", "entry_obu_id", "gantry_count", "gantry_records"]:
            assert f in r, f"Missing field: {f}"
        assert r["fraud_type"] == "TRUCK_USES_PASSENGER_OBU"
