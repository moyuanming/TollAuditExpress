# TollAuditExpress 项目架构文档

> 高速公路收费稽核系统 — 架构梳理  
> 生成日期：2026-06-17

---

## 1. 系统概述

TollAuditExpress 是一套面向**高速公路收费稽核**场景的全栈 Web 系统，核心目标是自动识别通行数据中的欺诈行为（出入口车辆不一致、客车套用货车 OBU、门架跳点、OBU 借用/屏蔽等），并通过可视化界面辅助人工复核。

系统从 Doris 数据仓库读取原始通行流水（入口/门架/出口），按 PASSID 聚合形成行程，然后对行程执行多维度稽核检测（视觉比对、规则引擎、LLM 二次判定），将可疑记录入库供人工审核。同时提供定时任务调度、规则管理、营销落地页等辅助功能。

### 核心业务流程

```
原始通行流水(Doris) → 行程聚合 → 多维度检测 → 可疑记录入库 → 人工复核 → 确认/驳回
                                        ↑
                              vehicle-ai-service (视觉+LLM)
```

---

## 2. 技术栈

| 层级 | 技术 | 版本/说明 |
|------|------|-----------|
| **后端框架** | FastAPI | ≥0.104.0, 异步 ASGI |
| **ASGI 服务器** | Uvicorn | ≥0.24.0 |
| **数据校验** | Pydantic v2 | ≥2.5.0, 前后端共享契约 |
| **数据源库** | Apache Doris | 源库 `dwd_tolldata` (只读原始通行流水) |
| **稽核目标库** | Apache Doris | `ods_AI_DB` (稽核派生表，原 SQLite 已迁移) |
| **DB 驱动** | PyMySQL | ≥1.1.0, DictCursor + 连接池 |
| **HTTP 客户端** | httpx | ≥0.25.0, 调用 vehicle-ai-service |
| **重试** | tenacity | ≥8.2.0 |
| **认证** | PyJWT[crypto] | ≥2.8.0, JWT Bearer + API Key 双模 |
| **前端框架** | React 18 | SPA, Vite 构建 |
| **前端路由** | React Router v6 | BrowserRouter |
| **图表** | ECharts (echarts-for-react) | ≥5.6.0 |
| **图标** | Lucide React | ≥0.460.0 |
| **前端测试** | Vitest + Testing Library | 单元/组件测试 |
| **后端测试** | pytest + pytest-cov | 覆盖率 ≥60% |
| **Lint** | ruff (后端) / ESLint (前端) | |
| **容器化** | Docker + docker-compose | 多阶段构建 |
| **CI/CD** | GitHub Actions | lint → test → docker build |
| **Python** | 3.10 | |
| **Node.js** | 18 (构建) / 20 (CI) | |

---

## 3. 项目结构

```
TollAuditExpress/
├── apps/
│   ├── api/                    # 后端 FastAPI 应用
│   │   ├── main.py             # 应用入口, lifespan, 路由注册, SPA fallback
│   │   ├── core/               # 核心横切关注点
│   │   │   ├── config.py       # 环境变量 & 配置管理
│   │   │   ├── auth.py         # 统一鉴权中间件 (JWT + API Key)
│   │   │   ├── jwt_util.py     # JWT 编解码 & 验证
│   │   │   ├── oauth_service.py# OAuth 令牌交换/刷新/撤销
│   │   │   ├── token_cache.py  # Token 黑名单 & refresh_token 缓存
│   │   │   ├── rate_limit.py   # 滑动窗口限流
│   │   │   ├── vehicle_ai_client.py  # vehicle-ai-service HTTP 客户端
│   │   │   └── logging_config.py     # 日志配置
│   │   ├── routers/            # API 路由层
│   │   │   ├── audit.py        # 稽核核心路由 (行程/可疑/检测/聚合)
│   │   │   ├── health.py       # 健康检查 (含 Doris 详细诊断)
│   │   │   ├── landing.py      # 营销落地页线索提交
│   │   │   ├── oauth.py        # OAuth 登录/登出/配置
│   │   │   ├── rules.py        # 检测规则 CRUD
│   │   │   └── tasks.py        # 定时任务 CRUD + 手动执行
│   │   ├── services/           # 业务逻辑层
│   │   │   ├── trip_aggregator.py      # 行程聚合 (Doris→audit_trips)
│   │   │   ├── entry_exit_matcher.py   # 出入口车辆比对 (调 AI 服务)
│   │   │   ├── vehicle_comparator.py   # 双图比对业务封装
│   │   │   ├── passenger_obu_detector.py # 客车套用货车OBU检测
│   │   │   ├── detectors.py            # 多维度检测器 (门架跳点/大车小标/同牌不同车/OBU借用/OBU屏蔽)
│   │   │   ├── rule_engine.py          # 规则引擎 (JSON s-expression DSL)
│   │   │   ├── rule_loader.py          # 规则只读加载 (调度用)
│   │   │   ├── doris_trip_query.py     # Doris 原始数据直查
│   │   │   ├── ai_verify_batch.py      # LLM 批量验证
│   │   │   ├── task_scheduler.py       # 后台定时任务调度器 (daemon 线程)
│   │   │   ├── task_executor.py        # 任务执行器
│   │   │   └── image_utils.py          # 图片下载/处理工具
│   │   ├── database/           # 数据层
│   │   │   ├── connection.py           # SQLite 连接 (遗留, 已迁移至 Doris)
│   │   │   ├── doris_connection.py     # Doris 连接池 (线程安全, queue.Queue)
│   │   │   ├── doris_ddl.sql           # Doris 建表 DDL (启动时幂等执行)
│   │   │   ├── migrate_sqlite_to_doris.py # SQLite→Doris 迁移脚本
│   │   │   ├── migrations/             # 增量迁移 SQL (001~007)
│   │   │   └── repositories/           # 数据访问层 (Repository 模式)
│   │   │       ├── audit_repository.py        # 稽核结果 CRUD
│   │   │       ├── trip_repository.py         # 行程 CRUD + 多条件查询
│   │   │       ├── rule_repository.py         # 检测规则 CRUD
│   │   │       ├── task_repository.py         # 定时任务 CRUD
│   │   │       ├── landing_repository.py      # 落地页线索 CRUD
│   │   │       ├── topology_repository.py     # 门架拓扑边 CRUD
│   │   │       └── truck_obu_stats_repository.py # 货车OBU每日统计
│   │   ├── models/
│   │   │   └── schemas.py      # 从 contracts 重新导出 (向后兼容)
│   │   └── requirements.txt    # Python 依赖
│   │
│   └── web/                    # 前端 React SPA
│       ├── src/
│       │   ├── main.jsx        # 入口, ReactDOM.createRoot
│       │   ├── App.jsx         # 路由定义, 导航栏, AuthProvider
│       │   ├── api/            # API 客户端封装
│       │   │   ├── audit.js    # 稽核/行程/可疑/任务 API
│       │   │   ├── landing.js  # 落地页线索提交 API
│       │   │   └── rules.js    # 规则管理 API
│       │   ├── pages/          # 页面组件
│       │   │   ├── Dashboard.jsx           # 仪表盘 (概览统计)
│       │   │   ├── TripQuery.jsx           # 行程查询
│       │   │   ├── VehicleQuery.jsx        # 车辆查询 (Doris 原始数据)
│       │   │   ├── SuspectList.jsx         # 可疑记录列表
│       │   │   ├── Statistics.jsx          # 统计分析 (图表)
│       │   │   ├── TaskManager.jsx         # 定时任务管理
│       │   │   ├── PassengerOBUMonitor.jsx # 客车OBU监测
│       │   │   ├── RuleStudio.jsx          # 规则管理
│       │   │   ├── Redirect.jsx            # OAuth 回调重定向
│       │   │   └── Landing/               # 营销落地页
│       │   ├── components/     # 共享组件
│       │   │   ├── AuthContext.jsx    # 认证上下文 (Provider + useAuth)
│       │   │   ├── AuthGuard.jsx      # 路由守卫
│       │   │   ├── GantryTimeline.jsx # 门架时间线
│       │   │   ├── GantryImageTimeline.jsx # 门架图片时间线
│       │   │   ├── SmartImage.jsx     # 智能图片 (懒加载+错误处理)
│       │   │   ├── VehicleTripDetail.jsx  # 车辆行程详情
│       │   │   ├── Icon.jsx           # Lucide 图标封装
│       │   │   ├── LandingNav.jsx     # 落地页导航
│       │   │   ├── charts/            # 图表组件
│       │   │   │   ├── DailyScanBar.jsx
│       │   │   │   ├── LineTrend.jsx
│       │   │   │   └── PieDistribution.jsx
│       │   │   └── tripDetailUtils.jsx
│       │   └── styles/         # 全局样式
│       ├── vite.config.js      # Vite 配置 (代理 /api → :8000)
│       └── package.json
│
├── packages/
│   └── contracts/              # 前后端共享契约 (单一事实来源)
│       └── types/
│           ├── schemas.py      # Pydantic 模型定义
│           └── index.ts        # TypeScript 类型定义 (预留)
│
├── tests/                      # 测试
│   ├── unit/                   # 单元测试 (services/repositories)
│   ├── api/                    # API 路由集成测试
│   ├── e2e/                    # 端到端测试
│   └── web/                    # 前端组件测试
│
├── scripts/                    # 运维/数据脚本
│   ├── detect_ganquanbao.py    # 货权包检测
│   ├── aggregate_ganquanbao.py # 货权包聚合
│   ├── backfill_passenger_obu_details.py  # 回填客车OBU详情
│   ├── apply_007_ddl.py        # 应用 007 DDL
│   ├── check-conn.sh           # 连接检查
│   └── cron-watchdog.sh        # Cron 看门狗
│
├── Dockerfile                  # 多阶段构建 (Node→Python→Production)
├── docker-compose.yml          # 单容器编排
├── build.sh                    # 发布构建脚本 (测试→构建→打包)
├── deploy.sh                   # 三机拓扑部署脚本
├── .github/workflows/ci.yml    # CI 流水线
└── docs/                       # 文档
```

---

## 4. 后端架构

### 4.1 路由层 (Routers)

所有路由挂载在 `main.py` 中，按功能域分组：

| 路由模块 | 前缀 | Tag | 职责 |
|---------|------|-----|------|
| `health` | `/api` | health | 健康检查、Doris 连接诊断 |
| `audit` | `/api/audit` | audit | 稽核核心：行程查询/可疑记录/检测/聚合/客车OBU监测 |
| `tasks` | `/api` | tasks | 定时任务 CRUD + 手动执行 + 执行历史 |
| `rules` | `/api/audit` | rules | 检测规则 CRUD + 启用/禁用/试运行 |
| `oauth` | `/api/oauth` | oauth | OAuth 回调/登出/配置 |
| `landing` | `/api/landing` | landing | 营销落地页线索提交 (IP 限流) |

**关键端点一览：**

```
GET  /api/health                          # 基础健康检查
GET  /api/health/doris                    # Doris 详细诊断 (连接池/表行数/后端节点)

GET  /api/audit/stats/overview            # 稽核概览统计
GET  /api/audit/trips                     # 行程列表 (多条件过滤+排序+分页)
GET  /api/audit/trip/{passid}             # 行程详情
GET  /api/audit/trip/{passid}/full        # 行程完整详情 (含门架图片+稽核结果)
POST /api/audit/trips/aggregate           # 启动批量聚合任务 (后台执行)
GET  /api/audit/trips/aggregate/stream/{id} # SSE 聚合进度推送

GET  /api/audit/doris/vehicles            # Doris 原始数据车辆查询
GET  /api/audit/doris/vehicle/{passid}/full # Doris 原始行程详情

GET  /api/audit/suspects                  # 可疑记录列表 (欺诈类型/处理状态/LLM结果过滤)
GET  /api/audit/suspect/{id}              # 可疑记录详情 (含门架图片流水)
POST /api/audit/suspect/{id}/llm-verify   # 手动触发 LLM 双图比对
POST /api/audit/suspect/{id}/process      # 处理可疑记录 (确认/驳回)

POST /api/audit/detect/passenger-obu      # 检测客车套用货车OBU

GET  /api/audit/rules                     # 规则列表
POST /api/audit/rules                     # 创建规则
PUT  /api/audit/rules/{id}                # 更新规则
PATCH /api/audit/rules/{id}/toggle        # 启用/禁用规则
PATCH /api/audit/rules/{id}/dry-run       # 设置试运行模式

GET  /api/tasks                           # 任务列表
POST /api/tasks                           # 创建任务
POST /api/tasks/{id}/execute             # 手动执行任务
GET  /api/tasks/{id}/executions          # 执行历史

POST /api/oauth/callback                  # OAuth 回调
POST /api/oauth/logout                    # 登出
GET  /api/oauth/config                    # 获取认证配置

POST /api/landing/leads                   # 提交线索 (IP 限流 5/min)
GET  /api/landing/leads                   # 查询线索 (需认证)
```

### 4.2 服务层 (Services)

服务层封装核心业务逻辑，路由层仅做参数校验和响应组装：

| 服务 | 职责 |
|------|------|
| `TripAggregator` | 从 Doris 源库读取通行流水，按 PASSID 聚合入口-门架-出口记录，写入 `audit_trips` 表；支持门架图片匹配（交易流水 ↔ 抓拍图片） |
| `EntryExitMatcher` | 出入口车辆比对，调用 vehicle-ai-service 进行视觉比对+车牌 OCR |
| `VehicleComparator` | 双图比对业务封装：取出入口图片 URL + 视觉信号 + 车牌 OCR，调 AI 服务判定是否同一辆车 |
| `PassengerObuDetector` | 客车套用货车 OBU 检测：ML 视觉分类 → LLM 二次复核 |
| `Detectors` | 多维度检测器框架：`BaseDetector` Protocol + 5 个具体检测器 (GATEWAY_ANOMALY / VEHICLE_TYPE_DOWNGRADE / SAME_PLATE_DIFF_VEHICLE / OBU_UNBIND / OBU_SHIELD) |
| `RuleEngine` | 规则引擎：JSON s-expression DSL 解释器，白名单操作符 + 字段访问，安全求值 |
| `RuleLoader` | 规则只读加载（带错误收集，供调度使用） |
| `DorisTripQuery` | Doris 原始数据直查：按 PASSID 聚合源表、客车 OBU 候选筛选 |
| `AIVerifyBatch` | LLM 批量验证：取待判定可疑记录，批量调 vehicle-ai-service |
| `TaskScheduler` | 后台定时任务调度器：daemon 线程，30 秒轮询到期任务，执行 + 超时清理 |
| `TaskExecutor` | 任务执行器：按 task_type 分派到具体执行逻辑 |
| `ImageUtils` | 图片下载/处理工具 |

### 4.3 数据层 (Database & Repositories)

#### 数据库架构

系统使用双库模式：

```
┌─────────────────────────────┐     ┌─────────────────────────────┐
│  源库: dwd_tolldata (只读)   │     │  稽核目标库: ods_AI_DB (读写) │
│  ─────────────────────────  │     │  ─────────────────────────  │
│  t_waste_en_ex_gantry       │────→│  audit_trips               │
│  (原始通行流水: 入口/门架/出口)│     │  audit_results             │
│                             │     │  audit_actions             │
│  t_grantry_image            │     │  detection_rules           │
│  (门架抓拍图片流水)           │     │  scheduled_tasks           │
│                             │     │  task_executions           │
│                             │     │  landing_leads             │
│                             │     │  gateway_topology          │
│                             │     │  audit_truck_obu_daily_stats│
│                             │     │  migration_log             │
└─────────────────────────────┘     └─────────────────────────────┘
```

- **源库** (`dwd_tolldata`)：远程 Doris，只读，存储原始通行流水
- **稽核目标库** (`ods_AI_DB`)：Doris，读写，承载所有稽核派生表

#### 连接管理

- `doris_connection.py`：线程安全连接池（`queue.Queue`，默认 8 连接），lazy init，出池自动 ping/reconnect，用完归还前 rollback 清除残留事务
- `connection.py`：SQLite 遗留连接（已迁移至 Doris，保留向后兼容）

#### Repository 模式

| Repository | 表 | 职责 |
|-----------|-----|------|
| `TripRepository` | `audit_trips` | 行程 CRUD，多条件动态查询构建（`_build_where`），车辆/OBU/风险评分/门架数过滤 |
| `AuditRepository` | `audit_results` + `audit_actions` | 稽核结果 CRUD，可疑记录查询（JOIN audit_trips），LLM 判定更新，处理状态更新 |
| `RuleRepository` | `detection_rules` | 规则 CRUD，启用/禁用/试运行切换 |
| `TaskRepository` | `scheduled_tasks` + `task_executions` | 任务 CRUD，到期任务查询，执行记录创建/完成/清理僵尸记录 |
| `LandingRepository` | `landing_leads` | 线索写入 + 分页查询 |
| `TopologyRepository` | `gateway_topology` | 门架拓扑边 CRUD，邻居查询 |
| `TruckObuStatsRepository` | `audit_truck_obu_daily_stats` | 每日统计 upsert（SELECT+INSERT/UPDATE 两步走，兼容 Doris） |

#### 迁移

- SQLite 时代：`connection.py` + `migrations/001~007.sql`（增量迁移，schema_version 跟踪）
- Doris 迁移：`migrate_sqlite_to_doris.py` 一键迁移；`doris_ddl.sql` 启动时幂等执行 DDL

---

## 5. 前端架构

### 5.1 技术选型

- **React 18** + **React Router v6** (BrowserRouter)
- **Vite 5** 构建，开发时代理 `/api` → `localhost:8000`
- **ECharts** 图表（echarts-for-react）
- **Lucide React** 图标库
- 纯 CSS 样式（无 UI 框架，自定义全局样式）

### 5.2 路由结构

```
/                           → Landing (营销落地页，公开)
/redirect                   → Redirect (OAuth 回调重定向)
/app/*                      → AuthGuard 保护区域
  /app                      → Dashboard (仪表盘)
  /app/trips                → TripQuery (行程查询)
  /app/vehicles             → VehicleQuery (车辆查询，Doris 原始数据)
  /app/suspects             → SuspectList (可疑记录)
  /app/stats                → Statistics (统计分析)
  /app/tasks                → TaskManager (定时任务)
  /app/passenger-obu-monitor → PassengerOBUMonitor (客车OBU监测)
  /app/rules                → RuleStudio (规则管理)
```

旧路径（`/trips`, `/vehicles` 等）通过 `LegacyRedirect` 组件 301 跳转到 `/app/*` 新路径。

### 5.3 认证流程

```
AuthProvider (Context)
  ├── token 存储在 localStorage ('auth_token')
  ├── login(newToken) → localStorage.setItem + setState
  ├── logout() → POST /api/oauth/logout → localStorage.removeItem
  └── 监听 'auth:invalid' 事件 → 自动清除 token

AuthGuard
  └── 检查 isAuthenticated → 否则重定向到 OAuth 登录页

fetchJSON (api/audit.js)
  ├── 优先附加 Authorization: Bearer {token}
  ├── 回退 X-API-Key header
  ├── 响应头 X-New-Access-Token → 自动刷新 token
  └── 401 → 触发 'auth:invalid' 事件 → 自动登出
```

### 5.4 API 客户端

| 模块 | 基路径 | 覆盖端点 |
|------|--------|---------|
| `audit.js` | `/api/audit` | 行程/可疑/检测/聚合/客车OBU监测 + `/api` 任务 |
| `landing.js` | `/api/landing` | 线索提交 |
| `rules.js` | `/api/audit/rules` | 规则 CRUD（复用 `fetchJSON`） |

所有 API 调用通过 `fetchJSON` 统一处理：认证 header 注入、错误监听、token 自动刷新。

### 5.5 页面与组件

| 页面 | 核心功能 |
|------|---------|
| **Dashboard** | 稽核概览统计卡片（总行程/已验证/可疑/确认欺诈） |
| **TripQuery** | 行程列表查询（多条件过滤 + 排序 + 分页）+ 行程详情弹窗（门架时间线+稽核结果） |
| **VehicleQuery** | Doris 原始数据车辆查询（无检测后字段） |
| **SuspectList** | 可疑记录列表（欺诈类型/处理状态/LLM 结果过滤）+ 详情 + LLM 手动验证 + 确认/驳回 |
| **Statistics** | 统计分析图表（ECharts：日扫描量柱状图/趋势折线/分布饼图） |
| **TaskManager** | 定时任务 CRUD + 手动执行 + 执行历史查看 |
| **PassengerOBUMonitor** | 客车 OBU 监测：概览卡片 + 每日统计 + 异常记录列表 |
| **RuleStudio** | 规则管理：列表/创建/编辑/启用禁用/试运行/删除 |
| **Landing** | 营销落地页：Hero + Capabilities + Architecture + Stats + CTA |

**共享组件：**
- `GantryTimeline` / `GantryImageTimeline`：门架通行时间线可视化
- `SmartImage`：智能图片组件（懒加载 + 错误处理 + 占位）
- `VehicleTripDetail`：车辆行程详情（入口/出口/门架信息）
- `Icon`：Lucide 图标统一封装
- `charts/`：DailyScanBar / LineTrend / PieDistribution 图表组件

---

## 6. 数据流

### 6.1 行程聚合与检测流程

```
                    Doris 源库 (dwd_tolldata)
                    ┌───────────────────────┐
                    │ t_waste_en_ex_gantry   │  原始通行流水
                    │ t_grantry_image        │  门架抓拍图片
                    └──────────┬────────────┘
                               │
                    ┌──────────▼────────────┐
                    │   TripAggregator      │  按 PASSID 聚合
                    │   (services层)        │  入口→门架→出口
                    └──────────┬────────────┘
                               │
                    ┌──────────▼────────────┐
                    │   audit_trips 表      │  聚合后行程
                    │   (ods_AI_DB)         │
                    └──────────┬────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐  ┌─────▼──────┐  ┌──────▼─────────┐
    │ EntryExitMatcher│  │ Detectors  │  │ PassengerObu   │
    │ (出入口比对)    │  │ (5维度检测) │  │ Detector       │
    └────────┬───────┘  └─────┬──────┘  └──────┬─────────┘
             │                │                │
             └────────────────┼────────────────┘
                              │
                   ┌──────────▼──────────┐
                   │  vehicle-ai-service │  独立部署 (10.11.1.40:8081)
                   │  ┌────────────────┐ │
                   │  │ 视觉比对       │ │  ResNet/ResNet 特征提取
                   │  │ 车牌 OCR       │ │  车牌识别
                   │  │ ML 车型分类    │ │  YOLOv8 车型检测
                   │  │ LLM 二次复核   │ │  智谱/OpenAI 大模型
                   │  │ 分档裁决器     │ │  廉价信号优先,省 LLM
                   │  └────────────────┘ │
                   └──────────┬──────────┘
                              │
                   ┌──────────▼────────────┐
                   │   audit_results 表    │  检测结果
                   │   + audit_actions 表  │  人工处理记录
                   └───────────────────────┘
```

### 6.2 前端查询流程

```
React 页面 → api/audit.js (fetchJSON) → FastAPI Router → Service → Repository → Doris
                                                                    ↓
                                                              Pydantic 响应模型
                                                                    ↓
                                                              JSON → React State → UI 渲染
```

### 6.3 认证数据流

```
浏览器 → OAuth 登录页 → 统一认证平台
                         ↓ (授权码)
         POST /api/oauth/callback → oauth_service.exchange_token
                         ↓
         JWT decode + validate → token_cache 存储 refresh_token
                         ↓
         返回 accessToken → localStorage → AuthContext → 后续请求 Bearer header
```

### 6.4 定时任务调度流

```
TaskScheduler (daemon 线程, 30s 轮询)
  → TaskRepository.get_due_tasks()
  → TaskExecutor.execute()
    → 按 task_type 分派:
      - aggregate_detect → TripAggregator + Detectors
      - passenger_obu_scan → PassengerObuDetector
    → TaskRepository.complete_execution()
  → TaskRepository.update_after_run() (计算 next_run_at)
```

---

## 7. 部署架构

### 7.1 三机拓扑

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  本地 macOS       │────→│  构建服务器       │     │  目标服务器       │
│  (调度端)         │     │  (Docker Build)  │     │  (运行容器)       │
│                  │     │                  │     │                  │
│  - deploy.sh     │────→│  docker build    │     │  docker run      │
│  - 代码中转      │     │  docker save     │     │  toll-audit-     │
│  - .env 推送     │     │                  │     │  express         │
└──────────────────┘     └──────────────────┘     └──────────────────┘
         │                        │                        │
         └─── scp 拉回镜像 ───────┘                        │
         └────── scp 推送镜像 ────────────────────────────┘
```

- **构建机 ↔ 目标机网络不通**，必须经本地 macOS 中转
- 部署模式：`code`（仅更新代码，docker cp + restart）或 `full`（重建镜像）

### 7.2 Docker 架构

**多阶段构建 (Dockerfile)：**

```
Stage 1: Node 18-slim     → npm install + npm run build → 前端 dist/
Stage 2: Python 3.10-slim → pip install (含 PyTorch CPU) → Python 依赖
Stage 3: Python 3.10-slim → 复制后端代码 + 前端 dist/ + 模型文件
         → 非root用户 (appuser:1000)
         → HEALTHCHECK (30s 间隔)
         → ENTRYPOINT: uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

**容器内结构：**
```
/app/
├── apps/api/          # 后端代码
├── apps/web/dist/     # 前端构建产物 (SPA)
├── packages/          # 共享契约
├── apps/api/data/     # 数据目录 (volume 挂载)
└── yolov8n.pt         # 模型文件 (volume 只读挂载)
```

FastAPI 同时服务 API 和前端 SPA：
- `/api/*` → API 路由
- 其他路径 → SPA fallback (返回 index.html)
- `/assets/*` → 静态资源

### 7.3 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DB_HOST/PORT/USER/PASSWORD/NAME` | 源库连接 (dwd_tolldata) | localhost:9030 |
| `DB_AUDIT_HOST/PORT/USER/PASSWORD/NAME` | 稽核目标库连接 (ods_AI_DB) | 同源库 |
| `DORIS_POOL_SIZE` | Doris 连接池大小 | 8 |
| `VEHICLE_AI_SERVICE_URL` | vehicle-ai-service 地址 | http://10.11.1.40:8081 |
| `VEHICLE_AI_SERVICE_TIMEOUT` | AI 服务超时 (秒) | 65 |
| `API_KEY` | 静态 API Key 鉴权 | 空 (不鉴权) |
| `AUTH_ENABLED` | 启用 JWT OAuth 鉴权 | false |
| `AUTH_JWT_*` | JWT/OAuth 相关配置 | - |
| `CORS_ORIGINS` | 允许的跨域来源 | http://localhost:3000 |
| `FRONTEND_DIR` | 前端构建产物目录 | apps/web/dist |
| `IMAGE_DOWNLOAD_TIMEOUT/RETRIES` | 图片下载配置 | 15s / 3次 |
| `TRUCK_OBU_CONFIDENCE_THRESHOLD` | 货车OBU置信度阈值 | 0.8 |
| `FINGERPRINT_SIM_THRESHOLD` | 指纹相似度阈值 | 0.6 |
| `MAX_EXECUTION_MINUTES` | 任务最长执行时长 | 60 |
| `GANTRY_IMAGE_BASE` | 门架图片服务地址 | http://10.165.83.43/... |
| `LOG_LEVEL` | 日志级别 | INFO |

### 7.4 CI/CD 流水线

```
GitHub Actions (ci.yml)
  ├── api-lint    → ruff check + format (Python 3.10)
  ├── api-test    → pytest (unit + api, 覆盖率 ≥60%)
  ├── web-test    → ESLint + Vitest + Vite build (Node 20)
  └── docker-build → docker build (仅 main 分支 push)
```

### 7.5 健康检查

- `GET /api/health`：基础存活检查
- `GET /api/health/db`：稽核目标库连接 + audit_trips 行数
- `GET /api/health/doris`：详细诊断（目标库/源库连接状态、版本、表行数、连接池、Doris 后端节点存活状态）

---

## 附录：关键设计决策

1. **Doris 替代 SQLite**：稽核目标库从 SQLite 迁移至 Doris，保留 `connection.py` 向后兼容，新代码统一走 `doris_connection.py`
2. **vehicle-ai-service 外置**：视觉模型（YOLOv8/ResNet）和 LLM 调用从主 API 剥离为独立服务，主 API 仅通过 HTTP 客户端调用，降低主服务依赖和镜像体积
3. **分档裁决器**：在调 LLM 前优先使用廉价信号（颜色/车型/fingerprint_sim/车牌 OCR）做分档判定，大部分 case 可省去 LLM 调用
4. **Repository 模式**：数据访问统一封装为 Repository 类，路由层不直接写 SQL
5. **共享契约**：`packages/contracts` 作为前后端接口契约的单一事实来源，Pydantic 模型定义在此，`apps/api/models/schemas.py` 重新导出
6. **SPA 同源部署**：生产环境 FastAPI 同时服务 API 和前端 SPA，避免跨域和额外 Nginx 层
7. **规则引擎 DSL**：自实现 JSON s-expression 解释器，白名单操作符 + 字段访问，禁止 eval/import，安全求值
8. **Doris 兼容**：Doris 2.1.9-rc02 不支持 UPSERT 语法，采用 SELECT + INSERT/UPDATE 两步走；UNIQUE KEY merge-on-write 存在 read-after-write 延迟，写入后基于请求数据构建响应而非重新读取
