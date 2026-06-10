-- 006_add_llm_columns.sql
-- 给 audit_results 加 LLM 二次判定结果列
ALTER TABLE audit_results ADD COLUMN llm_is_same_vehicle INTEGER;
ALTER TABLE audit_results ADD COLUMN llm_confidence REAL;
ALTER TABLE audit_results ADD COLUMN llm_reason TEXT;
ALTER TABLE audit_results ADD COLUMN llm_model TEXT;
ALTER TABLE audit_results ADD COLUMN llm_checked_at TEXT;
CREATE INDEX IF NOT EXISTS idx_results_llm_pending
    ON audit_results(llm_checked_at) WHERE llm_checked_at IS NULL;
