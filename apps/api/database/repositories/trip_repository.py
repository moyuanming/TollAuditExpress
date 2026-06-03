"""行程数据访问层"""

from typing import Optional, List, Dict
from datetime import datetime

from apps.api.database.connection import get_connection


class TripRepository:
    """行程仓储"""

    def get_trips(self, status: Optional[str] = None, limit: int = 100, offset: int = 0,
                  entry_station: Optional[str] = None, exit_station: Optional[str] = None,
                  start_time: Optional[str] = None, end_time: Optional[str] = None) -> List[Dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []

            if status:
                conditions.append("audit_status = ?")
                params.append(status)
            if entry_station:
                conditions.append("entry_station_name LIKE ?")
                params.append(f"%{entry_station}%")
            if exit_station:
                conditions.append("exit_station_name LIKE ?")
                params.append(f"%{exit_station}%")
            if start_time:
                conditions.append("entry_time >= ?")
                params.append(start_time)
            if end_time:
                conditions.append("entry_time <= ?")
                params.append(end_time)

            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            sql = f"SELECT * FROM audit_trips{where} ORDER BY entry_time DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_total_count(self, status: Optional[str] = None,
                        entry_station: Optional[str] = None, exit_station: Optional[str] = None,
                        start_time: Optional[str] = None, end_time: Optional[str] = None) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []

            if status:
                conditions.append("audit_status = ?")
                params.append(status)
            if entry_station:
                conditions.append("entry_station_name LIKE ?")
                params.append(f"%{entry_station}%")
            if exit_station:
                conditions.append("exit_station_name LIKE ?")
                params.append(f"%{exit_station}%")
            if start_time:
                conditions.append("entry_time >= ?")
                params.append(start_time)
            if end_time:
                conditions.append("entry_time <= ?")
                params.append(end_time)

            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            cursor.execute(f"SELECT COUNT(*) as count FROM audit_trips{where}", params)
            return cursor.fetchone()['count']

    def get_trip_detail(self, passid: str) -> Optional[Dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_trips WHERE passid = ?", (passid,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_stats(self) -> Dict:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total_trips,
                    COALESCE(SUM(CASE WHEN audit_status = 'VERIFIED' THEN 1 ELSE 0 END), 0) as verified_trips,
                    (SELECT COUNT(*) FROM audit_results WHERE is_suspicious = 1 AND process_status = 'UNPROCESSED') as suspected_trips,
                    (SELECT COUNT(*) FROM audit_results WHERE process_status = 'CONFIRMED') as confirmed_fraud
                FROM audit_trips
            """)
            return dict(cursor.fetchone())

    def save_trip(self, trip_data: Dict) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()

            sql = """
            INSERT OR REPLACE INTO audit_trips (
                passid, entry_time, entry_station_name, entry_lane_id,
                entry_vehicle_id, entry_vehicle_type, entry_vehicle_color,
                entry_obu_id, entry_media_type, entry_image_license, entry_image_trans,
                exit_time, exit_station_name, exit_lane_id,
                exit_vehicle_id, exit_vehicle_type, exit_vehicle_color,
                exit_obu_id, exit_media_type, exit_image_license, exit_image_trans,
                gantry_count, audit_status, risk_score,
                created_at, entry_visual_type, exit_visual_type, fingerprint_sim,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            values = (
                trip_data.get('passid'),
                trip_data.get('entry_time'), trip_data.get('entry_station_name'), trip_data.get('entry_lane_id'),
                trip_data.get('entry_vehicle_id'), trip_data.get('entry_vehicle_type'), trip_data.get('entry_vehicle_color'),
                trip_data.get('entry_obu_id'), trip_data.get('entry_media_type'),
                trip_data.get('entry_image_license'), trip_data.get('entry_image_trans'),
                trip_data.get('exit_time'), trip_data.get('exit_station_name'), trip_data.get('exit_lane_id'),
                trip_data.get('exit_vehicle_id'), trip_data.get('exit_vehicle_type'), trip_data.get('exit_vehicle_color'),
                trip_data.get('exit_obu_id'), trip_data.get('exit_media_type'),
                trip_data.get('exit_image_license'), trip_data.get('exit_image_trans'),
                trip_data.get('gantry_count', 0),
                trip_data.get('audit_status', 'PENDING'),
                trip_data.get('risk_score', 0),
                now,
                trip_data.get('entry_visual_type'),
                trip_data.get('exit_visual_type'),
                trip_data.get('fingerprint_sim'),
                now
            )

            cursor.execute(sql, values)
            trip_id = cursor.lastrowid
            if not trip_id:
                row = cursor.execute("SELECT id FROM audit_trips WHERE passid = ?", (trip_data.get('passid'),)).fetchone()
                trip_id = row['id'] if row else None
            conn.commit()
            return trip_id

    def save_trip_with_detection_results(self, trip_id: int, passid: str, results: List[Dict]):
        """在单个事务中保存稽核检测结果、更新行程视觉类型和状态"""
        with get_connection() as conn:
            cursor = conn.cursor()

            # 1. INSERT audit_results
            for r in results:
                cursor.execute("""
                    INSERT INTO audit_results (
                        audit_trip_id, fraud_type,
                        entry_vehicle_type, entry_visual_type, entry_color,
                        exit_vehicle_type, exit_visual_type, exit_color,
                        is_suspicious, risk_score, details, process_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r.get('audit_trip_id'),
                    r.get('fraud_type'),
                    r.get('entry_vehicle_type'),
                    r.get('entry_visual_type'),
                    r.get('entry_color'),
                    r.get('exit_vehicle_type'),
                    r.get('exit_visual_type'),
                    r.get('exit_color'),
                    r.get('is_suspicious', 0),
                    r.get('risk_score', 0),
                    r.get('details'),
                    r.get('process_status', 'UNPROCESSED')
                ))

            # 2. Collect and UPDATE visual types
            entry_vis = None
            exit_vis = None
            fp_sim = None
            for r in results:
                if r['fraud_type'] == 'TRUCK_USES_PASSENGER_OBU':
                    entry_vis = r.get('entry_visual_type')
                elif r['fraud_type'] == 'ENTRY_EXIT_MISMATCH':
                    entry_vis = r.get('entry_visual_type') or entry_vis
                    exit_vis = r.get('exit_visual_type')
                    fp_sim = r.get('risk_score')

            updates = []
            values = []
            if entry_vis is not None:
                updates.append("entry_visual_type = ?")
                values.append(entry_vis)
            if exit_vis is not None:
                updates.append("exit_visual_type = ?")
                values.append(exit_vis)
            if fp_sim is not None:
                updates.append("fingerprint_sim = ?")
                values.append(fp_sim)

            if updates:
                values.append(passid)
                cursor.execute(
                    f"UPDATE audit_trips SET {', '.join(updates)}, updated_at = datetime('now', 'localtime') WHERE passid = ?",
                    values
                )

            # 3. Update trip status
            if any(r['is_suspicious'] for r in results):
                max_risk = max(r['risk_score'] for r in results)
                cursor.execute(
                    "UPDATE audit_trips SET audit_status = ?, risk_score = ?, updated_at = datetime('now', 'localtime') WHERE passid = ?",
                    ('SUSPECTED', max_risk, passid)
                )

            conn.commit()

    def get_trips_without_visual(self, limit: int = 500) -> List[Dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM audit_trips WHERE entry_visual_type IS NULL AND entry_image_trans IS NOT NULL AND entry_image_trans != '' AND entry_image_trans NOT LIKE '%None%' LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_status(self, passid: str, status: str, risk_score: float = 0):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE audit_trips SET audit_status = ?, risk_score = ?, updated_at = datetime('now', 'localtime') WHERE passid = ?",
                (status, risk_score, passid)
            )
            conn.commit()

    def update_visual_types(self, passid: str, entry_visual_type: str = None, exit_visual_type: str = None, fingerprint_sim: float = None):
        with get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            values = []
            if entry_visual_type is not None:
                updates.append("entry_visual_type = ?")
                values.append(entry_visual_type)
            if exit_visual_type is not None:
                updates.append("exit_visual_type = ?")
                values.append(exit_visual_type)
            if fingerprint_sim is not None:
                updates.append("fingerprint_sim = ?")
                values.append(fingerprint_sim)

            if updates:
                values.append(passid)
                cursor.execute(
                    f"UPDATE audit_trips SET {', '.join(updates)}, updated_at = datetime('now', 'localtime') WHERE passid = ?",
                    values
                )
                conn.commit()
