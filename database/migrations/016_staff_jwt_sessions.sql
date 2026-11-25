-- Existing opaque sessions remain intact for development or a deliberate rollback.
-- A JWT session stores only the digest of its current opaque refresh credential.
ALTER TABLE auth_sessions
    ADD COLUMN auth_mode text NOT NULL DEFAULT 'opaque'
    CHECK (auth_mode IN ('opaque','jwt'));
