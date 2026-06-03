"""
行程聚合服务 - 按PASSID聚合入口-门架-出口记录，并执行视觉检测
"""

from datetime import datetime
from typing import List, Dict, Optional, Callable
import json

try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

from apps.api.core.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
from apps.api.core.logging_config import get_logger

logger = get_logger(__name__)

DB_CONFIG = {
    'host': DB_HOST,
    'port': DB_PORT,
    'user': DB_USER,
    'password': DB_PASSWORD,
    'database': DB_NAME
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
    """行程聚合器 - 支持自动视觉检测"""

    _truck_detector = None
    _entry_exit_matcher = None

    def _get_truck_detector(self):
        if TripAggregator._truck_detector is None:
            from apps.api.services.truck_obu_detector import TruckOBUDetector
            TripAggregator._truck_detector = TruckOBUDetector()
        return TripAggregator._truck_detector

    def _get_entry_exit_matcher(self):
        if TripAggregator._entry_exit_matcher is None:
            from apps.api.services.entry_exit_matcher import EntryExitMatcher
            TripAggregator._entry_exit_matcher = EntryExitMatcher()
        return TripAggregator._entry_exit_matcher

    def _run_detection(self, trip_data: Dict, trip_id: int):
        """对行程运行视觉检测"""
        results_to_save = []

        # Model A: 货车套用客车OBU检测
        try:
            detector = self._get_truck_detector()
            entry_record = {
                'VEHICLETYPE': trip_data.get('entry_vehicle_type'),
                'image_trans': trip_data.get('entry_image_trans')
            }
            model_a_result = detector.detect(entry_record)

            if model_a_result.get('visual_vehicle_type'):
                is_sus = 1 if model_a_result.get('is_suspicious') else 0
                risk = model_a_result.get('confidence', 0) if is_sus else 0
                results_to_save.append({
                    'audit_trip_id': trip_id,
                    'fraud_type': 'TRUCK_USES_PASSENGER_OBU',
                    'entry_vehicle_type': trip_data.get('entry_vehicle_type'),
                    'entry_visual_type': model_a_result.get('visual_vehicle_type'),
                    'is_suspicious': is_sus,
                    'risk_score': risk,
                    'details': json.dumps(model_a_result)
                })
        except Exception as e:
            logger.error("Model A detection error: %s", e)

        # Model B: 出入口车辆比对
        try:
            matcher = self._get_entry_exit_matcher()
            entry_record = {'image_license': trip_data.get('entry_image_license')}
            exit_record = {'image_license': trip_data.get('exit_image_license')}
            model_b_result = matcher.compare(entry_record, exit_record)

            if model_b_result.get('_comparison_success') or model_b_result.get('fingerprint_sim'):
                results_to_save.append({
                    'audit_trip_id': trip_id,
                    'fraud_type': 'ENTRY_EXIT_MISMATCH',
                    'entry_visual_type': model_b_result.get('entry_visual_type'),
                    'exit_visual_type': model_b_result.get('exit_visual_type'),
                    'entry_color': model_b_result.get('entry_color'),
                    'exit_color': model_b_result.get('exit_color'),
                    'is_suspicious': 1 if model_b_result.get('is_suspicious') else 0,
                    'risk_score': model_b_result.get('fingerprint_sim', 0),
                    'details': json.dumps(model_b_result)
                })
        except Exception as e:
            logger.error("Model B detection error: %s", e)

        # 保存检测结果（单事务：audit_results + visual_types + status）
        if results_to_save:
            try:
                from apps.api.database.repositories.trip_repository import TripRepository
                trip_repo = TripRepository()
                trip_repo.save_trip_with_detection_results(trip_id, trip_data['passid'], results_to_save)
            except Exception as e:
                logger.error("Saving results error: %s", e)

    def aggregate_recent_trips(self, days: int = 7, limit: int = 100, on_progress: Optional[Callable] = None, run_detection: bool = True) -> int:
        """聚合最近的行程并可选执行视觉检测"""
        from apps.api.database.repositories.trip_repository import TripRepository

        passids = get_recent_passids(days=days, limit=limit)
        repo = TripRepository()
        count = 0

        for i, passid in enumerate(passids):
            trip_data = aggregate_trip(passid)
            if trip_data:
                trip_id = repo.save_trip(trip_data)
                
                # 运行视觉检测
                if run_detection and trip_id:
                    try:
                        self._run_detection(trip_data, trip_id)
                    except Exception as e:
                        logger.error("Detection error for %s: %s", passid, e)
                
                count += 1

            if on_progress:
                on_progress({
                    'current': i + 1,
                    'total': len(passids),
                    'passid': passid,
                    'count': count
                })

        return count
