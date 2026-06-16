# 客车 OBU 监测功能文档

> 对应 fraud_type: `PASSENGER_USES_TRUCK_OBU_NON_NEW_A`
> 对应 task_type: `passenger_obu_audit`

---

## 1. 功能概述

客车 OBU 监测用于识别**客车（vehicle_type=1）套用货车 OBU** 的异常通行行为。核心场景：车辆申报为客车，但实际安装了货车 OBU 设备，通过抓拍图片的视觉识别（ML）+ LLM 二次复核来判定是否为货车，从而发现"客车挂货车 OBU"的欺诈行为。

### 监测范围

- **申报车型** = 1（客车）
- **车牌前缀** ≠ `新A`（新疆阿克苏地区车辆排除，因该地区客车挂货车 OBU 为合法业务场景）
- **媒体类型** = 1（OBU 通行记录）

### 检测输出

- **fraud_type**: `PASSENGER_USES_TRUCK_OBU_NON_NEW_A`
- **risk_score**: 双侧命中 0.95，单侧命中 0.85
- **source_side**: `ENTRY` / `EXIT` / `BOTH`（入口、出口或双侧均命中）

---

## 2. 核心逻辑流程

### 2.1 整体流程

```
┌─────────────────────────────────────────────────────────────────┐
│  定时任务 (task_type=passenger_obu_audit)                        │
│  ↓                                                              │
│  1. 计算扫描窗口 [start_time, NOW]                               │
│     - 首次执行: [filter_rules.start_time, NOW]                   │
│     - 增量执行: [last_run_at - 5min, NOW]  (重叠容错防漏边界)     │
│  ↓                                                              │
│  2. SQL 预筛候选行程 (find_passenger_obu_candidates_doris)       │
│     - VEHICLETYPE = 1, MEDIATYPE = 1                            │
│     - VEHICLEID NOT LIKE '新A%'                                 │
│     - OCCURTIME ∈ [window_start, window_end]                    │
│  ↓                                                              │
│  3. 逐条调用 detect_trip (并行, max_workers=4)                   │
│     - 对入口/出口两侧分别做 _side_check                          │
│     - 调 vehicle-ai-service.truck_obu() 进行 ML+LLM 复合检测     │
│  ↓                                                              │
│  4. 命中结果写入 audit_results                                   │
│  ↓                                                              │
│  5. 按日累加统计写入 audit_truck_obu_daily_stats                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 单条行程检测流程 (`detect_trip`)

```
detect_trip(trip)
  ├── 对入口侧执行 _side_check(trip, "entry", ...)
  ├── 对出口侧执行 _side_check(trip, "exit", ...)
  ├── 若两侧均未命中 → 返回 None
  └── 至少一侧命中 → 组装命中结果
        ├── source_side: "ENTRY" / "EXIT" / "BOTH"
        ├── llm_verified: 两侧均通过时为 True
        ├── llm_confidence: 两侧置信度均值
        ├── risk_score: BOTH=0.95, 单侧=0.85
        └── llm_call_status: 取两侧最严重状态
```

### 2.3 单侧检测流程 (`_side_check`)

```
_side_check(trip, side, ...)
  │
  ├─ ① 申报车型检查: trip[vehicle_type] != 1 → 未命中, 返回 None
  ├─ ② 车牌前缀检查: vehicle_id 为空 或 以"新A"开头 → 未命中, 返回 None
  ├─ ③ 视觉类型预筛(优化): visual_type 已有值且不属于货车类型 → 未命中, 返回 None
  ├─ ④ 图片可用性检查: image_trans 为空 → 未命中, 返回 None
  ├─ ⑤ 调用 vehicle-ai-service.truck_obu(image_url, declared_vehicle_type=1)
  │     - 异常/超时/返回 error → 返回 None
  │     - is_suspicious=False → 未命中, 返回 None
  └─ ⑥ AI 返回 is_suspicious=True → 命中
        ├── llm_verified: resp.llm_verified (LLM 复核结果)
        ├── confidence: resp.confidence (ML 置信度)
        ├── visual_vehicle_type: resp.visual_vehicle_type (视觉识别车型)
        └── llm_call_status: confirmed / rejected
```

### 2.4 AI Service 调用链

`vehicle-ai-service` 的 `truck_obu` 端点为复合端点，内部执行：

1. **ML 视觉分类** — 判断图片中的车辆是否为货车
2. **LLM 二次复核** — 当 ML 判定为货车 (`is_truck=True`) 时，自动调用 LLM 验证

> **Fail-open 机制**: LLM 失败时（如 MaaS 抖动），AI service 返回 `is_suspicious=True` + `llm_verified=False`，主项目仍写入嫌疑行，便于审计追溯。

---

## 3. 关键数据结构

### 3.1 候选行程 (Trip)

由 `find_passenger_obu_candidates_doris` 从 Doris 原始表查询并组装，字段如下：

| 字段 | 类型 | 说明 |
|------|------|------|
| `passid` | str | 行程唯一标识 |
| `entry_time` / `exit_time` | str | 入/出口时间 |
| `entry_station_name` / `exit_station_name` | str | 入/出口站名 |
| `entry_vehicle_id` / `exit_vehicle_id` | str | 入/出口车牌号 |
| `entry_vehicle_type` / `exit_vehicle_type` | int | 入/出口申报车型 (1=客车) |
| `entry_vehicle_color` / `exit_vehicle_color` | int | 入/出口车辆颜色 |
| `entry_obu_id` / `exit_obu_id` | str | 入/出口 OBU ID |
| `entry_media_type` / `exit_media_type` | int | 入/出口媒体类型 |
| `entry_image_trans` / `exit_image_trans` | str | 入/出口车头图片 URL |
| `entry_image_license` / `exit_image_license` | str | 入/出口车牌图片 URL |
| `entry_visual_type` / `exit_visual_type` | str | 入/出口视觉识别车型 |

### 3.2 命中结果 (detect_trip 返回值)

| 字段 | 类型 | 说明 |
|------|------|------|
| `fraud_type` | str | 固定值 `PASSENGER_USES_TRUCK_OBU_NON_NEW_A` |
| `source_side` | str | 命中侧: `ENTRY` / `EXIT` / `BOTH` |
| `entry_vehicle_type` / `exit_vehicle_type` | int | 入/出口申报车型 |
| `entry_obu_id` / `exit_obu_id` | str | 入/出口 OBU ID |
| `entry_image_trans` / `exit_image_trans` | str | 入/出口图片 URL |
| `entry_visual_type` / `exit_visual_type` | str | 入/出口视觉识别车型 |
| `llm_verified` | bool | LLM 复核是否通过 (双侧均通过才为 True) |
| `llm_confidence` | float | LLM 置信度 (双侧均值) |
| `visual_vehicle_type` | str | 主侧视觉识别车型 |
| `risk_score` | float | 风险评分: BOTH=0.95, 单侧=0.85 |
| `llm_call_status` | str | LLM 调用状态 (取最严重) |

### 3.3 LLM 调用状态 (llm_call_status)

按严重度递增排列，聚合时取 max：

| 状态值 | 严重度 | 说明 |
|--------|--------|------|
| `called_confirmed` | 1 | LLM 已调用且确认是货车 |
| `not_called` | 2 | LLM 未被调用 |
| `called_rejected` | 3 | LLM 已调用但拒绝确认 |
| `service_error` | 4 | LLM 服务异常 |

### 3.4 每日统计表 (audit_truck_obu_daily_stats)

| 字段 | 类型 | 说明 |
|------|------|------|
| `date` | DATE | 统计日期 |
| `fraud_type` | VARCHAR(50) | 欺诈类型 |
| `scanned_count` | BIGINT | 当日扫描行程数 |
| `suspicious_count` | BIGINT | 当日命中可疑数 |
| `confirmed_count` | BIGINT | 当日已确认数 |
| `last_run_at` | DATETIME | 当日最后执行时间 |
| `updated_at` | DATETIME | 自动更新时间 |

联合主键: `(date, fraud_type)`

### 3.5 响应 Schema

#### PassengerObuOverviewResponse

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_scanned` | int | 累计扫描数 |
| `total_suspicious` | int | 累计异常数 |
| `total_pending` | int | 待处理数 |
| `total_confirmed` | int | 已确认数 |
| `last_run_at` | str \| None | 最近执行时间 |
| `last_30_days` | list[PassengerObuDailyStat] | 最近30天趋势 |

#### PassengerObuAnomalyItem

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | audit_results.id |
| `audit_trip_id` | int | 关联行程 ID |
| `fraud_type` | str | 欺诈类型 |
| `passid` | str \| None | 行程标识 |
| `entry_time` / `exit_time` | str \| None | 入/出口时间 |
| `entry_station_name` / `exit_station_name` | str \| None | 入/出口站名 |
| `entry_vehicle_id` / `exit_vehicle_id` | str \| None | 入/出口车牌 |
| `entry_vehicle_type` / `exit_vehicle_type` | int \| None | 入/出口申报车型 |
| `entry_obu_id` / `exit_obu_id` | str \| None | 入/出口 OBU ID |
| `entry_media_type` / `exit_media_type` | int \| None | 入/出口媒体类型 |
| `risk_score` | float | 风险评分 |
| `process_status` | str | 处理状态 |
| `source_side` | str \| None | 命中侧 |
| `visual_vehicle_type` | str \| None | 视觉识别车型 |
| `llm_verified` | bool \| None | LLM 复核结果 |
| `llm_confidence` | float \| None | LLM 置信度 |
| `llm_call_status` | str \| None | LLM 调用状态 |
| `entry_image_trans` / `exit_image_trans` | str \| None | 入/出口图片 URL |

---

## 4. 检测规则

### 4.1 SQL 预筛规则 (候选行程筛选)

在 `find_passenger_obu_candidates_doris` 中执行，直接查 Doris 原始表 `dwd_tolldata.t_waste_en_ex_gantry`：

```sql
-- Step 1: 找候选 PASSID
SELECT t.PASSID
FROM dwd_tolldata.t_waste_en_ex_gantry t
WHERE t.VEHICLETYPE = 1              -- 申报为客车
  AND t.MEDIATYPE = 1                -- OBU 通行记录
  AND t.VEHICLEID IS NOT NULL        -- 车牌号不为空
  AND t.VEHICLEID NOT LIKE '新A%'    -- 排除新A前缀
  AND t.LANETYPE IN ('入口', '出口')  -- 仅出入口记录
  AND t.OCCURTIME >= {start_time}
  AND t.OCCURTIME < {end_time}
GROUP BY t.PASSID
ORDER BY MAX(t.OCCURTIME) ASC
LIMIT {limit} OFFSET {offset}

-- Step 2: 取候选行程的入口/出口详情 + JOIN 站点字典构造图片 URL
```

### 4.2 单侧命中规则 (`_side_check`)

所有条件**必须同时满足**（短路求值，按顺序检查）：

| 序号 | 规则 | 说明 |
|------|------|------|
| ① | `vehicle_type == 1` | 申报车型为客车 |
| ② | `vehicle_id` 非空 且 不以 `新A` 开头 | 排除新A前缀车辆 |
| ③ | `visual_type` 为空 或 属于货车类型集合 | 已有视觉类型且非货车则跳过（优化） |
| ④ | `image_trans` 非空 | 有可用的车头图片 |
| ⑤ | `vehicle-ai-service.truck_obu()` 返回 `is_suspicious=True` | AI 判定为可疑 |

### 4.3 货车视觉类型集合

```python
TRUCK_VISUAL_TYPES = frozenset({"14", "15", "16", "truck"})
```

- `14` / `15` / `16` 对应 Doris 车车类型编码
- `truck` 为通用货车标识

### 4.4 风险评分规则

| 场景 | risk_score |
|------|------------|
| 入口或出口单侧命中 | 0.85 |
| 入口和出口双侧均命中 | 0.95 |

### 4.5 LLM 聚合规则

- **llm_verified**: 双侧均 `True` 时为 `True`（`all()` 语义）
- **llm_confidence**: 双侧置信度均值
- **llm_call_status**: 取双侧中严重度最高者（`max` by `_LLM_STATUS_SEVERITY`）

### 4.6 扫描窗口规则

| 执行场景 | 窗口起始 | 窗口结束 |
|----------|----------|----------|
| 首次执行 (last_run_at 为空) | `filter_rules.start_time` (默认 `2026-06-01 00:00:00`) | 当前北京时间 |
| 增量执行 | `last_run_at - 5min` (重叠容错) | 当前北京时间 |

### 4.7 任务参数默认值

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `start_time` | `2026-06-01 00:00:00` | 首次扫描起始时间 |
| `declared_vehicle_type` | 1 | 申报车型（客车） |
| `plate_prefix_exclude` | `新A` | 排除的车牌前缀 |
| `limit` | 2000 | 单次任务最大扫描行程数 |
| `page_size` | 500 | 分页大小 |
| `max_workers` | 4 | 并行调 AI service 线程数 |

---

## 5. API 接口

### 5.1 单条检测

```
POST /audit/detect/passenger-obu
```

**请求体**:
```json
{ "passid": "xxx" }
```

**响应**:
```json
// 未命中
{ "is_suspicious": false, "fraud_type": "PASSENGER_USES_TRUCK_OBU_NON_NEW_A", "details": null }

// 命中
{ "is_suspicious": true, "fraud_type": "PASSENGER_USES_TRUCK_OBU_NON_NEW_A", "details": { ... } }
```

**逻辑**: 查询行程详情 → 调用 `detect_trip` → 命中则写入 `audit_results`

### 5.2 概览统计

```
GET /audit/passenger-obu/overview
```

**响应**: `PassengerObuOverviewResponse`

```json
{
  "total_scanned": 12000,
  "total_suspicious": 156,
  "total_pending": 42,
  "total_confirmed": 30,
  "last_run_at": "2026-06-15T10:30:00",
  "last_30_days": [
    { "date": "2026-06-15", "fraud_type": "...", "scanned_count": 500, "suspicious_count": 8, "confirmed_count": 2, "last_run_at": "..." }
  ]
}
```

### 5.3 每日统计

```
GET /audit/passenger-obu/stats/daily
```

**查询参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `from_date` | str | 起始日期 (YYYY-MM-DD) |
| `to_date` | str | 结束日期 (YYYY-MM-DD) |
| `fraud_type` | str | 默认 `PASSENGER_USES_TRUCK_OBU_NON_NEW_A` |

**响应**: `PassengerObuDailyStatListResponse`

```json
{
  "stats": [
    { "date": "2026-06-15", "fraud_type": "...", "scanned_count": 500, "suspicious_count": 8, "confirmed_count": 2, "last_run_at": "..." }
  ],
  "total": 30
}
```

### 5.4 异常记录列表

```
GET /audit/passenger-obu/anomalies
```

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `process_status` | str \| None | - | 处理状态过滤 |
| `llm_result` | str \| None | - | LLM 结果过滤 (same/different/pending) |
| `sort_by` | str | `exit_time` | 排序字段 (exit_time/created_at/risk_score) |
| `limit` | int | 50 | 每页条数 |
| `offset` | int | 0 | 偏移量 |

**响应**: `PassengerObuAnomalyListResponse`

```json
{
  "anomalies": [ { ... PassengerObuAnomalyItem ... } ],
  "total": 156,
  "limit": 50,
  "offset": 0
}
```

---

## 附录：关键代码文件

| 文件 | 职责 |
|------|------|
| `apps/api/services/passenger_obu_detector.py` | 核心检测逻辑: `detect_trip` / `_side_check` |
| `apps/api/services/task_executor.py` | 批量任务执行: `_execute_passenger_obu_audit` |
| `apps/api/services/doris_trip_query.py` | Doris 候选行程查询: `find_passenger_obu_candidates_doris` |
| `apps/api/database/repositories/truck_obu_stats_repository.py` | 每日统计 CRUD: `TruckObuStatsRepository` |
| `apps/api/database/repositories/trip_repository.py` | 候选行程查询入口: `find_passenger_obu_candidates` |
| `apps/api/core/vehicle_ai_client.py` | AI Service 客户端: `VehicleAIClient.truck_obu` |
| `apps/api/routers/audit.py` | API 路由: passenger-obu 相关端点 |
| `apps/api/database/migrations/007_truck_obu_audit.sql` | SQLite 建表迁移 |
| `apps/api/database/doris_ddl.sql` | Doris 建表 DDL |
| `packages/contracts/types/schemas.py` | 响应 Schema 定义 |
