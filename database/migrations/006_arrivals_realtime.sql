CREATE TABLE appointment_slots (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 department_id uuid NOT NULL REFERENCES departments(id),
 starts_at timestamptz NOT NULL,
 capacity integer NOT NULL CHECK (capacity BETWEEN 1 AND 20),
 created_by uuid REFERENCES users(id),
 UNIQUE(department_id, starts_at)
);
CREATE TABLE appointments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 slot_id uuid NOT NULL REFERENCES appointment_slots(id),
 reference text NOT NULL UNIQUE,
 public_key text NOT NULL UNIQUE,
 status text NOT NULL DEFAULT 'booked' CHECK (status IN ('booked','checked_in','cancelled')),
 token_id uuid UNIQUE REFERENCES queue_tokens(id),
 created_by uuid REFERENCES users(id),
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((status='checked_in') = (token_id IS NOT NULL))
);
CREATE INDEX appointments_slot_idx ON appointments(slot_id);
CREATE TABLE checkin_kiosks (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 department_id uuid NOT NULL REFERENCES departments(id),
 public_key text NOT NULL UNIQUE,
 expires_at timestamptz NOT NULL,
 revoked_at timestamptz,
 created_by uuid REFERENCES users(id)
);
CREATE TABLE self_checkins (
 kiosk_id uuid NOT NULL REFERENCES checkin_kiosks(id),
 request_id uuid NOT NULL,
 token_id uuid NOT NULL REFERENCES queue_tokens(id),
 PRIMARY KEY(kiosk_id, request_id)
);
-- Empty invalidation events carry no token IDs or patient links. PostgreSQL
-- delivers them only after commit, including changes from other API workers.
CREATE FUNCTION notify_queue_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE department uuid;
BEGIN
 IF TG_TABLE_NAME='staff_availability' THEN
  SELECT department_id INTO department FROM staff WHERE id=NEW.staff_id;
 ELSE department := NEW.department_id;
 END IF;
 PERFORM pg_notify('queuesense_queue', '');
 IF department IS NOT NULL THEN
  PERFORM pg_notify('queuesense_' || replace(department::text, '-', ''), '');
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER token_realtime AFTER INSERT OR UPDATE ON queue_tokens FOR EACH ROW EXECUTE FUNCTION notify_queue_change();
CREATE TRIGGER availability_realtime AFTER INSERT ON staff_availability FOR EACH ROW EXECUTE FUNCTION notify_queue_change();
CREATE TRIGGER session_realtime AFTER INSERT OR UPDATE ON queue_sessions FOR EACH ROW EXECUTE FUNCTION notify_queue_change();
