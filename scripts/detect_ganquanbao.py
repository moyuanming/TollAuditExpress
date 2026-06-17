"""
甘泉堡定向检测脚本：专注处理出口为新疆甘泉堡匝道站的行程
阶段2: 视觉检测（Model A: 货车套OBU + Model B: 出入口比对）
用法: python scripts/detect_ganquanbao.py
"""
import os
import sys

sys.path.insert(0, '/Users/moyuanming/TollAuditExpress')

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join('/Users/moyuanming/TollAuditExpress', '.env'))
except ImportError:
    pass

import json
import logging
import sqlite3

from apps.api.services.entry_exit_matcher import EntryExitMatcher
from apps.api.services.truck_obu_detector import TruckOBUDetector

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = '/Users/moyuanming/TollAuditExpress/apps/api/data/audit.db'


def get_ganquanbao_undetected(limit=200):
    """获取甘泉堡出口且未检测的行程"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM audit_trips
        WHERE exit_station_name LIKE '%甘泉堡%'
        AND entry_visual_type IS NULL
        AND entry_image_license NOT LIKE '%None%'
        AND exit_image_license NOT LIKE '%None%'
        AND entry_image_trans NOT LIKE '%None%'
        ORDER BY entry_time DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def save_results(trip_id, passid, results):
    """保存检测结果（事务写入 audit_results + 更新 audit_trips）"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for r in results:
        cur.execute("""
            INSERT INTO audit_results (
                audit_trip_id, fraud_type,
                entry_vehicle_type, entry_visual_type, entry_color,
                exit_vehicle_type, exit_visual_type, exit_color,
                is_suspicious, risk_score, details, process_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r.get('audit_trip_id'),
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

    # 更新 visual_types
    entry_vis = None
    exit_vis = None
    fp_sim = None
    for r in results:
        if r['fraud_type'] == 'TRUCK_USES_PASSENGER_OBU':
            entry_vis = r.get('entry_visual_type')
        elif r['fraud_type'] == 'ENTRY_EXIT_MISMATCH':
            entry_vis = r.get('entry_visual_type') or entry_vis
            exit_vis = r.get('exit_visual_type')
            fp_sim = r.get('risk_score')

    updates = []
    values = []
    if entry_vis is not None:
        updates.append("entry_visual_type = ?")
        values.append(entry_vis)
    if exit_vis is not None:
        updates.append("exit_visual_type = ?")
        values.append(exit_vis)
    if fp_sim is not None:
        updates.append("fingerprint_sim = ?")
        values.append(fp_sim)

    if updates:
        values.append(passid)
        cur.execute(
            f"UPDATE audit_trips SET {', '.join(updates)}, updated_at = datetime('now', 'localtime') WHERE passid = ?",
            values
        )

    # 可疑则更新状态
    if any(r['is_suspicious'] for r in results):
        max_risk = max(r['risk_score'] for r in results)
        cur.execute(
            "UPDATE audit_trips SET audit_status = ?, risk_score = ?, updated_at = datetime('now', 'localtime') WHERE passid = ?",
            ('SUSPECTED', max_risk, passid)
        )

    conn.commit()
    conn.close()


def main():
    trips = get_ganquanbao_undetected(limit=500)
    logger.info("Found %d 甘泉堡 trips needing detection", len(trips))

    detector = TruckOBUDetector()
    matcher = EntryExitMatcher()

    detect_count = 0
    suspect_count = 0

    for i, trip in enumerate(trips):
        passid = trip['passid']
        trip_id = trip['id']
        results_to_save = []

        # Model A: 货车套用客车OBU（仅 type-1 客车）
        if trip.get('entry_vehicle_type') == 1:
            try:
                entry_record = {
                    'VEHICLETYPE': trip.get('entry_vehicle_type'),
                    'image_trans': trip.get('entry_image_trans')
                }
                r = detector.detect(entry_record)
                if r.get('visual_vehicle_type'):
                    is_sus = 1 if r.get('is_suspicious') else 0
                    risk = r.get('confidence', 0) if is_sus else 0
                    results_to_save.append({
                        'audit_trip_id': trip_id,
                        'fraud_type': 'TRUCK_USES_PASSENGER_OBU',
                        'entry_vehicle_type': trip.get('entry_vehicle_type'),
                        'entry_visual_type': r.get('visual_vehicle_type'),
                        'is_suspicious': is_sus,
                        'risk_score': risk,
                        'details': json.dumps(r)
                    })
            except Exception as e:
                logger.debug("Model A error for %s: %s", passid, e)

        # Model B: 出入口车辆比对
        try:
            entry_rec = {'image_license': trip.get('entry_image_license')}
            exit_rec = {'image_license': trip.get('exit_image_license')}
            r = matcher.compare(entry_rec, exit_rec)
            if r.get('_comparison_success') or r.get('fingerprint_sim'):
                results_to_save.append({
                    'audit_trip_id': trip_id,
                    'fraud_type': 'ENTRY_EXIT_MISMATCH',
                    'entry_visual_type': r.get('entry_visual_type'),
                    'exit_visual_type': r.get('exit_visual_type'),
                    'entry_color': r.get('entry_color'),
                    'exit_color': r.get('exit_color'),
                    'is_suspicious': 1 if r.get('is_suspicious') else 0,
                    'risk_score': r.get('fingerprint_sim', 0),
                    'details': json.dumps(r)
                })
        except Exception as e:
            logger.debug("Model B error for %s: %s", passid, e)

        if results_to_save:
            try:
                save_results(trip_id, passid, results_to_save)
                detect_count += 1
                for r in results_to_save:
                    if r.get('is_suspicious'):
                        suspect_count += 1
                        logger.warning("⚠ SUSPICIOUS [%s] %s ev=%s xv=%s risk=%.3f",
                                       r['fraud_type'], passid[:35],
                                       r.get('entry_visual_type', '?'),
                                       r.get('exit_visual_type', '?'),
                                       r['risk_score'])
            except Exception as e:
                logger.error("Save error for %s: %s", passid, e)

        if (i + 1) % 20 == 0:
            logger.info("[%d/%d] detected=%d suspected=%d",
                        i + 1, len(trips), detect_count, suspect_count)

    logger.info("===== DONE: detected=%d suspected=%d =====", detect_count, suspect_count)

    # 最终统计
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audit_trips WHERE exit_station_name LIKE '%甘泉堡%' AND entry_visual_type IS NOT NULL")
    detected = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM audit_trips WHERE exit_station_name LIKE '%甘泉堡%' AND audit_status = 'SUSPECTED'")
    suspected = cur.fetchone()[0]
    conn.close()
    logger.info("甘泉堡: total detected=%d, suspected=%d", detected, suspected)


if __name__ == '__main__':
    main()
