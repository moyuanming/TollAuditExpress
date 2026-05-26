"""
行程聚合服务 - 按PASSID聚合入口-门架-出口记录
适配自 getmoveobu/audit/services/trip_aggregator.py
"""

from datetime import datetime
from typing import List, Dict, Optional, Callable

try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

# 数据库配置 - 从环境变量或默认值读取
DB_CONFIG = {
    'host': '10.11.1.36',
    'port': 9030,
    'user': 'root',
    'password': 'AynyDskmXx@AynyDskmXx',
    'database': 'dwd_tolldata'
}


def build_image_url(record: dict, suffix: str = '_license.jpg') -> str:
    """构建图片URL"""
    occur_time = record.get('OCCURTIME')
    if isinstance(occur_time, datetime):
        date_str = occur_time.strftime('%Y%m%d')
    else:
        date_str = str(occur_time)[:10].replace('-', '') if occur_time else ''
    return f"http://{record.get('IPADDRESS')}/img/data/{record.get('LANE_ID')}/{date_str}/{record.get('ID')}{suffix}"


def get_records_by_passid(passid: str) -> List[Dict]:
    """获取同一PASSID的所有记录"""
    if not HAS_PYMYSQL:
        return []

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    sql = """
    SELECT
        t.PASSID, t.LANETYPE, t.VEHICLETYPE,
        CONCAT(t.VEHICLEID, '_', t.VEHICLECOLOR) as VEHICLE_ID,
        t.VEHICLEID, t.VEHICLECOLOR, t.OBUID,
        d.IPADDRESS, t.LANE_ID, t.OCCURTIME, t.ID, t.STATION_NAME,
        t.MEDIATYPE
    FROM dwd_tolldata.t_waste_en_ex_gantry t
    LEFT JOIN dwd_tolldata.t_md_tollstationdic d ON d.ID = t.STATION_ID
    WHERE t.PASSID = %s
    ORDER BY t.OCCURTIME
    """

    cursor.execute(sql, (passid,))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results


def aggregate_trip(passid: str) -> Optional[Dict]:
    """聚合单个行程"""
    records = get_records_by_passid(passid)
    if not records:
        return None

    entry = None
    exit_record = None
    gantry_records = []

    for r in records:
        lanetype = r.get('LANETYPE', '')
        if lanetype == '入口':
            entry = r
        elif lanetype == '出口':
            exit_record = r
        elif lanetype == '门架':
            gantry_records.append(r)

    if not entry or not exit_record:
        return None

    def format_time(t):
        if isinstance(t, datetime):
            return t.isoformat()
        return str(t) if t else None

    return {
        'passid': passid,
        'entry_time': format_time(entry.get('OCCURTIME')),
        'entry_station_name': entry.get('STATION_NAME'),
        'entry_lane_id': entry.get('LANE_ID'),
        'entry_vehicle_id': entry.get('VEHICLEID'),
        'entry_vehicle_type': entry.get('VEHICLETYPE'),
        'entry_vehicle_color': entry.get('VEHICLECOLOR'),
        'entry_obu_id': entry.get('OBUID'),
        'entry_media_type': entry.get('MEDIATYPE'),
        'entry_image_license': build_image_url(entry, '_license.jpg'),
        'entry_image_trans': build_image_url(entry, '_trans.jpg'),
        'exit_time': format_time(exit_record.get('OCCURTIME')),
        'exit_station_name': exit_record.get('STATION_NAME'),
        'exit_lane_id': exit_record.get('LANE_ID'),
        'exit_vehicle_id': exit_record.get('VEHICLEID'),
        'exit_vehicle_type': exit_record.get('VEHICLETYPE'),
        'exit_vehicle_color': exit_record.get('VEHICLECOLOR'),
        'exit_obu_id': exit_record.get('OBUID'),
        'exit_media_type': exit_record.get('MEDIATYPE'),
        'exit_image_license': build_image_url(exit_record, '_license.jpg'),
        'exit_image_trans': build_image_url(exit_record, '_trans.jpg'),
        'gantry_count': len(gantry_records)
    }


def get_recent_passids(days: int = 7, limit: int = 100) -> List[str]:
    """获取最近的PASSID列表"""
    if not HAS_PYMYSQL:
        return []

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    sql = """
    SELECT PASSID
    FROM (
        SELECT PASSID, MAX(OCCURTIME) as max_time
        FROM dwd_tolldata.t_waste_en_ex_gantry
        WHERE LANETYPE = '出口'
        AND OCCURTIME >= DATE_SUB(NOW(), INTERVAL %s DAY)
        AND MEDIATYPE = 1
        GROUP BY PASSID
    ) t
    ORDER BY max_time DESC
    LIMIT %s
    """

    cursor.execute(sql, (days, limit))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return [r['PASSID'] for r in results]


class TripAggregator:
    """行程聚合器"""

    def __init__(self):
        pass

    def aggregate_recent_trips(self, days: int = 7, limit: int = 100, on_progress: Optional[Callable] = None) -> int:
        """聚合最近的行程"""
        from apps.api.database.repositories.trip_repository import TripRepository

        passids = get_recent_passids(days=days, limit=limit)
        repo = TripRepository()
        count = 0

        for i, passid in enumerate(passids):
            trip_data = aggregate_trip(passid)
            if trip_data:
                repo.save_trip(trip_data)
                count += 1

            if on_progress:
                on_progress({
                    'current': i + 1,
                    'total': len(passids),
                    'passid': passid,
                    'count': count
                })

        return count
