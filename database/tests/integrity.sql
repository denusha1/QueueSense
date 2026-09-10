CREATE FUNCTION pg_temp.expect_rejected(statement text, expected_state text DEFAULT NULL) RETURNS void LANGUAGE plpgsql AS $$
DECLARE rejected boolean := false;
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN OTHERS THEN
        IF expected_state IS NOT NULL AND SQLSTATE <> expected_state THEN RAISE; END IF;
        rejected := true;
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'Invalid statement unexpectedly succeeded: %', statement; END IF;
END;
$$;

DO $$
DECLARE session_id uuid; dept_id uuid; clinician uuid; other_clinician uuid; token_id uuid := gen_random_uuid(); arrival timestamptz; bad_id uuid := gen_random_uuid();
BEGIN
    SELECT s.id, s.department_id, s.opened_at INTO session_id, dept_id, arrival FROM queue_sessions s ORDER BY service_date LIMIT 1;
    SELECT id INTO clinician FROM staff WHERE department_id = dept_id LIMIT 1;
    SELECT id INTO other_clinician FROM staff WHERE department_id <> dept_id LIMIT 1;
    INSERT INTO queue_tokens(id,session_id,department_id,token_no,synthetic_patient_id,check_in_at)
    VALUES(token_id,session_id,dept_id,99999,'SYN-TEST',arrival);

    -- Constraint failures: duplicate daily token, missing reference, invalid timestamp/state, cross-department assignment.
    PERFORM pg_temp.expect_rejected(format('INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at) VALUES(%L,%L,99999,''SYN-DUPLICATE'',%L)',session_id,dept_id,arrival), '23505');
    PERFORM pg_temp.expect_rejected(format('INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at) VALUES(%L,%L,99998,''SYN-MISSING'',%L)',bad_id,dept_id,arrival), '23503');
    PERFORM pg_temp.expect_rejected(format('UPDATE queue_tokens SET status=''called'',staff_id=%L,called_at=%L WHERE id=%L',clinician,arrival - interval '1 minute',token_id), '23514');
    PERFORM pg_temp.expect_rejected(format('UPDATE queue_tokens SET status=''called'',staff_id=%L,called_at=%L WHERE id=%L',other_clinician,arrival,token_id), '23503');
    PERFORM pg_temp.expect_rejected(format('UPDATE queue_tokens SET status=''completed'',staff_id=%L,called_at=%L,service_start_at=%L,completed_at=%L,ended_at=%L WHERE id=%L',clinician,arrival,arrival,arrival,arrival,token_id), 'P0001');
    PERFORM pg_temp.expect_rejected(format('UPDATE queue_tokens SET check_in_at=%L WHERE id=%L',arrival + interval '1 minute',token_id), 'P0001');

    UPDATE queue_tokens SET status='called',staff_id=clinician,called_at=arrival + interval '1 minute' WHERE id=token_id;
    PERFORM pg_temp.expect_rejected(format('UPDATE queue_tokens SET status=''waiting'',called_at=NULL WHERE id=%L',token_id), 'P0001');
    UPDATE queue_tokens SET status='in_service',service_start_at=arrival + interval '2 minutes' WHERE id=token_id;
    UPDATE queue_tokens SET status='completed',completed_at=arrival + interval '12 minutes',ended_at=arrival + interval '12 minutes' WHERE id=token_id;
    PERFORM pg_temp.expect_rejected(format('UPDATE queue_tokens SET token_no=99997 WHERE id=%L',token_id), 'P0001');
    PERFORM pg_temp.expect_rejected(format('INSERT INTO service_events(token_id,department_id,staff_id,event_type,event_time) VALUES(%L,%L,%L,''completed'',%L)',token_id,dept_id,clinician,arrival + interval '20 minutes'), 'P0001');
    INSERT INTO service_events(token_id,department_id,staff_id,event_type,event_time) VALUES(token_id,dept_id,clinician,'completed',arrival + interval '12 minutes');
    IF (SELECT waiting_minutes FROM token_durations WHERE id=token_id) <> 2 THEN RAISE EXCEPTION 'Waiting KPI mismatch'; END IF;
    IF (SELECT service_minutes FROM token_durations WHERE id=token_id) <> 10 THEN RAISE EXCEPTION 'Service KPI mismatch'; END IF;
    PERFORM pg_temp.expect_rejected(format('DELETE FROM departments WHERE id=%L',dept_id), '23503');
    PERFORM pg_temp.expect_rejected(format('INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at) VALUES(%L,%L,99998,''SYN-WRONG-DAY'',%L)',session_id,dept_id,arrival + interval '1 day'), 'P0001');
END;
$$;
