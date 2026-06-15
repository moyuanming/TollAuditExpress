"""TruckObuStatsRepository 单元测试 — 每日统计仓储

行为契约:
  - upsert_daily_stat 不存在 → INSERT
  - upsert_daily_stat 已存在 → 累加 (scanned_count / suspicious_count)
  - get_daily_stats 按 (date, fraud_type) 过滤、按 date 排序
  - get_overview 累计扫描/异常/确认 + 最近执行时间
"""

import pytest

from apps.api.database.repositories.truck_obu_stats_repository import TruckObuStatsRepository


@pytest.fixture
def repo(temp_db):
    return TruckObuStatsRepository()


# ============================================================
# upsert_daily_stat
# ============================================================


class TestUpsertDailyStat:
    def test_insert_when_not_exists(self, repo):
        repo.upsert_daily_stat(
            date='2026-06-14',
            fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=10,
            suspicious_count_delta=3,
            last_run_at='2026-06-14 12:00:00',
        )

        stats = repo.get_daily_stats(fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A')
        assert len(stats) == 1
        assert stats[0]['date'] == '2026-06-14'
        assert stats[0]['scanned_count'] == 10
        assert stats[0]['suspicious_count'] == 3
        assert stats[0]['last_run_at'] == '2026-06-14 12:00:00'

    def test_upsert_accumulates_on_duplicate(self, repo):
        """ON CONFLICT 应累加计数,不是覆盖"""
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=10, suspicious_count_delta=3,
            last_run_at='2026-06-14 12:00:00',
        )
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=5, suspicious_count_delta=2,
            last_run_at='2026-06-14 13:00:00',
        )

        stats = repo.get_daily_stats(fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A')
        assert len(stats) == 1
        assert stats[0]['scanned_count'] == 15  # 10+5
        assert stats[0]['suspicious_count'] == 5  # 3+2
        # last_run_at 应被新值覆盖
        assert stats[0]['last_run_at'] == '2026-06-14 13:00:00'

    def test_separate_fraud_types_not_merged(self, repo):
        """不同 fraud_type 是不同行,不应互相覆盖"""
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=10, suspicious_count_delta=3,
            last_run_at='2026-06-14 12:00:00',
        )
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='OTHER_FRAUD',
            scanned_count_delta=20, suspicious_count_delta=7,
            last_run_at='2026-06-14 12:30:00',
        )

        a = repo.get_daily_stats(fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A')
        b = repo.get_daily_stats(fraud_type='OTHER_FRAUD')
        assert a[0]['scanned_count'] == 10
        assert b[0]['scanned_count'] == 20


# ============================================================
# get_daily_stats
# ============================================================


class TestGetDailyStats:
    def test_filter_by_date_range(self, repo):
        for day in ('2026-06-12', '2026-06-13', '2026-06-14', '2026-06-15'):
            repo.upsert_daily_stat(
                date=day, fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
                scanned_count_delta=1, suspicious_count_delta=0,
                last_run_at=f'{day} 12:00:00',
            )

        stats = repo.get_daily_stats(
            from_date='2026-06-13', to_date='2026-06-14',
            fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
        )
        assert [s['date'] for s in stats] == ['2026-06-13', '2026-06-14']

    def test_no_filter_returns_all(self, repo):
        repo.upsert_daily_stat(
            date='2026-06-12', fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=1, suspicious_count_delta=0,
            last_run_at='2026-06-12 12:00:00',
        )
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=2, suspicious_count_delta=1,
            last_run_at='2026-06-14 12:00:00',
        )

        stats = repo.get_daily_stats()
        assert len(stats) == 2
        # 排序:date ASC
        assert stats[0]['date'] == '2026-06-12'
        assert stats[1]['date'] == '2026-06-14'

    def test_filter_by_fraud_type(self, repo):
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=10, suspicious_count_delta=3,
            last_run_at='2026-06-14 12:00:00',
        )
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='OTHER_FRAUD',
            scanned_count_delta=99, suspicious_count_delta=0,
            last_run_at='2026-06-14 12:00:00',
        )

        stats = repo.get_daily_stats(fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A')
        assert len(stats) == 1
        assert stats[0]['scanned_count'] == 10


# ============================================================
# get_overview
# ============================================================


class TestGetOverview:
    def test_empty_returns_zeros(self, repo):
        overview = repo.get_overview()
        assert overview['total_scanned'] == 0
        assert overview['total_suspicious'] == 0
        assert overview['total_confirmed'] == 0
        assert overview['last_run_at'] is None

    def test_aggregates_across_days(self, repo):
        repo.upsert_daily_stat(
            date='2026-06-13', fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=10, suspicious_count_delta=3,
            last_run_at='2026-06-13 23:00:00',
        )
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
            scanned_count_delta=20, suspicious_count_delta=7,
            last_run_at='2026-06-14 12:00:00',
        )
        repo.upsert_daily_stat(
            date='2026-06-14', fraud_type='OTHER_FRAUD',
            scanned_count_delta=100, suspicious_count_delta=0,
            last_run_at='2026-06-14 13:00:00',
        )

        overview = repo.get_overview()
        assert overview['total_scanned'] == 130  # 10+20+100
        assert overview['total_suspicious'] == 10  # 3+7+0
        # last_run_at 应为最近一次的时间 (MAX)
        assert overview['last_run_at'] == '2026-06-14 13:00:00'
