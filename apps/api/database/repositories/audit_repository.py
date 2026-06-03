"""稽核结果数据访问层"""

from typing import Optional, List, Dict
from datetime import datetime

from apps.api.database.connection import get_connection


class AuditRepository:
    """稽核结果仓储"""

    def get_suspects(self, fraud_type: str = None, process_status: str = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            conditions = ["ar.is_suspicious = 1"]
            params = []
            if fraud_type:
                conditions.append("ar.fraud_type = ?")
                params.append(fraud_type)
            if process_status:
                conditions.append("ar.process_status = ?")
                params.append(process_status)
            where = " AND ".join(conditions)
            cursor.execute(f"""
                SELECT ar.*, at.passid, at.entry_time, at.exit_time,
                       at.entry_vehicle_id, at.exit_vehicle_id,
                       at.entry_vehicle_type, at.exit_vehicle_type
                FROM audit_results ar
                JOIN audit_trips at ON ar.audit_trip_id = at.id
                WHERE {where}
                ORDER BY ar.created_at DESC LIMIT ? OFFSET ?
            """, params + [limit, offset])
            return [dict(row) for row in cursor.fetchall()]

    def get_suspects_count(self, fraud_type: str = None, process_status: str = None) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            conditions = ["is_suspicious = 1"]
            params = []
            if fraud_type:
                conditions.append("fraud_type = ?")
                params.append(fraud_type)
            if process_status:
                conditions.append("process_status = ?")
                params.append(process_status)
            where = " AND ".join(conditions)
            cursor.execute(f"SELECT COUNT(*) as count FROM audit_results WHERE {where}", params)
            return cursor.fetchone()['count']

    def get_suspect_detail(self, suspect_id: int) -> Optional[Dict]:
        with get_connection() as conn:
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
            return dict(row) if row else None

    def save_result(self, result_data: Dict) -> int:
        with get_connection() as conn:
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
            return result_id

    def update_process_status(self, result_id: int, action: str, operator: str = None, comments: str = None):
        with get_connection() as conn:
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
