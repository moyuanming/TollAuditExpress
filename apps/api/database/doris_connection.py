"""Doris 连接管理(稽核目标库 ods_AI_DB)。

与 SQLite 时代 `connection.py` 的使用方式保持一致: 提供 `get_connection()` 上下文管理器,
返回的连接带 DictCursor, 业务代码用 `with get_connection() as conn:` 风格。

线程安全连接池(基于 queue.Queue + lazy init), 容量 8, ping 复用, 出池后自动 ping/reconnect。
"""

import os
import queue
import threading
from contextlib import contextmanager

import pymysql
from pymysql.constants import FIELD_TYPE
from pymysql.converters import conversions
from pymysql.cursors import DictCursor

from apps.api.core import config
from apps.api.core.logging_config import get_logger

logger = get_logger(__name__)

# pymysql 默认返回 datetime 对象, 但 SQLite 返回字符串, 这里统一为字符串避免 Pydantic 校验报错
_conv = conversions.copy()
_conv[FIELD_TYPE.DATETIME] = str
_conv[FIELD_TYPE.TIMESTAMP] = str
_conv[FIELD_TYPE.DATE] = str
_conv[FIELD_TYPE.TIME] = str

_POOL_SIZE = int(os.getenv("DORIS_POOL_SIZE", "8"))
_pool: "queue.Queue[pymysql.connections.Connection]" = None
_pool_lock = threading.Lock()
_SCHEMA_VERSION = 1


def _new_connection() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=config.DB_AUDIT_HOST,
        port=config.DB_AUDIT_PORT,
        user=config.DB_AUDIT_USER,
        password=config.DB_AUDIT_PASSWORD,
        database=config.DB_AUDIT_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
        conv=_conv,
        autocommit=True,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )


def _get_pool() -> "queue.Queue[pymysql.connections.Connection]":
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            _pool = queue.Queue(maxsize=_POOL_SIZE)
            for _ in range(_POOL_SIZE):
                _pool.put(_new_connection())
            logger.info("Doris pool initialized: size=%d host=%s db=%s",
                        _POOL_SIZE, config.DB_AUDIT_HOST, config.DB_AUDIT_NAME)
    return _pool


@contextmanager
def get_connection():
    """从池里取连接, 用完归还。连接断开时自动重连。"""
    pool = _get_pool()
    conn = pool.get()
    try:
        try:
            conn.ping(reconnect=True)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            conn = _new_connection()
        # 取出时 rollback，确保不在残留事务快照中
        try:
            conn.rollback()
        except Exception:
            pass
        yield conn
    finally:
        # 归还前 rollback，清除残留事务避免后续读到旧快照
        try:
            conn.rollback()
        except Exception:
            pass
        pool.put(conn)


def init_doris() -> None:
    """启动时跑 DDL(幂等)。"""
    ddl_path = os.path.join(os.path.dirname(__file__), "doris_ddl.sql")
    if not os.path.exists(ddl_path):
        logger.warning("DDL file not found: %s", ddl_path)
        return
    with open(ddl_path, "r", encoding="utf-8") as f:
        sql = f.read()
    # 先剥注释行,再按 ; 切分,过滤掉空段。注释夹在语句中间不会破坏 SQL。
    def _strip_sql_comments(s: str) -> str:
        return "\n".join(line for line in s.split("\n")
                         if not line.strip().startswith("--")).strip()
    statements = [_strip_sql_comments(s) for s in sql.split(";")]
    statements = [s for s in statements if s]
    with get_connection() as conn:
        cur = conn.cursor()
        failed = 0
        for stmt in statements:
            try:
                cur.execute(stmt)
            except Exception as e:
                msg = str(e).lower()
                if "already exist" in msg or "duplicate" in msg:
                    continue
                failed += 1
                logger.warning("DDL statement failed (continuing): %s | err=%s",
                               stmt[:80], str(e)[:200])
        try:
            conn.commit()
            cur.execute("INSERT INTO migration_log (version, description) VALUES (%s, %s)",
                        (_SCHEMA_VERSION, "init_doris() on startup"))
            conn.commit()
        except Exception as e:
            logger.warning("migration_log insert failed (continuing): %s", str(e)[:200])
    if failed:
        logger.warning("Doris schema init completed with %d DDL failures "
                       "(详见 doris_ddl.sql 兼容性,跟踪迁移计划)", failed)
    else:
        logger.info("Doris schema initialized (version=%d)", _SCHEMA_VERSION)
