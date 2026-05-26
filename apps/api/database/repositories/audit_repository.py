"""稽核结果数据访问层"""

from typing import Optional, List, Dict
from datetime import datetime

from apps.api.database.connection import get_connection


class AuditRepository:
    """稽核结果仓储"""

    def get_suspects(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT ar.*, at.passid, at.entry_time, at.exit_time,
                   at.entry_vehicle_id, at.exit_vehicle_id,
                   at.entry_vehicle_type, at.exit_vehicle_type
            FROM audit_results ar
            JOIN audit_trips at ON ar.audit_trip_id = at.id
            WHERE ar.is_suspicious = 1
            ORDER BY ar.created_at DESC LIMIT ? OFFSET ?
        """, (limit, offset))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_suspects_count(self) -> int:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM audit_results WHERE is_suspicious = 1")
        count = cursor.fetchone()['count']
        conn.close()
        return count

    def get_suspect_detail(self, suspect_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT ar.*, at.passid, at.entry_time, at.exit_time,
                   at.entry_station_name, at.exit_station_name,
                   at.entry_lane_id, at.exit_lane_id,
                   at.entry_vehicle_id, at.exit_vehicle_id,
                   at.entry_vehicle_type, at.exit_vehicle_type,
                   at.entry_vehicle_color, at.exit_vehicle_color,
                   at.entry_obu_id, at.exit_obu_id,
                   at.entry_media_type, at.exit_media_type,
                   at.entry_image_license, at.exit_image_license,
                   at.entry_image_trans, at.exit_image_trans
            FROM audit_results ar
            JOIN audit_trips at ON ar.audit_trip_id = at.id
            WHERE ar.id = ?
        """, (suspect_id,))

        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def save_result(self, result_data: Dict) -> int:
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO audit_results (
            audit_trip_id, fraud_type,
            entry_vehicle_type, entry_visual_type, entry_color,
            exit_vehicle_type, exit_visual_type, exit_color,
            is_suspicious, risk_score, details, process_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        values = (
            result_data.get('audit_trip_id'),
            result_data.get('fraud_type'),
            result_data.get('entry_vehicle_type'),
            result_data.get('entry_visual_type'),
            result_data.get('entry_color'),
            result_data.get('exit_vehicle_type'),
            result_data.get('exit_visual_type'),
            result_data.get('exit_color'),
            result_data.get('is_suspicious', 0),
            result_data.get('risk_score', 0),
            result_data.get('details'),
            result_data.get('process_status', 'UNPROCESSED')
        )

        cursor.execute(sql, values)
        result_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return result_id

    def update_process_status(self, result_id: int, action: str, operator: str = None, comments: str = None):
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE audit_results
            SET process_status = ?
            WHERE id = ?
        """, (action, result_id))

        cursor.execute("""
            INSERT INTO audit_actions (result_id, action, operator, comments)
            VALUES (?, ?, ?, ?)
        """, (result_id, action, operator, comments))

        conn.commit()
        conn.close()
