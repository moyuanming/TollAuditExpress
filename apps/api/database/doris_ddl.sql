-- TollAuditExpress 审计目标库 DDL (Doris ods_AI_DB)
-- 取代 SQLite migrations/001-006.sql + connection.py 里的 CREATE TABLE
-- 表名约束: ^[a-zA-Z][a-zA-Z0-9-_]*$ (Doris 强制, 不能以数字/下划线开头, 不能含 .)
-- 业务键设计:
--   audit_trips: UNIQUE KEY(passid) — passid 是业务唯一键, save_trip() 做 upsert
--   其他表:     UNIQUE KEY(id) — id 仍是自增主键, 与 SQLite 行为对齐
-- 与 SQLite 差异:
--   - INTEGER PK → BIGINT AUTO_INCREMENT
--   - TEXT → VARCHAR(N) (按源表 Doris 字段宽度)
--   - REAL → DOUBLE
--   - TEXT (JSON) → JSON
--   - TEXT (时间) → DATETIME
--   - 删除 aggregation_logs(死表)
--   - 删除 schema_version → 用 migration_log 替代
--   - 删除所有 FOREIGN KEY(Doris 不支持, 由应用保证一致性)
--   - 删除所有外键索引(无 FK 就不需要)

-- 行程聚合快照(主表)
-- Doris UNIQUE KEY 必须把 key 列放在表首列,所以 passid 排第一,id 作为保留的 SQLite 自增兼容列(供 audit_results.audit_trip_id 等 FK 引用)
CREATE TABLE IF NOT EXISTS audit_trips (
    passid VARCHAR(120) NOT NULL,
    id BIGINT NOT NULL AUTO_INCREMENT,
    entry_time DATETIME,
    entry_station_name VARCHAR(450),
    entry_lane_id VARCHAR(12),
    entry_vehicle_id VARCHAR(60),
    entry_vehicle_type TINYINT,
    entry_vehicle_color TINYINT,
    entry_obu_id VARCHAR(48),
    entry_media_type TINYINT,
    entry_image_license VARCHAR(500),
    entry_image_trans VARCHAR(500),
    exit_time DATETIME,
    exit_station_name VARCHAR(450),
    exit_lane_id VARCHAR(12),
    exit_vehicle_id VARCHAR(60),
    exit_vehicle_type TINYINT,
    exit_vehicle_color TINYINT,
    exit_obu_id VARCHAR(48),
    exit_media_type TINYINT,
    exit_image_license VARCHAR(500),
    exit_image_trans VARCHAR(500),
    gantry_count INT DEFAULT 0,
    gantry_records JSON,
    audit_status VARCHAR(20) DEFAULT 'PENDING',
    risk_score DOUBLE DEFAULT 0,
    entry_visual_type VARCHAR(20),
    exit_visual_type VARCHAR(20),
    fingerprint_sim DOUBLE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
)
UNIQUE KEY(passid)
DISTRIBUTED BY HASH(passid) BUCKETS 10
PROPERTIES (
    "replication_num" = "1",
    "enable_unique_key_merge_on_write" = "true"
);

-- 稽核结果(检测产出, 一条 trip 可多条)
CREATE TABLE IF NOT EXISTS audit_results (
    id BIGINT NOT NULL AUTO_INCREMENT,
    audit_trip_id BIGINT NOT NULL,
    fraud_type VARCHAR(50) NOT NULL,
    entry_vehicle_type TINYINT,
    entry_visual_type VARCHAR(20),
    entry_color VARCHAR(20),
    exit_vehicle_type TINYINT,
    exit_visual_type VARCHAR(20),
    exit_color VARCHAR(20),
    is_suspicious TINYINT DEFAULT 0,
    risk_score DOUBLE DEFAULT 0,
    details JSON,
    process_status VARCHAR(20) DEFAULT 'UNPROCESSED',
    llm_is_same_vehicle TINYINT,
    llm_confidence DOUBLE,
    llm_reason VARCHAR(2000),
    llm_model VARCHAR(100),
    llm_checked_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
UNIQUE KEY(id)
DISTRIBUTED BY HASH(id) BUCKETS 10
PROPERTIES (
    "replication_num" = "1",
    "enable_unique_key_merge_on_write" = "true"
);

-- 人工稽核操作审计
CREATE TABLE IF NOT EXISTS audit_actions (
    id BIGINT NOT NULL AUTO_INCREMENT,
    result_id BIGINT NOT NULL,
    action VARCHAR(20) NOT NULL,
    operator VARCHAR(100),
    comments VARCHAR(2000),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
UNIQUE KEY(id)
DISTRIBUTED BY HASH(id) BUCKETS 4
PROPERTIES (
    "replication_num" = "1",
    "enable_unique_key_merge_on_write" = "true"
);

-- 定时任务配置
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id BIGINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(200) NOT NULL,
    description VARCHAR(1000),
    task_type VARCHAR(50) NOT NULL DEFAULT 'aggregate_detect',
    filter_rules JSON,
    schedule_type VARCHAR(20) NOT NULL DEFAULT 'interval',
    schedule_config JSON NOT NULL,
    enabled TINYINT NOT NULL DEFAULT 1,
    last_run_at DATETIME,
    next_run_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
)
UNIQUE KEY(id)
DISTRIBUTED BY HASH(id) BUCKETS 2
PROPERTIES (
    "replication_num" = "1",
    "enable_unique_key_merge_on_write" = "true"
);

-- 任务执行历史
CREATE TABLE IF NOT EXISTS task_executions (
    id BIGINT NOT NULL AUTO_INCREMENT,
    task_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    result_summary JSON,
    error_message VARCHAR(2000),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
UNIQUE KEY(id)
DISTRIBUTED BY HASH(id) BUCKETS 4
PROPERTIES (
    "replication_num" = "1",
    "enable_unique_key_merge_on_write" = "true"
);

-- Migration 记录表(替代 SQLite 的 schema_version)
CREATE TABLE IF NOT EXISTS migration_log (
    version INT NOT NULL,
    description VARCHAR(500),
    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
UNIQUE KEY(version)
DISTRIBUTED BY HASH(version) BUCKETS 1
PROPERTIES (
    "replication_num" = "1",
    "enable_unique_key_merge_on_write" = "true"
);
