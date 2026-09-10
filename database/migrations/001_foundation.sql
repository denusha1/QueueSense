-- All event timestamps are timezone-aware. Department timezone defines service dates.
CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL CHECK (email = lower(email) AND position('@' in email) > 1),
    password_hash text NOT NULL CHECK (length(password_hash) > 20),
    role text NOT NULL CHECK (role IN ('admin','reception','doctor','manager')),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(email)
);
CREATE TABLE departments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE CHECK (code ~ '^[A-Z]{2,8}$'),
    name text NOT NULL UNIQUE,
    location text NOT NULL,
    timezone text NOT NULL DEFAULT 'Asia/Colombo',
    queue_threshold integer NOT NULL DEFAULT 15 CHECK (queue_threshold > 0),
    is_active boolean NOT NULL DEFAULT true
);
CREATE TABLE staff (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid UNIQUE REFERENCES users(id),
    department_id uuid NOT NULL REFERENCES departments(id),
    display_name text NOT NULL,
    staff_type text NOT NULL CHECK (staff_type IN ('doctor','service')),
    is_active boolean NOT NULL DEFAULT true,
    UNIQUE(id, department_id)
);
CREATE TABLE staff_schedules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id uuid NOT NULL REFERENCES staff(id),
    service_date date NOT NULL,
    start_at timestamptz NOT NULL,
    end_at timestamptz NOT NULL,
    status text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','cancelled')),
    CHECK (end_at > start_at),
    UNIQUE(staff_id, start_at)
);
CREATE TABLE queue_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    department_id uuid NOT NULL REFERENCES departments(id),
    service_date date NOT NULL,
    opened_at timestamptz NOT NULL,
    closed_at timestamptz,
    CHECK (closed_at IS NULL OR closed_at >= opened_at),
    UNIQUE(department_id, service_date),
    UNIQUE(id, department_id)
);
CREATE TABLE queue_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL,
    department_id uuid NOT NULL,
    staff_id uuid,
    token_no integer NOT NULL CHECK (token_no > 0),
    synthetic_patient_id text NOT NULL CHECK (synthetic_patient_id ~ '^SYN-[A-Z0-9-]+$'),
    priority_class text NOT NULL DEFAULT 'standard' CHECK (priority_class IN ('standard','expedited')),
    status text NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting','called','in_service','completed','cancelled','no_show')),
    check_in_at timestamptz NOT NULL,
    called_at timestamptz,
    service_start_at timestamptz,
    completed_at timestamptz,
    ended_at timestamptz,
    FOREIGN KEY (session_id, department_id) REFERENCES queue_sessions(id, department_id),
    FOREIGN KEY (staff_id, department_id) REFERENCES staff(id, department_id),
    UNIQUE(session_id, token_no),
    UNIQUE(id, department_id),
    CHECK (called_at IS NULL OR called_at >= check_in_at),
    CHECK (service_start_at IS NULL OR (called_at IS NOT NULL AND service_start_at >= called_at)),
    CHECK (completed_at IS NULL OR (service_start_at IS NOT NULL AND completed_at >= service_start_at)),
    CHECK (ended_at IS NULL OR ended_at >= coalesce(completed_at, service_start_at, called_at, check_in_at)),
    CHECK (
        (status = 'waiting' AND called_at IS NULL AND service_start_at IS NULL AND completed_at IS NULL AND ended_at IS NULL) OR
        (status = 'called' AND called_at IS NOT NULL AND staff_id IS NOT NULL AND service_start_at IS NULL AND completed_at IS NULL AND ended_at IS NULL) OR
        (status = 'in_service' AND service_start_at IS NOT NULL AND staff_id IS NOT NULL AND completed_at IS NULL AND ended_at IS NULL) OR
        (status = 'completed' AND completed_at IS NOT NULL AND staff_id IS NOT NULL AND ended_at = completed_at AND ended_at IS NOT NULL) OR
        (status = 'cancelled' AND service_start_at IS NULL AND completed_at IS NULL AND ended_at IS NOT NULL) OR
        (status = 'no_show' AND called_at IS NOT NULL AND staff_id IS NOT NULL AND service_start_at IS NULL AND completed_at IS NULL AND ended_at IS NOT NULL)
    )
);
CREATE TABLE service_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_id uuid NOT NULL,
    department_id uuid NOT NULL,
    staff_id uuid,
    event_type text NOT NULL CHECK (event_type IN ('check_in','called','service_start','completed','cancelled','no_show')),
    event_time timestamptz NOT NULL,
    FOREIGN KEY (token_id, department_id) REFERENCES queue_tokens(id, department_id),
    FOREIGN KEY (staff_id, department_id) REFERENCES staff(id, department_id),
    UNIQUE(token_id, event_type)
);
CREATE TABLE staff_availability (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id uuid NOT NULL REFERENCES staff(id),
    status text NOT NULL CHECK (status IN ('available','busy','break','offline')),
    changed_at timestamptz NOT NULL,
    UNIQUE(staff_id, changed_at)
);
CREATE TABLE model_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name text NOT NULL,
    version text NOT NULL UNIQUE,
    training_start timestamptz NOT NULL,
    training_end timestamptz NOT NULL,
    mae double precision NOT NULL CHECK (mae >= 0 AND mae < 'Infinity'::float8),
    rmse double precision NOT NULL CHECK (rmse >= 0 AND rmse < 'Infinity'::float8),
    r2 double precision NOT NULL CHECK (r2 > '-Infinity'::float8 AND r2 <= 1),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (training_end > training_start)
);
CREATE TABLE predictions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_id uuid NOT NULL REFERENCES queue_tokens(id),
    predicted_wait_minutes double precision NOT NULL CHECK (predicted_wait_minutes >= 0 AND predicted_wait_minutes < 'Infinity'::float8),
    model_version text NOT NULL REFERENCES model_runs(version),
    predicted_at timestamptz NOT NULL
);
CREATE TABLE alerts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    department_id uuid NOT NULL REFERENCES departments(id),
    alert_type text NOT NULL CHECK (alert_type IN ('high_queue','delay','capacity','model_error')),
    severity text NOT NULL CHECK (severity IN ('info','warning','critical')),
    message text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    CHECK (resolved_at IS NULL OR resolved_at >= created_at)
);
CREATE TABLE audit_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users(id),
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX queue_tokens_waiting_idx ON queue_tokens(session_id, check_in_at) WHERE status = 'waiting';
CREATE INDEX queue_tokens_department_arrival_idx ON queue_tokens(department_id, check_in_at);
CREATE INDEX queue_tokens_completion_idx ON queue_tokens(department_id, completed_at) WHERE status = 'completed';
CREATE INDEX queue_tokens_staff_idx ON queue_tokens(staff_id, service_start_at);
CREATE INDEX service_events_time_idx ON service_events(token_id, event_time);
CREATE INDEX staff_schedules_date_idx ON staff_schedules(service_date, staff_id);
CREATE INDEX availability_latest_idx ON staff_availability(staff_id, changed_at DESC);
CREATE INDEX predictions_token_time_idx ON predictions(token_id, predicted_at DESC);
CREATE INDEX alerts_open_idx ON alerts(department_id, created_at DESC) WHERE resolved_at IS NULL;
CREATE INDEX audit_logs_time_idx ON audit_logs(created_at DESC);

-- Direct inserts may carry validated historical states. Updates must follow the operational lifecycle.
CREATE FUNCTION validate_token_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.session_id, NEW.department_id, NEW.token_no, NEW.synthetic_patient_id, NEW.check_in_at)
       IS DISTINCT FROM ROW(OLD.session_id, OLD.department_id, OLD.token_no, OLD.synthetic_patient_id, OLD.check_in_at) THEN
        RAISE EXCEPTION 'Token identity and arrival are immutable';
    END IF;
    IF (OLD.called_at IS NOT NULL AND NEW.called_at IS DISTINCT FROM OLD.called_at)
       OR (OLD.service_start_at IS NOT NULL AND NEW.service_start_at IS DISTINCT FROM OLD.service_start_at)
       OR (OLD.completed_at IS NOT NULL AND NEW.completed_at IS DISTINCT FROM OLD.completed_at)
       OR (OLD.ended_at IS NOT NULL AND NEW.ended_at IS DISTINCT FROM OLD.ended_at) THEN
        RAISE EXCEPTION 'Recorded event timestamps are immutable';
    END IF;
    IF OLD.status IN ('completed','cancelled','no_show') AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'Terminal tokens are immutable';
    END IF;
    IF NEW.status <> OLD.status AND NOT (
        (OLD.status = 'waiting' AND NEW.status IN ('called','cancelled')) OR
        (OLD.status = 'called' AND NEW.status IN ('in_service','cancelled','no_show')) OR
        (OLD.status = 'in_service' AND NEW.status = 'completed')
    ) THEN
        RAISE EXCEPTION 'Invalid queue transition: % -> %', OLD.status, NEW.status;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER token_lifecycle BEFORE UPDATE ON queue_tokens FOR EACH ROW EXECUTE FUNCTION validate_token_update();
