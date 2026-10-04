ALTER TABLE audit_logs ADD COLUMN actor_type text NOT NULL DEFAULT 'system' CHECK (actor_type IN ('staff','patient','system'));
ALTER TABLE audit_logs ADD COLUMN details jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(details)='object');
UPDATE audit_logs SET actor_type=CASE WHEN user_id IS NULL THEN 'system' ELSE 'staff' END;
CREATE INDEX audit_logs_entity_time_idx ON audit_logs(entity_type,entity_id,created_at DESC);
