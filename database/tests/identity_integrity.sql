-- Run after integrity.sql in the same test transaction, then roll it back.
DO $$
DECLARE
    department uuid;
    other_department uuid;
    clinician uuid;
    other_clinician uuid;
    session uuid;
    other_session uuid;
    slot uuid;
    first_patient uuid;
    second_patient uuid;
    token uuid;
    other_patient_token uuid;
    other_department_token uuid;
    booking uuid;
    arrival timestamptz;
    shift timestamptz := '2099-01-01 09:00:00+05:30';
BEGIN
    SELECT s.id, s.department_id, s.opened_at INTO STRICT session, department, arrival
      FROM queue_sessions s ORDER BY s.service_date,s.department_id LIMIT 1;
    SELECT d.id INTO STRICT other_department FROM departments d WHERE d.id <> department LIMIT 1;
    SELECT s.id INTO STRICT other_session FROM queue_sessions s
      WHERE s.department_id = other_department
        AND s.service_date = (arrival AT TIME ZONE 'Asia/Colombo')::date;
    SELECT id INTO STRICT clinician FROM staff WHERE department_id = department LIMIT 1;
    SELECT id INTO STRICT other_clinician FROM staff WHERE department_id = department AND id <> clinician LIMIT 1;

    INSERT INTO patients(external_id) VALUES('TEST-IDENTITY-1') RETURNING id INTO first_patient;
    INSERT INTO patients(external_id) VALUES('TEST-IDENTITY-2') RETURNING id INTO second_patient;
    PERFORM pg_temp.expect_rejected('INSERT INTO patients(external_id) VALUES(''TEST-IDENTITY-1'')', '23505');
    PERFORM pg_temp.expect_rejected('INSERT INTO patients(external_id) VALUES(''test-lowercase'')', '23514');
    PERFORM pg_temp.expect_rejected('INSERT INTO role_permissions(role_code,permission_code) VALUES(''doctor'',''missing-permission'')', '23503');

    INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at,patient_id)
      VALUES(session,department,88001,'SYN-IDENTITY-1',arrival,first_patient) RETURNING id INTO token;

    PERFORM pg_temp.expect_rejected(format(
        'INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at,patient_id) VALUES(%L,%L,88002,''SYN-IDENTITY-DUP'',%L,%L)',
        session,department,arrival,first_patient), '23505');
    PERFORM pg_temp.expect_rejected(format(
        'INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at,patient_id) VALUES(%L,%L,88002,''SYN-IDENTITY-MISSING'',%L,%L)',
        session,department,arrival,gen_random_uuid()), '23503');
    PERFORM pg_temp.expect_rejected(format(
        'UPDATE queue_tokens SET patient_id=%L WHERE id=%L',second_patient,token), '23514');

    UPDATE queue_tokens SET status='called',staff_id=clinician,called_at=arrival WHERE id=token;
    PERFORM pg_temp.expect_rejected(format(
        'UPDATE queue_tokens SET staff_id=%L WHERE id=%L',other_clinician,token), '23514');
    UPDATE queue_tokens SET status='no_show',ended_at=arrival WHERE id=token;
    INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at,patient_id)
      VALUES(session,department,88002,'SYN-IDENTITY-RETURN',arrival,first_patient) RETURNING id INTO token;
    INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at,patient_id)
      VALUES(session,department,88003,'SYN-IDENTITY-2',arrival,second_patient) RETURNING id INTO other_patient_token;
    INSERT INTO queue_tokens(session_id,department_id,token_no,synthetic_patient_id,check_in_at,patient_id)
      VALUES(other_session,other_department,88001,'SYN-IDENTITY-OTHER-DEPT',arrival,first_patient)
      RETURNING id INTO other_department_token;

    INSERT INTO appointment_slots(department_id,starts_at,capacity) VALUES(department,shift,3) RETURNING id INTO slot;
    INSERT INTO appointments(slot_id,reference,public_key,patient_id)
      VALUES(slot,'TEST-IDENTITY-BOOKING','test-identity-booking',first_patient) RETURNING id INTO booking;
    PERFORM pg_temp.expect_rejected(format(
        'INSERT INTO appointments(slot_id,reference,public_key,patient_id) VALUES(%L,''TEST-IDENTITY-DUP'',''test-identity-dup'',%L)',
        slot,first_patient), '23505');
    PERFORM pg_temp.expect_rejected(format(
        'UPDATE appointments SET status=''checked_in'',token_id=%L WHERE id=%L',other_patient_token,booking), '23514');
    PERFORM pg_temp.expect_rejected(format(
        'UPDATE appointments SET status=''checked_in'',token_id=%L WHERE id=%L',other_department_token,booking), '23514');
    UPDATE appointments SET status='checked_in',token_id=token WHERE id=booking;
    PERFORM pg_temp.expect_rejected(format(
        'UPDATE appointment_slots SET department_id=%L WHERE id=%L',other_department,slot), '23514');
    PERFORM pg_temp.expect_rejected(format(
        'INSERT INTO notifications(department_id,token_id,audience,kind,message,event_key) VALUES(%L,%L,''patient'',''test'',''Test'',''identity-wrong-department'')',
        other_department,token), '23503');

    INSERT INTO staff_schedules(staff_id,service_date,start_at,end_at)
      VALUES(clinician,'2099-01-01',shift,shift + interval '2 hours');
    PERFORM pg_temp.expect_rejected(format(
        'INSERT INTO staff_schedules(staff_id,service_date,start_at,end_at) VALUES(%L,''2099-01-01'',%L,%L)',
        clinician,shift + interval '1 hour',shift + interval '3 hours'), '23P01');
    INSERT INTO staff_schedules(staff_id,service_date,start_at,end_at,status)
      VALUES(clinician,'2099-01-01',shift + interval '1 hour',shift + interval '3 hours','cancelled');
    INSERT INTO staff_schedules(staff_id,service_date,start_at,end_at)
      VALUES(clinician,'2099-01-01',shift + interval '2 hours',shift + interval '3 hours');
END;
$$;
