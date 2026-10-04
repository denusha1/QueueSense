CREATE TABLE patient_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_id uuid NOT NULL UNIQUE REFERENCES queue_tokens(id) ON DELETE CASCADE,
    rating smallint NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment text NOT NULL DEFAULT '' CHECK (length(comment) <= 1000),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX patient_feedback_created_idx ON patient_feedback(created_at);
