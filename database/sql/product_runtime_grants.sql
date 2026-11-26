-- Runtime permission expansion for implemented product services; never schema ownership.
GRANT SELECT,INSERT ON users TO queuesense_auth;
GRANT UPDATE(role,is_active,password_hash) ON users TO queuesense_auth;
GRANT SELECT,INSERT,UPDATE ON departments,staff,staff_schedules,queue_sessions,queue_tokens,staff_availability,alerts TO queuesense_auth;
GRANT SELECT,INSERT ON service_events,predictions,audit_logs TO queuesense_auth;
GRANT SELECT ON token_durations,daily_department_summary,model_runs TO queuesense_auth;
GRANT SELECT,INSERT,UPDATE ON appointment_slots,appointments,checkin_kiosks TO queuesense_auth;
GRANT SELECT,INSERT ON self_checkins TO queuesense_auth;
GRANT SELECT,INSERT ON patient_feedback TO queuesense_auth;
GRANT SELECT,INSERT,UPDATE ON notifications,automation_state TO queuesense_auth;
GRANT SELECT,INSERT ON notification_reads TO queuesense_auth;
GRANT UPDATE(display_name,preferred_language) ON users TO queuesense_auth;
GRANT SELECT,INSERT,UPDATE,DELETE ON account_mfa,account_recovery,security_attempts,notification_targets,notification_deliveries TO queuesense_auth;
-- Only clinic identifiers can be corrected. The runtime cannot delete identities or edit role policy.
GRANT SELECT(id,external_id), INSERT(external_id,created_by), UPDATE(external_id) ON patients TO queuesense_auth;
GRANT SELECT ON roles,permissions,role_permissions TO queuesense_auth;
GRANT SELECT,INSERT,UPDATE,DELETE ON api_traffic_budgets TO queuesense_auth;
