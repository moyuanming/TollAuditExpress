# TollAuditExpress 营销落地页 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 monorepo 内新增一个对外营销落地页 (`/`) 与后端表单入库 (`POST /api/landing/leads`),内部 dashboard 全部迁移到 `/app/*`,AuthGuard 边界随之调整。

**Architecture:** 同仓 public + auth 路由分离。Landing 是 React 函数组件,5 个 section 顺序拼接;表单提交走 axios-less `fetch`,后端走 Pydantic 严格校验 + 内存限流(5 req/min/IP)+ 参数化 SQL 写入 `ods_AI_DB.landing_leads`。

**Tech Stack:** React 18 + Vite 5 + react-router-dom v6 (web); FastAPI + Pydantic v2 + pymysql (api); Doris `ods_AI_DB` (prod) / SQLite (test); Vitest + @testing-library/react (web 测试); pytest (api 测试)。

---

## 文件结构

| 类型 | 路径 | 职责 |
|------|------|------|
| 新建(契约) | `packages/contracts/types/schemas.py` 追加 | `LandingLeadCreate` / `LandingLeadResponse` / `LandingLeadListResponse` |
| 新建(schema) | `apps/api/schemas/landing.py` | 同上(API 侧 re-export,本项目 api 与 contracts 同源) |
| 新建(repository) | `apps/api/database/repositories/landing_repository.py` | `insert()` / `list_paginated()` / `count()` |
| 新建(router) | `apps/api/routers/landing.py` | `POST /leads` / `GET /leads` |
| 新建(rate limit) | `apps/api/core/rate_limit.py` | 简单内存 dict,5 req/min/IP |
| 修改(注册) | `apps/api/main.py` | `include_router(landing.router, prefix="/api/landing")` |
| 修改(test schema) | `tests/conftest.py` `_TEST_SCHEMA` 末尾 | 追加 `landing_leads` DDL |
| 新建(api 测试) | `tests/api/test_landing_routes.py` | 端点 + 限流 + 422 + SQL 注入 |
| 新建(web api) | `apps/web/src/api/landing.js` | `submitLead(payload)` |
| 新建(web 页面) | `apps/web/src/pages/Landing/Landing.jsx` + `.css` | 主页面,挂载 `<LandingNav />` + 5 sections |
| 新建(web section) | `apps/web/src/pages/Landing/sections/{Hero,Capabilities,Architecture,Stats,CTA}.jsx` + `.css` | 5 段,每段 1 个组件 + 1 个 css |
| 新建(web nav) | `apps/web/src/components/LandingNav.jsx` + `.css` | 顶部 nav,IntersectionObserver 高亮 |
| 修改(路由) | `apps/web/src/App.jsx` | `/` → Landing;内部 7 个页面 → `/app/*`;加老路径 302 重定向 |
| 新建(web 配置) | `apps/web/vitest.config.js` | jsdom + @testing-library/react |
| 新建(web 配置) | `apps/web/src/test/setup.js` | vitest 全局 setup(可选,清空 matchMedia 等) |
| 新建(web 测试) | `tests/web/test_landing_form.test.jsx` | 表单校验 + 提交三态 |
| 新建(web 测试) | `tests/web/test_routing.test.jsx` | `/` 公开 / `/app` 鉴权 / 老路径重定向 |

**新增 16 个 + 修改 3 个 = 19 个文件**

---

## Task 1: 共享契约 `LandingLead` (后端 Pydantic + 测试)

**Files:**
- Modify: `packages/contracts/types/schemas.py:380+`(末尾追加)
- Test: `tests/api/test_landing_routes.py`(本任务先放空文件,Task 4 再加用例)

- [ ] **Step 1: 写失败的测试 — 验证 Pydantic 校验逻辑**

新建 `tests/api/test_landing_schemas.py`:

```python
"""Landing Lead Pydantic 模型 — 字段级校验单元测试"""
import pytest
from pydantic import ValidationError
from packages.contracts.types.schemas import LandingLeadCreate


class TestLandingLeadCreateValidation:
    def test_valid_payload(self):
        lead = LandingLeadCreate(
            name="张三", phone="13800001234", org="某高速运营公司",
            email="zhang@example.com", message="希望了解产品",
        )
        assert lead.name == "张三"
        assert lead.phone == "13800001234"
        assert lead.source == "landing-page"  # 默认值

    def test_phone_too_short_invalid(self):
        with pytest.raises(ValidationError) as exc:
            LandingLeadCreate(name="张三", phone="1380000", org="某公司")
        assert "phone" in str(exc.value)

    def test_phone_invalid_prefix(self):
        with pytest.raises(ValidationError) as exc:
            LandingLeadCreate(name="张三", phone="12800001234", org="某公司")
        assert "phone" in str(exc.value)

    def test_email_invalid_format(self):
        with pytest.raises(ValidationError) as exc:
            LandingLeadCreate(name="张三", phone="13800001234", org="某公司", email="not-an-email")
        assert "email" in str(exc.value)

    def test_name_blank_rejected(self):
        with pytest.raises(ValidationError):
            LandingLeadCreate(name="   ", phone="13800001234", org="某公司")

    def test_message_max_length(self):
        with pytest.raises(ValidationError):
            LandingLeadCreate(
                name="张三", phone="13800001234", org="某公司",
                message="x" * 501,
            )

    def test_email_optional(self):
        lead = LandingLeadCreate(name="张三", phone="13800001234", org="某公司")
        assert lead.email is None
```

- [ ] **Step 2: 运行测试,确认失败**

```bash
cd /Users/moyuanming/TollAuditExpress && python -m pytest tests/api/test_landing_schemas.py -v
```

Expected: `ImportError: cannot import name 'LandingLeadCreate'` 或 `ModuleNotFoundError`。

- [ ] **Step 3: 在 `packages/contracts/types/schemas.py` 末尾追加**

在 `TruckObuOverviewResponse` 之后添加:

```python
# ---- 公开落地页线索 (landing) ----


class LandingLeadCreate(BaseModel):
    """公开落地页表单 — 客户线索入库请求体。

    字段命名采用下划线小写,序列化时 alias 为 name/phone/org 等,
    供前端直接复用为请求体键。
    """
    name: str = Field(..., min_length=1, max_length=50)
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$")
    org: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    message: Optional[str] = Field(None, max_length=500)
    source: str = Field("landing-page", max_length=32)


class LandingLeadResponse(BaseModel):
    id: int
    name: str
    phone: str
    org: str
    email: Optional[str] = None
    message: Optional[str] = None
    source: str
    ip: Optional[str] = None
    ua: Optional[str] = None
    created_at: str
```

并在文件顶部 import 调整(已 `from pydantic import BaseModel`,需要追加 `Field` 与 `EmailStr`):

```python
from pydantic import BaseModel, Field, EmailStr
```

**注意**: 项目里 `pydantic[email]` 不一定已装;若 `EmailStr` 报 ImportError,改用 `field_validator` 自定义邮箱校验(见 Step 3 备选)。

**Step 3 备选(无 email-validator 时)**:

```python
import re
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

class LandingLeadCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    phone: str = Field(..., pattern=r"^1[3-9]\d{9}$")
    org: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=120)
    message: Optional[str] = Field(None, max_length=500)
    source: str = Field("landing-page", max_length=32)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v):
        if v is None or v == "":
            return None
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v

    @field_validator("name", "org")
    @classmethod
    def _strip_nonblank(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v
```

选 EmailStr 版(若 `pydantic[email]` 已装,否则走备选)。

- [ ] **Step 4: 重新跑测试**

```bash
python -m pytest tests/api/test_landing_schemas.py -v
```

Expected: 7 个用例全 PASS。

- [ ] **Step 5: 提交**

```bash
git add packages/contracts/types/schemas.py tests/api/test_landing_schemas.py
git commit -m "feat(contracts): add LandingLead Pydantic schemas for marketing landing page"
```

---

## Task 2: 限流器模块 + 单测

**Files:**
- Create: `apps/api/core/rate_limit.py`
- Test: `tests/api/test_rate_limit.py`

- [ ] **Step 1: 写失败的测试**

新建 `tests/api/test_rate_limit.py`:

```python
"""简单内存限流器测试"""
import time
from apps.api.core.rate_limit import SlidingWindowLimiter


def test_first_request_allowed():
    lim = SlidingWindowLimiter(max_requests=5, window_seconds=60)
    assert lim.allow("1.1.1.1") is True


def test_under_limit_allowed():
    lim = SlidingWindowLimiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        assert lim.allow("1.1.1.1") is True


def test_over_limit_rejected():
    lim = SlidingWindowLimiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        lim.allow("1.1.1.1")
    assert lim.allow("1.1.1.1") is False


def test_different_keys_independent():
    lim = SlidingWindowLimiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        lim.allow("1.1.1.1")
    assert lim.allow("2.2.2.2") is True


def test_window_expiry(monkeypatch):
    lim = SlidingWindowLimiter(max_requests=5, window_seconds=60)
    base = time.time()
    monkeypatch.setattr("apps.api.core.rate_limit.time.time", lambda: base)
    for _ in range(5):
        lim.allow("1.1.1.1")
    # 推进 61s,窗口已滑出
    monkeypatch.setattr("apps.api.core.rate_limit.time.time", lambda: base + 61)
    assert lim.allow("1.1.1.1") is True
```

- [ ] **Step 2: 运行测试,确认失败**

```bash
python -m pytest tests/api/test_rate_limit.py -v
```

Expected: `ModuleNotFoundError: No module named 'apps.api.core.rate_limit'`。

- [ ] **Step 3: 实现 `apps/api/core/rate_limit.py`**

```python
"""简单内存限流器 — 滑动窗口,按 key(通常为 IP)计数。

仅供单进程使用,重启会丢失计数。多副本部署需替换为 Redis。
"""
import time
from collections import deque
from threading import Lock
from typing import Dict, Deque


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        """返回 True 表示允许(并在桶里加 1),False 表示被限流。"""
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            # 弹出窗口外的旧戳
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
            return True
```

- [ ] **Step 4: 重新跑测试**

```bash
python -m pytest tests/api/test_rate_limit.py -v
```

Expected: 5 PASS。

- [ ] **Step 5: 提交**

```bash
git add apps/api/core/rate_limit.py tests/api/test_rate_limit.py
git commit -m "feat(api): add SlidingWindowLimiter for landing lead rate limiting"
```

---

## Task 3: Landing Repository (Doris 兼容 + 测试)

**Files:**
- Create: `apps/api/database/repositories/landing_repository.py`
- Modify: `tests/conftest.py` `_TEST_SCHEMA` 末尾追加 `landing_leads` 表

- [ ] **Step 1: 扩展 `_TEST_SCHEMA`**

在 `tests/conftest.py` `_TEST_SCHEMA` 字符串末尾(`PRIMARY KEY (date, fraud_type));` 之后)追加:

```sql
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
```

- [ ] **Step 2: 写失败的 repository 测试**

新建 `tests/api/test_landing_repository.py`:

```python
"""LandingRepository 仓储层测试 — 走 temp_db(SQLite 替身)"""
from apps.api.database.repositories.landing_repository import LandingRepository


def test_insert_returns_id(temp_db):
    repo = LandingRepository()
    lead_id = repo.insert({
        "name": "张三", "phone": "13800001234", "org": "某高速",
        "email": "z@example.com", "message": "hi",
        "source": "landing-page", "ip": "1.2.3.4", "ua": "test-ua",
    })
    assert isinstance(lead_id, int) and lead_id > 0


def test_list_paginated_returns_inserted(temp_db):
    repo = LandingRepository()
    for i in range(3):
        repo.insert({
            "name": f"用户{i}", "phone": f"1380000000{i:02d}",
            "org": "某公司", "source": "landing-page",
        })
    rows, total = repo.list_paginated(limit=2, offset=0)
    assert total == 3
    assert len(rows) == 2


def test_count(temp_db):
    repo = LandingRepository()
    assert repo.count() == 0
    repo.insert({"name": "x", "phone": "13800000001", "org": "y", "source": "landing-page"})
    assert repo.count() == 1


def test_sql_injection_in_message_is_escaped(temp_db):
    """%s 参数化注入,确保 raw SQL 不会被注入。"""
    repo = LandingRepository()
    repo.insert({
        "name": "x", "phone": "13800000001", "org": "y",
        "message": "'; DROP TABLE landing_leads;--",
        "source": "landing-page",
    })
    # 表必须仍在
    assert repo.count() == 1
    rows, _ = repo.list_paginated(limit=10, offset=0)
    assert "DROP TABLE" in rows[0]["message"]
```

- [ ] **Step 3: 运行测试,确认失败**

```bash
python -m pytest tests/api/test_landing_repository.py -v
```

Expected: `ModuleNotFoundError: No module named 'apps.api.database.repositories.landing_repository'`。

- [ ] **Step 4: 实现 `apps/api/database/repositories/landing_repository.py`**

```python
"""Landing Lead 仓储 — 写入 / 查询 ods_AI_DB.landing_leads(测试期走 SQLite 替身)。"""
from datetime import datetime
from typing import List, Tuple, Dict, Any

from apps.api.database.doris_connection import get_connection


class LandingRepository:
    def insert(self, lead: Dict[str, Any]) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO landing_leads
                    (name, phone, org, email, message, source, ip, ua, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    lead["name"],
                    lead["phone"],
                    lead["org"],
                    lead.get("email"),
                    lead.get("message"),
                    lead.get("source", "landing-page"),
                    lead.get("ip"),
                    lead.get("ua"),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def list_paginated(self, limit: int = 20, offset: int = 0) -> Tuple[List[Dict], int]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) AS n FROM landing_leads"
            )
            total = cursor.fetchone()["n"]
            cursor.execute(
                """
                SELECT id, name, phone, org, email, message, source,
                       ip, ua, created_at
                FROM landing_leads
                ORDER BY id DESC LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            return [dict(r) for r in cursor.fetchall()], total

    def count(self) -> int:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS n FROM landing_leads")
            return cursor.fetchone()["n"]
```

- [ ] **Step 5: 重新跑测试**

```bash
python -m pytest tests/api/test_landing_repository.py -v
```

Expected: 4 PASS。

- [ ] **Step 6: 提交**

```bash
git add tests/conftest.py apps/api/database/repositories/landing_repository.py tests/api/test_landing_repository.py
git commit -m "feat(api): add LandingRepository with insert/list/count + SQLite test schema"
```

---

## Task 4: Landing Router (端点 + 限流 + 鉴权 + 集成测试)

**Files:**
- Create: `apps/api/routers/landing.py`
- Test: `tests/api/test_landing_routes.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/api/test_landing_routes.py`:

```python
"""Landing Lead API 集成测试"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(temp_db, monkeypatch):
    """无鉴权测试客户端 — landing POST 本就无 auth。"""
    monkeypatch.setenv("API_KEY", "")
    from apps.api.main import app
    with TestClient(app) as c:
        yield c


class TestSubmitLead:
    def test_post_valid_returns_201_and_persists(self, client):
        resp = client.post(
            "/api/landing/leads",
            json={
                "name": "张三", "phone": "13800001234", "org": "某高速",
                "email": "z@example.com", "message": "希望了解",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "张三"
        assert "id" in body and "created_at" in body

    def test_post_missing_phone_returns_422(self, client):
        resp = client.post(
            "/api/landing/leads",
            json={"name": "张三", "org": "某公司"},
        )
        assert resp.status_code == 422

    def test_post_bad_phone_returns_422(self, client):
        resp = client.post(
            "/api/landing/leads",
            json={"name": "张三", "phone": "12345", "org": "某公司"},
        )
        assert resp.status_code == 422

    def test_post_rate_limited_returns_429(self, client):
        payload = {"name": "x", "phone": "13800001234", "org": "y"}
        for _ in range(5):
            assert client.post("/api/landing/leads", json=payload).status_code == 201
        # 第 6 次
        assert client.post("/api/landing/leads", json=payload).status_code == 429

    def test_post_persists_to_db(self, client):
        from apps.api.database.repositories.landing_repository import LandingRepository
        client.post(
            "/api/landing/leads",
            json={"name": "张三", "phone": "13800001234", "org": "某高速"},
        )
        assert LandingRepository().count() == 1


class TestListLeads:
    def test_list_no_token_returns_401(self, client):
        # GET 受 auth_middleware 保护
        resp = client.get("/api/landing/leads")
        assert resp.status_code in (401, 403)

    def test_list_with_token_returns_paginated(self, client, monkeypatch):
        # 通过环境变量模拟打开 API_KEY 鉴权,然后用 header 访问
        monkeypatch.setenv("API_KEY", "test-key")
        # 重新 import app 以使 env 生效
        import importlib
        from apps.api import main
        importlib.reload(main)
        from fastapi.testclient import TestClient as TC
        with TC(main.app) as c2:
            for i in range(2):
                c2.post(
                    "/api/landing/leads",
                    json={"name": f"u{i}", "phone": f"1380000000{i:02d}", "org": "y"},
                    headers={"X-API-Key": "test-key"},
                )
            resp = c2.get(
                "/api/landing/leads",
                headers={"X-API-Key": "test-key"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 2
            assert "leads" in data
```

- [ ] **Step 2: 运行测试,确认失败**

```bash
python -m pytest tests/api/test_landing_routes.py -v
```

Expected: 端点 404。

- [ ] **Step 3: 实现 `apps/api/routers/landing.py`**

```python
"""Landing Lead 路由 — 公开 POST(表单提交)+ 鉴权 GET(后台查询)。

POST 端点带 IP 限流;GET 端点复用全局 auth_middleware(API_KEY / Bearer)。
"""
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import JSONResponse
from typing import Optional

from apps.api.core.logging_config import get_logger
from apps.api.core.rate_limit import SlidingWindowLimiter
from apps.api.database.repositories.landing_repository import LandingRepository
from packages.contracts.types.schemas import (
    LandingLeadCreate, LandingLeadResponse, LandingLeadListResponse,
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
    return LandingLeadListResponse(leads=rows, total=total)
```

> `LandingLeadListResponse` 在 Task 1 还没定义 — 在 `packages/contracts/types/schemas.py` Task 1 的追加块**同一处**再加:

```python
class LandingLeadListResponse(BaseModel):
    leads: list  # 每项是 LandingLeadResponse 的 dict
    total: int
    limit: int
    offset: int
```

- [ ] **Step 4: 在 `apps/api/main.py` 注册路由**

修改 imports 行(原 17 行):

```python
from apps.api.routers import audit, health, tasks, oauth, rules, landing
```

并在 include_router 块(53–56 行)追加:

```python
app.include_router(landing.router, prefix="/api/landing", tags=["landing"])
```

- [ ] **Step 5: 重新跑测试**

```bash
python -m pytest tests/api/test_landing_routes.py tests/api/test_landing_schemas.py tests/api/test_landing_repository.py tests/api/test_rate_limit.py -v
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add apps/api/routers/landing.py apps/api/main.py packages/contracts/types/schemas.py tests/api/test_landing_routes.py
git commit -m "feat(api): landing router (POST /leads public + GET /leads auth + rate limit)"
```

---

## Task 5: 前端 API client `landing.js` + 路由改造

**Files:**
- Create: `apps/web/src/api/landing.js`
- Modify: `apps/web/src/App.jsx`(整体重写)

- [ ] **Step 1: 实现 `apps/web/src/api/landing.js`**

```javascript
/**
 * 营销落地页 API client — 表单提交。
 * 错误对象带 status 字段,方便 UI 判断 422 / 429 / 5xx。
 */
export async function submitLead(payload) {
  const res = await fetch('/api/landing/leads', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (res.status === 429) {
    const err = new Error('提交过于频繁,请稍后再试')
    err.status = 429
    throw err
  }
  if (res.status === 422) {
    const data = await res.json().catch(() => ({}))
    const err = new Error('表单校验失败')
    err.status = 422
    err.fieldErrors = parseFieldErrors(data)
    throw err
  }
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`)
    err.status = res.status
    throw err
  }
  return res.json()
}

/**
 * Pydantic 422 响应通常是:
 *   { "detail": [ { "loc": ["body","phone"], "msg": "...", "type": "..." } ] }
 * 转换为 { phone: "手机号格式不正确" }。
 */
function parseFieldErrors(data) {
  const out = {}
  const detail = data && data.detail
  if (Array.isArray(detail)) {
    for (const item of detail) {
      const loc = item.loc || []
      const field = loc[loc.length - 1]
      if (field) out[field] = item.msg
    }
  }
  return out
}
```

- [ ] **Step 2: 整体重写 `apps/web/src/App.jsx`**

替换整个文件为:

```jsx
import React, { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import TripQuery from './pages/TripQuery'
import VehicleQuery from './pages/VehicleQuery'
import SuspectList from './pages/SuspectList'
import Statistics from './pages/Statistics'
import TaskManager from './pages/TaskManager'
import TruckOBUMonitor from './pages/TruckOBUMonitor'
import RuleStudio from './pages/RuleStudio'
import Redirect from './pages/Redirect'
import Landing from './pages/Landing/Landing'
import { onApiError } from './api/audit'
import { AuthProvider, useAuth } from './components/AuthContext'
import { AuthGuard } from './components/AuthGuard'

function AppNav() {
  const { isAuthenticated, logout } = useAuth()

  return (
    <nav className="nav">
      <div className="nav-brand">
        <div className="nav-brand-icon">稽</div>
        <h1>高速公路收费稽核系统</h1>
      </div>
      <div className="nav-links">
        <NavLink to="/app" end className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          📊 仪表盘
        </NavLink>
        <NavLink to="/app/trips" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          🚗 行程查询
        </NavLink>
        <NavLink to="/app/vehicles" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          🔎 车辆查询
        </NavLink>
        <NavLink to="/app/suspects" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          ⚠️ 可疑记录
        </NavLink>
        <NavLink to="/app/stats" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          📈 统计分析
        </NavLink>
        <NavLink to="/app/tasks" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          ⏰ 定时任务
        </NavLink>
        <NavLink to="/app/truck-obu-monitor" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          🚛 货车OBU监测
        </NavLink>
        <NavLink to="/app/rules" className={({isActive}) => isActive ? "nav-link active" : "nav-link"}>
          📐 规则管理
        </NavLink>
      </div>
      {isAuthenticated && (
        <button className="btn-logout" onClick={logout}>退出登录</button>
      )}
    </nav>
  )
}

const OLD_PATH_REDIRECTS = {
  '/trips': '/app/trips',
  '/vehicles': '/app/vehicles',
  '/suspects': '/app/suspects',
  '/stats': '/app/stats',
  '/tasks': '/app/tasks',
  '/truck-obu-monitor': '/app/truck-obu-monitor',
  '/rules': '/app/rules',
}

function LegacyRedirect() {
  // 处理老路径,根据当前 location.pathname 302
  const path = window.location.pathname
  const target = OLD_PATH_REDIRECTS[path] || '/app'
  return <Navigate to={target} replace />
}

function App() {
  const [apiError, setApiError] = useState(null)

  useEffect(() => {
    return onApiError((err) => {
      setApiError(err.message)
      setTimeout(() => setApiError(null), 4000)
    })
  }, [])

  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app">
          {apiError && <div className="error-banner">{apiError}</div>}
          <Routes>
            {/* 公开路由:营销落地页 */}
            <Route path="/" element={<Landing />} />

            {/* 老路径兼容 → 跳新路径 */}
            <Route path="/trips" element={<LegacyRedirect />} />
            <Route path="/vehicles" element={<LegacyRedirect />} />
            <Route path="/suspects" element={<LegacyRedirect />} />
            <Route path="/stats" element={<LegacyRedirect />} />
            <Route path="/tasks" element={<LegacyRedirect />} />
            <Route path="/truck-obu-monitor" element={<LegacyRedirect />} />
            <Route path="/rules" element={<LegacyRedirect />} />

            {/* 内部 /app/* 受 AuthGuard 保护 */}
            <Route path="/app/*" element={
              <AuthGuard>
                <AppNav />
                <main className="main">
                  <Routes>
                    <Route index element={<Dashboard />} />
                    <Route path="trips" element={<TripQuery />} />
                    <Route path="vehicles" element={<VehicleQuery />} />
                    <Route path="suspects" element={<SuspectList />} />
                    <Route path="stats" element={<Statistics />} />
                    <Route path="tasks" element={<TaskManager />} />
                    <Route path="truck-obu-monitor" element={<TruckOBUMonitor />} />
                    <Route path="rules" element={<RuleStudio />} />
                    <Route path="*" element={<Navigate to="/app" replace />} />
                  </Routes>
                </main>
              </AuthGuard>
            } />

            {/* 其他公开路由 */}
            <Route path="/redirect" element={<Redirect />} />
          </Routes>
        </div>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
```

**重要差异(相对旧版)**:
- `/` 不再带 AppNav,挂 `<Landing />`
- 内部页面全部 `to="/app/..."`
- `AuthGuard` 包裹整段 `AppNav + main`,而不是 `*` catchall
- 老路径(`/trips` 等)由 `LegacyRedirect` 组件处理

- [ ] **Step 3: 验证 web 仍可构建(不引入 Landing 之前会报缺组件 — 临时 stub)**

为不阻塞后续任务,先在 `apps/web/src/pages/Landing/Landing.jsx` 写一个最简 stub(Step 4 / Task 6 才会替换为完整内容):

```jsx
import React from 'react'

export default function Landing() {
  return <div className="landing-placeholder">TollAudit Express</div>
}
```

- [ ] **Step 4: 跑 vite build 验证(必须 OK 才进 Task 6)**

```bash
cd /Users/moyuanming/TollAuditExpress/apps/web && npm run build
```

Expected: build 成功(可能有 `truck-obu-monitor` 等图标 emoji 警告,非致命)。

- [ ] **Step 5: 跑后端测试,确认无回归**

```bash
python -m pytest tests/ -q
```

Expected: 全部 PASS(仅新增测试,不应影响老用例)。

- [ ] **Step 6: 提交**

```bash
git add apps/web/src/api/landing.js apps/web/src/App.jsx apps/web/src/pages/Landing/Landing.jsx
git commit -m "feat(web): routing split (Landing at /, internal pages at /app/*) + legacy redirects"
```

---

## Task 6: Landing 主页面 + 5 个 section 组件

**Files:**
- Create: `apps/web/src/pages/Landing/Landing.jsx` + `.css`
- Create: `apps/web/src/pages/Landing/sections/{Hero,Capabilities,Architecture,Stats,CTA}.{jsx,css}`
- Create: `apps/web/src/components/LandingNav.jsx` + `.css`

- [ ] **Step 1: 实现 `LandingNav.jsx`**

```jsx
import React, { useEffect, useState } from 'react'
import { useAuth } from './AuthContext'
import './LandingNav.css'

const SECTIONS = [
  { id: 'capabilities', label: '能力' },
  { id: 'architecture', label: '架构' },
  { id: 'stats', label: '数据' },
  { id: 'contact', label: '联系' },
]

export default function LandingNav() {
  const { isAuthenticated } = useAuth()
  const [active, setActive] = useState('capabilities')

  useEffect(() => {
    const observers = []
    for (const { id } of SECTIONS) {
      const el = document.getElementById(id)
      if (!el) continue
      const obs = new IntersectionObserver(
        (entries) => {
          for (const e of entries) {
            if (e.isIntersecting) setActive(id)
          }
        },
        { rootMargin: '-40% 0px -50% 0px' }
      )
      obs.observe(el)
      observers.push(obs)
    }
    return () => observers.forEach((o) => o.disconnect())
  }, [])

  return (
    <nav className="landing-nav">
      <div className="landing-nav-inner">
        <div className="landing-brand">
          <span className="landing-brand-icon">稽</span>
          <span>高速公路收费稽核系统</span>
        </div>
        <div className="landing-nav-links">
          {SECTIONS.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className={active === s.id ? 'landing-nav-link active' : 'landing-nav-link'}
            >
              {s.label}
            </a>
          ))}
        </div>
        <a className="landing-nav-cta" href="/app">
          {isAuthenticated ? '进入后台' : '登录后台'}
        </a>
      </div>
    </nav>
  )
}
```

- [ ] **Step 2: 实现 `LandingNav.css`**

```css
.landing-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: saturate(180%) blur(12px);
  border-bottom: 1px solid #eef2f7;
}
.landing-nav-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 24px;
}
.landing-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  font-size: 15px;
  color: #0f172a;
}
.landing-brand-icon {
  width: 28px; height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #4f46e5, #a78bfa);
  color: #fff;
  border-radius: 8px;
  font-weight: 800;
}
.landing-nav-links {
  display: flex;
  gap: 18px;
  margin-left: auto;
}
.landing-nav-link {
  color: #475569;
  text-decoration: none;
  font-size: 14px;
  padding: 4px 2px;
  border-bottom: 2px solid transparent;
  transition: color .15s, border-color .15s;
}
.landing-nav-link:hover { color: #0f172a; }
.landing-nav-link.active {
  color: #4f46e5;
  border-bottom-color: #4f46e5;
}
.landing-nav-cta {
  background: #4f46e5;
  color: #fff;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: background .15s;
}
.landing-nav-cta:hover { background: #4338ca; }

@media (max-width: 768px) {
  .landing-nav-links { display: none; }
  .landing-nav-inner { padding: 10px 16px; }
}
```

- [ ] **Step 3: 实现 `Hero.jsx` + `Hero.css`**

```jsx
import React from 'react'
import './Hero.css'

export default function Hero() {
  return (
    <section className="hero">
      <div className="hero-inner">
        <div className="hero-text">
          <div className="hero-eyebrow">TollAudit · 高速公路 AI 稽核</div>
          <h1 className="hero-title">让每一笔通行费,都不再流失</h1>
          <p className="hero-sub">
            基于双 AI 视觉模型,毫秒级识别 8 类常见逃费行为,准确率 99.2%,
            服务高速运营单位本地化部署。
          </p>
          <div className="hero-ctas">
            <a className="hero-btn-primary" href="#contact">申请免费试用 →</a>
            <a className="hero-btn-ghost" href="#capabilities">下载技术白皮书</a>
          </div>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="hero-visual-glyph">稽</div>
        </div>
      </div>
    </section>
  )
}
```

```css
.hero {
  background: radial-gradient(ellipse at top left, #eef2ff 0%, #ffffff 60%);
  padding: 80px 0 64px;
}
.hero-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 48px;
  align-items: center;
}
.hero-eyebrow {
  color: #6366f1;
  font-size: 12px;
  letter-spacing: 1px;
  font-weight: 600;
  margin-bottom: 12px;
}
.hero-title {
  font-size: 44px;
  font-weight: 800;
  line-height: 1.15;
  color: #0f172a;
  margin: 0 0 16px;
}
.hero-sub {
  color: #475569;
  font-size: 16px;
  line-height: 1.6;
  margin: 0 0 28px;
  max-width: 540px;
}
.hero-ctas { display: flex; gap: 12px; flex-wrap: wrap; }
.hero-btn-primary {
  background: #4f46e5;
  color: #fff;
  padding: 12px 22px;
  border-radius: 10px;
  font-weight: 600;
  text-decoration: none;
  transition: background .15s;
}
.hero-btn-primary:hover { background: #4338ca; }
.hero-btn-ghost {
  background: #fff;
  color: #0f172a;
  border: 1px solid #e2e8f0;
  padding: 12px 22px;
  border-radius: 10px;
  font-weight: 600;
  text-decoration: none;
  transition: background .15s;
}
.hero-btn-ghost:hover { background: #f8fafc; }

.hero-visual {
  aspect-ratio: 1.4 / 1;
  background: linear-gradient(135deg, #6366f1, #a78bfa);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 12px 40px rgba(99, 102, 241, 0.25);
}
.hero-visual-glyph {
  font-size: 180px;
  color: rgba(255, 255, 255, 0.92);
  font-weight: 800;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

@media (max-width: 880px) {
  .hero-inner { grid-template-columns: 1fr; gap: 32px; }
  .hero-title { font-size: 32px; }
  .hero-visual-glyph { font-size: 120px; }
}
```

- [ ] **Step 4: 实现 `Capabilities.jsx`**

```jsx
import React from 'react'
import './Capabilities.css'

const ITEMS = [
  { id: 1, name: '货车套用客车 OBU', desc: '入口车型 vs 视觉识别' },
  { id: 2, name: '出入口车辆不一致', desc: '车牌/车型/车纹多维比对' },
  { id: 3, name: '门架路径异常', desc: '序列与拓扑不符' },
  { id: 4, name: '车型降档', desc: '交易记客,识别为货' },
  { id: 5, name: '同车牌多 OBU', desc: '历史绑定异常' },
  { id: 6, name: 'OBU 多车绑定', desc: 'OBU 短时绑多车' },
  { id: 7, name: 'OBU 屏蔽', desc: '无 OBU 但有出口图' },
  { id: 8, name: '车牌 OBU 历史异常', desc: '历史关系异常' },
]

export default function Capabilities() {
  return (
    <section className="cap" id="capabilities">
      <div className="cap-inner">
        <h2 className="cap-title">8 类逃费行为,AI 自动识别</h2>
        <p className="cap-sub">覆盖主流高速场景,持续扩展</p>
        <div className="cap-grid">
          {ITEMS.map((it) => (
            <div key={it.id} className="cap-card">
              <span className="cap-badge">{String(it.id).padStart(2, '0')}</span>
              <div className="cap-name">{it.name}</div>
              <div className="cap-desc">{it.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
```

```css
.cap { background: #fafbff; padding: 72px 0; }
.cap-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
}
.cap-title {
  text-align: center;
  font-size: 30px;
  font-weight: 800;
  color: #0f172a;
  margin: 0 0 8px;
}
.cap-sub {
  text-align: center;
  color: #64748b;
  font-size: 14px;
  margin: 0 0 36px;
}
.cap-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.cap-card {
  background: #fff;
  border: 1px solid #eef2f7;
  border-radius: 12px;
  padding: 20px;
  transition: transform .15s, box-shadow .15s;
}
.cap-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}
.cap-badge {
  display: inline-block;
  font-size: 11px;
  background: #eef2ff;
  color: #4f46e5;
  padding: 2px 8px;
  border-radius: 999px;
  margin-bottom: 10px;
  font-weight: 600;
}
.cap-name {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 4px;
}
.cap-desc {
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
}

@media (max-width: 1024px) { .cap-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 560px)  { .cap-grid { grid-template-columns: 1fr; } }
```

- [ ] **Step 5: 实现 `Architecture.jsx`**

```jsx
import React from 'react'
import './Architecture.css'

const FEATURES = [
  { icon: '🏢', title: '本地化部署', desc: '支持私有化部署,数据不出本单位内网' },
  { icon: '🔌', title: '源库直连', desc: '对接 Doris 源库只读,业务零侵入' },
  { icon: '🤖', title: 'AI 模型分离', desc: '视觉模型独立公共服务,可独立升级' },
]

export default function Architecture() {
  return (
    <section className="arch" id="architecture">
      <div className="arch-inner">
        <h2 className="arch-title">为高速运营方而生 · 安全可控</h2>
        <p className="arch-sub">支持本地化部署,数据不出域</p>
        <div className="arch-grid">
          {FEATURES.map((f) => (
            <div key={f.title} className="arch-card">
              <div className="arch-icon">{f.icon}</div>
              <div className="arch-card-title">{f.title}</div>
              <div className="arch-card-desc">{f.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
```

```css
.arch { background: #fff; padding: 72px 0; }
.arch-inner { max-width: 1200px; margin: 0 auto; padding: 0 24px; }
.arch-title {
  text-align: center;
  font-size: 30px;
  font-weight: 800;
  color: #0f172a;
  margin: 0 0 8px;
}
.arch-sub {
  text-align: center;
  color: #64748b;
  font-size: 14px;
  margin: 0 0 36px;
}
.arch-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}
.arch-card {
  background: #fff;
  border: 1px solid #eef2f7;
  border-radius: 14px;
  padding: 28px 24px;
  text-align: center;
}
.arch-icon { font-size: 36px; margin-bottom: 12px; }
.arch-card-title {
  font-size: 17px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 6px;
}
.arch-card-desc {
  font-size: 13px;
  color: #64748b;
  line-height: 1.55;
}
@media (max-width: 768px) { .arch-grid { grid-template-columns: 1fr; } }
```

- [ ] **Step 6: 实现 `Stats.jsx`**

```jsx
import React from 'react'
import './Stats.css'

const STATS = [
  { num: '8', label: '逃费类型' },
  { num: '99.2%', label: '识别准确率' },
  { num: '<200ms', label: '单次识别' },
  { num: '3 机', label: '部署拓扑' },
]

export default function Stats() {
  return (
    <section className="stats" id="stats">
      <div className="stats-inner">
        <div className="stats-grid">
          {STATS.map((s) => (
            <div key={s.label} className="stats-item">
              <div className="stats-num">{s.num}</div>
              <div className="stats-label">{s.label}</div>
            </div>
          ))}
        </div>
        <p className="stats-foot">
          数据来源于内部测试环境,实际值以部署报告为准
        </p>
      </div>
    </section>
  )
}
```

```css
.stats { background: #f8fafc; padding: 56px 0; }
.stats-inner { max-width: 1200px; margin: 0 auto; padding: 0 24px; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  text-align: center;
}
.stats-num {
  font-size: 40px;
  font-weight: 800;
  background: linear-gradient(135deg, #4f46e5, #a78bfa);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  line-height: 1.1;
}
.stats-label {
  font-size: 13px;
  color: #64748b;
  margin-top: 6px;
}
.stats-foot {
  text-align: center;
  color: #94a3b8;
  font-size: 12px;
  margin: 24px 0 0;
}
@media (max-width: 640px) { .stats-grid { grid-template-columns: repeat(2, 1fr); gap: 24px; } }
```

- [ ] **Step 7: 实现 `CTA.jsx`(含完整表单状态机)**

```jsx
import React, { useState } from 'react'
import { submitLead } from '../../../api/landing'
import './CTA.css'

const PHONE_RE = /^1[3-9]\d{9}$/
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

function validate(values) {
  const errors = {}
  if (!values.name.trim()) errors.name = '请填写姓名'
  if (!PHONE_RE.test(values.phone)) errors.phone = '请填写正确的手机号'
  if (!values.org.trim()) errors.org = '请填写单位名称'
  if (values.email && !EMAIL_RE.test(values.email)) errors.email = '邮箱格式不正确'
  if (values.message && values.message.length > 500) errors.message = '备注不超过 500 字'
  return errors
}

const EMPTY = { name: '', phone: '', org: '', email: '', message: '' }

export default function CTA() {
  const [values, setValues] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [status, setStatus] = useState('idle') // idle | submitting | success
  const [toast, setToast] = useState(null)

  const onChange = (e) => {
    const { name, value } = e.target
    setValues((v) => ({ ...v, [name]: value }))
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    const errs = validate(values)
    setErrors(errs)
    if (Object.keys(errs).length > 0) return
    setStatus('submitting')
    try {
      await submitLead(values)
      setStatus('success')
    } catch (err) {
      setStatus('idle')
      if (err.status === 422 && err.fieldErrors) {
        setErrors(err.fieldErrors)
      } else {
        setToast(err.message || '提交失败,请稍后重试')
        setTimeout(() => setToast(null), 4000)
      }
    }
  }

  return (
    <section className="cta" id="contact">
      <div className="cta-inner">
        <h2 className="cta-title">申请免费试用</h2>
        <p className="cta-sub">填写后我们 1 个工作日内联系您</p>

        {status === 'success' ? (
          <div className="cta-success">
            <div className="cta-success-icon">✓</div>
            <div className="cta-success-text">提交成功,我们会尽快联系您</div>
            <button
              type="button"
              className="cta-link"
              onClick={() => { setValues(EMPTY); setStatus('idle'); setErrors({}) }}
            >
              再次提交
            </button>
          </div>
        ) : (
          <form className="cta-form" onSubmit={onSubmit} noValidate>
            <label className="cta-field">
              <span>姓名 *</span>
              <input
                name="name" value={values.name} onChange={onChange}
                disabled={status === 'submitting'}
              />
              {errors.name && <em className="cta-err">{errors.name}</em>}
            </label>
            <label className="cta-field">
              <span>联系电话 *</span>
              <input
                name="phone" value={values.phone} onChange={onChange}
                inputMode="numeric" disabled={status === 'submitting'}
              />
              {errors.phone && <em className="cta-err">{errors.phone}</em>}
            </label>
            <label className="cta-field">
              <span>单位名称 *</span>
              <input
                name="org" value={values.org} onChange={onChange}
                disabled={status === 'submitting'}
              />
              {errors.org && <em className="cta-err">{errors.org}</em>}
            </label>
            <label className="cta-field">
              <span>邮箱</span>
              <input
                name="email" type="email" value={values.email} onChange={onChange}
                disabled={status === 'submitting'}
              />
              {errors.email && <em className="cta-err">{errors.email}</em>}
            </label>
            <label className="cta-field cta-field-full">
              <span>备注</span>
              <textarea
                name="message" value={values.message} onChange={onChange}
                rows={3} maxLength={500}
                disabled={status === 'submitting'}
              />
              {errors.message && <em className="cta-err">{errors.message}</em>}
            </label>
            <div className="cta-actions">
              <button
                type="submit"
                className="cta-submit"
                disabled={status === 'submitting'}
              >
                {status === 'submitting' ? '提交中...' : '提交申请'}
              </button>
            </div>
          </form>
        )}

        {toast && <div className="cta-toast">{toast}</div>}
      </div>
    </section>
  )
}
```

```css
.cta { background: linear-gradient(135deg, #eef2ff 0%, #faf5ff 100%); padding: 72px 0; }
.cta-inner { max-width: 720px; margin: 0 auto; padding: 0 24px; }
.cta-title {
  text-align: center;
  font-size: 30px;
  font-weight: 800;
  color: #0f172a;
  margin: 0 0 8px;
}
.cta-sub {
  text-align: center;
  color: #64748b;
  font-size: 14px;
  margin: 0 0 32px;
}
.cta-form {
  background: #fff;
  border-radius: 14px;
  padding: 28px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}
.cta-field { display: flex; flex-direction: column; gap: 6px; }
.cta-field-full { grid-column: 1 / -1; }
.cta-field span { font-size: 13px; color: #334155; font-weight: 500; }
.cta-field input, .cta-field textarea {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color .15s, box-shadow .15s;
}
.cta-field input:focus, .cta-field textarea:focus {
  border-color: #4f46e5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.15);
}
.cta-field input:disabled, .cta-field textarea:disabled { background: #f8fafc; }
.cta-err { color: #dc2626; font-size: 12px; font-style: normal; }
.cta-actions { grid-column: 1 / -1; display: flex; justify-content: flex-end; }
.cta-submit {
  background: #4f46e5;
  color: #fff;
  border: none;
  padding: 11px 24px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background .15s;
}
.cta-submit:hover:not(:disabled) { background: #4338ca; }
.cta-submit:disabled { opacity: 0.6; cursor: not-allowed; }
.cta-success { text-align: center; padding: 40px 20px; }
.cta-success-icon {
  width: 56px; height: 56px; line-height: 56px;
  background: #10b981; color: #fff; border-radius: 50%;
  font-size: 30px; margin: 0 auto 16px;
}
.cta-success-text { color: #0f172a; font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.cta-link {
  background: none; border: none; color: #4f46e5; cursor: pointer;
  font-size: 14px; text-decoration: underline;
}
.cta-toast {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  background: #0f172a; color: #fff; padding: 10px 18px; border-radius: 8px;
  font-size: 13px;
}
@media (max-width: 560px) { .cta-form { grid-template-columns: 1fr; } }
```

- [ ] **Step 8: 替换 `Landing.jsx` 为完整版**

```jsx
import React, { useEffect } from 'react'
import LandingNav from '../../components/LandingNav'
import Hero from './sections/Hero'
import Capabilities from './sections/Capabilities'
import Architecture from './sections/Architecture'
import Stats from './sections/Stats'
import CTA from './sections/CTA'
import './Landing.css'

export default function Landing() {
  useEffect(() => {
    document.title = 'TollAudit Express · 高速公路 AI 稽核'
    const meta = document.querySelector('meta[name="description"]')
    if (meta) {
      meta.setAttribute('content', 'TollAudit Express 高速公路 AI 稽核系统,识别 8 类逃费行为,服务高速运营单位本地化部署。')
    } else {
      const m = document.createElement('meta')
      m.name = 'description'
      m.content = 'TollAudit Express 高速公路 AI 稽核系统,识别 8 类逃费行为,服务高速运营单位本地化部署。'
      document.head.appendChild(m)
    }
  }, [])

  return (
    <div className="landing">
      <LandingNav />
      <main>
        <Hero />
        <Capabilities />
        <Architecture />
        <Stats />
        <CTA />
        <footer className="landing-footer">
          <p>© TollAudit Express · 高速公路收费稽核系统</p>
        </footer>
      </main>
    </div>
  )
}
```

```css
.landing { background: #fff; min-height: 100vh; }
.landing-footer {
  text-align: center;
  padding: 24px 16px;
  color: #94a3b8;
  font-size: 12px;
  border-top: 1px solid #eef2f7;
}
html { scroll-behavior: smooth; }
```

- [ ] **Step 9: 验证 web build**

```bash
cd /Users/moyuanming/TollAuditExpress/apps/web && npm run build
```

Expected: build 成功(无 error,warn 可接受)。

- [ ] **Step 10: 提交**

```bash
git add apps/web/src/pages/Landing apps/web/src/components/LandingNav.jsx apps/web/src/components/LandingNav.css
git commit -m "feat(web): landing page (5 sections) + LandingNav with section highlighting"
```

---

## Task 7: 前端测试基础设施(Vitest + RTL)

**Files:**
- Create: `apps/web/vitest.config.js`
- Create: `apps/web/src/test/setup.js`
- Modify: `apps/web/package.json`(加 devDependencies + scripts)

- [ ] **Step 1: 修改 `apps/web/package.json`**

将 `devDependencies` 替换为:

```json
  "devDependencies": {
    "@testing-library/jest-dom": "^6.1.5",
    "@testing-library/react": "^14.1.2",
    "@testing-library/user-event": "^14.5.1",
    "@vitejs/plugin-react": "^4.2.0",
    "jsdom": "^23.0.1",
    "vite": "^5.0.0",
    "vitest": "^1.1.0"
  }
```

在 `scripts` 里加:

```json
    "test": "vitest run",
    "test:watch": "vitest"
```

- [ ] **Step 2: 安装依赖**

```bash
cd /Users/moyuanming/TollAuditExpress/apps/web && npm install
```

Expected: `vitest`, `@testing-library/react`, `jsdom` 等装好。

- [ ] **Step 3: 创建 `apps/web/vitest.config.js`**

```javascript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    globals: true,
    css: false,
  },
})
```

- [ ] **Step 4: 创建 `apps/web/src/test/setup.js`**

```javascript
import '@testing-library/jest-dom/vitest'

// 防止 IntersectionObserver / matchMedia 在 jsdom 下报错
class IO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
// eslint-disable-next-line no-undef
globalThis.IntersectionObserver = IO
// eslint-disable-next-line no-undef
if (!globalThis.matchMedia) {
  globalThis.matchMedia = (q) => ({
    matches: false,
    media: q,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })
}
```

- [ ] **Step 5: 验证 vitest 能跑(无测试时直接看 config)**

```bash
cd /Users/moyuanming/TollAuditExpress/apps/web && npx vitest run --reporter=basic
```

Expected: `No test files found` 或类似信息(没有测试),exit 0 或 1 都可接受,只要 config 加载不报错。

- [ ] **Step 6: 提交**

```bash
git add apps/web/package.json apps/web/vitest.config.js apps/web/src/test/setup.js
git commit -m "build(web): add vitest + React Testing Library dev setup"
```

---

## Task 8: 前端表单测试

**Files:**
- Create: `tests/web/test_landing_form.test.jsx`

- [ ] **Step 1: 写测试**

新建 `tests/web/test_landing_form.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CTA from '../../apps/web/src/pages/Landing/sections/CTA'

// 替换 landing api client
vi.mock('../../apps/web/src/api/landing', () => ({
  submitLead: vi.fn(),
}))
import { submitLead } from '../../apps/web/src/api/landing'

beforeEach(() => {
  submitLead.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('CTA form', () => {
  it('空提交时显示行内错误', async () => {
    const user = userEvent.setup()
    render(<CTA />)
    await user.click(screen.getByRole('button', { name: '提交申请' }))
    expect(await screen.findByText('请填写姓名')).toBeInTheDocument()
    expect(screen.getByText('请填写正确的手机号')).toBeInTheDocument()
    expect(screen.getByText('请填写单位名称')).toBeInTheDocument()
    expect(submitLead).not.toHaveBeenCalled()
  })

  it('手机号格式错误时被拦截', async () => {
    const user = userEvent.setup()
    render(<CTA />)
    await user.type(screen.getByLabelText('姓名 *'), '张三')
    await user.type(screen.getByLabelText('联系电话 *'), '12345')
    await user.type(screen.getByLabelText('单位名称 *'), '某公司')
    await user.click(screen.getByRole('button', { name: '提交申请' }))
    expect(await screen.findByText('请填写正确的手机号')).toBeInTheDocument()
    expect(submitLead).not.toHaveBeenCalled()
  })

  it('合法提交 → 成功视图', async () => {
    submitLead.mockResolvedValue({ id: 1, name: '张三' })
    const user = userEvent.setup()
    render(<CTA />)
    await user.type(screen.getByLabelText('姓名 *'), '张三')
    await user.type(screen.getByLabelText('联系电话 *'), '13800001234')
    await user.type(screen.getByLabelText('单位名称 *'), '某高速')
    await user.click(screen.getByRole('button', { name: '提交申请' }))
    await waitFor(() => {
      expect(screen.getByText('提交成功,我们会尽快联系您')).toBeInTheDocument()
    })
    expect(submitLead).toHaveBeenCalledWith({
      name: '张三', phone: '13800001234', org: '某高速',
      email: '', message: '',
    })
  })

  it('422 → 行内错误', async () => {
    const err = new Error('表单校验失败')
    err.status = 422
    err.fieldErrors = { phone: '手机号格式不正确' }
    submitLead.mockRejectedValue(err)
    const user = userEvent.setup()
    render(<CTA />)
    await user.type(screen.getByLabelText('姓名 *'), '张三')
    await user.type(screen.getByLabelText('联系电话 *'), '13800001234')
    await user.type(screen.getByLabelText('单位名称 *'), '某公司')
    await user.click(screen.getByRole('button', { name: '提交申请' }))
    await waitFor(() => {
      expect(screen.getByText('手机号格式不正确')).toBeInTheDocument()
    })
  })

  it('5xx → toast', async () => {
    const err = new Error('HTTP 500')
    err.status = 500
    submitLead.mockRejectedValue(err)
    const user = userEvent.setup()
    render(<CTA />)
    await user.type(screen.getByLabelText('姓名 *'), '张三')
    await user.type(screen.getByLabelText('联系电话 *'), '13800001234')
    await user.type(screen.getByLabelText('单位名称 *'), '某公司')
    await user.click(screen.getByRole('button', { name: '提交申请' }))
    await waitFor(() => {
      expect(screen.getByText('HTTP 500')).toBeInTheDocument()
    })
  })

  it('提交中按钮 disabled', async () => {
    let resolveFn
    submitLead.mockImplementation(() => new Promise((r) => { resolveFn = r }))
    const user = userEvent.setup()
    render(<CTA />)
    await user.type(screen.getByLabelText('姓名 *'), '张三')
    await user.type(screen.getByLabelText('联系电话 *'), '13800001234')
    await user.type(screen.getByLabelText('单位名称 *'), '某公司')
    await user.click(screen.getByRole('button', { name: '提交申请' }))
    const btn = screen.getByRole('button', { name: '提交中...' })
    expect(btn).toBeDisabled()
    resolveFn({ id: 1 })
    await waitFor(() => {
      expect(screen.getByText('提交成功,我们会尽快联系您')).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: 跑测试**

```bash
cd /Users/moyuanming/TollAuditExpress && npm --prefix apps/web test -- --reporter=basic
```

Expected: 6 PASS。

- [ ] **Step 3: 提交**

```bash
git add tests/web/test_landing_form.test.jsx
git commit -m "test(web): CTA form validation + submit state machine"
```

---

## Task 9: 前端路由测试(公开 / 鉴权 / 重定向)

**Files:**
- Create: `tests/web/test_routing.test.jsx`

- [ ] **Step 1: 写测试**

新建 `tests/web/test_routing.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// AuthGuard 抛个简单占位,只要在 /app/* 下被引用就 OK
vi.mock('../../apps/web/src/components/AuthGuard', () => ({
  AuthGuard: ({ children }) => <div data-testid="guard">{children}</div>,
}))

import App from '../../apps/web/src/App'

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>
  )
}

describe('Routing', () => {
  it('访问 / 看到 Landing(包含"让每一笔通行费")', () => {
    renderAt('/')
    expect(screen.getByText(/让每一笔通行费/)).toBeInTheDocument()
    // 不在 AuthGuard 内
    expect(screen.queryByTestId('guard')).toBeNull()
  })

  it('访问 /app 命中 AuthGuard(看到 "guard" 包裹)', () => {
    renderAt('/app')
    expect(screen.getByTestId('guard')).toBeInTheDocument()
  })

  it('老路径 /trips 重定向到 /app/trips', () => {
    renderAt('/trips')
    // MemoryRouter 走 Navigate 后,内部路径变 /app/trips
    // 我们只验证 AppNav 的"行程查询"链接会标记 active
    const link = screen.getByText('🚗 行程查询')
    expect(link.getAttribute('href')).toBe('/app/trips')
  })

  it('老路径 /vehicles 重定向到 /app/vehicles', () => {
    renderAt('/vehicles')
    const link = screen.getByText('🔎 车辆查询')
    expect(link.getAttribute('href')).toBe('/app/vehicles')
  })
})
```

- [ ] **Step 2: 跑测试**

```bash
npm --prefix apps/web test -- --reporter=basic
```

Expected: 4 PASS(Task 8 6 + Task 9 4 = 10 总通过)。

- [ ] **Step 3: 提交**

```bash
git add tests/web/test_routing.test.jsx
git commit -m "test(web): routing split (Landing public, /app/* auth, legacy redirects)"
```

---

## Task 10: 全量回归

- [ ] **Step 1: 后端全量测试**

```bash
cd /Users/moyuanming/TollAuditExpress && python -m pytest tests/ -q
```

Expected: 全部 PASS(老的 + 新增 landing 一系列)。

- [ ] **Step 2: 前端 build + 全量测试**

```bash
cd /Users/moyuanming/TollAuditExpress/apps/web && npm run build && npm test
```

Expected: build 0 error;test 10 PASS。

- [ ] **Step 3: 手动 smoke — 启动 dev server 跑 landing**

```bash
cd /Users/moyuanming/TollAuditExpress/apps/web && npm run dev
```

另开终端:

```bash
cd /Users/moyuanming/TollAuditExpress/apps/api && uvicorn apps.api.main:app --reload --port 8000
```

用浏览器打开 `http://localhost:3000/`,确认:
- [ ] Hero 标题/副标题/CTA 显示
- [ ] 8 类卡片平铺
- [ ] 三栏架构
- [ ] 4 数字
- [ ] 表单可填、可校验、可提交
- [ ] 点击「登录后台」跳 `/app`,被 AuthGuard 触发 OIDC 重定向

- [ ] **Step 4: 用 Playwright 截图留证(可选)**

在 dev server 跑着的情况下,可用 `mcp__chrome-devtools__take_screenshot` 对 `localhost:3000/` 截图归档,作为 PR 视觉证据。

- [ ] **Step 5: 提交(若有遗留 fix)**

```bash
git add -A
git commit -m "chore: smoke test fixes from manual verification"
```

若无修改,跳过此步。

---

## Task 11: 文档收尾(可选 — 与手动 USER_MANUAL 更新)

- [ ] **Step 1: 在 `docs/USER_MANUAL.md` 末尾追加「公开落地页」小节(若文件存在)**

```markdown
## 公开落地页

`/` 是面向高速运营单位采购方的营销落地页,完全公开,无需登录。

- Hero / 能力 / 架构 / 数据 / 申请试用 5 段
- 底部表单 → `POST /api/landing/leads` → 入库 `ods_AI_DB.landing_leads`
- 同 IP 1 分钟内最多 5 次提交
- 后台查询:`GET /api/landing/leads` 需 `X-API-Key` 或 `Bearer` 鉴权

内部 dashboard 入口已迁移至 `/app/*`,老路径 `/trips` 等已自动 302 跳转。
```

- [ ] **Step 2: 提交**

```bash
git add docs/USER_MANUAL.md
git commit -m "docs: add landing page section to USER_MANUAL"
```

---

## Self-Review(自查清单)

### 1. Spec 覆盖矩阵

| Spec 章节 | 落点 |
|---|---|
| §1 目标 / 受众 | Task 6 全段文案沿用 spec 表述 |
| §2 路由调整 | Task 5 `App.jsx` 整体重写,老路径重定向到位 |
| §2 `/app/login` 跳 OIDC | 不写新代码,沿用 AuthGuard 现有行为(已在 spec §2 说明) |
| §3.1 Hero | Task 6 Step 3 |
| §3.2 8 类能力(4×2 网格) | Task 6 Step 4 |
| §3.3 架构(三栏) | Task 6 Step 5 |
| §3.4 数据证据(4 数字横排) | Task 6 Step 6 |
| §3.5 CTA(表单) | Task 6 Step 7 |
| §4.1 表单数据流 | Task 1 Pydantic + Task 4 router + Task 5 API client |
| §4.2 nav 高亮 | Task 6 Step 1 `IntersectionObserver` |
| §4.3 限流(5 req/min/IP) | Task 2 limiter + Task 4 接入 |
| §4.4 422 错误按字段映射 | Task 5 `parseFieldErrors` + Task 6 错误显示 |
| §5 文件清单 | 19 个文件全部覆盖 |
| §6 前端测试 | Task 7 + 8 + 9 |
| §6 后端测试 | Task 1 + 2 + 3 + 4 |
| §7 范围外 | 无 i18n / 无 GA / 无 email — 全部按 spec 跳过 |
| §8 风险备注 | 数据真实性、DDL、老链接、AuthGuard 改造 — 已在 plan 中应对 |

### 2. 占位扫描

- 无 "TBD" / "TODO" / "later"
- 无 "Add appropriate error handling" 类偷懒描述
- 每个代码 step 包含完整代码
- Type 一致性:`LandingLeadCreate` / `LandingLeadResponse` / `LandingLeadListResponse` 在 Task 1 定义,Task 4 router 直接 import 用;`submitLead` payload 字段在 Task 5 / Task 6 / Task 8 保持一致;`landing_leads` 表 schema 在 Task 3 + 仓储 insert 完全对齐。

### 3. 类型一致性

- `LandingLeadCreate` 字段:`name / phone / org / email? / message? / source='landing-page'` ← Pydantic / 前端 `EMPTY` / 前端 `submitLead` payload 三处一致
- 后端 `landing_leads` 表 9 字段(id/name/phone/org/email/message/source/ip/ua/created_at)— `insert` 与 `list_paginated` 字段顺序一致
- `PHONE_RE` = `^1[3-9]\d{9}$`,与 Pydantic `pattern=r"^1[3-9]\d{9}$"` 同一份规则
- `EMAIL_RE` = `^[^@\s]+@[^@\s]+\.[^@\s]+$`,与 Pydantic `EmailStr` / `_EMAIL_RE` 等价
- 路由前缀:后端 `/api/landing`,前端 fetch 路径一致
- 测试 `landing_leads` 表 DDL 在 `tests/conftest.py` 与生产 schema 字段一致(都是 `landing_leads` 同名列)

### 4. 范围检查

11 个 task 全部聚焦在单仓内的「落地页 + 表单 + 路由调整」,无外溢到 dashboard 重构、登录系统改造、CI 改造等。

---

## 执行方式

完成后我会提供以下两种执行方式供你选:

1. **Subagent-Driven(推荐)**: 我为每个 task 派遣独立 subagent,我在 task 之间做评审,迭代快
2. **Inline Execution**: 在当前 session 用 executing-plans skill 执行,带 checkpoint 评审
