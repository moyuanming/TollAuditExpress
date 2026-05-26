"""行程数据访问层"""

from typing import Optional, List, Dict
from datetime import datetime

from apps.api.database.connection import get_connection


class TripRepository:
    """行程仓储"""

    def get_trips(self, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()

        if status:
            cursor.execute(
                "SELECT * FROM audit_trips WHERE audit_status = ? ORDER BY entry_time DESC LIMIT ? OFFSET ?",
                (status, limit, offset)
            )
        else:
            cursor.execute(
                "SELECT * FROM audit_trips ORDER BY entry_time DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_total_count(self, status: Optional[str] = None) -> int:
        conn = get_connection()
        cursor = conn.cursor()

        if status:
            cursor.execute("SELECT COUNT(*) as count FROM audit_trips WHERE audit_status = ?", (status,))
        else:
            cursor.execute("SELECT COUNT(*) as count FROM audit_trips")

        count = cursor.fetchone()['count']
        conn.close()
        return count

    def get_trip_detail(self, passid: str) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM audit_trips WHERE passid = ?", (passid,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_stats(self) -> Dict:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM audit_trips")
        total = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as count FROM audit_trips WHERE audit_status = 'VERIFIED'")
        verified = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM audit_results WHERE is_suspicious = 1 AND process_status = 'UNPROCESSED'")
        suspects = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM audit_results WHERE process_status = 'CONFIRMED'")
        confirmed = cursor.fetchone()['count']

        conn.close()
        return {
            'total_trips': total,
            'verified_trips': verified,
            'suspected_trips': suspects,
            'confirmed_fraud': confirmed
        }

    def save_trip(self, trip_data: Dict) -> int:
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        INSERT OR REPLACE INTO audit_trips (
            passid, entry_time, entry_station_name, entry_lane_id,
            entry_vehicle_id, entry_vehicle_type, entry_vehicle_color,
            entry_obu_id, entry_media_type, entry_image_license, entry_image_trans,
            exit_time, exit_station_name, exit_lane_id,
            exit_vehicle_id, exit_vehicle_type, exit_vehicle_color,
            exit_obu_id, exit_media_type, exit_image_license, exit_image_trans,
            gantry_count, audit_status, risk_score, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            now
        )

        cursor.execute(sql, values)
        trip_id = cursor.lastrowid
        if not trip_id:
            row = cursor.execute("SELECT id FROM audit_trips WHERE passid = ?", (trip_data.get('passid'),)).fetchone()
            trip_id = row['id'] if row else None
        conn.commit()
        conn.close()
        return trip_id

    def update_status(self, passid: str, status: str, risk_score: float = 0):
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE audit_trips SET audit_status = ?, risk_score = ?, updated_at = datetime('now', 'localtime') WHERE passid = ?",
            (status, risk_score, passid)
        )
        conn.commit()
        conn.close()
