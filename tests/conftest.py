"""共享测试 fixtures — Doris 迁移后版本

使用临时 SQLite 数据库代替生产 Doris，通过 monkeypatch doris_connection.get_connection 实现隔离。
SQLite 占位符 (?) 与 pymysql (%s) 不同，包装层自动转换。
"""

import os
import sys
import tempfile
import sqlite3
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
from io import BytesIO

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# SQLite 兼容建表 DDL（字段与 Doris DDL 对齐，类型适配 SQLite）
_TEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    passid TEXT UNIQUE NOT NULL,
    entry_time TEXT,
    entry_station_name TEXT,
    entry_lane_id TEXT,
    entry_vehicle_id TEXT,
    entry_vehicle_type INTEGER,
    entry_vehicle_color INTEGER,
    entry_obu_id TEXT,
    entry_media_type INTEGER,
    entry_image_license TEXT,
    entry_image_trans TEXT,
    exit_time TEXT,
    exit_station_name TEXT,
    exit_lane_id TEXT,
    exit_vehicle_id TEXT,
    exit_vehicle_type INTEGER,
    exit_vehicle_color INTEGER,
    exit_obu_id TEXT,
    exit_media_type INTEGER,
    exit_image_license TEXT,
    exit_image_trans TEXT,
    gantry_count INTEGER DEFAULT 0,
    gantry_records TEXT,
    audit_status TEXT DEFAULT 'PENDING',
    risk_score REAL DEFAULT 0,
    entry_visual_type TEXT,
    exit_visual_type TEXT,
    fingerprint_sim REAL,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_trip_id INTEGER NOT NULL,
    fraud_type TEXT NOT NULL,
    entry_vehicle_type INTEGER,
    entry_visual_type TEXT,
    entry_color TEXT,
    exit_vehicle_type INTEGER,
    exit_visual_type TEXT,
    exit_color TEXT,
    is_suspicious INTEGER DEFAULT 0,
    risk_score REAL DEFAULT 0,
    details TEXT,
    process_status TEXT DEFAULT 'UNPROCESSED',
    llm_is_same_vehicle INTEGER,
    llm_confidence REAL,
    llm_reason TEXT,
    llm_model TEXT,
    llm_checked_at TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    operator TEXT,
    comments TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    task_type TEXT NOT NULL DEFAULT 'aggregate_detect',
    filter_rules TEXT,
    schedule_type TEXT NOT NULL DEFAULT 'interval',
    schedule_config TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    next_run_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    result_summary TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS migration_log (
    version INTEGER PRIMARY KEY,
    description TEXT,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS detection_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    fraud_type TEXT NOT NULL,
    severity INTEGER DEFAULT 2,
    description TEXT,
    rule_expr TEXT NOT NULL,
    threshold REAL DEFAULT 0.5,
    enabled INTEGER DEFAULT 1,
    dry_run INTEGER DEFAULT 0,
    source TEXT DEFAULT 'manual',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS gateway_topology (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_station TEXT NOT NULL,
    to_station TEXT NOT NULL,
    distance_km REAL,
    is_connected INTEGER DEFAULT 1,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- 007: 货车 OBU 监测 — 每日统计表
CREATE TABLE IF NOT EXISTS audit_truck_obu_daily_stats (
    date TEXT NOT NULL,
    fraud_type TEXT NOT NULL,
    scanned_count INTEGER NOT NULL DEFAULT 0,
    suspicious_count INTEGER NOT NULL DEFAULT 0,
    confirmed_count INTEGER NOT NULL DEFAULT 0,
    last_run_at TEXT,
    updated_at TEXT,
    PRIMARY KEY (date, fraud_type)
);

CREATE INDEX IF NOT EXISTS idx_truck_obu_stats_date
    ON audit_truck_obu_daily_stats(date);

-- 008: Landing Lead 线索表
CREATE TABLE IF NOT EXISTS landing_leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    org TEXT NOT NULL,
    email TEXT,
    message TEXT,
    source TEXT DEFAULT 'landing-page',
    ip TEXT,
    ua TEXT,
    created_at TEXT NOT NULL
);
"""


class _SQLiteCursorWrapper:
    """包装 sqlite3 cursor，行为对齐 pymysql DictCursor。

    - execute() 自动把 %s 替换为 ?（兼容 pymysql → SQLite）
    - fetchone() / fetchall() 返回 dict
    """

    def __init__(self, sqlite_conn: sqlite3.Connection):
        self._conn = sqlite_conn
        self._cur = None
        self.lastrowid = None
        self.rowcount = -1

    def execute(self, sql: str, params=None):
        sql = sql.replace("%s", "?")
        if params is not None:
            self._cur = self._conn.execute(sql, params)
        else:
            self._cur = self._conn.execute(sql)
        self.lastrowid = self._cur.lastrowid if self._cur else None
        self.rowcount = self._cur.rowcount if self._cur else -1
        return self

    def fetchone(self):
        if self._cur is None:
            return None
        row = self._cur.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        if self._cur is None:
            return []
        return [dict(r) for r in self._cur.fetchall()]


class _SQLiteConnectionWrapper:
    """包装 sqlite3 Connection，行为对齐 pymysql Connection。

    支持 cursor() 和 sqlite3 快捷 execute()（部分测试直接 conn.execute().fetchone()）。
    """

    def __init__(self, sqlite_conn: sqlite3.Connection):
        self._conn = sqlite_conn

    def cursor(self):
        return _SQLiteCursorWrapper(self._conn)

    def execute(self, sql: str, params=None):
        """sqlite3 快捷方式：conn.execute() → cursor。返回底层 sqlite3 Cursor
        以兼容 fetchone()/fetchall() 返回 sqlite3.Row（调用方用 dict(row) 转换）。"""
        if params is not None:
            return self._conn.execute(sql, params)
        return self._conn.execute(sql)

    def commit(self):
        self._conn.commit()

    def ping(self, reconnect=False):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.fixture
def temp_db():
    """提供隔离的临时 SQLite 数据库，替代生产 Doris。

    用 unittest.mock.patch 修补所有 import get_connection 的模块，
    让仓储层在测试中走 SQLite，同时自动转换 %s → ? 占位符。
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # 初始化一次 schema（数据持久化在文件里）
    _init_conn = sqlite3.connect(path)
    _init_conn.executescript(_TEST_SCHEMA)
    _init_conn.commit()
    _init_conn.close()

    @contextmanager
    def _test_get_connection():
        """每次调用创建新的 SQLite 连接，保证线程安全（ai_verify_batch 用 ThreadPoolExecutor）。"""
        new_conn = sqlite3.connect(path, check_same_thread=False)
        new_conn.row_factory = sqlite3.Row
        new_conn.create_function("NOW", 0, lambda: __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        try:
            yield _SQLiteConnectionWrapper(new_conn)
        finally:
            new_conn.close()

    patchers = [
        patch("apps.api.database.doris_connection.get_connection", _test_get_connection),
        patch("apps.api.database.doris_connection.init_doris", lambda *a, **kw: None),
        patch("apps.api.main.init_doris", lambda *a, **kw: None),
        patch("apps.api.database.connection.get_connection", _test_get_connection),
        patch("apps.api.database.repositories.trip_repository.get_connection", _test_get_connection),
        patch("apps.api.database.repositories.audit_repository.get_connection", _test_get_connection),
        patch("apps.api.database.repositories.task_repository.get_connection", _test_get_connection),
        patch("apps.api.database.repositories.rule_repository.get_connection", _test_get_connection),
        patch("apps.api.database.repositories.topology_repository.get_connection", _test_get_connection),
        patch("apps.api.database.repositories.truck_obu_stats_repository.get_connection", _test_get_connection),
        patch("apps.api.database.repositories.landing_repository.get_connection", _test_get_connection),
        patch("apps.api.services.rule_loader.get_connection", _test_get_connection),
    ]
    for p in patchers:
        p.start()

    yield path

    for p in patchers:
        p.stop()

    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def mock_ai_client():
    """Mock vehicle-ai-service 公共服务的 HTTP 客户端 — 走公共服务后,所有视觉比对都封到 client 上。

    注意:`get_client` 在 truck_obu_detector / entry_exit_matcher / vehicle_comparator / trip_aggregator
    四个模块里都是 `from apps.api.core.vehicle_ai_client import get_client`,import 时把函数对象
    拷到模块 namespace。要让 patch 生效,必须 patch 这 4 处的本地绑定,不能只 patch 源模块。
    """
    fake = MagicMock()
    fake.truck_obu.return_value = {
        'is_suspicious': True,
        'fraud_type': 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A',
        'visual_vehicle_type': 'truck',
        'is_truck': True,
        'confidence': 0.95,
        'llm_verified': True,
        'llm_confidence': 0.93,
    }
    fake.entry_exit.return_value = {
        'is_suspicious': False,
        'fraud_type': None,
        'color_match': True,
        'type_match': True,
        'fingerprint_sim': 0.92,
        'entry_color': 'blue',
        'exit_color': 'blue',
        'entry_visual_type': 'truck',
        'exit_visual_type': 'truck',
        'comparison_success': True,
    }
    fake.compare.return_value = {
        'is_same_vehicle': True,
        'confidence': 0.92,
        'reason': '车牌号一致',
        'model': 'qwen2.5-vl-72b',
    }
    fake.recognize_plate.return_value = {
        'plate': '京A12345',
        'confidence': 0.95,
    }
    patchers = [
        patch("apps.api.core.vehicle_ai_client.get_client", return_value=fake),
        patch("apps.api.services.passenger_obu_detector.get_client", return_value=fake),
        patch("apps.api.services.entry_exit_matcher.get_client", return_value=fake),
        patch("apps.api.services.vehicle_comparator.get_client", return_value=fake),
    ]
    for p in patchers:
        p.start()
    try:
        yield fake
    finally:
        for p in patchers:
            p.stop()


@pytest.fixture
def mock_image_download():
    """Mock 图片下载 — 视觉检测器走公共服务后不再调用本地下载,但保留为 no-op 以避免依赖业务代码里残留的 import。"""
    fake_bytes = BytesIO(b'fake-image-data')
    with patch(
        'apps.api.services.entry_exit_matcher.download_image',
        return_value=fake_bytes
    ), patch(
        'apps.api.services.image_utils.download_image',
        return_value=fake_bytes
    ):
        yield fake_bytes
