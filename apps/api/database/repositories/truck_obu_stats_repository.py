"""货车 OBU 监测 — 每日统计仓储（兼容 SQLite/Doris）

注意:Doris 2.1.9-rc02 不支持 MySQL/PG 风格的 UPSERT 子句
（ON DUPLICATE KEY UPDATE / ON CONFLICT / REPLACE INTO 全部报语法错）。
改用 SELECT + INSERT/UPDATE 两步走,SQLite 与 Doris 都能跑。
"""


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

        采用 SELECT + INSERT/UPDATE 两步走 — Doris 2.1.9-rc02 不识别
        ON DUPLICATE KEY UPDATE / ON CONFLICT,SQLite 也保持同语义。
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT scanned_count, suspicious_count
                FROM audit_truck_obu_daily_stats
                WHERE date = %s AND fraud_type = %s
                """,
                (date, fraud_type),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """
                    INSERT INTO audit_truck_obu_daily_stats
                        (date, fraud_type, scanned_count, suspicious_count, last_run_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (date, fraud_type, scanned_count_delta,
                     suspicious_count_delta, last_run_at),
                )
            else:
                cursor.execute(
                    """
                    UPDATE audit_truck_obu_daily_stats
                    SET scanned_count    = scanned_count + %s,
                        suspicious_count = suspicious_count + %s,
                        last_run_at      = %s
                    WHERE date = %s AND fraud_type = %s
                    """,
                    (scanned_count_delta, suspicious_count_delta,
                     last_run_at, date, fraud_type),
                )
            conn.commit()

    def get_daily_stats(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        fraud_type: str | None = None,
    ) -> list[dict]:
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

    def get_overview(self) -> dict:
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
