-- Add visual detection fields to audit_trips
ALTER TABLE audit_trips ADD COLUMN entry_visual_type TEXT;
ALTER TABLE audit_trips ADD COLUMN exit_visual_type TEXT;
ALTER TABLE audit_trips ADD COLUMN fingerprint_sim REAL;
