"""TopologyRepository 单元测试 — 阶段 1 MVP

行为契约：
  - list_edges() 全表扫描，按 (from_station, to_station) 排序
  - get_neighbors(station) 返回该站点的所有相邻站点
  - add_edge() 必须传 from_station/to_station
  - delete_edge(id) 返回是否真删了
  - get_edge(from_station, to_station) 查重，避免重复录入
"""

import pytest

from apps.api.database.repositories.topology_repository import TopologyRepository


@pytest.fixture
def repo(temp_db):
    return TopologyRepository()


class TestListEdges:
    def test_returns_empty_list(self, repo):
        assert repo.list_edges() == []

    def test_lists_all_edges(self, repo):
        repo.add_edge(from_station="A", to_station="B", distance_km=10.5)
        repo.add_edge(from_station="B", to_station="C", distance_km=20.0)
        edges = repo.list_edges()
        assert len(edges) == 2
        pairs = [(e["from_station"], e["to_station"]) for e in edges]
        assert ("A", "B") in pairs
        assert ("B", "C") in pairs


class TestAddEdge:
    def test_creates_edge_with_distance(self, repo):
        eid = repo.add_edge(from_station="A", to_station="B", distance_km=10.5)
        assert isinstance(eid, int)
        edge = repo.get_edge_by_id(eid)
        assert edge["from_station"] == "A"
        assert edge["to_station"] == "B"
        assert edge["distance_km"] == 10.5
        assert edge["is_connected"] == 1

    def test_creates_edge_with_notes(self, repo):
        eid = repo.add_edge(from_station="A", to_station="B", notes="main line")
        edge = repo.get_edge_by_id(eid)
        assert edge["notes"] == "main line"

    def test_raises_when_required_field_missing(self, repo):
        with pytest.raises(ValueError):
            repo.add_edge(from_station="A", to_station=None)


class TestGetNeighbors:
    def test_returns_empty_when_no_edges(self, repo):
        assert repo.get_neighbors("A") == []

    def test_returns_all_outgoing_neighbors(self, repo):
        repo.add_edge(from_station="A", to_station="B", distance_km=10)
        repo.add_edge(from_station="A", to_station="C", distance_km=20)
        repo.add_edge(from_station="B", to_station="C", distance_km=5)
        neighbors_a = repo.get_neighbors("A")
        assert sorted(n["to_station"] for n in neighbors_a) == ["B", "C"]
        assert neighbors_a[0]["distance_km"] in (10.0, 20.0)

    def test_filters_disconnected_edges(self, repo):
        eid1 = repo.add_edge(from_station="A", to_station="B", distance_km=10)
        repo.add_edge(from_station="A", to_station="C", distance_km=20)
        repo.set_connected(eid1, False)
        neighbors = repo.get_neighbors("A")
        assert [n["to_station"] for n in neighbors] == ["C"]


class TestGetEdge:
    def test_returns_edge_by_endpoints(self, repo):
        repo.add_edge(from_station="A", to_station="B", distance_km=10)
        edge = repo.get_edge("A", "B")
        assert edge is not None
        assert edge["from_station"] == "A"

    def test_returns_none_when_not_found(self, repo):
        assert repo.get_edge("A", "Z") is None


class TestDeleteEdge:
    def test_deletes_existing_edge(self, repo):
        eid = repo.add_edge(from_station="A", to_station="B")
        assert repo.delete_edge(eid) is True
        assert repo.get_edge_by_id(eid) is None

    def test_returns_false_for_missing_id(self, repo):
        assert repo.delete_edge(999) is False


class TestSetConnected:
    def test_updates_connection_state(self, repo):
        eid = repo.add_edge(from_station="A", to_station="B")
        assert repo.set_connected(eid, False) is True
        edge = repo.get_edge_by_id(eid)
        assert edge["is_connected"] == 0

    def test_returns_false_for_missing_id(self, repo):
        assert repo.set_connected(999, False) is False
