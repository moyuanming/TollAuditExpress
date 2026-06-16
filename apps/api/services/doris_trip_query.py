"""
车辆查询服务 - 直接从 Doris 原始表 dwd_tolldata.t_waste_en_ex_gantry 查询
并按 PASSID 聚合为行程级结果（与 audit_trips 的检测后快照区分）。

设计原则：
  - 任意车辆通行信息查询的数据源是 Doris 原始表，audit_trips 是检测/聚合后快照。
  - 通过 PASSID GROUP BY 在 Doris 端完成聚合，避免把大量原始记录拉到应用层。
  - 排序列走 allowlist 防 SQL 注入；过滤条件用占位符绑定。
  - 门架/出入口站名等区分入口/出口的字段在 HAVING 阶段后置过滤。
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any

try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

from apps.api.services.trip_aggregator import (
    DB_CONFIG,
    aggregate_trip,
    get_gantry_images_by_vehicle,
    get_records_by_passid,
    serialize_gantry_image_records,
    serialize_gantry_records,
    build_image_url,
)
from apps.api.core.logging_config import get_logger

logger = get_logger(__name__)


# 排序列白名单（仅允许以下三列出现在 ORDER BY 中）
SORTABLE_COLUMNS_DORIS = frozenset({
    'entry_time',
    'exit_time',
    'gantry_count',
})

# 车牌匹配方式
VEHICLE_ID_MATCH_MODES_DORIS = frozenset({'exact', 'prefix', 'contains'})


def _normalize_vehicle_id(value: Optional[str]) -> str:
    """清理车牌输入：去空白 + 转大写。空字符串返回空串。"""
    if not value:
        return ''
    return value.strip().upper()


def _build_where_clause(filters: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """根据过滤条件构造 WHERE 子句（作用在原始记录上）。

    返回 (where_sql, params)。params 顺序与占位符顺序一致。
    """
    clauses: List[str] = []
    params: List[Any] = []

    vehicle_id = _normalize_vehicle_id(filters.get('vehicle_id'))
    match_mode = filters.get('vehicle_id_match', 'exact')
    if match_mode not in VEHICLE_ID_MATCH_MODES_DORIS:
        match_mode = 'exact'

    if vehicle_id:
        escaped = vehicle_id.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        if match_mode == 'prefix':
            clauses.append('t.VEHICLEID LIKE %s')
            params.append(f"{escaped}%")
        elif match_mode == 'contains':
            clauses.append('t.VEHICLEID LIKE %s')
            params.append(f"%{escaped}%")
        else:  # exact
            clauses.append('t.VEHICLEID = %s')
            params.append(vehicle_id)

    obu_id = filters.get('obu_id')
    if obu_id:
        clauses.append('t.OBUID = %s')
        params.append(str(obu_id).strip())

    vehicle_type = filters.get('vehicle_type')
    if vehicle_type is not None and vehicle_type != '':
        try:
            params.append(int(vehicle_type))
            clauses.append('t.VEHICLETYPE = %s')
        except (TypeError, ValueError):
            pass

    vehicle_color = filters.get('vehicle_color')
    if vehicle_color is not None and vehicle_color != '':
        try:
            params.append(int(vehicle_color))
            clauses.append('t.VEHICLECOLOR = %s')
        except (TypeError, ValueError):
            pass

    start_time = filters.get('start_time')
    end_time = filters.get('end_time')
    if start_time and end_time:
        clauses.append('t.OCCURTIME BETWEEN %s AND %s')
        params.extend([start_time, end_time])
    elif start_time:
        clauses.append('t.OCCURTIME >= %s')
        params.append(start_time)
    elif end_time:
        clauses.append('t.OCCURTIME <= %s')
        params.append(end_time)

    where_sql = ' AND '.join(clauses) if clauses else '1=1'
    return where_sql, params


def _build_having_clause(filters: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """HAVING 子句（基于聚合后的 entry_* / exit_* / gantry_count 字段）。"""
    clauses: List[str] = []
    params: List[Any] = []

    entry_station = (filters.get('entry_station_name') or '').strip()
    if entry_station:
        clauses.append('entry_station_name LIKE %s')
        escaped = entry_station.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        params.append(f"%{escaped}%")

    exit_station = (filters.get('exit_station_name') or '').strip()
    if exit_station:
        clauses.append('exit_station_name LIKE %s')
        escaped = exit_station.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        params.append(f"%{escaped}%")

    min_gantry = filters.get('min_gantry_count')
    max_gantry = filters.get('max_gantry_count')
    if min_gantry is not None and min_gantry != '':
        try:
            params.append(int(min_gantry))
            clauses.append('gantry_count >= %s')
        except (TypeError, ValueError):
            pass
    if max_gantry is not None and max_gantry != '':
        try:
            params.append(int(max_gantry))
            clauses.append('gantry_count <= %s')
        except (TypeError, ValueError):
            pass

    having_sql = ' AND '.join(clauses) if clauses else ''
    return having_sql, params


def _build_passid_cte(where_sql: str, having_sql: str) -> str:
    """构造按 PASSID 聚合的 CTE SQL（不含外层 SELECT / ORDER BY / LIMIT）。"""
    having_block = f"HAVING {having_sql}" if having_sql else ""
    return f"""
    WITH passid_agg AS (
        SELECT
            t.PASSID,
            MAX(CASE WHEN t.LANETYPE='入口' THEN t.OCCURTIME END) AS entry_time,
            MAX(CASE WHEN t.LANETYPE='入口' THEN t.STATION_NAME END) AS entry_station_name,
            MAX(CASE WHEN t.LANETYPE='入口' THEN t.VEHICLEID END) AS entry_vehicle_id,
            MAX(CASE WHEN t.LANETYPE='入口' THEN t.VEHICLECOLOR END) AS entry_vehicle_color,
            MAX(CASE WHEN t.LANETYPE='入口' THEN t.VEHICLETYPE END) AS entry_vehicle_type,
            MAX(CASE WHEN t.LANETYPE='入口' THEN t.OBUID END) AS entry_obu_id,
            MAX(CASE WHEN t.LANETYPE='出口' THEN t.OCCURTIME END) AS exit_time,
            MAX(CASE WHEN t.LANETYPE='出口' THEN t.STATION_NAME END) AS exit_station_name,
            MAX(CASE WHEN t.LANETYPE='出口' THEN t.VEHICLEID END) AS exit_vehicle_id,
            MAX(CASE WHEN t.LANETYPE='出口' THEN t.VEHICLECOLOR END) AS exit_vehicle_color,
            MAX(CASE WHEN t.LANETYPE='出口' THEN t.VEHICLETYPE END) AS exit_vehicle_type,
            MAX(CASE WHEN t.LANETYPE='出口' THEN t.OBUID END) AS exit_obu_id,
            SUM(CASE WHEN t.LANETYPE='门架' THEN 1 ELSE 0 END) AS gantry_count
        FROM dwd_tolldata.t_waste_en_ex_gantry t
        WHERE {where_sql}
        GROUP BY t.PASSID
        {having_block}
    )
    """


def _format_time(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    """把 CTE 查询的 dict 行序列化为前端消费的 RawTripResponse 字段集。"""
    def _str_or_none(v: Any) -> Optional[str]:
        if v is None:
            return None
        return v if isinstance(v, str) else str(v)

    return {
        'passid': row.get('PASSID'),
        'entry_time': _format_time(row.get('entry_time')),
        'entry_station_name': row.get('entry_station_name'),
        'entry_vehicle_id': row.get('entry_vehicle_id'),
        'entry_vehicle_color': _str_or_none(row.get('entry_vehicle_color')),
        'entry_vehicle_type': row.get('entry_vehicle_type'),
        'entry_obu_id': row.get('entry_obu_id'),
        'exit_time': _format_time(row.get('exit_time')),
        'exit_station_name': row.get('exit_station_name'),
        'exit_vehicle_id': row.get('exit_vehicle_id'),
        'exit_vehicle_color': _str_or_none(row.get('exit_vehicle_color')),
        'exit_vehicle_type': row.get('exit_vehicle_type'),
        'exit_obu_id': row.get('exit_obu_id'),
        'gantry_count': int(row.get('gantry_count') or 0),
    }


def query_trips(filters: Dict[str, Any], limit: int = 20, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """在 Doris 端按 PASSID 聚合，返回 (rows, total)。

    - 入口/出口站名、门架数范围走 HAVING 后置过滤
    - 排序列严格走 SORTABLE_COLUMNS_DORIS 白名单
    - 入参过滤值会做基本类型转换与字符串清洗
    """
    if not HAS_PYMYSQL:
        return [], 0

    order_by = filters.get('order_by', 'entry_time')
    if order_by not in SORTABLE_COLUMNS_DORIS:
        raise ValueError(f"Invalid order_by: {order_by}")

    order_dir = 'DESC' if (filters.get('order') or 'desc').lower() == 'desc' else 'ASC'
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    where_sql, where_params = _build_where_clause(filters)
    having_sql, having_params = _build_having_clause(filters)
    cte = _build_passid_cte(where_sql, having_sql)
    cte_params = where_params + having_params

    conn = pymysql.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        try:
            count_sql = f"{cte} SELECT COUNT(*) AS total FROM passid_agg"
            cursor.execute(count_sql, cte_params)
            count_row = cursor.fetchone()
            total = int(count_row.get('total') or 0) if count_row else 0

            if total == 0:
                return [], 0

            list_sql = (
                f"{cte} SELECT * FROM passid_agg "
                f"ORDER BY {order_by} {order_dir} LIMIT %s OFFSET %s"
            )
            cursor.execute(list_sql, cte_params + [limit, offset])
            rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        conn.close()

    return [_row_to_dict(r) for r in rows], total


def get_trip_detail(passid: str) -> Optional[Dict[str, Any]]:
    """获取单个行程的原始数据详情。

    复用 trip_aggregator.aggregate_trip() 拿到入口/出口/门架流水，再补门架抓拍图片流水。
    容忍缺失入口或出口（车在途、或时间范围仅覆盖单边）。
    不返回 audit_results（原始数据视角下没有"决策"概念）。
    """
    if not passid or not HAS_PYMYSQL:
        return None

    trip = aggregate_trip(passid)

    if not trip:
        # 回退：单边记录也允许展示（车在途场景）
        records = get_records_by_passid(passid)
        if not records:
            return None
        entry = next((r for r in records if r.get('LANETYPE') == '入口'), None)
        exit_record = next((r for r in records if r.get('LANETYPE') == '出口'), None)
        gantry_records = [r for r in records if r.get('LANETYPE') == '门架']

        def _fmt(t):
            if isinstance(t, datetime):
                return t.isoformat()
            return str(t) if t else None

        def _row(r):
            if not r:
                return {}
            return {
                'time': _fmt(r.get('OCCURTIME')),
                'station_name': r.get('STATION_NAME'),
                'lane_id': r.get('LANE_ID'),
                'vehicle_id': r.get('VEHICLEID'),
                'vehicle_color': r.get('VEHICLECOLOR'),
                'vehicle_type': r.get('VEHICLETYPE'),
                'obu_id': r.get('OBUID'),
                'image_license': build_image_url(r, '_license.jpg'),
                'image_trans': build_image_url(r, '_trans.jpg'),
            }

        e = _row(entry)
        x = _row(exit_record)
        trip = {
            'passid': passid,
            'entry_time': e.get('time'),
            'entry_station_name': e.get('station_name'),
            'entry_lane_id': e.get('lane_id'),
            'entry_vehicle_id': e.get('vehicle_id'),
            'entry_vehicle_color': e.get('vehicle_color'),
            'entry_vehicle_type': e.get('vehicle_type'),
            'entry_obu_id': e.get('obu_id'),
            'exit_time': x.get('time'),
            'exit_station_name': x.get('station_name'),
            'exit_lane_id': x.get('lane_id'),
            'exit_vehicle_id': x.get('vehicle_id'),
            'exit_vehicle_color': x.get('vehicle_color'),
            'exit_vehicle_type': x.get('vehicle_type'),
            'exit_obu_id': x.get('obu_id'),
            'gantry_count': len(gantry_records),
            'entry_image_license': e.get('image_license'),
            'entry_image_trans': e.get('image_trans'),
            'exit_image_license': x.get('image_license'),
            'exit_image_trans': x.get('image_trans'),
            'gantry_records': serialize_gantry_records(gantry_records),
        }

    entry_vehicle = trip.get('entry_vehicle_id') or trip.get('exit_vehicle_id')
    entry_time = trip.get('entry_time')
    exit_time = trip.get('exit_time')
    vehicle_color = trip.get('exit_vehicle_color') or trip.get('entry_vehicle_color')

    gantry_images: List[Dict[str, Any]] = []
    if entry_vehicle and entry_time:
        try:
            entry_dt = entry_time if isinstance(entry_time, datetime) else datetime.fromisoformat(str(entry_time))
        except (ValueError, TypeError):
            entry_dt = None
        if entry_dt:
            try:
                if exit_time:
                    exit_dt = exit_time if isinstance(exit_time, datetime) else datetime.fromisoformat(str(exit_time))
                    upper = exit_dt if exit_dt >= entry_dt else entry_dt
                else:
                    upper = entry_dt + timedelta(days=7)
                gantry_images = get_gantry_images_by_vehicle(
                    entry_vehicle, entry_dt, upper, vehicle_color
                )
            except Exception as e:
                logger.error("get_gantry_images_by_vehicle failed for %s: %s", passid, e)
                gantry_images = []

    detail = {
        'passid': passid,
        'entry_time': trip.get('entry_time'),
        'entry_station_name': trip.get('entry_station_name'),
        'entry_vehicle_id': trip.get('entry_vehicle_id'),
        'entry_vehicle_color': str(trip.get('entry_vehicle_color')) if trip.get('entry_vehicle_color') is not None else None,
        'entry_vehicle_type': trip.get('entry_vehicle_type'),
        'entry_obu_id': trip.get('entry_obu_id'),
        'exit_time': trip.get('exit_time'),
        'exit_station_name': trip.get('exit_station_name'),
        'exit_vehicle_id': trip.get('exit_vehicle_id'),
        'exit_vehicle_color': str(trip.get('exit_vehicle_color')) if trip.get('exit_vehicle_color') is not None else None,
        'exit_vehicle_type': trip.get('exit_vehicle_type'),
        'exit_obu_id': trip.get('exit_obu_id'),
        'gantry_count': trip.get('gantry_count', 0),
        'entry_lane_id': trip.get('entry_lane_id'),
        'exit_lane_id': trip.get('exit_lane_id'),
        'entry_image_license': trip.get('entry_image_license'),
        'entry_image_trans': trip.get('entry_image_trans'),
        'exit_image_license': trip.get('exit_image_license'),
        'exit_image_trans': trip.get('exit_image_trans'),
        'gantry_records': trip.get('gantry_records'),
        'gantry_image_records': serialize_gantry_image_records(gantry_images),
    }
    return detail


# ---- 客车 OBU 监测候选筛选（直接查 t_waste_en_ex_gantry）----


def find_passenger_obu_candidates_doris(
    start_time: str,
    end_time: str,
    plate_prefix_exclude: str = '新A',
    declared_vehicle_type: int = 1,
    media_type: int = 1,
    limit: int = 500,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """从 Doris 原始表筛选客车 OBU 候选行程（两步 CTE）。

    Step 1: 找 PASSID — VEHICLETYPE=1, MEDIATYPE=1, VEHICLEID NOT LIKE '新A%'
    Step 2: 取入口/出口详情 + JOIN 站点字典拿 IPADDRESS 构造图片 URL

    返回与 detect_trip 兼容的 dict 列表。
    """
    if not HAS_PYMYSQL:
        return []

    prefix = f"{plate_prefix_exclude}%"
    sql = """
    WITH candidate_passids AS (
        SELECT t.PASSID
        FROM dwd_tolldata.t_waste_en_ex_gantry t
        WHERE t.VEHICLETYPE = %s
          AND t.MEDIATYPE = %s
          AND t.VEHICLEID IS NOT NULL
          AND t.VEHICLEID NOT LIKE %s
          AND t.LANETYPE IN ('入口', '出口')
          AND t.OCCURTIME >= %s
          AND t.OCCURTIME < %s
        GROUP BY t.PASSID
        ORDER BY MAX(t.OCCURTIME) ASC
        LIMIT %s OFFSET %s
    ),
    entry_exit AS (
        SELECT t.PASSID, t.LANETYPE, t.VEHICLETYPE, t.VEHICLEID, t.VEHICLECOLOR,
               t.OBUID, t.MEDIATYPE, t.STATION_NAME, t.LANE_ID,
               t.OCCURTIME, t.ID, t.STATION_ID,
               d.IPADDRESS
        FROM dwd_tolldata.t_waste_en_ex_gantry t
        LEFT JOIN dwd_tolldata.t_md_tollstationdic d ON d.ID = t.STATION_ID
        WHERE t.PASSID IN (SELECT PASSID FROM candidate_passids)
          AND t.LANETYPE IN ('入口', '出口')
        ORDER BY t.PASSID, t.LANETYPE
    )
    SELECT * FROM entry_exit
    """
    params = [
        declared_vehicle_type, media_type, prefix,
        start_time, end_time, limit, offset,
    ]

    conn = pymysql.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        conn.close()

    return _rows_to_candidate_trips(rows)


def _rows_to_candidate_trips(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将 Doris 扁平 entry/exit 行按 PASSID 分组为 detect_trip 兼容的 dict。"""
    from collections import defaultdict

    by_passid: Dict[str, List[Dict]] = defaultdict(list)
    for r in rows:
        by_passid[r['PASSID']].append(r)

    trips = []
    for passid, records in by_passid.items():
        entry = next((r for r in records if r['LANETYPE'] == '入口'), None)
        exit_rec = next((r for r in records if r['LANETYPE'] == '出口'), None)
        if not entry and not exit_rec:
            continue

        def _fmt_time(r):
            if not r:
                return None
            t = r.get('OCCURTIME')
            if isinstance(t, datetime):
                return t.isoformat()
            return str(t) if t else None

        def _img(r, suffix):
            if not r or not r.get('IPADDRESS'):
                return None
            return build_image_url(r, suffix)

        trips.append({
            'passid': passid,
            'entry_time': _fmt_time(entry),
            'entry_station_name': entry.get('STATION_NAME') if entry else None,
            'entry_lane_id': entry.get('LANE_ID') if entry else None,
            'entry_vehicle_id': entry.get('VEHICLEID') if entry else None,
            'entry_vehicle_type': entry.get('VEHICLETYPE') if entry else None,
            'entry_vehicle_color': entry.get('VEHICLECOLOR') if entry else None,
            'entry_obu_id': entry.get('OBUID') if entry else None,
            'entry_media_type': entry.get('MEDIATYPE') if entry else None,
            'entry_image_trans': _img(entry, '_trans.jpg'),
            'entry_image_license': _img(entry, '_license.jpg'),
            'entry_visual_type': None,
            'exit_time': _fmt_time(exit_rec),
            'exit_station_name': exit_rec.get('STATION_NAME') if exit_rec else None,
            'exit_lane_id': exit_rec.get('LANE_ID') if exit_rec else None,
            'exit_vehicle_id': exit_rec.get('VEHICLEID') if exit_rec else None,
            'exit_vehicle_type': exit_rec.get('VEHICLETYPE') if exit_rec else None,
            'exit_vehicle_color': exit_rec.get('VEHICLECOLOR') if exit_rec else None,
            'exit_obu_id': exit_rec.get('OBUID') if exit_rec else None,
            'exit_media_type': exit_rec.get('MEDIATYPE') if exit_rec else None,
            'exit_image_trans': _img(exit_rec, '_trans.jpg'),
            'exit_image_license': _img(exit_rec, '_license.jpg'),
            'exit_visual_type': None,
        })
    return trips
