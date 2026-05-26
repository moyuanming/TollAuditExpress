"""健康检查路由"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok"}


@router.get("/health/db")
async def db_health_check():
    from apps.api.database.connection import get_connection
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM audit_trips")
        result = cursor.fetchone()
        conn.close()
        return {"status": "ok", "trips_count": result["count"]}
    except Exception as e:
        return {"status": "error", "message": str(e)}
