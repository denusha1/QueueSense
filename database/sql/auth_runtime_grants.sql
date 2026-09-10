-- Create queuesense_auth as a LOGIN role with a private password first.
-- Run as the database owner; never use that owner credential in the API.
GRANT CONNECT ON DATABASE queuesense TO queuesense_auth;
GRANT USAGE ON SCHEMA public TO queuesense_auth;
GRANT SELECT(id,email,password_hash,role,is_active) ON users TO queuesense_auth;
GRANT UPDATE(password_hash) ON users TO queuesense_auth;
GRANT SELECT,INSERT,DELETE ON auth_sessions,login_attempts TO queuesense_auth;
GRANT USAGE,SELECT ON SEQUENCE login_attempts_id_seq TO queuesense_auth;
