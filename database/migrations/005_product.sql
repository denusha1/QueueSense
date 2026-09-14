ALTER TABLE queue_tokens ADD COLUMN public_key text UNIQUE;
ALTER TABLE queue_tokens ADD COLUMN import_key text UNIQUE;
CREATE UNIQUE INDEX one_live_token_per_staff ON queue_tokens(staff_id) WHERE status IN ('called','in_service');
CREATE UNIQUE INDEX one_open_alert ON alerts(department_id,alert_type) WHERE resolved_at IS NULL;
CREATE INDEX token_import_key_idx ON queue_tokens(import_key) WHERE import_key IS NOT NULL;
