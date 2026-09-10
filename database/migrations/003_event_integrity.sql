CREATE FUNCTION validate_token_session() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE session_row queue_sessions%ROWTYPE; zone_name text;
BEGIN
    SELECT * INTO session_row FROM queue_sessions WHERE id = NEW.session_id;
    IF NOT FOUND THEN RETURN NEW; END IF; -- foreign key emits the missing-session error
    SELECT timezone INTO zone_name FROM departments WHERE id = session_row.department_id;
    IF (NEW.check_in_at AT TIME ZONE zone_name)::date <> session_row.service_date
       OR NEW.check_in_at < session_row.opened_at
       OR (session_row.closed_at IS NOT NULL AND coalesce(NEW.ended_at, NEW.service_start_at, NEW.called_at, NEW.check_in_at) > session_row.closed_at) THEN
        RAISE EXCEPTION 'Token timestamps are outside its service session';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER token_session_times BEFORE INSERT OR UPDATE ON queue_tokens FOR EACH ROW EXECUTE FUNCTION validate_token_session();

CREATE FUNCTION validate_service_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE token_row queue_tokens%ROWTYPE; expected_time timestamptz;
BEGIN
    SELECT * INTO token_row FROM queue_tokens WHERE id = NEW.token_id;
    IF NOT FOUND THEN RETURN NEW; END IF;
    expected_time := CASE NEW.event_type
        WHEN 'check_in' THEN token_row.check_in_at
        WHEN 'called' THEN token_row.called_at
        WHEN 'service_start' THEN token_row.service_start_at
        WHEN 'completed' THEN token_row.completed_at
        WHEN 'cancelled' THEN CASE WHEN token_row.status = 'cancelled' THEN token_row.ended_at END
        WHEN 'no_show' THEN CASE WHEN token_row.status = 'no_show' THEN token_row.ended_at END
    END;
    IF expected_time IS NULL OR NEW.event_time <> expected_time THEN
        RAISE EXCEPTION 'Service event must match the recorded token timestamp and outcome';
    END IF;
    IF NEW.event_type <> 'check_in' AND NEW.staff_id IS DISTINCT FROM token_row.staff_id THEN
        RAISE EXCEPTION 'Service event staff must match token staff';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER event_consistency BEFORE INSERT OR UPDATE ON service_events FOR EACH ROW EXECUTE FUNCTION validate_service_event();
