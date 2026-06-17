"""健康检查路由"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/health/db")
async def db_health_check():
    from apps.api.database.doris_connection import get_connection
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM audit_trips")
            result = cursor.fetchone()
        return {"status": "ok", "trips_count": result["count"]}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/health/doris")
async def doris_health_check():
    """详细 Doris 健康检查：连接、连接池、表行数、副本状态。

    返回字段：
    - status: "ok" | "degraded" | "error"
    - target_db: 稽核目标库 (ods_AI_DB) 连接状态、版本、表行数
    - source_db: 数据源库 (dwd_tolldata) 连接状态
    - pool: 连接池大小和可用数
    - backends: Doris 后端节点存活状态
    """
    from apps.api.database.doris_connection import _POOL_SIZE, _pool, get_connection

    result: dict = {
        "status": "ok",
        "target_db": {},
        "source_db": {},
        "pool": {
            "max_size": _POOL_SIZE,
            "available": _pool.qsize() if _pool is not None else 0,
            "initialized": _pool is not None,
        },
    }

    # ── 稽核目标库 (ods_AI_DB) ──
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            result["target_db"]["connected"] = True
    except Exception as e:
        result["status"] = "error"
        result["target_db"]["connected"] = False
        result["target_db"]["error"] = str(e)

    if result["target_db"].get("connected"):
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT VERSION() AS version")
                ver = cur.fetchone()
                result["target_db"]["version"] = ver.get("version", "unknown") if ver else "unknown"
        except Exception:
            result["target_db"]["version"] = "unknown"

        tables = ["audit_trips", "audit_results", "audit_actions",
                  "scheduled_tasks", "task_executions"]
        counts: dict[str, int] = {}
        for t in tables:
            try:
                with get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(f"SELECT COUNT(*) AS cnt FROM {t}")
                    counts[t] = cur.fetchone()["cnt"]
            except Exception:
                counts[t] = -1
        result["target_db"]["table_counts"] = counts

        # 后端节点存活状态
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SHOW BACKENDS")
                backends = cur.fetchall()
                result["backends"] = {
                    "total": len(backends),
                    "alive": sum(1 for b in backends if b.get("Alive", "").lower() == "true"),
                }
        except Exception:
            result["backends"] = {"total": -1, "alive": -1}

    # ── 数据源库 (dwd_tolldata) ──
    try:
        import pymysql

        from apps.api.core import config
        src = pymysql.connect(
            host=config.DB_HOST, port=config.DB_PORT,
            user=config.DB_USER, password=config.DB_PASSWORD,
            database=config.DB_NAME,
            charset="utf8mb4", connect_timeout=5,
        )
        try:
            cur = src.cursor()
            cur.execute("SELECT 1")
            result["source_db"]["connected"] = True
            cur.execute("SELECT VERSION() AS version")
            ver = cur.fetchone()
            result["source_db"]["version"] = ver.get("version", "unknown") if ver else "unknown"
        finally:
            src.close()
    except Exception as e:
        if result["status"] == "ok":
            result["status"] = "degraded"
        result["source_db"]["connected"] = False
        result["source_db"]["error"] = str(e)

    return result
