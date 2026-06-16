# TollAuditExpress — 高速公路收费稽核系统

基于 FastAPI + React 的全栈稽核平台，用于高速公路通行数据的异常检测、车辆比对与收费稽核。

## 功能概览

| 模块 | 说明 |
|------|------|
| 行程查询 | 按车牌、时间段等条件检索通行流水，支持出入口匹配与门架图片回放 |
| 车辆查询 | 跨库查询车辆行程明细，AI 辅助比对车脸/部件一致性 |
| 可疑记录 | 自动标记 OBU 异常、套牌嫌疑、通行路径矛盾等稽核线索 |
| 统计分析 | 可疑类型分布、日扫描趋势、通行量统计等可视化图表 |
| 定时任务 | 可配置定时稽核扫描任务，支持手动触发与执行历史查看 |
| 客车 OBU 监测 | 专项检测客车 OBU 安装与一致性异常 |
| 规则管理 | 可视化编辑稽核检测规则，支持规则启用/禁用与表达式校验 |

## 技术栈

**后端** — Python 3.10 / FastAPI / Pydantic v2 / Uvicorn / Apache Doris (MySQL 协议) / PyJWT / httpx / tenacity

**前端** — React 18 / Vite 5 / React Router v6 / ECharts 5 / Lucide React

**共享契约** — `packages/contracts` 存放前后端共享的 DTO 与类型定义

**基础设施** — Docker 多阶段构建 / docker-compose / GitHub Actions CI

## 项目结构

```
TollAuditExpress/
├── apps/
│   ├── api/                  # FastAPI 后端
│   │   ├── main.py           # 应用入口 & 路由注册
│   │   ├── core/             # 配置、鉴权、JWT、限流、日志
│   │   ├── routers/          # API 路由 (audit, tasks, rules, oauth, landing, health)
│   │   ├── services/         # 业务逻辑 (稽核、比对、调度、规则引擎)
│   │   ├── models/           # Pydantic schemas
│   │   └── database/         # Doris 连接、Repository、迁移
│   └── web/                  # React 前端
│       └── src/
│           ├── pages/        # 页面组件 (Dashboard, TripQuery, SuspectList, …)
│           ├── components/   # 通用组件 (图表、门架时间线、鉴权守卫)
│           ├── api/          # 后端 API 调用封装
│           └── styles/       # 全局样式
├── packages/
│   └── contracts/            # 前后端共享类型与 DTO
├── tests/
│   ├── unit/                 # 后端单元测试
│   ├── api/                  # API 路由测试
│   ├── web/                  # 前端测试
│   └── e2e/                  # 端到端测试
├── docker-compose.yml
├── Dockerfile
├── build.sh                  # 构建脚本
├── deploy.sh                 # 部署脚本
└── .env.example              # 环境变量模板
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Apache Doris / MySQL (兼容 MySQL 协议的数据源)

### 安装依赖

```bash
# 后端
cd apps/api && pip install -r requirements.txt

# 前端
cd apps/web && npm install
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入数据库连接、API Key、OAuth 等配置
```

关键配置项：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DB_HOST` / `DB_PORT` | 源数据库（Doris）地址 | `localhost:9030` |
| `DB_AUDIT_HOST` | 审计目标库地址（默认同源库） | — |
| `VEHICLE_AI_SERVICE_URL` | 车辆 AI 比对服务地址 | `http://10.11.1.40:8081` |
| `API_KEY` | 接口鉴权密钥（留空跳过鉴权） | 空 |
| `AUTH_ENABLED` | 启用 OAuth/JWT 登录 | `false` |
| `CORS_ORIGINS` | 允许的前端来源（逗号分隔） | `http://localhost:3000` |

### 本地开发

```bash
# 后端（热重载）
cd apps/api && uvicorn main:app --reload --port 8000

# 前端（热重载，默认 5173 端口）
cd apps/web && npm run dev
```

后端 API 文档：http://localhost:8000/docs

### Docker 部署

```bash
# 构建并启动
docker-compose up -d --build

# 或使用部署脚本
bash deploy.sh
```

## 测试

```bash
# 后端全量测试（覆盖率 ≥ 60%）
pytest

# 后端单元测试
pytest tests/unit/

# 前端测试
cd apps/web && npm test
```

## 代码质量

```bash
# 后端 lint + format 检查
ruff check apps/api/ tests/
ruff format --check apps/api/ tests/

# 前端 lint
cd apps/web && npx eslint src/
```

## 数据迁移

```bash
# SQLite → Doris 迁移
cd apps/api && python -m database.migrate_sqlite_to_doris
```

## License

Internal use — 高速公路收费稽核专用系统
