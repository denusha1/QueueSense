INSERT INTO permissions (code, description) VALUES
    ('account:self', 'Manage personal account settings and sessions'),
    ('account:security', 'Configure administrator MFA and initiate staff recovery'),
    ('department:read', 'Read the department directory'),
    ('department:manage', 'Manage departments'),
    ('doctor:read', 'Read clinician directory and schedules'),
    ('doctor:manage', 'Manage clinicians, schedules and service profiles'),
    ('users:manage', 'Manage staff accounts'),
    ('audit:read', 'Read administrative audit events'),
    ('queue:read', 'Read clinic queues, limited to own assignments for doctors'),
    ('queue:create', 'Issue queue tokens'),
    ('queue:update', 'Update queues, limited to own assignments for doctors'),
    ('queue:links', 'Recover private tracking links at the reception desk'),
    ('queue:close', 'Close a department queue session'),
    ('queue:balance', 'Read visit-specific redistribution proposals'),
    ('appointment:read', 'Read clinic appointments and arrivals'),
    ('appointment:update', 'Manage arrival slots and cancel appointments'),
    ('kiosk:manage', 'Manage reception kiosk links'),
    ('planning:read', 'Use anonymized planning and prediction tools'),
    ('analytics:read', 'Read analytics and forecasting'),
    ('reports:read', 'Export operational reports'),
    ('performance:read', 'Read model performance and service health'),
    ('alerts:read', 'Read operational alerts and staff notifications'),
    ('alerts:manage', 'Evaluate and resolve operational alerts'),
    ('feedback:read', 'Read clinic feedback summaries'),
    ('feedback:comments', 'Review voluntary free-text patient feedback'),
    ('data:import', 'Import synthetic historical visits');

INSERT INTO role_permissions (role_code, permission_code)
SELECT roles.code, grant_code
FROM (VALUES
    (ARRAY['admin','reception','doctor','manager'],
     ARRAY['account:self','department:read','doctor:read','planning:read','alerts:read']),
    (ARRAY['admin','reception','doctor'], ARRAY['queue:read','queue:update']),
    (ARRAY['admin','reception'],
     ARRAY['queue:create','queue:links','queue:close','queue:balance',
           'appointment:read','appointment:update','kiosk:manage']),
    (ARRAY['admin','manager'],
     ARRAY['analytics:read','reports:read','performance:read','feedback:read']),
    (ARRAY['admin'],
     ARRAY['account:security','department:manage','doctor:manage','users:manage',
           'audit:read','alerts:manage','feedback:comments','data:import'])
) grants (roles, permissions)
CROSS JOIN LATERAL unnest(grants.roles) AS roles(code)
CROSS JOIN LATERAL unnest(grants.permissions) AS grant_code;
