CREATE TABLE api_traffic_budgets (
    policy text NOT NULL,
    subject uuid NOT NULL,
    window_start bigint NOT NULL,
    requests integer NOT NULL CHECK (requests > 0),
    PRIMARY KEY (policy, subject)
);

CREATE INDEX api_traffic_budgets_window_idx ON api_traffic_budgets (window_start);

-- Existing installations may already have their runtime role provisioned.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'queuesense_auth') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON api_traffic_budgets TO queuesense_auth;
    END IF;
END;
$$;
