"""任务执行器 — 根据任务配置执行聚合+检测"""

import json
import logging

logger = logging.getLogger(__name__)


def execute_task(task: dict) -> dict:
    """执行单个任务，返回结果摘要"""
    task_type = task.get('task_type', 'aggregate_detect')
    filter_rules = {}
    if task.get('filter_rules'):
        try:
            filter_rules = json.loads(task['filter_rules'])
        except (json.JSONDecodeError, TypeError):
            pass

    from apps.api.database.repositories.trip_repository import TripRepository
    trip_repo = TripRepository()

    if task_type == 'aggregate_detect':
        return _execute_aggregate_detect(filter_rules, trip_repo)
    elif task_type == 'detect_only':
        return _execute_detect_only(filter_rules, trip_repo)
    elif task_type == 're_detect':
        return _execute_re_detect(trip_repo)
    elif task_type == 'llm_verify':
        return _execute_llm_verify(filter_rules)
    else:
        return {"error": f"Unknown task_type: {task_type}"}


def _execute_llm_verify(filter_rules: dict) -> dict:
    """LLM 二次判定：批跑所有 llm_checked_at IS NULL 的可疑记录。"""
    from apps.api.services.llm_batch import run_llm_batch_for_suspects
    limit = int(filter_rules.get('limit', 50))
    max_workers = int(filter_rules.get('max_workers', 4))
    return run_llm_batch_for_suspects(limit=limit, max_workers=max_workers)


def _execute_aggregate_detect(filter_rules: dict, trip_repo) -> dict:
    """聚合+检测"""
    days = filter_rules.get('days', 3)
    limit = filter_rules.get('limit', 500)
    exit_station = filter_rules.get('exit_station', '')
    entry_station = filter_rules.get('entry_station', '')

    aggregator = None
    from apps.api.services.trip_aggregator import TripAggregator
    aggregator = TripAggregator()

    if exit_station or entry_station:
        return _targeted_aggregate(exit_station, entry_station, days, limit, trip_repo, aggregator)

    aggregated = aggregator.aggregate_recent_trips(days=days, limit=limit, run_detection=True)
    stats = trip_repo.get_stats()
    return {"aggregated": aggregated, "detected": 0, "suspected": stats.get('suspected_trips', 0)}


def _targeted_aggregate(exit_station: str, entry_station: str, days: int, limit: int, trip_repo, aggregator) -> dict:
    """定向聚合指定站点"""
    import pymysql
    from apps.api.services.trip_aggregator import DB_CONFIG, aggregate_trip

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    conditions = ["t.LANETYPE = '出口'", "t.MEDIATYPE = 1",
                  "t.OCCURTIME >= DATE_SUB(NOW(), INTERVAL %s DAY)"]
    params = [days]
    if exit_station:
        conditions.append("t.STATION_NAME LIKE %s")
        params.append(f"%{exit_station}%")

    sql = f"""
    SELECT t.PASSID FROM dwd_tolldata.t_waste_en_ex_gantry t
    WHERE {' AND '.join(conditions)}
    GROUP BY t.PASSID ORDER BY MAX(t.OCCURTIME) DESC LIMIT %s
    """
    params.append(limit)
    cursor.execute(sql, params)
    passids = [r['PASSID'] for r in cursor.fetchall()]
    cursor.close()
    conn.close()

    logger.info("Targeted aggregate: %d PASSIDs found", len(passids))

    aggregated = 0
    for passid in passids:
        existing = trip_repo.get_trip_detail(passid)
        if existing:
            continue
        trip_data = aggregate_trip(passid)
        if not trip_data:
            continue
        trip_id = trip_repo.save_trip(trip_data)
        if trip_id:
            aggregated += 1
            try:
                aggregator._run_detection(trip_data, trip_id)
            except Exception as e:
                logger.warning("Detection failed for %s: %s", passid, e)

    stats = trip_repo.get_stats()
    return {"aggregated": aggregated, "detected": aggregated, "suspected": stats.get('suspected_trips', 0)}


def _execute_detect_only(filter_rules: dict, trip_repo) -> dict:
    """仅检测"""
    exit_station = filter_rules.get('exit_station', '')
    entry_station = filter_rules.get('entry_station', '')
    limit = filter_rules.get('limit', 200)

    from apps.api.services.truck_obu_detector import TruckOBUDetector
    from apps.api.services.entry_exit_matcher import EntryExitMatcher

    trips = trip_repo.get_trips_without_visual(limit=limit)
    detector = TruckOBUDetector()
    matcher = EntryExitMatcher()
    detected = 0
    suspected = 0

    for trip in trips:
        passid = trip['passid']
        trip_id = trip['id']

        if exit_station and exit_station not in (trip.get('exit_station_name') or ''):
            continue
        if entry_station and entry_station not in (trip.get('entry_station_name') or ''):
            continue

        trip_results = []
        if trip.get('entry_vehicle_type') == 1:
            try:
                r = detector.detect({
                    'VEHICLETYPE': trip.get('entry_vehicle_type'),
                    'image_trans': trip.get('entry_image_trans')
                })
                if r.get('visual_vehicle_type'):
                    is_sus = 1 if r.get('is_suspicious') else 0
                    trip_results.append({
                        'audit_trip_id': trip_id,
                        'fraud_type': 'TRUCK_USES_PASSENGER_OBU',
                        'entry_vehicle_type': trip.get('entry_vehicle_type'),
                        'entry_visual_type': r.get('visual_vehicle_type'),
                        'is_suspicious': is_sus,
                        'risk_score': r.get('confidence', 0) if is_sus else 0,
                        'details': json.dumps(r)
                    })
            except Exception as e:
                logger.debug("Model A error: %s", e)

        try:
            r = matcher.compare(
                {'image_license': trip.get('entry_image_license')},
                {'image_license': trip.get('exit_image_license')}
            )
            if r.get('_comparison_success') or r.get('fingerprint_sim'):
                trip_results.append({
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
            logger.debug("Model B error: %s", e)

        if trip_results:
            try:
                trip_repo.save_trip_with_detection_results(trip_id, passid, trip_results)
                detected += 1
                if any(r['is_suspicious'] for r in trip_results):
                    suspected += 1
            except Exception as e:
                logger.error("Save error for %s: %s", passid, e)

    return {"aggregated": 0, "detected": detected, "suspected": suspected}


def _execute_re_detect(trip_repo) -> dict:
    """补检测"""
    from apps.api.services.truck_obu_detector import TruckOBUDetector
    from apps.api.services.entry_exit_matcher import EntryExitMatcher

    trips = trip_repo.get_trips_without_visual(limit=500)
    detector = TruckOBUDetector()
    matcher = EntryExitMatcher()
    detected = 0
    suspected = 0

    for trip in trips:
        trip_id = trip['id']
        passid = trip['passid']
        trip_results = []

        if trip.get('entry_vehicle_type') == 1 and trip.get('entry_image_trans'):
            try:
                r = detector.detect({
                    'VEHICLETYPE': trip.get('entry_vehicle_type'),
                    'image_trans': trip.get('entry_image_trans')
                })
                if r.get('visual_vehicle_type'):
                    is_sus = 1 if r.get('is_suspicious') else 0
                    trip_results.append({
                        'audit_trip_id': trip_id,
                        'fraud_type': 'TRUCK_USES_PASSENGER_OBU',
                        'entry_vehicle_type': trip.get('entry_vehicle_type'),
                        'entry_visual_type': r.get('visual_vehicle_type'),
                        'is_suspicious': is_sus,
                        'risk_score': r.get('confidence', 0) if is_sus else 0,
                        'details': json.dumps(r)
                    })
            except Exception:
                pass

        if trip.get('entry_image_license') and trip.get('exit_image_license'):
            try:
                r = matcher.compare(
                    {'image_license': trip.get('entry_image_license')},
                    {'image_license': trip.get('exit_image_license')}
                )
                if r.get('_comparison_success') or r.get('fingerprint_sim'):
                    trip_results.append({
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
            except Exception:
                pass

        if trip_results:
            try:
                trip_repo.save_trip_with_detection_results(trip_id, passid, trip_results)
                detected += 1
                if any(r['is_suspicious'] for r in trip_results):
                    suspected += 1
            except Exception:
                pass

    return {"aggregated": 0, "detected": detected, "suspected": suspected}
