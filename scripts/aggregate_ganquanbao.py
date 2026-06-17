"""
批量聚合脚本：一次查询Doris拉取所有甘泉堡相关记录，内存聚合后批量写入SQLite
"""
import os
import sys

sys.path.insert(0, '/Users/moyuanming/TollAuditExpress')

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join('/Users/moyuanming/TollAuditExpress', '.env'))
except ImportError:
    pass

import logging
from collections import defaultdict
from datetime import datetime

import pymysql

from apps.api.database.repositories.trip_repository import TripRepository
from apps.api.services.trip_aggregator import DB_CONFIG, build_image_url

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def format_time(t):
    if isinstance(t, datetime):
        return t.isoformat()
    return str(t) if t else None


def batch_aggregate_ganquanbao(days=3):
    """一次查询Doris，批量聚合所有甘泉堡出口行程"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # Step 1: Get all records for甘泉堡 exit PASSIDs in one query
    sql = """
    SELECT
        t.PASSID, t.LANETYPE, t.VEHICLETYPE,
        CONCAT(t.VEHICLEID, '_', t.VEHICLECOLOR) as VEHICLE_ID,
        t.VEHICLEID, t.VEHICLECOLOR, t.OBUID,
        d.IPADDRESS, t.LANE_ID, t.OCCURTIME, t.ID, t.STATION_NAME,
        t.MEDIATYPE
    FROM dwd_tolldata.t_waste_en_ex_gantry t
    LEFT JOIN dwd_tolldata.t_md_tollstationdic d ON d.ID = t.STATION_ID
    WHERE t.PASSID IN (
        SELECT PASSID
        FROM dwd_tolldata.t_waste_en_ex_gantry
        WHERE LANETYPE = '出口'
        AND STATION_NAME LIKE %s
        AND OCCURTIME >= DATE_SUB(NOW(), INTERVAL %s DAY)
        AND MEDIATYPE = 1
    )
    ORDER BY t.PASSID, t.OCCURTIME
    """
    logger.info("Fetching all records from Doris (this may take a moment)...")
    cursor.execute(sql, ('%甘泉堡%', days))
    all_records = cursor.fetchall()
    cursor.close()
    conn.close()
    logger.info("Fetched %d records from Doris", len(all_records))

    # Step 2: Group by PASSID and aggregate
    groups = defaultdict(list)
    for r in all_records:
        groups[r['PASSID']].append(r)

    logger.info("Grouped into %d unique PASSIDs", len(groups))

    # Step 3: Aggregate each group into trip data
    trips = []
    fail_count = 0
    for passid, records in groups.items():
        entry = None
        exit_record = None
        gantry_count = 0

        for r in records:
            lt = r.get('LANETYPE', '')
            if lt == '入口':
                entry = r
            elif lt == '出口':
                exit_record = r
            elif lt == '门架':
                gantry_count += 1

        if not entry or not exit_record:
            fail_count += 1
            continue

        trips.append({
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
            'gantry_count': gantry_count
        })

    logger.info("Aggregated %d complete trips (%d failed: missing entry/exit)",
                len(trips), fail_count)

    # Step 4: Save to SQLite
    repo = TripRepository()
    new_count = 0
    skip_count = 0

    for i, trip in enumerate(trips):
        existing = repo.get_trip_detail(trip['passid'])
        if existing:
            skip_count += 1
        else:
            repo.save_trip(trip)
            new_count += 1

        if (i + 1) % 500 == 0:
            logger.info("[%d/%d] new=%d skip=%d", i + 1, len(trips), new_count, skip_count)

    logger.info("===== DONE: new=%d skip=%d total_local=%d =====",
                new_count, skip_count, new_count + skip_count)

    stats = repo.get_stats()
    logger.info("DB stats: total=%s suspected=%s confirmed=%s",
                stats['total_trips'], stats['suspected_trips'], stats['confirmed_fraud'])


if __name__ == '__main__':
    batch_aggregate_ganquanbao(days=3)
