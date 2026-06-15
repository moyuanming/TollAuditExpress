-- 007: 货车 OBU 监测 — 每日统计表
-- 设计要点：
--   - (date, fraud_type) 联合主键，覆盖按日聚合查询
--   - scanned_count: 该日累计扫描 trip 数（去重后）
--   - suspicious_count: 该日写入 audit_results 的可疑数
--   - confirmed_count: 该日已 CONFIRMED 数（process_status='CONFIRMED'）
--   - last_run_at: 该日最后一次任务执行时间
--   - updated_at: ON UPDATE 自动维护
-- 注：本文件为 SQLite 兼容版本（测试环境），Doris 版本见 doris_ddl.sql

CREATE TABLE IF NOT EXISTS audit_truck_obu_daily_stats (
    date TEXT NOT NULL,
    fraud_type TEXT NOT NULL,
    scanned_count INTEGER NOT NULL DEFAULT 0,
    suspicious_count INTEGER NOT NULL DEFAULT 0,
    confirmed_count INTEGER NOT NULL DEFAULT 0,
    last_run_at TEXT,
    updated_at TEXT DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (date, fraud_type)
);

CREATE INDEX IF NOT EXISTS idx_truck_obu_stats_date
    ON audit_truck_obu_daily_stats(date);

-- audit_results 加索引支持新 fraud_type 扫描
CREATE INDEX IF NOT EXISTS idx_results_type_created
    ON audit_results(fraud_type, created_at);
