# TollAuditExpress 功能清单

> 本文档梳理项目当前真实可用的功能模块、API 端点、组件、数据库与部署拓扑,作为全量测试与目标机发布的基线参考。
> 扫描基线:2026-06-16,commit `f78c9b2`(develop 分支顶端)。

---

## 1. 项目形态

- **monorepo 结构**:`apps/api`(FastAPI)+ `apps/web`(React/Vite)+ `packages/contracts`(共享契约,当前仅空 `types/`)+ `tests/`(根,跨前后端)
- **架构边界**:前端仅 UI/状态编排;后端负责请求边界/auth/业务/DB/第三方;契约为前后端单一事实来源
- **核心入口**:后端 `apps/api/main.py:35`(`lifespan` 启动初始化 Doris + 后台任务调度器);前端 `apps/web/src/main.jsx:6`(`createRoot` 挂载 `App`)

---

## 2. 后端 API 矩阵

后端共 **41 个端点**,分布在 6 个 router,全部注册于 `apps/api/main.py:51-56`。

### 2.1 系统端点 — `/api/health`(`routers/health.py`)

| Method | Path | 行号 | 说明 |
|---|---|---|---|
| GET | `/api/health` | L8 | 简单存活探针,返回 `{status:"ok"}` |
| GET | `/api/health/db` | L13 | 审计库 Doris 查 `audit_trips` 行数 |
| GET | `/api/health/doris` | L26 | 详细健康:连接池 / 5 张核心表行数 / 源库连通 / 后端节点存活 |

### 2.2 稽核业务 — `/api/audit`(核心,`routers/audit.py`,22 个端点)

| Method | Path | 行号 | 功能 |
|---|---|---|---|
| GET | `/stats/overview` | L49 | 首页 KPI 统计 |
| GET | `/trips` | L57 | 行程列表(分页/筛选) |
| GET | `/trip/{passid}` | L129 | 行程基础详情 |
| GET | `/trip/{passid}/full` | L139 | 行程完整详情(含门架、检测) |
| GET | `/doris/vehicles` | L169 | 源库 Doris 原始通行流水 |
| GET | `/doris/vehicle/{passid}/full` | L240 | 源库单条详情 |
| POST | `/trips/aggregate` | L255 | 触发行程聚合任务(异步) |
| GET | `/trips/aggregate/{task_id}` | L299 | 查询聚合进度 |
| POST | `/trips/aggregate/{task_id}/stop` | L306 | 暂停聚合任务 |
| GET | `/trips/aggregate/stream/{task_id}` | L314 | SSE 流式进度推送 |
| GET | `/suspects` | L330 | 可疑记录列表 |
| POST | `/suspect/{suspect_id}/llm-verify` | L359 | LLM 二次判定 |
| GET | `/suspect/{suspect_id}` | L399 | 可疑记录详情 |
| POST | `/suspect/{suspect_id}/process` | L425 | 人工复核处理 |
| POST | `/detect/passenger-obu` | L433 | 客车 OBU 检测 |
| POST | `/detect/entry-exit` | L478 | 出入口车辆图片比对 |
| POST | `/detect/entry-exit/llm` | L509 | 出入口 LLM 比对 |
| POST | `/detect/recognize-plate` | L536 | 车牌识别 |
| POST | `/trips/re-detect` | L555 | 行程重新检测 |
| GET | `/image-proxy` | L650 | 图片代理(中转下游图片源) |
| GET | `/passenger-obu/overview` | L671 | 客车 OBU 总览 |
| GET | `/passenger-obu/stats/daily` | L692 | 客车 OBU 每日统计 |
| GET | `/passenger-obu/anomalies` | L719 | 客车 OBU 异常明细 |

### 2.3 规则引擎 — `/api/audit/rules`(`routers/rules.py`)

| Method | Path | 行号 | 功能 |
|---|---|---|---|
| GET | `/rules` | L46 | 规则列表(可按 fraud_type / enabled 过滤) |
| GET | `/rules/{rule_id}` | L61 | 规则详情 |
| POST | `/rules` | L70 | 新建规则(JSON s-expression DSL) |
| PUT | `/rules/{rule_id}` | L110 | 更新规则 |
| DELETE | `/rules/{rule_id}` | L152 | 删除 |
| PATCH | `/rules/{rule_id}/toggle` | L161 | 启停切换 |
| PATCH | `/rules/{rule_id}/dry-run` | L178 | 干跑预览 |

### 2.4 定时任务 — `/api/tasks`(`routers/tasks.py`)

| Method | Path | 行号 | 功能 |
|---|---|---|---|
| GET | `/tasks` | L17 | 任务列表 |
| POST | `/tasks` | L25 | 新建 |
| GET | `/tasks/{task_id}` | L34 | 详情 |
| PUT | `/tasks/{task_id}` | L44 | 更新 |
| DELETE | `/tasks/{task_id}` | L59 | 删除 |
| POST | `/tasks/{task_id}/execute` | L70 | 立即执行 |
| GET | `/tasks/{task_id}/executions` | L82 | 执行历史列表 |
| GET | `/tasks/{task_id}/executions/{execution_id}` | L91 | 单次执行详情 |

### 2.5 落地线索 — `/api/landing/leads`(`routers/landing.py`)

| Method | Path | 行号 | 功能 |
|---|---|---|---|
| POST | `/leads` | L27 | 落地页表单提交(带 IP 限流) |
| GET | `/leads` | L51 | 列表查询(管理用) |

### 2.6 OAuth — `/oauth/*`(`routers/oauth.py`,无统一前缀)

| Method | Path | 行号 | 功能 |
|---|---|---|---|
| POST | `/oauth/callback` | L17 | 授权码换 token |
| POST | `/oauth/logout` | L43 | 登出 |
| GET | `/oauth/config` | L63 | 前端拉取登录配置 |

---

## 3. 后端服务层(`apps/api/services/`)

12 个业务服务,职责单一,均位于系统边界附近:

| 文件 | 职责 |
|---|---|
| `trip_aggregator.py` | 按 PASSID 聚合"入口→门架→出口",执行视觉检测 |
| `detectors.py` | 多维度欺诈检测器(4 个 fraud_type) |
| `passenger_obu_detector.py` | 客车 OBU 监测(元数据 + 图片 + LLM) |
| `entry_exit_matcher.py` | 出入口车辆图片比对(调 vehicle-ai-service) |
| `vehicle_comparator.py` | 手动触发双图比对业务封装 |
| `ai_verify_batch.py` | 批量 AI 复核(后台调度 + 检测后入口) |
| `rule_engine.py` | RuleEngine 骨架(JSON s-expression DSL 求值) |
| `rule_loader.py` | 静态规则加载(带错误收集) |
| `task_scheduler.py` | 后台 daemon 线程调度器(`main.py:20,28` 启动) |
| `task_executor.py` | 任务执行器(聚合+检测) |
| `doris_trip_query.py` | 直查 Doris 源库 `dwd_tolldata.t_waste_en_ex_gantry` |
| `image_utils.py` | 图片下载公共工具 |

---

## 4. 数据库与数据迁移

### 4.1 双 Doris 架构

- **源库** `dwd_tolldata`(`DB_*`)— 只读,装原始门架/出入口通行流水,运行时通过 `doris_trip_query.py` 和 `trip_aggregator.py` 访问。
- **目标库** `ods_AI_DB`(`DB_AUDIT_*`)— 读写,装 SQLite 迁移来的派生数据(`audit_trips` / `audit_results` / `audit_actions` / `scheduled_tasks` / `task_executions` 等)。连接走 `apps/api/database/doris_connection.py`(`init_doris()` + `get_connection()` 连接池)。

### 4.2 7 个 DDL(`apps/api/database/migrations/`)

```
001_initial_schema.sql       # 初始 5 张核心表
002_add_visual_fields.sql    # 增加视觉字段
003_scheduled_tasks.sql      # 定时任务相关表
004_gantry_records.sql       # 门架记录
005_vehicle_search_indexes.sql  # 搜索索引
006_add_llm_columns.sql      # LLM 结果字段
007_truck_obu_audit.sql      # 货车 OBU 稽核
```

### 4.3 7 个 Repository(`apps/api/database/repositories/`)

`audit_repository` / `trip_repository` / `rule_repository` / `task_repository` / `topology_repository` / `truck_obu_stats_repository` / `landing_repository` — 全部走 Doris 连接池。

### 4.4 迁移状态

- `apps/api/database/migrate_sqlite_to_doris.py` 提供一次性迁移脚本。
- `apps/api/data/audit.db`(54 MB)仍保留,作为迁移源(本次不动)。
- `apps/api/database/connection.py`(旧 SQLite)目前**仅**被 `conftest.py`(测试替身)和迁移脚本引用,生产代码已全部切到 Doris。

---

## 5. 核心配置开关(`apps/api/core/config.py`)

| 变量 | 默认 | 用途 |
|---|---|---|
| `DB_HOST/PORT/USER/PASSWORD/NAME` | 见 `.env.example` | 源 Doris `dwd_tolldata` |
| `DB_AUDIT_HOST/AUDIT_PORT/...` | 同 `DB_*` 兜底 | 目标 Doris `ods_AI_DB` |
| `IMAGE_DOWNLOAD_TIMEOUT` | `15` | 图片下载超时(秒) |
| `IMAGE_DOWNLOAD_RETRIES` | `3` | 重试次数 |
| `TRUCK_OBU_CONFIDENCE_THRESHOLD` | `0.8` | 货车 OBU 置信度门槛 |
| `FINGERPRINT_SIM_THRESHOLD` | `0.6` | 指纹相似度门槛 |
| `VEHICLE_AI_SERVICE_URL` | `http://10.11.1.40:8081` | 视觉/LLM 公共服务地址 |
| `VEHICLE_AI_SERVICE_TIMEOUT` | `65` | 公共服务调用超时 |
| `CORS_ORIGINS` | `http://localhost:3000` | 跨域白名单 |
| `API_KEY` | — | API Key 鉴权 |
| `AUTH_ENABLED` | `false` | OAuth 统一登录开关(`false` 时走 API_KEY) |
| `LOG_LEVEL` | `INFO` | 日志级别 |

---

## 6. 前端页面与组件(`apps/web/src/`)

### 6.1 路由(`App.jsx:93-129`)

| 路由 | 文件 | 行数 | 主要 API |
|---|---|---|---|
| `/` | `pages/Landing/Landing.jsx` | 营销落地 | `landingApi.submitLead` |
| `/redirect` | `pages/Redirect.jsx` | OAuth 回调 | URL token 解析 |
| `/app` | `pages/Dashboard.jsx` | 238 | `auditApi.getStats` |
| `/app/trips` | `pages/TripQuery.jsx` | 551 | trips/aggregate/getAggregationStatus |
| `/app/vehicles` | `pages/VehicleQuery.jsx` | 512 | getRawVehicles/getRawVehicleFull |
| `/app/suspects` | `pages/SuspectList.jsx` | 424 | suspects/LLM/process |
| `/app/stats` | `pages/Statistics.jsx` | 181 | stats |
| `/app/tasks` | `pages/TaskManager.jsx` | 625 | taskApi 全套 |
| `/app/passenger-obu-monitor` | `pages/PassengerOBUMonitor.jsx` | 372 | overview/daily/anomalies + 触发 |
| `/app/rules` | `pages/RuleStudio.jsx` | 869 | rulesApi 全套 + 中文化辅助 |

`/app/*` 受 `AuthGuard` 保护,基于 `/api/oauth/config` 决定是否强制跳转登录。

### 6.2 关键组件

- `components/VehicleTripDetail.jsx`(323 行)— 行程详情主组件,被 TripQuery/VehicleQuery 复用
- `components/GantryTimeline.jsx`(48)+ `GantryImageTimeline.jsx`(63)— 门架时间线/图片时间线
- `components/tripDetailUtils.jsx`(92)— 行程详情渲染辅助(标签/颜色/格式化)
- `components/SmartImage.jsx`(65)— 智能图片(懒加载 + 失败回退)
- `components/Icon.jsx`(88)— 统一图标,封装 lucide-react
- `components/AuthContext.jsx`(43)— Context + `useAuth()`,token 存 localStorage,401 派发 `auth:invalid` 事件(L23-26)
- `components/AuthGuard.jsx`(27)— 拉取 `/api/oauth/config` 决定是否强制跳转登录
- `components/charts/`(echarts-for-react)— `DailyScanBar`/`LineTrend`/`PieDistribution`

### 6.3 API 调用层(`apps/web/src/api/`)

- `api/audit.js`(232 行)— `auditApi`(20 方法)+ `taskApi`(8 方法);`fetchJSON()`(L7-47)自动注入 Bearer + 401 清理 + `X-New-Access-Token` 续签 + `errorListeners` 广播
- `api/rules.js`(59 行)— `rulesApi`,自动 `JSON.parse(rule_expr)`
- `api/landing.js`(46 行)— 营销表单 `submitLead`,解析 Pydantic 422 错误

### 6.4 状态管理

无 Redux/Zustand/React Query。仅 `AuthContext` Context + 各页面 `useState/useEffect/useRef/useMemo`。

### 6.5 测试覆盖

- `tests/web/test_routing.test.jsx`(4 用例:路由 + 老路径重定向)
- `tests/web/test_landing_form.test.jsx`(6 用例:表单空/非法/合法/422/5xx/submitting)
- **`apps/web/src/` 内 0 个测试文件**,无 hooks/utils/charts 单测,无 E2E(无 playwright 目录)

---

## 7. 部署拓扑

```
本地(macOS,本机)
  └─rsync─► 构建机(159.138.100.157, root)
              ├─ docker buildx 构建镜像
              └─ docker save | gzip
  └─scp──► 目标机(10.11.1.40:8080, root)
              └─ docker load + docker run --restart unless-stopped
```

**关键路径**:
- `deploy.sh:185` 内嵌 `pytest tests/ -m "not slow"`(发布前自动跑)
- `deploy.sh:196` 注释:大文件 rsync 用 save/scp 中转(macOS rsync 2.6.9 与构建机 3.2.7 不兼容)
- `deploy.config.env`:`BUILD_SERVER`/`TARGET_SERVER`/`SERVICE_PORT=8080`(目标机 8000 被 sqlbot 占用)/`SSH_OPTS`
- 容器无 PM2/systemd,完全靠 `--restart unless-stopped` 保活
- 目标机挂载:`-v .../.env:/app/.env:ro`(配置只读)、`-v .../data:/app/apps/api/data`(审计数据)、`-v .../logs:/app/logs`(日志)

---

## 8. 测试与 CI 现状

- 后端覆盖率:commit `b26589c` 将 services 层从 10% 升至 82%;`pytest.ini` 门槛 60%
- 前端测试覆盖率低:仅 2 文件(路由 + 落地页表单),`apps/web/src/` 内零测试
- `tests/e2e/` 仅 `test_health.py` + `test_schemas.py`,用 in-process TestClient
- CI(`.github/workflows/ci.yml`):4 job — `api-lint` + `api-test` + `web-test` + `docker-build`(仅 main)
- 已知遗留:`.hermes/kanban.md` 登记 150+ ruff 历史告警(本次只检查新增)

---

## 9. 当前风险清单

| # | 风险 | 状态 | 缓解 |
|---|---|---|---|
| R1 | `AUTH_ENABLED=false` 默认关闭 | 与目标机现状一致 | 本次发布保持默认 |
| R2 | `apps/api/data/audit.db` 54 MB 未清理 | 保留作迁移源 | Out of scope |
| R3 | ruff 历史告警 150+ | 不修 | 仅检查新增 |
| R4 | RuleStudio/TaskManager 零单测 | 不阻塞 | 记入后续 backlog |
| R5 | E2E 仅 health + schemas | 不阻塞 | kanban 已登记 |
| R6 | 目标机 8000 端口被 sqlbot 占用 | 已规避 | 用 8080 |
| R7 | macOS 与构建机 rsync 大文件不兼容 | 已规避 | save/scp 中转 |

## 10. 不在本期范围(Out of Scope)

- 不删除 SQLite 源文件
- 不新增前端测试
- 不调整 CI/CD 配置
- 不推进 SQLite → Doris 完整 4 阶段迁移的剩余工作
- 不引入新依赖或重构既有模块
