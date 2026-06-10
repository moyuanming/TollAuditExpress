-- 005: 车辆查询索引
-- 为"任意车辆通行查询"页面添加的索引：车牌、OBU、入口时间、风险评分
-- 全部使用 IF NOT EXISTS 保证幂等

CREATE INDEX IF NOT EXISTS idx_trips_entry_vehicle_id ON audit_trips(entry_vehicle_id);
CREATE INDEX IF NOT EXISTS idx_trips_exit_vehicle_id ON audit_trips(exit_vehicle_id);
CREATE INDEX IF NOT EXISTS idx_trips_entry_time ON audit_trips(entry_time);
CREATE INDEX IF NOT EXISTS idx_trips_entry_obu_id ON audit_trips(entry_obu_id);
CREATE INDEX IF NOT EXISTS idx_trips_risk_score ON audit_trips(risk_score);
