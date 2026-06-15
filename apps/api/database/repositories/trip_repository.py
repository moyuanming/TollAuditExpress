"""行程数据访问层"""

from typing import Optional, List, Dict, Tuple
from datetime import datetime

from apps.api.database.doris_connection import get_connection
from apps.api.core.logging_config import get_logger

logger = get_logger(__name__)


# 允许排序的列名（防 SQL 注入）
SORTABLE_COLUMNS = {
    "entry_time", "exit_time", "risk_score", "gantry_count",
}

# 车辆类型合法值
VEHICLE_TYPE_VALUES = {1, 2}

# 车牌匹配方式合法值
VEHICLE_ID_MATCH_MODES = {"exact", "prefix", "contains"}


def _build_where(filters: dict) -> Tuple[str, list]:
    """根据过滤条件构造 WHERE 子句与绑定参数。

    支持的过滤键：
      - status, audit_status: 稽核状态（精确，audit_status 优先）
      - entry_station, exit_station: 站名（LIKE %x%）
      - start_time, end_time: 入口时间范围（>=, <=）
      - entry_vehicle_id, exit_vehicle_id, vehicle_id: 车牌
      - vehicle_id_match: exact/prefix/contains（默认 exact）
      - entry_obu_id: 入口 OBU 精确
      - vehicle_type: 1/2（车型；同时匹配 entry/exit 之一）
      - vehicle_color: 颜色精确
      - min_risk_score, max_risk_score: 风险评分区间 [0, 1]
      - min_gantry_count, max_gantry_count: 门架数区间（>=, <=）
    """
    conditions: list = []
    params: list = []

    audit_status = filters.get("audit_status") or filters.get("status")
    if audit_status:
        conditions.append("audit_status = %s")
        params.append(audit_status)

    if filters.get("entry_station"):
        conditions.append("entry_station_name LIKE %s")
        params.append(f"%{filters['entry_station']}%")
    if filters.get("exit_station"):
        conditions.append("exit_station_name LIKE %s")
        params.append(f"%{filters['exit_station']}%")

    if filters.get("start_time"):
        conditions.append("entry_time >= %s")
        params.append(filters["start_time"])
    if filters.get("end_time"):
        conditions.append("entry_time <= %s")
        params.append(filters["end_time"])

    match_mode = filters.get("vehicle_id_match", "exact")
    if match_mode not in VEHICLE_ID_MATCH_MODES:
        match_mode = "exact"

    def _plate_clause(column: str, value: str) -> str:
        if match_mode == "exact":
            return f"{column} = %s"
        return f"{column} LIKE %s"

    def _plate_param(value: str) -> str:
        if match_mode == "exact":
            return value
        if match_mode == "prefix":
            return f"{value}%"
        return f"%{value}%"

    if filters.get("entry_vehicle_id"):
        conditions.append(_plate_clause("entry_vehicle_id", filters["entry_vehicle_id"]))
        params.append(_plate_param(filters["entry_vehicle_id"]))
    if filters.get("exit_vehicle_id"):
        conditions.append(_plate_clause("exit_vehicle_id", filters["exit_vehicle_id"]))
        params.append(_plate_param(filters["exit_vehicle_id"]))
    if filters.get("vehicle_id"):
        v = filters["vehicle_id"]
        if match_mode == "exact":
            conditions.append("(entry_vehicle_id = %s OR exit_vehicle_id = %s)")
            params.extend([v, v])
        else:
            conditions.append("(entry_vehicle_id LIKE %s OR exit_vehicle_id LIKE %s)")
            params.extend([_plate_param(v), _plate_param(v)])

    if filters.get("entry_obu_id"):
        conditions.append("entry_obu_id = %s")
        params.append(filters["entry_obu_id"])

    if filters.get("vehicle_type") is not None:
        vt = filters["vehicle_type"]
        if vt in VEHICLE_TYPE_VALUES:
            conditions.append("(entry_vehicle_type = %s OR exit_vehicle_type = %s)")
            params.extend([vt, vt])

    if filters.get("vehicle_color") is not None:
        conditions.append("(entry_vehicle_color = %s OR exit_vehicle_color = %s)")
        params.extend([filters["vehicle_color"], filters["vehicle_color"]])

    if filters.get("min_risk_score") is not None:
        conditions.append("risk_score >= %s")
        params.append(filters["min_risk_score"])
    if filters.get("max_risk_score") is not None:
        conditions.append("risk_score <= %s")
        params.append(filters["max_risk_score"])

    if filters.get("min_gantry_count") is not None:
        conditions.append("gantry_count >= %s")
        params.append(filters["min_gantry_count"])
    if filters.get("max_gantry_count") is not None:
        conditions.append("gantry_count <= %s")
        params.append(filters["max_gantry_count"])

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


def _resolve_order(filters: dict) -> str:
    """根据过滤条件构造 ORDER BY 子句（使用 allowlist 防止 SQL 注入）。"""
    order_by = filters.get("order_by", "entry_time")
    if order_by not in SORTABLE_COLUMNS:
        order_by = "entry_time"
    order = (filters.get("order") or "desc").lower()
    if order not in {"asc", "desc"}:
        order = "desc"
    return f" ORDER BY {order_by} {order.upper()}"


class TripRepository:
    """行程仓储"""

    def get_trips(self, status: Optional[str] = None, limit: int = 100, offset: int = 0,
                  entry_station: Optional[str] = None, exit_station: Optional[str] = None,
                  start_time: Optional[str] = None, end_time: Optional[str] = None,
                  **kwargs) -> List[Dict]:
        """获取行程列表。

        兼容旧签名（status/entry_station/...），同时支持通过 kwargs 传入新过滤参数。
        """
        filters = {
            "status": status,
            "entry_station": entry_station,
            "exit_station": exit_station,
            "start_time": start_time,
            "end_time": end_time,
        }
        filters.update(kwargs)
        where, params = _build_where(filters)
        order = _resolve_order(filters)

        sql = f"SELECT * FROM audit_trips{where}{order} LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_total_count(self, status: Optional[str] = None,
                        entry_station: Optional[str] = None, exit_station: Optional[str] = None,
                        start_time: Optional[str] = None, end_time: Optional[str] = None,
                        **kwargs) -> int:
        """获取行程总数（与 get_trips 的过滤参数保持一致）。"""
        filters = {
            "status": status,
            "entry_station": entry_station,
            "exit_station": exit_station,
            "start_time": start_time,
            "end_time": end_time,
        }
        filters.update(kwargs)
        where, params = _build_where(filters)

        sql = f"SELECT COUNT(*) as count FROM audit_trips{where}"
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchone()['count']

    def get_trip_detail(self, passid: str) -> Optional[Dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_trips WHERE passid = %s", (passid,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_trip_detail_with_results(self, passid: str) -> Tuple[Optional[Dict], List[Dict]]:
        """获取行程详情 + 该行程关联的所有稽核结果（JOIN 后字段齐全，可直接喂给 SuspectResponse）。

        返回 (trip_dict, [result_dict, ...])，若 trip 不存在则 trip_dict 为 None。
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_trips WHERE passid = %s", (passid,))
            trip_row = cursor.fetchone()
            if not trip_row:
                return None, []
            trip = dict(trip_row)
            cursor.execute("""
                SELECT ar.*, at.passid, at.entry_time, at.exit_time,
                       at.entry_station_name, at.exit_station_name,
                       at.entry_lane_id, at.exit_lane_id,
                       at.entry_vehicle_id, at.exit_vehicle_id,
                       at.entry_vehicle_type, at.exit_vehicle_type,
                       at.entry_vehicle_color, at.exit_vehicle_color,
                       at.entry_obu_id, at.exit_obu_id,
                       at.entry_media_type, at.exit_media_type,
                       at.entry_image_license, at.entry_image_trans,
                       at.exit_image_license, at.exit_image_trans,
                       at.gantry_count, at.gantry_records
                FROM audit_results ar
                JOIN audit_trips at ON ar.audit_trip_id = at.id
                WHERE ar.audit_trip_id = %s
                ORDER BY ar.id
            """, (trip['id'],))
            results = [dict(r) for r in cursor.fetchall()]
            return trip, results

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
            INSERT INTO audit_trips (
                passid, entry_time, entry_station_name, entry_lane_id,
                entry_vehicle_id, entry_vehicle_type, entry_vehicle_color,
                entry_obu_id, entry_media_type, entry_image_license, entry_image_trans,
                exit_time, exit_station_name, exit_lane_id,
                exit_vehicle_id, exit_vehicle_type, exit_vehicle_color,
                exit_obu_id, exit_media_type, exit_image_license, exit_image_trans,
                gantry_count, gantry_records, audit_status, risk_score,
                created_at, entry_visual_type, exit_visual_type, fingerprint_sim,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                trip_data.get('gantry_records'),
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
                cursor.execute("SELECT id FROM audit_trips WHERE passid = %s", (trip_data.get('passid'),))
                row = cursor.fetchone()
                trip_id = row['id'] if row else None
            conn.commit()
            return trip_id

    def save_trip_with_detection_results(self, trip_id: int, passid: str, results: List[Dict]):
        """在单个事务中保存稽核检测结果、更新行程视觉类型和状态"""
        with get_connection() as conn:
            cursor = conn.cursor()

            # 验证 trip_id 和 passid 的一致性，防止数据不一致
            cursor.execute("SELECT id, passid FROM audit_trips WHERE passid = %s", (passid,))
            existing = cursor.fetchone()
            if existing and existing['id'] != trip_id:
                # 如果 trip_id 不匹配，以 passid 对应的实际 id 为准
                trip_id = existing['id']
            elif not existing:
                logger.warning("No audit_trip found for passid: %s, trip_id: %s", passid, trip_id)

            # 1. INSERT audit_results
            for r in results:
                cursor.execute("""
                    INSERT INTO audit_results (
                        audit_trip_id, fraud_type,
                        entry_vehicle_type, entry_visual_type, entry_color,
                        exit_vehicle_type, exit_visual_type, exit_color,
                        is_suspicious, risk_score, details, process_status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    trip_id,  # 使用验证后的 trip_id，保证数据一致性
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
                if r['fraud_type'] == 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A':
                    entry_vis = r.get('entry_visual_type')
                elif r['fraud_type'] == 'ENTRY_EXIT_MISMATCH':
                    entry_vis = r.get('entry_visual_type') or entry_vis
                    exit_vis = r.get('exit_visual_type')
                    fp_sim = r.get('risk_score')

            updates = []
            values = []
            if entry_vis is not None:
                updates.append("entry_visual_type = %s")
                values.append(entry_vis)
            if exit_vis is not None:
                updates.append("exit_visual_type = %s")
                values.append(exit_vis)
            if fp_sim is not None:
                updates.append("fingerprint_sim = %s")
                values.append(fp_sim)

            if updates:
                values.append(passid)
                cursor.execute(
                    f"UPDATE audit_trips SET {', '.join(updates)}, updated_at = NOW() WHERE passid = %s",
                    values
                )

            # 3. Update trip status
            if any(r['is_suspicious'] for r in results):
                max_risk = max(r['risk_score'] for r in results)
                cursor.execute(
                    "UPDATE audit_trips SET audit_status = %s, risk_score = %s, updated_at = NOW() WHERE passid = %s",
                    ('SUSPECTED', max_risk, passid)
                )

            conn.commit()

    def get_trips_without_visual(self, limit: int = 500) -> List[Dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM audit_trips WHERE entry_visual_type IS NULL AND entry_image_trans IS NOT NULL AND entry_image_trans != '' AND entry_image_trans NOT LIKE '%None%' LIMIT %s",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def find_truck_obu_candidates(
        self,
        vehicle_types: List[int],
        media_type: int,
        plate_prefix_exclude: str,
        start_time: str,
        end_time: str,
        limit: int = 500,
        offset: int = 0,
    ) -> List[Dict]:
        """查询货车+OBU+非新A 的候选 trip（带分页）。

        任一侧（入口/出口）满足以下三条即视为候选:
          1. vehicle_type ∈ vehicle_types（如 14/15/16）
          2. media_type == 1（OBU 介质）
          3. vehicle_id NOT LIKE '新A%'（非新A 开头）

        注：不走 _build_where,因为现有 _build_where 的 vehicle_type 过滤只支持 {1, 2},
        不支持 IN (14, 15, 16)。这里直接拼一个专用查询。
        """
        placeholders = ",".join(["%s"] * len(vehicle_types))
        sql = f"""
            SELECT id, passid, entry_time, exit_time,
                   entry_vehicle_id, exit_vehicle_id,
                   entry_vehicle_type, exit_vehicle_type,
                   entry_media_type, exit_media_type,
                   entry_obu_id, exit_obu_id
            FROM audit_trips
            WHERE entry_time >= %s AND entry_time < %s
              AND (
                   (entry_vehicle_type IN ({placeholders})
                    AND entry_media_type = %s
                    AND entry_vehicle_id IS NOT NULL
                    AND entry_vehicle_id NOT LIKE %s)
                OR (exit_vehicle_type IN ({placeholders})
                    AND exit_media_type = %s
                    AND exit_vehicle_id IS NOT NULL
                    AND exit_vehicle_id NOT LIKE %s)
              )
            ORDER BY entry_time ASC
            LIMIT %s OFFSET %s
        """
        params = [
            start_time, end_time,
            *vehicle_types, media_type, f"{plate_prefix_exclude}%",
            *vehicle_types, media_type, f"{plate_prefix_exclude}%",
            limit, offset,
        ]
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return [dict(r) for r in cursor.fetchall()]

    def find_passenger_obu_candidates(
        self,
        start_time: str,
        end_time: str,
        plate_prefix_exclude: str = '新A',
        declared_vehicle_type: int = 1,
        limit: int = 500,
        offset: int = 0,
    ) -> List[Dict]:
        """查询客车+非新A+任一侧有 image_trans 的候选 trip（带分页）。

        命中后还会进一步走 vehicle-ai-service 复核 + LLM 验证(在 detector 层)。
        这里只做 SQL 预筛,省一次模型调用。

        注：专用查询,不走通用 _build_where,后者 vehicle_type 过滤只支持 {1, 2},
        不支持形参化 declared_vehicle_type。
        """
        sql = f"""
            SELECT id, passid, entry_time, exit_time,
                   entry_vehicle_id, exit_vehicle_id,
                   entry_vehicle_type, exit_vehicle_type,
                   entry_media_type, exit_media_type,
                   entry_obu_id, exit_obu_id,
                   entry_image_trans, exit_image_trans,
                   entry_visual_type, exit_visual_type
            FROM audit_trips
            WHERE entry_time >= %s AND entry_time < %s
              AND (
                   (entry_vehicle_type = %s
                    AND entry_vehicle_id IS NOT NULL
                    AND entry_vehicle_id NOT LIKE %s
                    AND entry_image_trans IS NOT NULL
                    AND entry_image_trans != ''
                    AND entry_image_trans NOT LIKE '%None%')
                OR (exit_vehicle_type = %s
                    AND exit_vehicle_id IS NOT NULL
                    AND exit_vehicle_id NOT LIKE %s
                    AND exit_image_trans IS NOT NULL
                    AND exit_image_trans != ''
                    AND exit_image_trans NOT LIKE '%None%')
              )
            ORDER BY entry_time ASC
            LIMIT %s OFFSET %s
        """
        prefix = f"{plate_prefix_exclude}%"
        params = [
            start_time, end_time,
            declared_vehicle_type, prefix,
            declared_vehicle_type, prefix,
            limit, offset,
        ]
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return [dict(r) for r in cursor.fetchall()]

    def update_status(self, passid: str, status: str, risk_score: float = 0):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE audit_trips SET audit_status = %s, risk_score = %s, updated_at = NOW() WHERE passid = %s",
                (status, risk_score, passid)
            )
            conn.commit()

    def update_visual_types(self, passid: str, entry_visual_type: str = None, exit_visual_type: str = None, fingerprint_sim: float = None):
        with get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            values = []
            if entry_visual_type is not None:
                updates.append("entry_visual_type = %s")
                values.append(entry_visual_type)
            if exit_visual_type is not None:
                updates.append("exit_visual_type = %s")
                values.append(exit_visual_type)
            if fingerprint_sim is not None:
                updates.append("fingerprint_sim = %s")
                values.append(fingerprint_sim)

            if updates:
                values.append(passid)
                cursor.execute(
                    f"UPDATE audit_trips SET {', '.join(updates)}, updated_at = NOW() WHERE passid = %s",
                    values
                )
                conn.commit()
