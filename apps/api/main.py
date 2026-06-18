"""
FastAPI 应用入口
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import FileResponse

from apps.api.core.auth import auth_middleware

# 注：dotenv 由 apps.api.core.config 顶部负责，此处无需重复加载
from apps.api.core.config import CORS_ORIGINS
from apps.api.database.doris_connection import init_doris
from apps.api.routers import audit, health, landing, oauth, rules, tasks
from apps.api.services.task_scheduler import start_scheduler

FRONTEND_DIR = os.environ.get("FRONTEND_DIR", os.path.join(os.path.dirname(__file__), "..", "web", "dist"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_doris()
    start_scheduler()
    app.state.truck_detector = None
    app.state.entry_exit_matcher = None
    app.state.aggregation_tasks = {}
    yield


app = FastAPI(title="TollAuditExpress API", description="高速公路收费稽核系统", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    return await auth_middleware(request, call_next)


app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(tasks.router, prefix="/api", tags=["tasks"])
app.include_router(rules.router, prefix="/api/audit", tags=["rules"])
app.include_router(oauth.router)
app.include_router(landing.router, prefix="/api/landing", tags=["landing"])


@app.get("/")
async def root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path, headers={"Cache-Control": "no-cache, must-revalidate"})
    return {"message": "TollAuditExpress API", "version": "1.0.0"}


# Serve frontend static files if built
if os.path.isdir(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

    @app.middleware("http")
    async def spa_fallback(request: Request, call_next):
        """Catch-all: serve index.html for SPA routes (must run before auth middleware)"""
        path = request.url.path
        # Skip API/static paths
        if (
            path.startswith("/api/")
            or path.startswith("/health")
            or path.startswith("/docs")
            or path.startswith("/openapi.json")
            or path.startswith("/redoc")
            or path.startswith("/assets/")
        ):
            return await call_next(request)
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path, headers={"Cache-Control": "no-cache, must-revalidate"})
        return await call_next(request)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
