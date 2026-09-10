CREATE TABLE auth_sessions (
    token_hash text PRIMARY KEY CHECK (length(token_hash) = 64),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    CHECK (expires_at > created_at)
);
CREATE INDEX auth_sessions_user_idx ON auth_sessions(user_id);
CREATE INDEX auth_sessions_expiry_idx ON auth_sessions(expires_at);
CREATE TABLE login_attempts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_hash text NOT NULL,
    source_hash text NOT NULL,
    succeeded boolean NOT NULL,
    attempted_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX login_attempts_account_idx ON login_attempts(account_hash, attempted_at DESC);
CREATE INDEX login_attempts_source_idx ON login_attempts(source_hash, attempted_at DESC);
