# TollAuditExpress 项目使用手册

> 高速公路收费稽核系统 — 基于 AI 视觉识别的逃费行为检测平台

---

## 目录

1. [项目概述](#1-项目概述)
2. [快速开始](#2-快速开始)
3. [功能模块详解](#3-功能模块详解)
   - 3.1 [仪表盘](#31-仪表盘)
   - 3.2 [行程查询](#32-行程查询)
   - 3.3 [可疑记录](#33-可疑记录)
   - 3.4 [统计分析](#34-统计分析)
   - 3.5 [定时任务](#35-定时任务)
4. [技术架构](#4-技术架构)
5. [API 接口](#5-api-接口)
6. [数据模型](#6-数据模型)
7. [部署指南](#7-部署指南)
8. [配置说明](#8-配置说明)
9. [开发指南](#9-开发指南)
10. [常见问题](#10-常见问题)

---

## 1. 项目概述

TollAuditExpress 是面向高速公路收费稽核业务的智能化系统，通过**双 AI 视觉模型**自动识别潜在的逃费行为，大幅提升稽核效率。

### 1.1 核心能力

| 稽核模型 | 欺诈类型 | 检测对象 |
|---|---|---|
| **货车 OBU 检测** | `TRUCK_USES_PASSENGER_OBU`(货车套用客车 OBU) | 入口车型登记 vs 车辆图像识别 |
| **出入口比对** | `ENTRY_EXIT_MISMATCH`(出入口车辆不一致) | 入口车牌/车标/颜色 vs 出口 |
| **门架路径检测** | `GATEWAY_ANOMALY`(门架序列与拓扑不符) | 门架流水 |
| **车型降档检测** | `VEHICLE_TYPE_DOWNGRADE`(交易记客车,AI 识别为货车) | 交易车型 vs 视觉识别 |
| **同车牌多 OBU** | `SAME_PLATE_DIFF_VEHICLE`(同一车牌历史多 OBU) | 历史绑定关系 |
| **OBU 多车绑定** | `OBU_UNBIND`(同一 OBU 短时间绑多车) | 历史绑定关系 |
| **OBU 屏蔽** | `OBU_SHIELD`(客车记录无 OBU 但有出口图) | 介质类型 vs 出口图片 |
| **车牌 OBU 历史** | `PLATE_OBU_HISTORY`(车牌-OBU 历史异常) | 历史绑定关系 |

### 1.2 系统功能

- 📊 **数据聚合**:从源数据库(Doris/StarRocks)拉取门架通行记录,按 PASSID 聚合成完整行程
- 🔍 **行程查询**:多条件筛选(站点、时间、状态)
- 🚙 **车辆查询**:按车牌/OBU 跨行程反查历史绑定关系
- ⚠️ **可疑识别**:AI 模型自动识别逃费嫌疑,结果入库(8 类欺诈)
- ✅ **人工稽核**:确认/驳回可疑记录,保留操作审计
- 📈 **统计分析**:实时统计总览、趋势分析
- 🛠 **规则管理**:JSON s-expression 规则 CRUD,支持 `dry_run` 演练
- ⏰ **自动化**:定时任务系统(5 种 task_type),支持自定义筛选规则和调度策略
- 🚀 **一键部署**:Docker 化,本地 + 远程三机拓扑

### 1.3 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | React 18 + React Router v6 + Vite 5 |
| 后端 | FastAPI + Uvicorn + Pydantic v2 |
| 数据库 | Doris(`dwd_tolldata` 只读源库 + `ods_AI_DB` 读写目标库,pymysql 连接池) |
| 共享契约 | Pydantic(Python)+ TypeScript |
| AI 模型 | **vehicle-ai-service**(独立公共服务,部署在目标机 `10.11.1.40:8081`,主项目不自部署) |
| 鉴权 | JWT/OAuth PKCE 双模式(`AUTH_ENABLED` 切换) |
| 部署 | Docker + 三机拓扑(macOS 调度 / 构建机 / 运行机) |

---

## 2. 快速开始

### 2.1 本地开发模式

**前置条件：** Node.js 18+, Python 3.10+

```bash
# 1. 安装 Python 依赖
cd apps/api
pip install -r requirements.txt

# 2. 启动后端（端口 8000）
cd ../..
python -m uvicorn apps.api.main:app --reload --port 8000

# 3. 另开终端，启动前端（端口 3000）
cd apps/web
npm install --legacy-peer-deps
npm run dev
```

**访问：** http://localhost:3000

### 2.2 Docker 部署模式

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填写 DB_HOST, DB_USER, DB_PASSWORD 等

# 2. 启动
docker-compose up -d --build

# 3. 查看状态
docker-compose ps
curl http://localhost:8000/health
```

**访问：** http://localhost:8000（前后端同端口）

### 2.3 一键发布

```bash
# 生成本地发布包
./build.sh
# 输出: toll-audit-express-20260603-xxxxxx.tar.gz

# 部署到远程服务器
./deploy.sh code   # 仅热更新代码
./deploy.sh full   # 完整重建镜像
```

---

## 3. 功能模块详解

### 3.1 仪表盘

**路径：** `/`

**功能：**
- **总览统计卡片**：展示总行程数、已稽核数、可疑数、确认逃费数
- **批量聚合**：选择天数（1-30）和数量限制（10-5000），从源库拉取门架记录聚合成行程
- **实时进度**：聚合过程中通过 SSE 流推送进度（已处理 / 总数 / 当前 PASSID）
- **停止控制**：支持中途停止聚合任务
- **补检测入口**：对未完成视觉识别的行程重新运行检测

**操作流程：**
```
点击"开始批量聚合"
  → 调整天数滑块（如 7 天）
  → 调整数量限制（如 1000 条）
  → 点击"开始聚合"
  → 观察实时进度条和当前处理 PASSID
  → 完成后系统自动跳转到"行程查询"
```

**关键指标：**
- `total_trips` — 总行程数
- `verified_trips` — 已稽核（视觉识别完成）
- `suspected_trips` — 可疑记录
- `confirmed_fraud` — 已确认逃费

### 3.2 行程查询

**路径：** `/trips`

**功能：**
- **多条件筛选**：
  - 入口站（模糊匹配）
  - 出口站（模糊匹配）
  - 起始时间 / 结束时间
  - 稽核状态（PENDING / VERIFIED / SUSPECTED / CONFIRMED）
- **分页浏览**：默认 100 条/页，可调整 limit/offset
- **行程详情**：点击 PASSID 查看入口/出口完整记录（车牌、车型、OBU、图像 URL）
- **手动检测**：详情页可触发"模型 A 检测"和"模型 B 检测"

**状态说明：**
| 状态 | 含义 |
|---|---|
| `UNPROCESSED` | 未处理(初始态) |
| `PENDING` | AI 复核中 |
| `AI_VERIFIED` | AI 复核完成(由公共服务判定) |
| `VERIFIED` | 已验证(识别完成,未发现异常) |
| `SUSPECTED` | 可疑(识别发现异常) |
| `CONFIRMED` | 已确认逃费(人工稽核确认) |

### 3.3 可疑记录

**路径：** `/suspects`

**功能：**
- **可疑列表**：所有 AI 识别为"可疑"的稽核结果
- **筛选维度**：
  - 欺诈类型(支持多选):
    - `TRUCK_USES_PASSENGER_OBU`(货车套用客车 OBU)
    - `ENTRY_EXIT_MISMATCH`(出入口车辆不一致)
    - `GATEWAY_ANOMALY`(门架路径异常)
    - `VEHICLE_TYPE_DOWNGRADE`(车型降档)
    - `SAME_PLATE_DIFF_VEHICLE`(同车牌多 OBU)
    - `OBU_UNBIND`(OBU 多车绑定)
    - `OBU_SHIELD`(OBU 屏蔽)
  - 处理状态(`UNPROCESSED` / `AI_VERIFIED` / `CONFIRMED` / `REJECTED`)
- **详情查看**：点击查看检测详情（识别类型、置信度、风险评分）
- **稽核操作**：
  - **确认逃费**（CONFIRMED）：标记为真实逃费行为
  - **驳回**（REJECTED）：误报
  - 填写操作员姓名 + 备注（写入审计日志）
- **图像对比**：详情页支持出入口图像并排对比

**操作流程：**
```
进入"可疑记录"页
  → 点击可疑记录
  → 查看检测详情（模型 A 或 B 的识别结果）
  → 查看图像对比（如有图像）
  → 确认/驳回
  → 填写操作员和备注
  → 提交
  → 列表自动更新处理状态
```

### 3.4 统计分析

**路径：** `/stats`

**功能：**
- **总览统计**：与仪表盘同源
- **趋势分析**：可疑记录时间分布、欺诈类型分布
- **稽核员工作量**：按操作员统计确认/驳回数

### 3.5 车辆查询

**路径：** `/vehicles`

**功能：**
- **按车牌号查询**：输入车牌号,展示该车牌的所有行程历史
- **按 OBU 编号查询**：输入 OBU 编号,展示该 OBU 绑定的所有车辆
- **历史绑定关系可视化**：时间轴展示车牌-OBU 绑定关系变更
- **欺诈关联**：高亮显示该车牌/OBU 涉及的可疑记录

### 3.6 规则管理

**路径：** `/rules`

**功能：**
- **规则列表**：显示所有检测规则,字段包含名称/欺诈类型/严重度/阈值/`dry_run`/启用
- **规则创建/编辑**：JSON s-expression DSL(16 个白名单操作符)在线编辑
- **`dry_run` 演练**：开启后规则匹配只记录不落库,适合新规则灰度
- **启用/停用**：单条规则可独立启停,不影响其他规则

### 3.7 定时任务

**路径：** `/tasks`

**功能：**
- **任务列表**：显示所有定时任务，状态包括启用/停用、上次执行、下次执行
- **任务创建**：点击"+ 新建任务"打开表单
  - 任务名称（必填）
  - 描述（可选）
  - 任务类型：
    - `aggregate_detect` — 聚合+检测（推荐）
    - `detect_only` — 仅检测
    - `re_detect` — 补检测
  - 筛选规则：出口站、入口站、天数（1-30）、条数限制（10-5000）
  - 调度设置：间隔分钟（5-1440）
- **任务操作**：
  - 启用/停用
  - 立即执行（手动触发）
  - 编辑
  - 删除
- **执行历史**：展开任务卡片查看历史执行记录
  - 状态（运行中 / 已完成 / 失败）
  - 开始时间、完成时间
  - 结果摘要（聚合X 检测Y 可疑Z）
  - 错误信息（如有）
- **实时轮询**：点击"立即执行"后，前端每 2 秒轮询状态，展开区域自动显示运行状态

**任务类型详解：**
| 类型 | 适用场景 | 性能 |
|---|---|---|
| `aggregate_detect` | 增量拉取新数据并检测 | 较慢（受 Doris 拉取速度影响） |
| `detect_only` | 对本地已有行程补检测 | 较快（仅跑 AI 模型） |
| `re_detect` | 对缺失视觉结果的行程重新检测 | 中等 |

**典型使用模式：**
```
场景 1：每 2 小时自动监测甘泉堡匝道站
  → 任务类型: aggregate_detect
  → 筛选: 出口站=甘泉堡, 3天, 500条
  → 调度: 每 120 分钟

场景 2：每 30 分钟对未检测行程补检测
  → 任务类型: re_detect
  → 调度: 每 30 分钟

场景 3：每 10 分钟快速检测本地数据
  → 任务类型: detect_only
  → 筛选: 限 200 条
  → 调度: 每 10 分钟
```

---

## 4. 技术架构

### 4.1 整体架构

```
┌──────────────────────────────────────────────────────────┐
│                    Frontend (React)                       │
│ Dashboard │ Trip │ Vehicle │ Suspects │ Stats │ Rules │ Tasks│
│         ↓ fetchJSON + Bearer Token                        │
└──────────────────────────────────────────────────────────┘
                           │ HTTP REST
┌──────────────────────────────────────────────────────────┐
│                   FastAPI (main.py)                       │
│  ┌─ JWT/OAuth Middleware ─┐  ┌─ CORS Middleware ─┐         │
│  │ /health (公开)           │  │ SPA Fallback (生产)│        │
│  └──────────────────────────┘  └────────────────────┘         │
│  Routers: health / audit / tasks / rules / oauth            │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  TripAggregator │ TruckOBUDetector │ EntryExitMatcher│ │
│  │  TaskScheduler  │ TaskExecutor    │ RuleEngine       │ │
│  │  VehicleComparator (调公共服务)                      │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
         │              │              │              │
         ↓              ↓              ↓              ↓
   ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌──────────┐
   │  Doris   │  │ vehicle-ai-  │  │ 抓拍服务器 │  │ OAuth   │
   │ ods_AI_DB│  │   service    │  │ (内网图片)│  │ 登录平台 │
   │ (读写)   │  │ (目标机 8081) │  │          │  │          │
   └──────────┘  └──────────────┘  └──────────┘  └──────────┘
   audit_trips
   audit_results
   scheduled_tasks
   task_executions
   detection_rules
   gateway_topology
```

### 4.2 公共服务拆分(vehicle-ai-service)

自 Phase 4 起,所有视觉识别(车型、车纹、出入口比对、货车套 OBU)和 LLM 二次判定从主项目拆出,部署在 `vehicle-ai-service`(独立仓库,目标机 `10.11.1.40:8081`)。主项目不再自部署任何 AI 模型。

**调用入口**:`apps/api/core/vehicle_ai_client.py` 暴露 `get_client()` 单例,提供 3 个端点:
- `compare(entry_url, exit_url, **9 项元数据)` — 出入口双图"同一辆车"判定
- `entry_exit(entry_url, exit_url)` — 出入口视觉信号(颜色/车型/车纹)
- `truck_obu(image_url, declared_vehicle_type=1)` — 货车套用客车 OBU 检测

**降级契约**:公共服务不可用时,客户端返回 `{'error': 'service_unavailable', 'detail': '...'}`,业务封装不抛异常,返回安全的默认结果(降级而非崩溃)。

**SSRF 防护**:`image_utils` 强制域名白名单,禁止 `169.254/10.x/192.168/127.x/localhost/metadata.*` 等内网与元数据地址。

### 4.2 目录结构

```
TollAuditExpress/
├── apps/
│   ├── api/                       # 后端 (FastAPI)
│   │   ├── main.py                # 应用入口
│   │   ├── core/                  # 基础设施
│   │   │   ├── auth.py            # API Key 中间件
│   │   │   ├── config.py          # 配置加载
│   │   │   ├── logging_config.py  # 日志配置
│   │   │   └── ml/                # AI 模型封装
│   │   ├── database/
│   │   │   ├── doris_connection.py  # Doris 连接池（pymysql）
│   │   │   ├── doris_ddl.sql        # DDL 幂等建表
│   │   │   └── repositories/        # 数据访问层
│   │   ├── models/
│   │   │   └── schemas.py         # (已迁移到 packages/contracts)
│   │   ├── routers/               # API 路由
│   │   │   ├── audit.py
│   │   │   ├── health.py
│   │   │   └── tasks.py
│   │   └── services/              # 业务逻辑
│   │       ├── trip_aggregator.py
│   │       ├── truck_obu_detector.py
│   │       ├── entry_exit_matcher.py
│   │       ├── image_utils.py
│   │       ├── task_scheduler.py
│   │       └── task_executor.py
│   ├── web/                       # 前端 (React + Vite)
│   │   ├── src/
│   │   │   ├── App.jsx
│   │   │   ├── api/audit.js       # API 客户端
│   │   │   ├── pages/             # 页面
│   │   │   └── styles/global.css  # 设计 tokens + 组件样式
│   │   └── vite.config.js
│   └── ...
├── packages/
│   └── contracts/                 # 共享契约（前后端类型）
│       └── types/
│           ├── schemas.py         # Pydantic 模型
│           └── index.ts           # TypeScript 接口
├── tests/
│   ├── unit/                      # 单元测试
│   ├── api/                       # API 集成测试
│   └── e2e/                       # 端到端测试
├── scripts/                       # 数据处理脚本
├── Dockerfile                     # 多阶段构建
├── docker-compose.yml             # 容器编排
├── build.sh                       # 构建发布包
├── deploy.sh                      # 一键部署
└── pytest.ini
```

---

## 5. API 接口

### 5.1 鉴权

除 `/`、`/health`、`/health/*`、`/docs`、`/openapi.json`、`/redoc`、`/assets/*` 外，所有 API 需在请求头携带 Bearer Token：

```bash
curl http://localhost:8000/api/audit/trips \
  -H "Authorization: Bearer YOUR_API_KEY"
```

或使用 `X-API-Key` header。如未设置 `API_KEY` 环境变量，鉴权自动跳过（开发模式）。

### 5.2 接口列表

#### 健康检查
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 根路径（生产模式返回前端 index.html） |
| GET | `/health` | 服务健康检查 |
| GET | `/health/db` | 数据库连接检查 |
| GET | `/health/doris` | Doris 连接池状态、副本延迟 |
| GET | `/docs` | OpenAPI 文档（Swagger UI） |

#### 行程管理
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/audit/stats/overview` | 统计总览 |
| GET | `/api/audit/trips` | 行程列表（支持筛选） |
| GET | `/api/audit/trip/{passid}` | 行程详情 |
| POST | `/api/audit/trips/aggregate` | 启动聚合任务 |
| GET | `/api/audit/trips/aggregate/{task_id}` | 聚合状态 |
| POST | `/api/audit/trips/aggregate/{task_id}/stop` | 停止聚合 |
| GET | `/api/audit/trips/aggregate/stream/{task_id}` | SSE 流式进度 |
| POST | `/api/audit/trips/re-detect` | 补检测任务 |

#### 可疑记录
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/audit/suspects` | 可疑列表 |
| GET | `/api/audit/suspect/{id}` | 详情 |
| POST | `/api/audit/suspect/{id}/process` | 确认/驳回 |

#### 手动检测
| 方法 | 路径 | 请求体 | 说明 |
|---|---|---|---|
| POST | `/api/audit/detect/truck-obu` | `{"passid": "xxx"}` | 模型 A 检测 |
| POST | `/api/audit/detect/entry-exit` | `{"passid": "xxx"}` | 模型 B 检测 |

#### 定时任务
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/tasks` | 任务列表 |
| POST | `/api/tasks` | 创建任务 |
| GET | `/api/tasks/{id}` | 任务详情 |
| PUT | `/api/tasks/{id}` | 更新任务 |
| DELETE | `/api/tasks/{id}` | 删除任务 |
| POST | `/api/tasks/{id}/execute` | 立即执行 |
| GET | `/api/tasks/{id}/executions` | 执行历史 |

### 5.3 请求示例

**批量聚合：**
```bash
curl -X POST http://localhost:8000/api/audit/trips/aggregate \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"days": 7, "limit": 500}'
```

**响应：**
```json
{"task_id": "abc-123-def", "status": "started"}
```

**查询进度：**
```bash
curl http://localhost:8000/api/audit/trips/aggregate/abc-123-def \
  -H "Authorization: Bearer $API_KEY"
```

**响应：**
```json
{
  "status": "running",
  "current": 142,
  "total": 500,
  "count": 142,
  "passid": "PASS20250603000001"
}
```

**创建定时任务：**
```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "甘泉堡匝道站监测",
    "description": "每2小时自动检测甘泉堡匝道",
    "task_type": "aggregate_detect",
    "filter_rules": {"exit_station": "甘泉堡", "days": 3, "limit": 500},
    "schedule_type": "interval",
    "schedule_config": {"minutes": 120}
  }'
```

---

## 6. 数据模型

### 6.1 Doris 表结构（`ods_AI_DB`）

#### `audit_trips`（行程）
```sql
passid          VARCHAR(120) UNIQUE NOT NULL  -- 通行标识
id              BIGINT AUTO_INCREMENT
entry_time      DATETIME                     -- 入口时间
entry_station_name VARCHAR(128)               -- 入口站名
entry_vehicle_type  TINYINT                   -- 入口车型 (1=客车, 2=货车)
entry_obu_id    VARCHAR(64)                   -- 入口 OBU 编号
entry_image_license VARCHAR(512)              -- 入口车牌图像 URL
entry_image_trans   VARCHAR(512)              -- 入口车体/侧面图像 URL
exit_time       DATETIME                     -- 出口时间
exit_station_name   VARCHAR(128)
exit_image_license  VARCHAR(512)
exit_image_trans    VARCHAR(512)
audit_status    VARCHAR(20) DEFAULT 'PENDING' -- PENDING/VERIFIED/SUSPECTED/CONFIRMED
risk_score      DECIMAL(4,3) DEFAULT 0
entry_visual_type   VARCHAR(32)               -- AI 识别入口车型
exit_visual_type    VARCHAR(32)
fingerprint_sim     DECIMAL(4,3)              -- 出入口指纹相似度
UNIQUE KEY(passid)
```

#### `audit_results`（稽核结果）
```sql
id              BIGINT AUTO_INCREMENT
audit_trip_id   BIGINT                       -- 关联 audit_trips.id
fraud_type      VARCHAR(64)                  -- TRUCK_USES_PASSENGER_OBU / ENTRY_EXIT_MISMATCH
entry_visual_type / exit_visual_type VARCHAR(32)
entry_color / exit_color VARCHAR(16)
is_suspicious   TINYINT (0/1)
risk_score      DECIMAL(4,3)
process_status  VARCHAR(20) DEFAULT 'UNPROCESSED' -- UNPROCESSED/CONFIRMED/REJECTED
details         JSON
```

#### `scheduled_tasks`（定时任务）
```sql
id              BIGINT AUTO_INCREMENT
name            VARCHAR(128) NOT NULL
task_type       VARCHAR(32)                  -- aggregate_detect / detect_only / re_detect
filter_rules    JSON
schedule_type   VARCHAR(16) DEFAULT 'interval'
schedule_config JSON                         -- {"minutes": 60}
enabled         TINYINT DEFAULT 1
last_run_at     DATETIME
next_run_at     DATETIME
```

#### `task_executions`（任务执行历史）
```sql
id              BIGINT AUTO_INCREMENT
task_id         BIGINT
status          VARCHAR(16)                  -- running/completed/failed
started_at      DATETIME
completed_at    DATETIME
result_summary  JSON                         -- {"aggregated": 100, "detected": 80, "suspected": 3}
error_message   VARCHAR(2048)
```

### 6.2 源数据库（Doris `dwd_tolldata`）

表：`dwd_tolldata.t_waste_en_ex_gantry`

| 字段 | 说明 |
|---|---|
| `PASSID` | 通行标识（聚合主键） |
| `LANETYPE` | 车道类型（"出口" / "入口"） |
| `MEDIATYPE` | 介质类型 (1=OBU) |
| `OCCURTIME` | 通行时间 |
| `STATION_NAME` | 站点名称 |
| `VEHICLETYPE` | 车辆类型 |
| `image_license` | 车牌图像 |
| `image_trans` | 车体/侧面图像 |

---

## 7. 部署指南

### 7.1 三机部署拓扑

```
┌─────────────────┐       ┌──────────────────────┐
│  本地 macOS     │──────▶│  构建机 159.138.100.157│
│  (开发 & 调度)   │       │  (Docker 27.5.1)      │
│                 │       │  - docker build       │
│                 │       │  - docker save        │
│                 │       └──────────────────────┘
│                 │            ▲              │
│                 │            │ 镜像 tar      │ 镜像 tar
│                 │            │              ▼
│                 │       ┌──────────────────────┐
│                 │──────▶│  运行机 10.11.1.40    │
└─────────────────┘       │  (Docker 24.0.7)     │
                          │  - docker load       │
                          │  - docker run        │
                          └──────────────────────┘
```

**关键约束**：构建机 ↔ 运行机 **网络不通**，镜像 tar 必须经本地 macOS 中转。本仓库的 `./deploy.sh full` 已实现这个桥接逻辑。

| 角色 | IP | 用途 |
|---|---|---|
| 本地 macOS | — | 调度：`rsync` 触发两端同步；镜像 tar 中转 |
| 构建机 | `159.138.100.157` | `docker build` 多阶段镜像（PyTorch CPU + Node） |
| 运行机 | `10.11.1.40` | 承载 `toll-audit-express:latest` 容器，**8080 端口**（8000 已被 sqlbot 占用） |

### 7.2 首次部署前置条件

**本地 macOS：**
```bash
# 1. 安装依赖工具
brew install rsync                  # macOS 自带 rsync 通常够用
which docker ssh rsync              # 应都有

# 2. 准备 SSH 免密登录（如果还没做）
ssh-copy-id root@159.138.100.157
ssh-copy-id root@10.11.1.40

# 3. 准备真实部署配置
cp deploy.config.env.example deploy.config.env
vim deploy.config.env               # 改 BUILD_SERVER / TARGET_SERVER 为真实 IP

# 4. 准备真实 .env（含真实密钥）
cp .env.example .env
vim .env                            # 填 DB_* / LLM_KEY 等

# 5. 验证联通性
./scripts/check-conn.sh
# 期望：构建机 + 目标机都打 ✓
```

**目标机（10.11.1.40）：**
- 装好 Docker 24+
- `docker info` 能正常输出
- 8080 端口空闲（或停掉占用它的旧容器；目标机的 8000 已被 sqlbot 占用，本项目部署用 8080）

### 7.3 全量发布（首次或依赖变更）

```bash
./deploy.sh full
```

脚本自动完成：
1. 本地构前端（如未构）
2. 清构建机旧镜像
3. `rsync` 源码到构建机 `/opt/toll-audit-build`（排除 `.env`）
4. 构建机 `docker build -t toll-audit-express:latest .`
5. 构建机 `docker save` → 拉回本地 `/tmp`
6. 本地 → 目标机 `/tmp`（**桥接镜像传输**）
7. 推 `.env` 到目标机 `/opt/toll-audit/.env`（chmod 600）
8. 目标机 `docker load` + `docker run -d`（自动清掉旧 `toll-audit` 同名/同名镜像的孤儿容器）
9. `curl /health` 校验

**预计耗时**：5–10 分钟（多阶段构建要装 PyTorch CPU + Node 依赖）。

### 7.4 局部热更新（日常迭代）

代码改动后、不需要重装 Python 依赖时：

```bash
./deploy.sh code
```

脚本自动完成：
1. 推 `.env`（如果本地有变化）
2. `rsync` 源码到目标机 `/opt/toll-audit`（排除 `.env` / `node_modules` / `__pycache__`）
3. `docker cp` 把代码塞进运行中的容器
4. `docker restart`
5. `curl /health` 校验

**预计耗时**：10–30 秒。

### 7.5 健康检查与日志

```bash
# 容器状态
ssh root@10.11.1.40 "docker ps --format '{{.Names}}: {{.Status}}' | grep toll-audit-express"

# 健康端点
curl http://10.11.1.40:8080/health
curl http://10.11.1.40:8080/health/db
curl http://10.11.1.40:8080/health/doris

# 容器日志（最近 200 行）
ssh root@10.11.1.40 "docker logs --tail 200 toll-audit-express"

# 进入容器调试
ssh root@10.11.1.40 "docker exec -it toll-audit-express bash"

# 实时日志
ssh root@10.11.1.40 "docker logs -f toll-audit-express"
```

### 7.6 故障排查

| 现象 | 排查命令 / 处理 |
|---|---|
| `./deploy.sh full` 第 4 步构建失败 | `ssh root@159.138.100.157 "cd /opt/toll-audit-build && docker build -t toll-audit-express:latest . 2>&1 \| tail -50"` 看具体报错（一般是 `apps/api/requirements.txt` 装包失败） |
| 健康检查返回 000 | `ssh root@10.11.1.40 "docker ps -a \| grep toll-audit"` 看容器是否 exited；`docker logs --tail 200 toll-audit-express` 看启动日志 |
| 容器启动后立刻退出 | 大概率 `.env` 缺关键变量（`DB_HOST` / `MAAS_API_KEY`），看启动日志中的 KeyError 或 pymysql 连接错误 |
| 部署端口（默认 8080）已被占用 | `ssh root@10.11.1.40 "ss -ltnp \| grep :8080"`；停掉占用方或改 `deploy.config.env` 的 `SERVICE_PORT` 后重跑 `./deploy.sh full` |
| 目标机上有同名旧容器（脚本没自动清掉） | `ssh root@10.11.1.40 "docker rm -f <old-name>"` 手动清；本脚本的 `cleanup_orphan_containers` 会清 `toll-audit` 镜像的孤儿 |
| 旧的 SQLite 数据想保留 | 数据在宿主机 `/opt/toll-audit/apps/api/data/audit.db`（容器挂在 `/app/apps/api/data`），卷外删除容器不会丢 |
| `truck` 之类的旧容器残留 | 手动 `docker stop truck && docker rm truck`；本脚本按 image 名匹配，可能不命中无 image 标签的旧容器 |
| 镜像 tar 太大、传输慢 | 第一次跑会传 ~1–2GB 镜像；后续增量只 rsync 源码即可（用 `code` 模式） |

---

## 8. 配置说明

### 8.1 环境变量

参考 `.env.example`：

```bash
# === API 鉴权（生产环境必填） ===
API_KEY=your-secret-key-here

# === CORS（开发环境允许所有） ===
CORS_ORIGINS=*

# === Doris/StarRocks 源数据库 ===
DB_HOST=192.168.1.100
DB_PORT=9030
DB_USER=root
DB_PASSWORD=password
DB_NAME=dwd_tolldata

# === 检测阈值 ===
FINGERPRINT_SIM_THRESHOLD=0.6
TRUCK_OBU_CONFIDENCE_THRESHOLD=0.8

# === LLM 服务（可选） ===
ZHIPUAI_API_KEY=
DOUBAO_API_KEY=
QWEN_API_KEY=
MAAS_API_KEY=
OLLAMA_API_URL=http://localhost:11434
```

### 8.2 调度器配置

调度器（`task_scheduler.py`）每 30 秒扫描一次到期任务（`next_run_at <= now`），如有正在运行的任务则跳过。间隔最小 5 分钟。

### 8.3 数据库初始化

启动时自动执行 `apps/api/database/doris_ddl.sql`（幂等 `CREATE TABLE IF NOT EXISTS`），通过 `migration_log` 表跟踪已应用版本。

### 8.4 环境变量（目标库）

```bash
# === Doris 目标库（稽核结果存储） ===
DB_AUDIT_HOST=10.11.1.36
DB_AUDIT_PORT=9030
DB_AUDIT_USER=root
DB_AUDIT_PASSWORD=
DB_AUDIT_NAME=ods_AI_DB
DORIS_POOL_SIZE=8
```

---

## 9. 开发指南

### 9.1 添加新的 API 端点

1. **定义契约**（`packages/contracts/types/schemas.py`）：
   ```python
   class MyResponse(BaseModel):
       field1: str
       field2: int
   ```

2. **添加路由**（`apps/api/routers/audit.py`）：
   ```python
   @router.get("/my-endpoint", response_model=MyResponse)
   async def my_endpoint():
       return MyResponse(field1="value", field2=42)
   ```

3. **前端 API 客户端**（`apps/web/src/api/audit.js`）：
   ```javascript
   export const auditApi = {
     myEndpoint: () => fetchJSON('/api/audit/my-endpoint')
   }
   ```

4. **调用**：
   ```javascript
   const data = await auditApi.myEndpoint()
   ```

### 9.2 添加新页面

1. 创建 `apps/web/src/pages/MyPage.jsx`
2. 在 `App.jsx` 中注册：
   ```jsx
   import MyPage from './pages/MyPage'
   <Route path="/my-page" element={<MyPage />} />
   ```
3. 添加导航项（NavLink）

### 9.3 添加新的 AI 模型

1. 在 `apps/api/core/ml/` 中新建模型类
2. 在 `apps/api/services/` 中封装业务逻辑
3. 在 `audit.py` 路由中暴露接口
4. 在 `task_executor.py` 中支持（可选）

### 9.4 测试

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit/

# 运行 API 集成测试
pytest tests/api/

# 带覆盖率
pytest --cov=apps/api
```

---

## 10. 常见问题

### Q1: 启动报错 "数据库表不存在"

**A:** 检查 Doris 目标库是否可达，DDL 是否执行成功：
```bash
curl http://localhost:8000/health/db
# 或手动验证
python -c "
from apps.api.database.doris_connection import get_connection
with get_connection() as conn:
    cur = conn.cursor()
    cur.execute('SHOW TABLES')
    print([r[0] for r in cur.fetchall()])
"
```

### Q2: 前端 401 错误

**A:** 检查 `.env` 中 `API_KEY` 设置，前端通过 Bearer Token 传递。如未设置 `API_KEY`，开发模式自动跳过鉴权。

### Q3: AI 模型检测慢

**A:** 
- 使用 CPU 模式时检测较慢，建议有 GPU 环境下将 Dockerfile 改为 CUDA 版本
- `re_detect` 任务批量处理时可能耗时较长，可调小 limit

### Q4: 聚合任务一直 "running"

**A:** 检查 Doris 源库是否可达。如 Doris 不可达，聚合会卡住或失败。
```bash
docker exec -it toll-audit-express python -c "
from apps.api.services.trip_aggregator import DB_CONFIG
import pymysql
conn = pymysql.connect(**DB_CONFIG)
print('OK')
"
```

### Q5: 定时任务不执行

**A:** 检查：
1. 任务是否启用（`enabled=1`）
2. 调度器是否启动（启动日志应有 "Task scheduler started"）
3. `next_run_at` 是否正确
4. 查看执行历史是否有失败记录

### Q6: 部署后访问首页显示 404

**A:** 检查前端 `dist` 是否成功构建。容器内执行：
```bash
docker exec -it toll-audit-express ls /app/apps/web/dist/
```

### Q7: 图像加载失败

**A:** 检查 `STATION_NAME` 和 `LANE_ID` 是否正确。图像 URL 模式：
```
http://{IPADDRESS}/img/data/{LANE_ID}/{date}/{ID}{suffix}.jpg
```

---

## 附录 A: 完整 API 响应示例

**行程列表：**
```json
{
  "trips": [
    {
      "id": 1,
      "passid": "PASS20250603000001",
      "entry_time": "2026-06-03 08:30:15",
      "entry_station_name": "乌拉泊",
      "entry_vehicle_type": 1,
      "entry_image_license": "http://10.0.0.1/img/data/L01/20260603/xxx_lic.jpg",
      "exit_time": "2026-06-03 10:15:30",
      "exit_station_name": "甘泉堡匝道站",
      "audit_status": "SUSPECTED",
      "risk_score": 0.87
    }
  ],
  "total": 1523,
  "limit": 100,
  "offset": 0
}
```

**可疑记录详情：**
```json
{
  "id": 42,
  "audit_trip_id": 123,
  "fraud_type": "TRUCK_USES_PASSENGER_OBU",
  "passid": "PASS20250603000042",
  "entry_vehicle_type": 2,
  "entry_visual_type": "truck",
  "is_suspicious": 1,
  "risk_score": 0.92,
  "process_status": "UNPROCESSED",
  "details": "{\"confidence\": 0.92, \"visual_vehicle_type\": \"truck\", \"registered_type\": 1}"
}
```

## 附录 B: 性能基线参考

| 操作 | 数据量 | 耗时 |
|---|---|---|
| 聚合 100 条 | 100 PASSID | ~10s |
| 聚合 500 条 | 500 PASSID | ~1-3min |
| 模型 A 检测 | 单条 | ~200-500ms |
| 模型 B 检测 | 单条 | ~300-800ms |
| Doris 行程查询 | 26K 条 | <100ms |
| 补检测 | 500 条 | ~5-10min |

性能受硬件（CPU/GPU）、网络（Doris 源库延迟）、数据量影响。
