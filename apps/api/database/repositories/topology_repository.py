"""gateway_topology 数据访问层 — 阶段 1 MVP

为 gateway_detector 提供：手工录入的相邻站点边集（from → to + 距离）。
阶段 2 由 topology_miner 从历史流水自动学习。
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from apps.api.database.doris_connection import get_connection


_BEIJING_TZ = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(_BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


class TopologyRepository:
    """gateway_topology 表 CRUD"""

    def list_edges(self) -> List[Dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM gateway_topology ORDER BY from_station, to_station"
            )
            rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def get_edge_by_id(self, edge_id: int) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM gateway_topology WHERE id = %s", (edge_id,))
            row = cursor.fetchone()
        return dict(row) if row else None

    def get_edge(self, from_station: str, to_station: str) -> Optional[Dict[str, Any]]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM gateway_topology WHERE from_station = %s AND to_station = %s",
                (from_station, to_station),
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def add_edge(
        self,
        from_station: str,
        to_station: str,
        distance_km: Optional[float] = None,
        notes: Optional[str] = None,
        is_connected: bool = True,
    ) -> int:
        if not from_station or not to_station:
            raise ValueError("from_station and to_station are required")

        with get_connection() as conn:
            cursor = conn.cursor()
            now = _now()
            cursor.execute(
                """
                INSERT INTO gateway_topology
                    (from_station, to_station, distance_km, is_connected, notes,
                     created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    from_station,
                    to_station,
                    distance_km,
                    1 if is_connected else 0,
                    notes,
                    now,
                    now,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def delete_edge(self, edge_id: int) -> bool:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM gateway_topology WHERE id = %s", (edge_id,))
            conn.commit()
            return cursor.rowcount > 0

    def set_connected(self, edge_id: int, is_connected: bool) -> bool:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE gateway_topology SET is_connected = %s, updated_at = %s WHERE id = %s",
                (1 if is_connected else 0, _now(), edge_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_neighbors(self, station: str) -> List[Dict[str, Any]]:
        """返回该站点的所有相邻下游站点（is_connected=1 的边）。"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM gateway_topology
                WHERE from_station = %s AND is_connected = 1
                ORDER BY to_station
                """,
                (station,),
            )
            rows = cursor.fetchall()
        return [dict(r) for r in rows]
