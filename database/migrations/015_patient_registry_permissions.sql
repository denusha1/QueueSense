INSERT INTO permissions (code, description) VALUES
    ('patient:read', 'Read the clinic patient registry'),
    ('patient:update', 'Correct the identifier of an existing patient');

INSERT INTO role_permissions (role_code, permission_code) VALUES
    ('admin', 'patient:read'),
    ('reception', 'patient:read'),
    ('admin', 'patient:update');
