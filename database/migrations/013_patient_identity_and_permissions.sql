-- Patient identities are optional for walk-ins and historical and demo records.
-- Legacy synthetic visit identifiers carry no evidence of a durable patient identity.
CREATE TABLE patients (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id text NOT NULL UNIQUE CHECK (external_id COLLATE "C" ~ '^[A-Z0-9][A-Z0-9._-]{0,63}$'),
    created_by uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE queue_tokens ADD COLUMN patient_id uuid REFERENCES patients(id);
ALTER TABLE appointments ADD COLUMN patient_id uuid REFERENCES patients(id);

CREATE UNIQUE INDEX queue_tokens_one_active_patient_per_session
    ON queue_tokens (session_id, patient_id)
    WHERE patient_id IS NOT NULL AND status IN ('waiting','called','in_service');
CREATE INDEX queue_tokens_patient_history_idx
    ON queue_tokens (patient_id, check_in_at DESC) WHERE patient_id IS NOT NULL;

CREATE UNIQUE INDEX appointments_one_patient_per_slot
    ON appointments (slot_id, patient_id)
    WHERE patient_id IS NOT NULL AND status <> 'cancelled';
CREATE INDEX appointments_patient_idx ON appointments (patient_id) WHERE patient_id IS NOT NULL;

CREATE TABLE roles (
    code text PRIMARY KEY,
    description text NOT NULL
);
INSERT INTO roles VALUES
    ('admin', 'Administrator'),
    ('reception', 'Receptionist'),
    ('doctor', 'Doctor'),
    ('manager', 'Manager');

-- Keep the original supported-role check for compatibility with staff workspace enums.
ALTER TABLE users ADD CONSTRAINT users_role_fkey FOREIGN KEY (role) REFERENCES roles(code);

CREATE TABLE permissions (
    code text PRIMARY KEY,
    description text NOT NULL
);
INSERT INTO permissions VALUES
    ('patient:register', 'Resolve or register a patient by clinic identifier'),
    ('queue:check_in', 'Issue a queue token at the reception desk'),
    ('appointment:book', 'Book a clinic arrival slot');

CREATE TABLE role_permissions (
    role_code text NOT NULL REFERENCES roles(code),
    permission_code text NOT NULL REFERENCES permissions(code),
    PRIMARY KEY (role_code, permission_code)
);
INSERT INTO role_permissions (role_code, permission_code)
SELECT roles.code, permissions.code
FROM roles CROSS JOIN permissions
WHERE roles.code IN ('admin','reception');
