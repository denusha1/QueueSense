ALTER TABLE queue_tokens ADD COLUMN priority_reason text NOT NULL DEFAULT '' CHECK(length(priority_reason)<=160);
ALTER TABLE queue_tokens ADD COLUMN initial_wait_minutes double precision CHECK(initial_wait_minutes>=0 AND initial_wait_minutes<'Infinity'::float8);
ALTER TABLE queue_tokens ADD COLUMN initial_prediction_version text;
ALTER TABLE queue_tokens ADD COLUMN initial_prediction_at timestamptz;
