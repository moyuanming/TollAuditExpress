"""Landing Lead 路由 — 公开 POST(表单提交)+ 鉴权 GET(后台查询)。

POST 端点带 IP 限流;GET 端点复用全局 auth_middleware(API_KEY / Bearer)。
"""
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from apps.api.core.logging_config import get_logger
from apps.api.core.rate_limit import SlidingWindowLimiter
from apps.api.database.repositories.landing_repository import LandingRepository
from packages.contracts.types.schemas import (
    LandingLeadCreate,
    LandingLeadListResponse,
    LandingLeadResponse,
)

logger = get_logger(__name__)
router = APIRouter()

# 单进程内存限流:5 req/min/IP
_lead_limiter = SlidingWindowLimiter(max_requests=5, window_seconds=60)


def _client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown"))


@router.post("/leads", response_model=LandingLeadResponse, status_code=201)
async def submit_lead(payload: LandingLeadCreate, request: Request):
    """公开端点 — 落地页表单提交。"""
    if not _lead_limiter.allow(_client_ip(request)):
        return JSONResponse(
            status_code=429,
            content={"detail": "提交过于频繁,请稍后再试"},
        )
    repo = LandingRepository()
    lead_id = repo.insert({
        **payload.model_dump(),
        "ip": _client_ip(request),
        "ua": request.headers.get("user-agent", "")[:512],
    })
    # 回读以拿到 created_at
    rows, _ = repo.list_paginated(limit=1, offset=0)
    row = next((r for r in rows if r["id"] == lead_id), None)
    return LandingLeadResponse(**row) if row else LandingLeadResponse(
        id=lead_id, name=payload.name, phone=payload.phone, org=payload.org,
        email=payload.email, message=payload.message,
        source=payload.source, ip=None, ua=None, created_at="",
    )


@router.get("/leads", response_model=LandingLeadListResponse)
async def list_leads(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    """鉴权端点 — 后台临时查询,带 API_KEY 或 Bearer 即可。"""
    repo = LandingRepository()
    rows, total = repo.list_paginated(limit=limit, offset=offset)
    return LandingLeadListResponse(leads=rows, total=total, limit=limit, offset=offset)
