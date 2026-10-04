ALTER TABLE appointments ADD COLUMN confirmed_at timestamptz;
ALTER TABLE appointments ADD COLUMN attendance_outcome text CHECK(attendance_outcome IN ('no_show'));
ALTER TABLE appointments ADD COLUMN outcome_at timestamptz;
CREATE TABLE notifications (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 department_id uuid NOT NULL REFERENCES departments(id),
 token_id uuid REFERENCES queue_tokens(id),
 appointment_id uuid REFERENCES appointments(id),
 audience text NOT NULL CHECK(audience IN ('staff','patient','appointment')),
 kind text NOT NULL,
 message text NOT NULL,
 event_key text NOT NULL UNIQUE,
 created_at timestamptz NOT NULL DEFAULT now(),
 private_read_at timestamptz,
 CHECK((audience='staff' AND token_id IS NULL AND appointment_id IS NULL) OR
       (audience='patient' AND token_id IS NOT NULL AND appointment_id IS NULL) OR
       (audience='appointment' AND appointment_id IS NOT NULL AND token_id IS NULL))
);
CREATE INDEX notifications_feed_idx ON notifications(audience,department_id,created_at DESC);
CREATE INDEX notifications_token_idx ON notifications(token_id,created_at DESC);
CREATE INDEX notifications_appointment_idx ON notifications(appointment_id,created_at DESC);
CREATE TABLE notification_reads (
 notification_id uuid NOT NULL REFERENCES notifications(id),
 user_id uuid NOT NULL REFERENCES users(id),
 read_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(notification_id,user_id)
);
CREATE TABLE automation_state (
 entity_key text PRIMARY KEY,
 payload jsonb NOT NULL,
 revision bigint NOT NULL DEFAULT 1,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION notify_appointment_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM pg_notify('queuesense_queue','');
 RETURN NEW;
END;
$$;
CREATE TRIGGER appointment_realtime AFTER INSERT OR UPDATE ON appointments FOR EACH ROW EXECUTE FUNCTION notify_appointment_change();
CREATE TRIGGER notification_realtime AFTER INSERT ON notifications FOR EACH ROW EXECUTE FUNCTION notify_queue_change();
CREATE FUNCTION notify_patient_status() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
  INSERT INTO notifications(department_id,token_id,audience,kind,message,event_key)
  VALUES(NEW.department_id,NEW.id,'patient','queue_status',
   CASE NEW.status WHEN 'waiting' THEN 'You have joined the queue. Your waiting estimate updates as the queue changes.'
    WHEN 'called' THEN 'It is your turn. Please follow the clinic staff’s directions.'
    WHEN 'in_service' THEN 'Your consultation is in progress.'
    WHEN 'completed' THEN 'Your visit is complete. You can now share feedback.'
    WHEN 'no_show' THEN 'Your token was marked as a missed call. Please contact reception.'
    ELSE 'Your token has been cancelled. Please contact reception if you need help.' END,
   'status:' || NEW.id::text || ':' || NEW.status)
  ON CONFLICT(event_key) DO NOTHING;
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER patient_status_notification AFTER INSERT OR UPDATE OF status ON queue_tokens FOR EACH ROW EXECUTE FUNCTION notify_patient_status();
