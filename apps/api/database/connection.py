"""
数据库连接管理
"""

import sqlite3
import os
from typing import Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "audit.db")


def ensure_db_dir():
    """确保数据库目录存在"""
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)


def get_connection():
    """获取数据库连接"""
    ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_db_path():
    """获取数据库路径"""
    return DB_PATH


def init_db():
    """初始化数据库表"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
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
        audit_status TEXT DEFAULT 'PENDING',
        risk_score REAL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        updated_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_passid ON audit_trips(passid)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trips_status ON audit_trips(audit_status)")

    cursor.execute("""
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
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (audit_trip_id) REFERENCES audit_trips(id)
    )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_results_type ON audit_results(fraud_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_results_status ON audit_results(process_status)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS aggregation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        passid TEXT NOT NULL,
        step_name TEXT NOT NULL,
        step_status TEXT NOT NULL,
        step_result TEXT,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_task ON aggregation_logs(task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_passid ON aggregation_logs(passid)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        result_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        operator TEXT,
        comments TEXT,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (result_id) REFERENCES audit_results(id)
    )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_result ON audit_actions(result_id)")

    conn.commit()
    conn.close()
