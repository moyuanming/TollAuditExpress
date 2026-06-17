"""
数据库连接管理
"""

import glob
import os
import sqlite3
from contextlib import contextmanager

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "audit.db")
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def ensure_db_dir():
    """确保数据库目录存在"""
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)


@contextmanager
def get_connection():
    """获取数据库连接（上下文管理器，自动关闭）"""
    ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def get_db_path():
    """获取数据库路径"""
    return DB_PATH


def init_db():
    """初始化数据库表"""
    with get_connection() as conn:
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
            entry_visual_type TEXT,
            exit_visual_type TEXT,
            fingerprint_sim REAL,
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

        # Schema version tracking
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """)

        conn.commit()

    # Run incremental migrations
    _run_migrations()


def _run_migrations():
    """执行未应用的增量迁移"""
    if not os.path.exists(MIGRATIONS_DIR):
        return

    with get_connection() as conn:
        cursor = conn.cursor()

        # Get current version
        cursor.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
        current_version = cursor.fetchone()[0]

        # Find and sort migration files
        migration_files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
        for mf in migration_files:
            basename = os.path.basename(mf)
            try:
                version = int(basename.split('_')[0])
            except (ValueError, IndexError):
                continue

            if version <= current_version:
                continue

            with open(mf) as f:
                sql = f.read()

            # Execute each statement separately (SQLite doesn't support multi-statement executes well)
            for statement in sql.split(';'):
                # Strip comment lines so leading comments don't block execution
                lines = statement.split('\n')
                clean_lines = [l for l in lines if not l.strip().startswith('--')]
                statement = '\n'.join(clean_lines).strip()
                if statement:
                    try:
                        cursor.execute(statement)
                    except sqlite3.OperationalError as e:
                        # Column already exists — safe to skip
                        if 'duplicate column name' in str(e).lower():
                            continue
                        raise

            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            conn.commit()
