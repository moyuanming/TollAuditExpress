"""
行程聚合服务 - 按PASSID聚合入口-门架-出口记录，并执行视觉检测

门架流水与抓拍图片的关系：
  - dwd_tolldata.t_waste_en_ex_gantry: 门架交易流水（ETC交易记录），字段含 STATION_ID, VEHICLEID, OCCURTIME
  - ods_tb_toll_db_tolldata_prod.t_grantry_image: 门架抓拍图片流水，字段含 GRANTRY_ID, VEHICLEID, CAPTURETIME, ID
  - 关联规则：同一门架（GRANTRY_ID = STATION_ID）+ 同一车牌（VEHICLEID）+ 相近时间（默认±120秒内）
    视为同一辆车经过同一门架的一次通行
  - 门架图片URL中的 pic_id 参数应使用 t_grantry_image.ID（抓拍记录ID），而非 t_waste_en_ex_gantry.ID（交易记录ID）
"""

from datetime import datetime
from typing import List, Dict, Optional, Callable
import json
import os
import threading
import urllib.parse

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

# 门架图片服务地址（门架抓拍图专用）
GANTRY_IMAGE_BASE = os.environ.get('GANTRY_IMAGE_BASE', 'http://10.165.83.43/auditImage/mj_images')


def build_image_url(record: dict, suffix: str = '_license.jpg') -> str:
    """构建入口/出口图片URL（路径式）"""
    occur_time = record.get('OCCURTIME')
    if isinstance(occur_time, datetime):
        date_str = occur_time.strftime('%Y%m%d')
    else:
        date_str = str(occur_time)[:10].replace('-', '') if occur_time else ''
    return f"http://{record.get('IPADDRESS')}/img/data/{record.get('LANE_ID')}/{date_str}/{record.get('ID')}{suffix}"


# 门架抓拍图片匹配时间窗口（秒）
GANTRY_IMAGE_TIME_WINDOW = int(os.environ.get('GANTRY_IMAGE_TIME_WINDOW', '120'))


def build_gantry_image_url(record: dict) -> Optional[str]:
    """构建门架图片URL（查询式）

    pic_id 取 t_grantry_image.ID（抓拍记录ID），如未匹配到则回退使用交易记录ID。
    规则: {base}?pic_id={pic_id}&vchicle={VEHICLEID}&vehicle_color={VEHICLECOLOR}
    """
    # 优先使用从 t_grantry_image 匹配到的抓拍记录ID
    pic_id = record.get('IMAGE_ID') or record.get('ID')
    plate = record.get('VEHICLEID')
    color = record.get('VEHICLECOLOR')
    if not (pic_id and plate and color is not None):
        return None
    return f"{GANTRY_IMAGE_BASE}?pic_id={pic_id}&vchicle={urllib.parse.quote(str(plate))}&vehicle_color={color}"


def get_gantry_image_match(record: dict, time_window: int = None) -> Optional[int]:
    """为一条门架交易流水记录查找匹配的门架抓拍图片记录。

    匹配规则：
      1. 同一门架：t_grantry_image.GRANTRY_ID = t_waste_en_ex_gantry.STATION_ID
      2. 同一车牌：t_grantry_image.VEHICLEID = t_waste_en_ex_gantry.VEHICLEID
      3. 相近时间：CAPTURETIME 在 OCCURTIME 前后 time_window 秒范围内

    返回匹配到的 t_grantry_image.ID，无匹配时返回 None。
    """
    if not HAS_PYMYSQL:
        return None

    if time_window is None:
        time_window = GANTRY_IMAGE_TIME_WINDOW

    station_id = record.get('STATION_ID')
    vehicle_id = record.get('VEHICLEID')
    occur_time = record.get('OCCURTIME')

    if not (station_id and vehicle_id and occur_time):
        return None

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    sql = """
    SELECT ID
    FROM ods_tb_toll_db_tolldata_prod.t_grantry_image
    WHERE GRANTRY_ID = %s
      AND VEHICLEID = %s
      AND CAPTURETIME BETWEEN DATE_SUB(%s, INTERVAL %s SECOND)
                           AND DATE_ADD(%s, INTERVAL %s SECOND)
    ORDER BY ABS(TIMESTAMPDIFF(SECOND, CAPTURETIME, %s))
    LIMIT 1
    """

    cursor.execute(sql, (
        station_id, vehicle_id,
        occur_time, time_window, occur_time, time_window,
        occur_time
    ))
    result = cursor.fetchone()
    cursor.close()
    conn.close()

    return result['ID'] if result else None


def get_gantry_images_by_vehicle(vehicle_id: str, entry_time, exit_time, vehicle_color=None) -> List[Dict]:
    """查询出入口时间范围内该车辆的所有门架抓拍图片记录。

    从 ods_tb_toll_db_tolldata_prod.t_grantry_image 查询，
    返回在 entry_time ~ exit_time 之间、同一车牌的所有抓拍记录。

    Args:
        vehicle_id: 车牌号
        entry_time: 入口时间 (datetime 或 str)
        exit_time: 出口时间 (datetime 或 str)
        vehicle_color: 车辆颜色（可选过滤）

    Returns:
        List[Dict]: 包含 ID, GRANTRY_ID, VEHICLEID, VEHICLECOLOR, CAPTURETIME 等字段
    """
    if not HAS_PYMYSQL or not (vehicle_id and entry_time and exit_time):
        return []

    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor(pymysql.cursors.DictCursor)
    except Exception as e:
        logger.error(f"Failed to connect to DB for gantry images: {e}")
        return []

    try:
        sql = """
        SELECT
            ID, GRANTRY_ID, VEHICLEID, VEHICLECOLOR, CAPTURETIME
        FROM ods_tb_toll_db_tolldata_prod.t_grantry_image
        WHERE VEHICLEID = %s
          AND CAPTURETIME >= %s
          AND CAPTURETIME <= %s
        ORDER BY CAPTURETIME
        """

        cursor.execute(sql, (vehicle_id, entry_time, exit_time))
        results = cursor.fetchall()
        logger.debug(f"Gantry image query for {vehicle_id}: {len(results)} records")
        return results
    except Exception as e:
        logger.error(f"Gantry image query failed for {vehicle_id}: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def serialize_gantry_image_records(records: List[Dict]) -> str:
    """将门架抓拍图片记录序列化为 JSON 字符串"""
    items = []
    for r in records:
        items.append({
            'pic_id': r.get('ID'),
            'station_name': r.get('STATION_NAME') or r.get('GRANTRY_ID'),
            'occur_time': r['CAPTURETIME'].isoformat() if isinstance(r.get('CAPTURETIME'), datetime) else str(r.get('CAPTURETIME') or ''),
            'vehicle_id': r.get('VEHICLEID'),
            'vehicle_color': r.get('VEHICLECOLOR'),
            'image_url': build_gantry_image_url({'IMAGE_ID': r.get('ID'), 'VEHICLEID': r.get('VEHICLEID'), 'VEHICLECOLOR': r.get('VEHICLECOLOR')}),
        })
    return json.dumps(items, ensure_ascii=False)


def serialize_gantry_records(records: List[Dict]) -> str:
    """将门架记录列表序列化为 JSON 字符串"""
    items = []
    for r in records:
        items.append({
            'pic_id': r.get('IMAGE_ID') or r.get('ID'),
            'station_name': r.get('STATION_NAME'),
            'occur_time': r['OCCURTIME'].isoformat() if isinstance(r.get('OCCURTIME'), datetime) else str(r.get('OCCURTIME') or ''),
            'vehicle_id': r.get('VEHICLEID'),
            'vehicle_color': r.get('VEHICLECOLOR'),
            'vehicle_type': r.get('VEHICLETYPE'),
            'obu_id': r.get('OBUID'),
            'image_url': build_gantry_image_url(r),
        })
    return json.dumps(items, ensure_ascii=False)


def get_records_by_passid(passid: str) -> List[Dict]:
    """获取同一PASSID的所有记录"""
    if not HAS_PYMYSQL:
        return []

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    sql = """
    SELECT
        t.PASSID, t.LANETYPE, t.VEHICLETYPE, t.STATION_ID,
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

    # 为门架交易记录匹配 t_grantry_image 抓拍图片ID
    for gr in gantry_records:
        try:
            image_id = get_gantry_image_match(gr)
            gr['IMAGE_ID'] = image_id
            if image_id is None:
                logger.debug("No gantry image match for station=%s vehicle=%s time=%s",
                            gr.get('STATION_ID'), gr.get('VEHICLEID'), gr.get('OCCURTIME'))
        except Exception as e:
            logger.warning("Failed to query gantry image for station=%s: %s", gr.get('STATION_ID'), e)
            gr['IMAGE_ID'] = None

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
        'gantry_count': len(gantry_records),
        'gantry_records': serialize_gantry_records(gantry_records)
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
                return

            # 后台异步跑 AI 二次判定（不阻塞检测主路径）
            self._schedule_llm_verification_async(trip_data.get('passid'))

    def _schedule_llm_verification_async(self, passid: Optional[str]) -> None:
        """起一个 daemon 线程跑 AI 公共服务批量复核，fire-and-forget。"""
        if not passid:
            return
        try:
            from apps.api.services.ai_verify_batch import run_ai_verify_batch_for_suspects
        except ImportError as e:
            logger.warning("ai_verify_batch not available, skip async verify: %s", e)
            return

        def _runner():
            try:
                result = run_ai_verify_batch_for_suspects(limit=50, max_workers=4)
                logger.info("async ai-verify batch for passid=%s done: %s", passid, result)
            except Exception as e:
                logger.error("async ai-verify batch for passid=%s crashed: %s", passid, e)

        t = threading.Thread(target=_runner, name=f"ai-verify-batch-{passid}", daemon=True)
        t.start()

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
