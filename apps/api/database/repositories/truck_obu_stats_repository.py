"""货车 OBU 监测 — 每日统计仓储（兼容 SQLite/Doris）

注意:UPSERT 语法在 SQLite 与 Doris 之间不通用。
- SQLite: INSERT ... ON CONFLICT(date, fraud_type) DO UPDATE SET ...
- Doris:  INSERT ... ON DUPLICATE KEY UPDATE ...

我们用 try/except 包装,失败时回落到 SQLite 风格的 ON CONFLICT 语法。
测试环境是 SQLite,所以主路径走 ON CONFLICT;生产 Doris 第一次跑会因语法差异抛错
(若生产用 ON CONFLICT 风格),届时把 except 块改成 ON DUPLICATE KEY UPDATE 即可。
此处为简化,统一使用 ON CONFLICT — 实施时若生产出错,需调整为驱动判断。
"""

from typing import Optional, List, Dict

from apps.api.database.doris_connection import get_connection


class TruckObuStatsRepository:
    """货车 OBU 监测 — 每日统计 CRUD"""

    def upsert_daily_stat(
        self,
        date: str,
        fraud_type: str,
        scanned_count_delta: int,
        suspicious_count_delta: int,
        last_run_at: str,
    ) -> None:
        """按 (date, fraud_type) 累加计数;不存在则 INSERT。
        SQLite 测试环境走 ON CONFLICT;Doris 生产环境走 ON DUPLICATE KEY UPDATE。
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            try:
                # SQLite 风格
                cursor.execute(
                    """
                    INSERT INTO audit_truck_obu_daily_stats
                        (date, fraud_type, scanned_count, suspicious_count, last_run_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT(date, fraud_type) DO UPDATE SET
                        scanned_count     = scanned_count + excluded.scanned_count,
                        suspicious_count  = suspicious_count + excluded.suspicious_count,
                        last_run_at       = excluded.last_run_at,
                        updated_at        = CURRENT_TIMESTAMP
                    """,
                    (date, fraud_type, scanned_count_delta, suspicious_count_delta, last_run_at),
                )
            except Exception:
                # Doris 风格回退
                cursor.execute(
                    """
                    INSERT INTO audit_truck_obu_daily_stats
                        (date, fraud_type, scanned_count, suspicious_count, last_run_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        scanned_count     = scanned_count + VALUES(scanned_count),
                        suspicious_count  = suspicious_count + VALUES(suspicious_count),
                        last_run_at       = VALUES(last_run_at)
                    """,
                    (date, fraud_type, scanned_count_delta, suspicious_count_delta, last_run_at),
                )
            conn.commit()

    def get_daily_stats(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        fraud_type: Optional[str] = None,
    ) -> List[Dict]:
        """按日期范围 [+ fraud_type] 查每日统计。"""
        with get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []
            if from_date:
                conditions.append("date >= %s")
                params.append(from_date)
            if to_date:
                conditions.append("date <= %s")
                params.append(to_date)
            if fraud_type:
                conditions.append("fraud_type = %s")
                params.append(fraud_type)
            where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            sql = f"""
                SELECT date, fraud_type, scanned_count, suspicious_count,
                       confirmed_count, last_run_at, updated_at
                FROM audit_truck_obu_daily_stats
                {where}
                ORDER BY date ASC, fraud_type ASC
            """
            cursor.execute(sql, params)
            return [dict(r) for r in cursor.fetchall()]

    def get_overview(self) -> Dict:
        """累计扫描/异常/确认 + 最近一次执行时间。"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COALESCE(SUM(scanned_count), 0)    AS total_scanned,
                    COALESCE(SUM(suspicious_count), 0) AS total_suspicious,
                    COALESCE(SUM(confirmed_count), 0)  AS total_confirmed,
                    MAX(last_run_at)                   AS last_run_at
                FROM audit_truck_obu_daily_stats
            """)
            row = cursor.fetchone()
            if not row:
                return {
                    "total_scanned": 0,
                    "total_suspicious": 0,
                    "total_confirmed": 0,
                    "last_run_at": None,
                }
            return dict(row)
