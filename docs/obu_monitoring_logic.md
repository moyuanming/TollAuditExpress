# 客车 OBU 监测功能文档

> 欺诈类型标识：`PASSENGER_USES_TRUCK_OBU_NON_NEW_A`
> 版本：v1 | 最后更新：2026-06-16

---

## 1. 概述

### 1.1 业务背景

在高速公路收费场景中，部分客车（申报车型为 1）套用货车 OBU 介质通行，利用货车费率低于客车的差价进行逃费。本功能旨在自动检测此类异常通行行为，核心逻辑为：

**客车申报 + 非新A车牌 + OBU介质 + 图片视觉识别为货车 + LLM复核 → 命中逃费嫌疑**

### 1.2 功能定位

- **检测对象**：通行记录中申报车型为客车（`vehicle_type=1`）、使用 OBU 介质（`media_type=1`）、且车牌非"新A"开头的车辆
- **检测手段**：SQL 元数据预筛 → AI 视觉模型识别 → LLM 二次复核
- **欺诈类型**：`PASSENGER_USES_TRUCK_OBU_NON_NEW_A`（客车套用货车OBU-非新A）
- **独立任务**：由定时任务 `task_type='passenger_obu_audit'` 独立调度，不混入通用检测流程

### 1.3 系统架构

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│  Doris 原始表 │────▶│  SQL 预筛候选    │────▶│  passenger_obu_      │
│ t_waste_en_  │     │  (find_passenger_ │     │  detector.detect_   │
│ ex_gantry    │     │  obu_candidates)  │     │  trip()             │
└──────────────┘     └──────────────────┘     └──────┬───────────────┘
                                                       │
                                              ┌────────▼────────┐
                                              │ vehicle-ai-     │
                                              │ service.truck_  │
                                              │ obu()           │
                                              │ (ML视觉+LLM复核)│
                                              └────────┬────────┘
                                                       │
                              ┌─────────────────────────▼──────────────────────┐
                              │              命中结果写入                      │
                              │  audit_trips + audit_results + daily_stats    │
                              └───────────────────────────────────────────────┘
```

---

## 2. 业务流程

### 2.1 整体流程

```
定时调度触发 / 手动执行
        │
        ▼
┌─────────────────────────┐
│ 1. 确定扫描时间窗口      │
│    - 首次: [start_time, NOW]
│    - 增量: [last_run_at-5min, NOW] │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│ 2. SQL 预筛候选行程      │
│    (Doris 原始表分页查询) │
│    按 page_size=500 分页 │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│ 3. 并行检测 (ThreadPool) │
│    max_workers=4        │
│    对每条候选 trip:      │
│    → detect_trip()      │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│ 4. 命中结果落库          │
│    - save_trip (upsert)  │
│    - save_result         │
│    - upsert_daily_stat   │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│ 5. 每页 flush 统计       │
│    (防超时丢整批数据)     │
└─────────────────────────┘
```

### 2.2 单条行程检测流程（detect_trip）

对每条候选行程，分别检查入口侧和出口侧：

```
对每侧 (entry / exit):
  │
  ├─ ① 申报车型检查: vehicle_type == 1 (客车)?
  │     └─ 否 → 跳过该侧
  │
  ├─ ② 车牌前缀检查: vehicle_id 不以 "新A" 开头?
  │     └─ 是"新A"开头 → 跳过该侧 (新A为合法区域)
  │
  ├─ ③ 视觉类型预筛: visual_type 已有值且非货车类型?
  │     └─ 是 → 跳过该侧 (免一次模型调用)
  │
  ├─ ④ 图片可用性: image_trans 非空?
  │     └─ 无图 → 跳过该侧
  │
  ├─ ⑤ 调用 AI 服务: vehicle-ai-service.truck_obu(image_url)
  │     ├─ 异常/超时 → 返回 None (该侧未命中)
  │     └─ 返回 is_suspicious=False → 该侧未命中
  │
  └─ ⑥ AI 返回 is_suspicious=True → 该侧命中
        记录: side, llm_verified, confidence, visual_vehicle_type,
              llm_call_status

两侧检测完成后:
  ├─ 无侧命中 → 返回 None (未命中)
  ├─ 单侧命中 → source_side = "ENTRY" 或 "EXIT"
  └─ 双侧命中 → source_side = "BOTH"
```

### 2.3 AI 服务调用链

`vehicle-ai-service` 的 `truck_obu` 端点为复合端点，内部执行：

```
truck_obu(image_url, declared_vehicle_type=1)
  │
  ├─ Step 1: ML 视觉分类
  │     输入: 车辆图片 URL
  │     输出: is_truck (bool), confidence (float), visual_vehicle_type (str)
  │
  └─ Step 2: LLM 二次复核 (仅当 is_truck=True 时调用)
        输入: 图片 + ML 结果
        输出: is_suspicious (bool), llm_verified (bool), confidence (float)
        ├─ LLM 确认是货车 → is_suspicious=True, llm_verified=True
        ├─ LLM 否定 → is_suspicious=False, llm_verified=False
        └─ LLM 服务异常 (fail-open) → is_suspicious=True, llm_verified=False
```

> **Fail-Open 策略**：当 LLM 服务不可达或超时时，AI 服务返回 `is_suspicious=True` + `llm_verified=False`，确保不漏过可疑记录，同时标记 `llm_verified=False` 供后续审计追溯。

---

## 3. 核心规则

### 3.1 候选筛选规则（SQL 预筛）

从 Doris 原始表 `dwd_tolldata.t_waste_en_ex_gantry` 筛选，条件如下：

| 条件 | 字段 | 值 | 说明 |
|------|------|-----|------|
| 申报车型 | `VEHICLETYPE` | `= 1` | 客车 |
| 介质类型 | `MEDIATYPE` | `= 1` | OBU 介质 |
| 车牌非空 | `VEHICLEID` | `IS NOT NULL` | — |
| 非新A车牌 | `VEHICLEID` | `NOT LIKE '新A%'` | 新A为合法区域 |
| 通行类型 | `LANETYPE` | `IN ('入口', '出口')` | 仅出入口记录 |
| 时间窗口 | `OCCURTIME` | `>= start_time AND < end_time` | 增量扫描 |

### 3.2 侧级命中规则

对入口侧或出口侧，**全部**以下条件同时满足才命中：

1. **申报为客车**：`vehicle_type == 1`（`DECLARED_VEHICLE_TYPE`）
2. **非新A车牌**：`vehicle_id` 不以 `"新A"` 开头（`NON_NEW_A_PREFIX`）
3. **视觉预筛通过**：`visual_type` 为空或属于货车类型集合 `{"14", "15", "16", "truck"}`
4. **图片可用**：`image_trans` 非空
5. **AI 服务命中**：`vehicle-ai-service.truck_obu()` 返回 `is_suspicious=True`

### 3.3 风险评分规则

| 场景 | 风险评分 | 说明 |
|------|---------|------|
| 双侧命中（BOTH） | `0.95` | 入口和出口均识别为货车，高度可疑 |
| 单侧命中（ENTRY/EXIT） | `0.85` | 仅一侧识别为货车 |

### 3.4 LLM 调用状态

| 状态值 | 严重度排序 | 含义 |
|--------|-----------|------|
| `called_confirmed` | 1（最轻） | LLM 已调用且确认是货车 |
| `not_called` | 2 | LLM 未调用（ML 高自信直接判定） |
| `called_rejected` | 3 | LLM 已调用但判定不是货车 |
| `service_error` | 4（最重） | AI 服务不可达或超时 |

多条侧命中时取**最严重**的状态（`_worst_llm_call_status`）。

### 3.5 视觉车型类型集合

```python
TRUCK_VISUAL_TYPES = frozenset({"14", "15", "16", "truck"})
```

- `"14"` / `"15"` / `"16"`：Doris 源表中的货车类型编码
- `"truck"`：AI 服务返回的通用货车标识

---

## 4. 数据模型

### 4.1 核心数据表

#### audit_trips（行程聚合快照）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 自增主键 |
| `passid` | VARCHAR(120) | 业务唯一键（通行ID） |
| `entry_vehicle_type` | TINYINT | 入口申报车型（1=客车） |
| `exit_vehicle_type` | TINYINT | 出口申报车型 |
| `entry_vehicle_id` | VARCHAR(60) | 入口车牌号 |
| `exit_vehicle_id` | VARCHAR(60) | 出口车牌号 |
| `entry_obu_id` | VARCHAR(48) | 入口 OBU ID |
| `exit_obu_id` | VARCHAR(48) | 出口 OBU ID |
| `entry_media_type` | TINYINT | 入口介质类型（1=OBU） |
| `exit_media_type` | TINYINT | 出口介质类型 |
| `entry_image_trans` | VARCHAR(500) | 入口车辆特写图 URL |
| `exit_image_trans` | VARCHAR(500) | 出口车辆特写图 URL |
| `entry_visual_type` | VARCHAR(20) | 入口视觉识别车型 |
| `exit_visual_type` | VARCHAR(20) | 出口视觉识别车型 |
| `audit_status` | VARCHAR(20) | 稽核状态 |
| `risk_score` | DOUBLE | 风险评分 |

#### audit_results（稽核结果）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 自增主键 |
| `audit_trip_id` | BIGINT | 关联 audit_trips.id |
| `fraud_type` | VARCHAR(50) | 欺诈类型（`PASSENGER_USES_TRUCK_OBU_NON_NEW_A`） |
| `is_suspicious` | TINYINT | 是否可疑（1=是） |
| `risk_score` | DOUBLE | 风险评分（0.85 或 0.95） |
| `details` | JSON | 命中详情（见下文） |
| `process_status` | VARCHAR(20) | 处理状态（UNPROCESSED/CONFIRMED/REJECTED） |

**details JSON 结构**：

```json
{
  "source_side": "ENTRY|EXIT|BOTH",
  "entry_obu_id": "OBU编号",
  "exit_obu_id": "OBU编号",
  "entry_media_type": 1,
  "exit_media_type": 1,
  "entry_visual_type": "14",
  "exit_visual_type": null,
  "visual_vehicle_type": "truck",
  "llm_verified": true,
  "llm_confidence": 0.92,
  "rule_version": "v1"
}
```

#### audit_truck_obu_daily_stats（每日统计）

| 字段 | 类型 | 说明 |
|------|------|------|
| `date` | DATE | 统计日期 |
| `fraud_type` | VARCHAR(50) | 欺诈类型 |
| `scanned_count` | BIGINT | 当日扫描行程数 |
| `suspicious_count` | BIGINT | 当日异常命中数 |
| `confirmed_count` | BIGINT | 当日已确认数 |
| `last_run_at` | DATETIME | 最后执行时间 |

联合主键：`(date, fraud_type)`

### 4.2 Pydantic 响应模型

#### PassengerObuOverviewResponse

```python
total_scanned: int       # 累计扫描数
total_suspicious: int    # 累计异常数
total_pending: int       # 待处理数
total_confirmed: int     # 已确认数
last_run_at: str         # 最近执行时间
last_30_days: List[PassengerObuDailyStat]  # 最近30天趋势
```

#### PassengerObuAnomalyItem

```python
id: int
audit_trip_id: int
fraud_type: str
passid: str
entry_time / exit_time: str
entry_station_name / exit_station_name: str
entry_vehicle_id / exit_vehicle_id: str
entry_vehicle_type / exit_vehicle_type: int
entry_obu_id / exit_obu_id: str
entry_media_type / exit_media_type: int
risk_score: float           # 默认 0.85
process_status: str         # UNPROCESSED / CONFIRMED / REJECTED
source_side: str            # ENTRY / EXIT / BOTH
visual_vehicle_type: str    # truck / car
llm_verified: bool          # LLM 是否确认
llm_confidence: float       # LLM 置信度
llm_call_status: str        # called_confirmed / called_rejected / not_called / service_error
entry_image_trans / exit_image_trans: str
```

---

## 5. 任务调度

### 5.1 任务配置

- **任务类型**：`passenger_obu_audit`
- **调度方式**：通过 `scheduled_tasks` 表配置，由 `task_scheduler` daemon 线程定期检查
- **调度周期**：默认 60 分钟（可通过 `schedule_config.minutes` 配置）
- **最大执行时长**：默认 60 分钟（环境变量 `MAX_EXECUTION_MINUTES`，全量回填建议设 360）

### 5.2 扫描窗口策略

| 场景 | 窗口起始 | 窗口结束 | 说明 |
|------|---------|---------|------|
| 首次执行 | `filter_rules.start_time`（默认 `2026-06-01 00:00:00`） | `NOW` | 全量扫描 |
| 增量执行 | `last_run_at - 5min` | `NOW` | 5分钟重叠容错防漏边界 |

### 5.3 并发控制

- **分页大小**：`page_size=500`（每页候选行程数）
- **并行线程**：`max_workers=4`（ThreadPoolExecutor）
- **总扫描上限**：`limit=2000`（单次任务最多扫描行程数）

### 5.4 执行流程细节

```
1. 确定扫描窗口 [start_dt, end_dt]
2. offset = 0
3. while scanned < limit:
     rows = find_passenger_obu_candidates(start, end, page_size, offset)
     if not rows: break
     scanned += len(rows)
     
     # 并行检测
     with ThreadPoolExecutor(max_workers=4) as ex:
       for trip, details in ex.map(_detect_one, rows):
         # 按 entry_time 落桶到日期
         if details is not None:
           trip_id = save_trip(trip)      # upsert
           rid = save_result(...)          # 写入 audit_results
           new_anomaly_ids.append(rid)
     
     # 每页 flush 统计（防超时丢整批）
     _flush_daily_stats()
     
     if len(rows) < page_size: break
     offset += page_size
4. 返回 {scanned, suspicious, anomaly_count, anomaly_ids_sample}
```

### 5.5 日志与进度

- 执行线程安装 `_CaptureHandler` 捕获日志到线程局部缓冲
- 每 5 秒由 flusher 线程将缓冲刷入 `task_executions` 表
- 前端可通过任务执行 API 实时查看进度

---

## 6. 异常处理

### 6.1 AI 服务异常

| 异常场景 | 处理方式 | 影响 |
|---------|---------|------|
| `vehicle-ai-service` 不可达 | `_side_check` 捕获异常，返回 None | 该侧未命中，不影响其他侧 |
| AI 服务返回 `error` 字段 | 记录错误日志，返回 None | 同上 |
| AI 服务超时 | httpx 超时（默认 65s），捕获 HTTPError | 同上 |
| LLM 服务异常（AI 服务内部） | AI 服务 fail-open：返回 `is_suspicious=True, llm_verified=False` | 仍写入嫌疑行，标记 `llm_verified=False` |

### 6.2 数据异常

| 异常场景 | 处理方式 |
|---------|---------|
| 候选行程缺少 `entry_time` | 按 `exit_time` 落桶日期；都缺则归到 `end_dt` |
| `save_trip` 失败 | 记录 warning 日志，跳过该条 |
| `save_result` 失败 | 记录 warning 日志，跳过该条 |
| `detect_trip` 内部异常 | `_detect_one` 捕获，返回 `(trip, None)` |

### 6.3 调度异常

| 异常场景 | 处理方式 |
|---------|---------|
| 任务超时（> MAX_EXECUTION_MINUTES） | `_cleanup_stuck_executions` 标记为 failed |
| 已有运行中执行（30分钟内） | 跳过本次调度 |
| 每页 flush 失败 | 不影响主流程，统计可能丢失当前页 |

### 6.4 数据库兼容性

- Doris 2.1.9-rc02 不支持 `ON DUPLICATE KEY UPDATE` / `ON CONFLICT` / `REPLACE INTO`
- `TruckObuStatsRepository.upsert_daily_stat` 采用 `SELECT + INSERT/UPDATE` 两步走
- SQLite 与 Doris 均可运行

---

## 7. API 接口

### 7.1 概览统计

```
GET /api/audit/passenger-obu/overview
```

**响应**：`PassengerObuOverviewResponse`

- 累计扫描 / 异常 / 待处理 / 已确认
- 最近 30 天趋势数据

### 7.2 每日统计

```
GET /api/audit/passenger-obu/stats/daily
    ?from_date=2026-06-01
    &to_date=2026-06-16
    &fraud_type=PASSENGER_USES_TRUCK_OBU_NON_NEW_A
```

**响应**：`PassengerObuDailyStatListResponse`

### 7.3 异常记录列表

```
GET /api/audit/passenger-obu/anomalies
    ?process_status=UNPROCESSED
    &llm_result=pending
    &sort_by=exit_time
    &limit=50
    &offset=0
```

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `process_status` | str | 处理状态过滤：UNPROCESSED / CONFIRMED / REJECTED |
| `llm_result` | str | LLM 结果过滤：same / different / pending |
| `sort_by` | str | 排序字段：exit_time / created_at / risk_score |
| `limit` | int | 每页条数 |
| `offset` | int | 偏移量 |

**响应**：`PassengerObuAnomalyListResponse`

### 7.4 单条检测（手动触发）

```
POST /api/audit/detect/passenger-obu
Body: { "passid": "xxx" }
```

对指定行程执行 OBU 检测，命中则写入 `audit_results`。

### 7.5 可疑记录处理

```
POST /api/audit/suspect/{suspect_id}/process
Body: { "action": "CONFIRMED|REJECTED", "operator": "admin", "comments": "..." }
```

### 7.6 LLM 手动复核

```
POST /api/audit/suspect/{suspect_id}/llm-verify
```

对单条可疑记录手动触发 MaaS 双图比对。

---

## 8. 前端交互

### 8.1 页面路由

- **路径**：`/app/passenger-obu-monitor`
- **组件**：`PassengerOBUMonitor`
- **旧路径兼容**：`/truck-obu-monitor` 重定向到新路径

### 8.2 页面结构

```
┌─────────────────────────────────────────────────────┐
│ 页面标题: 客车 OBU 监测                              │
│ 副标题: 非新A 客车使用 OBU 介质,入口或出口图片识别    │
│         为货车且 LLM 复核通过                         │
├─────────────────────────────────────────────────────┤
│ 统计条: [当前显示数] [待处理数]                       │
├─────────────────────────────────────────────────────┤
│ 过滤器: [处理状态▼] [LLM结果▼] [刷新]               │
├──────────────────────────┬──────────────────────────┤
│ 异常记录表格              │ 详情面板 (选中时展开)     │
│ ┌──────────────────────┐ │ ┌──────────────────────┐ │
│ │ID|PASSID|入口车辆|... │ │ │异常详情 #id          │ │
│ │  |      |入口车型|... │ │ │┌────────────────────┐│ │
│ │  |      |入口站  |... │ │ ││VehicleTripDetail   ││ │
│ │  |      |入口时间|... │ │ ││(图片/门架/操作)     ││ │
│ │  |      |出口...  |... │ │ │└────────────────────┘│ │
│ │  |      |命中侧  |... │ │ │稽核判定:             │ │
│ │  |      |视觉车型|... │ │ │ [操作员] [备注]      │ │
│ │  |      |风险评分|... │ │ │ [排除(误报)] [确认逃费]│ │
│ │  |      |LLM    |... │ │ └──────────────────────┘ │
│ │  |      |状态    |... │ │                          │
│ └──────────────────────┘ │                          │
└──────────────────────────┴──────────────────────────┘
```

### 8.3 表格列定义

| 列 | 字段 | 说明 |
|----|------|------|
| ID | `id` | 稽核结果 ID |
| PASSID | `passid` | 通行 ID |
| 入口车辆 | `entry_vehicle_id` | 入口车牌号 |
| 入口车型 | `entry_vehicle_type` | 1→客车, 2→货车, 14/15/16→货车 |
| 入口站 | `entry_station_name` | 入口站名 |
| 入口时间 | `entry_time` | 格式化时间 |
| 出口车辆 | `exit_vehicle_id` | 出口车牌号 |
| 出口车型 | `exit_vehicle_type` | 同入口车型 |
| 出口站 | `exit_station_name` | 出口站名 |
| 出口时间 | `exit_time` | 格式化时间 |
| 命中侧 | `source_side` | ENTRY(蓝)/EXIT(黄)/BOTH(红) |
| 视觉车型 | `visual_vehicle_type` | truck→红色标签, car→绿色标签 |
| 风险评分 | `risk_score` | >0.7 红色, 否则黄色 |
| LLM | `llm_call_status` | 通过(绿)/未通过(黄)/未调LLM(灰)/服务异常(红) |
| 状态 | `process_status` | 待处理(黄)/已确认(红)/已排除(绿) |

### 8.4 LLM 状态展示逻辑

| `llm_call_status` | 显示 | 样式 | Tooltip |
|-------------------|------|------|---------|
| `called_confirmed` | 通过 | 绿色 badge | LLM 调用: 已通过 (xx%) |
| `called_rejected` | 未通过 | 黄色 badge | LLM 调用: 判定不是货车 (xx%) |
| `not_called` | 未调LLM | 灰色 badge | LLM 未调用(ML 视觉已高自信) |
| `service_error` | 服务异常 | 红色 badge | vehicle-ai-service 不可达或超时 |
| (旧数据) `llm_verified=true` | 通过 | 绿色 badge | 置信度 xx% (老数据) |
| (旧数据) `llm_verified=false` | 未通过 | 黄色 badge | 未通过 (老数据) |
| 其他 | — | 蓝色 badge | LLM 状态未知 |

### 8.5 稽核判定操作

选中异常记录后，在详情面板可执行：

- **排除（误报）**：`action=REJECTED`，标记为已排除
- **确认逃费**：`action=CONFIRMED`，标记为已确认

操作需填写操作员姓名，备注可选。操作后自动刷新列表。

### 8.6 前端 API 调用

| 方法 | API 函数 | 后端接口 |
|------|---------|---------|
| 概览 | `auditApi.getPassengerObuOverview()` | `GET /passenger-obu/overview` |
| 每日统计 | `auditApi.getPassengerObuDailyStats(params)` | `GET /passenger-obu/stats/daily` |
| 异常列表 | `auditApi.getPassengerObuAnomalies(params)` | `GET /passenger-obu/anomalies` |
| 异常详情 | `auditApi.getSuspect(id)` | `GET /suspect/{id}` |
| 处理操作 | `auditApi.processSuspect(id, data)` | `POST /suspect/{id}/process` |
| 单条检测 | `auditApi.detectPassengerOBU(passid)` | `POST /detect/passenger-obu` |

---

## 9. 关键代码文件索引

| 文件 | 职责 |
|------|------|
| `apps/api/services/passenger_obu_detector.py` | 核心检测逻辑：`detect_trip()`、`_side_check()` |
| `apps/api/services/task_executor.py` | 任务执行入口：`_execute_passenger_obu_audit()` |
| `apps/api/services/task_scheduler.py` | 定时调度器：daemon 线程 + 超时清理 |
| `apps/api/services/doris_trip_query.py` | Doris 候选筛选：`find_passenger_obu_candidates_doris()` |
| `apps/api/core/vehicle_ai_client.py` | AI 服务客户端：`truck_obu()` |
| `apps/api/routers/audit.py` | API 路由：overview / daily-stats / anomalies |
| `apps/api/database/repositories/truck_obu_stats_repository.py` | 每日统计 CRUD |
| `apps/api/database/repositories/audit_repository.py` | 稽核结果 CRUD |
| `apps/api/database/repositories/trip_repository.py` | 行程数据 CRUD + 候选筛选委托 |
| `apps/api/database/migrations/007_truck_obu_audit.sql` | 每日统计表 DDL (SQLite) |
| `apps/api/database/doris_ddl.sql` | Doris 完整 DDL（含 audit_truck_obu_daily_stats） |
| `packages/contracts/types/schemas.py` | Pydantic 响应模型定义 |
| `apps/web/src/pages/PassengerOBUMonitor.jsx` | 前端监测页面 |
| `apps/web/src/api/audit.js` | 前端 API 客户端 |
| `apps/web/src/components/charts/DailyScanBar.jsx` | 每日扫描/异常柱状图 |

---

## 10. 配置参数

| 参数 | 环境变量 | 默认值 | 说明 |
|------|---------|--------|------|
| AI 服务地址 | `VEHICLE_AI_SERVICE_URL` | `http://10.11.1.40:8081` | vehicle-ai-service 基础 URL |
| AI 服务超时 | `VEHICLE_AI_SERVICE_TIMEOUT` | `65` | HTTP 请求超时（秒） |
| 最大执行时长 | `MAX_EXECUTION_MINUTES` | `60` | 单次任务最长执行分钟数 |
| 置信度阈值 | `TRUCK_OBU_CONFIDENCE_THRESHOLD` | `0.8` | 货车 OBU 置信度阈值 |
| 任务默认参数 | — | — | 见下 |

### 任务默认参数（`_normalize_passenger_obu_rules`）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `start_time` | `2026-06-01 00:00:00` | 首次扫描起始时间 |
| `declared_vehicle_type` | `1` | 申报车型（客车） |
| `plate_prefix_exclude` | `新A` | 排除的车牌前缀 |
| `limit` | `2000` | 单次最大扫描行程数 |
| `page_size` | `500` | 分页大小 |
| `max_workers` | `4` | 并行检测线程数 |

---

## 11. 与其他检测的关系

客车 OBU 监测是**独立检测通道**，与以下检测互不干扰：

| 检测类型 | 任务类型 | 说明 |
|---------|---------|------|
| 出入口比对 | `detect_only` / `re_detect` | 车牌/颜色/视觉特征不一致 |
| 聚合+检测 | `aggregate_detect` | 先聚合行程再跑通用检测 |
| 多维检测 | `multi_detect` | RuleEngine + Detector 联合 |
| LLM 批量复核 | `llm_verify` | 对已有可疑记录跑 LLM |
| **客车 OBU 监测** | **`passenger_obu_audit`** | **本功能，独立调度** |

> 注意：`detect_only` 和 `re_detect` 的代码注释明确标注"客车 OBU 套用检测由 passenger_obu_audit 任务独立负责"。

---

## 12. 数据流全景

```
Doris 原始表                    应用层                        持久化
─────────────                ──────────                    ──────────

t_waste_en_ex_gantry ──▶ find_passenger_obu_candidates_doris()
  (VEHICLETYPE=1            │
   MEDIATYPE=1               │ SQL 预筛
   VEHICLEID NOT LIKE '新A%')│
                             ▼
                        detect_trip()
                             │
                  ┌──────────┼──────────┐
                  ▼          ▼          ▼
            _side_check  _side_check   (无命中)
            (entry)      (exit)
                  │          │
                  ▼          ▼
         vehicle-ai-service.truck_obu()
         (ML 视觉分类 + LLM 复核)
                  │
                  ▼
            命中结果聚合
            (source_side / risk_score / llm_call_status)
                  │
                  ▼
         ┌────────┴────────┐
         ▼                 ▼
    save_trip()       save_result()
    (audit_trips)     (audit_results)
                            │
                            ▼
                    upsert_daily_stat()
                    (audit_truck_obu_daily_stats)
                            │
                            ▼
                    前端 PassengerOBUMonitor
                    (overview + anomalies + daily chart)
```
