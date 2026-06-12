"""稽核结果数据访问层"""

from typing import Optional, List, Dict
from datetime import datetime

from apps.api.database.doris_connection import get_connection


class AuditRepository:
    """稽核结果仓储"""

    def get_suspects(self, fraud_type: str = None, fraud_types: Optional[List[str]] = None,
                     process_status: str = None,
                     llm_result: str = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            conditions = ["ar.is_suspicious = 1"]
            params = []
            if fraud_types:
                placeholders = ",".join(["%s"] * len(fraud_types))
                conditions.append(f"ar.fraud_type IN ({placeholders})")
                params.extend(fraud_types)
            elif fraud_type:
                conditions.append("ar.fraud_type = %s")
                params.append(fraud_type)
            if process_status:
                conditions.append("ar.process_status = %s")
                params.append(process_status)
            if llm_result == 'same':
                conditions.append("ar.llm_is_same_vehicle = 1")
            elif llm_result == 'different':
                conditions.append("ar.llm_is_same_vehicle = 0")
            elif llm_result == 'pending':
                conditions.append("ar.llm_checked_at IS NULL")
            where = " AND ".join(conditions)
            cursor.execute(f"""
                SELECT ar.*, at.passid,
                       at.entry_time, at.exit_time,
                       at.entry_station_name, at.exit_station_name,
                       at.entry_vehicle_id, at.exit_vehicle_id,
                       at.entry_vehicle_type, at.exit_vehicle_type
                FROM audit_results ar
                JOIN audit_trips at ON ar.audit_trip_id = at.id
                WHERE {where}
                ORDER BY ar.created_at DESC LIMIT %s OFFSET %s
            """, params + [limit, offset])
            return [dict(row) for row in cursor.fetchall()]

    def get_suspects_count(self, fraud_type: str = None, fraud_types: Optional[List[str]] = None,
                           process_status: str = None,
                           llm_result: str = None) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            conditions = ["is_suspicious = 1"]
            params = []
            if fraud_types:
                placeholders = ",".join(["%s"] * len(fraud_types))
                conditions.append(f"fraud_type IN ({placeholders})")
                params.extend(fraud_types)
            elif fraud_type:
                conditions.append("fraud_type = %s")
                params.append(fraud_type)
            if process_status:
                conditions.append("process_status = %s")
                params.append(process_status)
            if llm_result == 'same':
                conditions.append("llm_is_same_vehicle = 1")
            elif llm_result == 'different':
                conditions.append("llm_is_same_vehicle = 0")
            elif llm_result == 'pending':
                conditions.append("llm_checked_at IS NULL")
            where = " AND ".join(conditions)
            cursor.execute(f"SELECT COUNT(*) as count FROM audit_results WHERE {where}", params)
            return cursor.fetchone()['count']

    def get_pending_llm_suspects(self, limit: int = 50) -> List[Dict]:
        """取尚未跑 LLM 判定且出入口 visual_type 齐全的可疑记录。"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ar.id, ar.audit_trip_id, ar.fraud_type, at.passid
                FROM audit_results ar
                JOIN audit_trips at ON ar.audit_trip_id = at.id
                WHERE ar.is_suspicious = 1
                  AND ar.llm_checked_at IS NULL
                  AND ar.entry_visual_type IS NOT NULL
                  AND ar.exit_visual_type IS NOT NULL
                ORDER BY ar.created_at DESC
                LIMIT %s
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def update_llm_verdict(self, suspect_id: int, *, is_same: bool,
                           confidence: float, reason: str, model: str,
                           checked_at: str) -> None:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE audit_results
                SET llm_is_same_vehicle = %s,
                    llm_confidence = %s,
                    llm_reason = %s,
                    llm_model = %s,
                    llm_checked_at = %s
                WHERE id = %s
            """, (1 if is_same else 0, confidence, reason, model, checked_at, suspect_id))
            conn.commit()

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
                       at.entry_image_trans, at.exit_image_trans,
                       at.gantry_count, at.gantry_records
                FROM audit_results ar
                JOIN audit_trips at ON ar.audit_trip_id = at.id
                WHERE ar.id = %s
            """, (suspect_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_suspect_by_id(self, suspect_id: int) -> Optional[Dict]:
        """仅取 audit_results 行（不含 trip join）—— 手动 LLM 路由用，验明存在性。"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_results WHERE id = %s", (suspect_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_visual_features_by_passid(self, passid: str) -> Optional[Dict]:
        """按 passid 取最近一条可疑稽核结果的视觉信号（颜色/车型/fingerprint_sim）。

        用于把侧车非 LLM 信号（HSV 颜色、ResNet18 车型、ResNet50 2048-d 余弦相似度）
        透传给 vehicle-ai-service 的分档裁决器，避免 LLM 调用。
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ar.entry_color, ar.exit_color,
                       ar.entry_visual_type, ar.exit_visual_type,
                       at.fingerprint_sim
                FROM audit_results ar
                JOIN audit_trips at ON ar.audit_trip_id = at.id
                WHERE at.passid = %s
                ORDER BY ar.created_at DESC
                LIMIT 1
            """, (passid,))
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
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                SET process_status = %s
                WHERE id = %s
            """, (action, result_id))
            cursor.execute("""
                INSERT INTO audit_actions (result_id, action, operator, comments)
                VALUES (%s, %s, %s, %s)
            """, (result_id, action, operator, comments))
            conn.commit()
