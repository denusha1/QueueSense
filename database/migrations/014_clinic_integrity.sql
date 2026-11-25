-- GiST can enforce schedule overlap across transactions. Half-open shifts may touch.
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;

DO $$
DECLARE extension_schema text;
BEGIN
    SELECT n.nspname INTO STRICT extension_schema
    FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
    WHERE e.extname = 'btree_gist';

    -- PostgreSQL cannot add an exclusion constraint as NOT VALID.
    -- On legacy overlaps the migration fails atomically without changing those rows.
    EXECUTE format(
        'ALTER TABLE staff_schedules ADD CONSTRAINT staff_schedules_no_overlap '
        'EXCLUDE USING gist (staff_id %I.gist_uuid_ops WITH =, '
        'tstzrange(start_at, end_at, ''[)'') WITH &&) WHERE (status = ''scheduled'')',
        extension_schema
    );
END;
$$;

CREATE FUNCTION keep_queue_patient_and_clinician() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.patient_id IS DISTINCT FROM OLD.patient_id THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'A token patient link is immutable';
    END IF;
    IF OLD.called_at IS NOT NULL AND NEW.staff_id IS DISTINCT FROM OLD.staff_id THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'A called token clinician is immutable';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER queue_token_links_immutable
    BEFORE UPDATE OF patient_id, staff_id ON queue_tokens
    FOR EACH ROW EXECUTE FUNCTION keep_queue_patient_and_clinician();

CREATE FUNCTION validate_appointment_token_link() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE matches_link boolean;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.patient_id IS DISTINCT FROM OLD.patient_id OR NEW.slot_id IS DISTINCT FROM OLD.slot_id THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'A booking patient and slot are immutable';
        END IF;
        IF OLD.token_id IS NOT NULL AND NEW.token_id IS DISTINCT FROM OLD.token_id THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'A checked-in appointment token is immutable';
        END IF;
    END IF;
    IF NEW.token_id IS NOT NULL THEN
        SELECT t.department_id = s.department_id AND t.patient_id IS NOT DISTINCT FROM NEW.patient_id
        INTO matches_link
        FROM queue_tokens t CROSS JOIN appointment_slots s
        WHERE t.id = NEW.token_id AND s.id = NEW.slot_id;
        -- Missing references are reported by the existing foreign keys.
        IF matches_link IS FALSE THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'Booking and token must match patient and department';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER appointment_token_link_check
    BEFORE INSERT OR UPDATE OF token_id, slot_id, patient_id ON appointments
    FOR EACH ROW EXECUTE FUNCTION validate_appointment_token_link();

CREATE FUNCTION keep_slot_department() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.department_id IS DISTINCT FROM OLD.department_id THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'A slot department is immutable';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER appointment_slot_department_immutable
    BEFORE UPDATE OF department_id ON appointment_slots
    FOR EACH ROW EXECUTE FUNCTION keep_slot_department();

-- New notification writes must reference a token in the same department.
-- Validate separately after review of historic data so old anomalies survive the upgrade.
ALTER TABLE notifications ADD CONSTRAINT notifications_token_department_fkey
    FOREIGN KEY (token_id, department_id) REFERENCES queue_tokens(id, department_id) NOT VALID;

-- Supports the existing audit actor FK and per-user incident queries.
CREATE INDEX audit_logs_actor_time_idx ON audit_logs (user_id, created_at DESC) WHERE user_id IS NOT NULL;
