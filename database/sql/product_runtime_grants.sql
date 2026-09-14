-- Runtime permission expansion for implemented product services; never schema ownership.
GRANT SELECT,INSERT ON users TO queuesense_auth;
GRANT UPDATE(role,is_active,password_hash) ON users TO queuesense_auth;
GRANT SELECT,INSERT,UPDATE ON departments,staff,staff_schedules,queue_sessions,queue_tokens,staff_availability,alerts TO queuesense_auth;
GRANT SELECT,INSERT ON service_events,predictions,audit_logs TO queuesense_auth;
GRANT SELECT ON token_durations,daily_department_summary,model_runs TO queuesense_auth;
GRANT SELECT,INSERT,UPDATE ON appointment_slots,appointments,checkin_kiosks TO queuesense_auth;
GRANT SELECT,INSERT ON self_checkins TO queuesense_auth;
