-- 004: 添加门架流水记录字段
-- 用于存储行程经过的所有门架（包含 pic_id, 站点, 时间, 车牌等）

ALTER TABLE audit_trips ADD COLUMN gantry_records TEXT;
