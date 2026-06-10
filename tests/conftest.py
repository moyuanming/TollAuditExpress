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

    def execute(self, sql: str, params=None):
        sql = sql.replace("%s", "?")
        if params is not None:
            self._cur = self._conn.execute(sql, params)
        else:
            self._cur = self._conn.execute(sql)
        self.lastrowid = self._cur.lastrowid if self._cur else None
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
        """每次调用创建新的 SQLite 连接，保证线程安全（llm_batch 用 ThreadPoolExecutor）。"""
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
def mock_ml_models():
    """Mock ML 模型，避免依赖 GPU 和模型文件"""
    import numpy as np

    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = [{'class': 'truck', 'confidence': 0.95}]

    mock_fp = MagicMock()
    mock_fp.extract_all_features.return_value = {
        'global': np.array([0.1] * 512),
        'parts': {},
        'color': 'blue'
    }

    with patch(
        'apps.api.services.entry_exit_matcher.VehicleClassifier',
        return_value=mock_classifier
    ), patch(
        'apps.api.services.truck_obu_detector.VehicleClassifier',
        return_value=mock_classifier
    ), patch(
        'apps.api.services.entry_exit_matcher.MultiPartFingerprint',
        return_value=mock_fp
    ), patch(
        'apps.api.services.truck_obu_detector.TruckOBUDetector._verify_with_llm',
        return_value=1
    ):
        yield


@pytest.fixture
def mock_image_download():
    """Mock 图片下载 — 需 patch 所有已导入该函数的模块"""
    fake_bytes = BytesIO(b'fake-image-data')
    with patch(
        'apps.api.services.entry_exit_matcher.download_image',
        return_value=fake_bytes
    ), patch(
        'apps.api.services.truck_obu_detector.download_image',
        return_value=fake_bytes
    ), patch(
        'apps.api.services.image_utils.download_image',
        return_value=fake_bytes
    ):
        yield
