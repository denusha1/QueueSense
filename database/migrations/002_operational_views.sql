-- Arrival cohort measures: filtering service_date selects the session, not completion date.
CREATE VIEW token_durations AS
SELECT t.*, s.service_date,
       extract(epoch FROM (t.service_start_at - t.check_in_at)) / 60.0 AS waiting_minutes,
       extract(epoch FROM (t.completed_at - t.service_start_at)) / 60.0 AS service_minutes
FROM queue_tokens t JOIN queue_sessions s ON s.id = t.session_id;

CREATE VIEW daily_department_summary AS
SELECT department_id, service_date,
       count(*) AS arrivals,
       count(*) FILTER (WHERE status = 'completed') AS completed,
       count(*) FILTER (WHERE status = 'waiting') AS waiting,
       count(*) FILTER (WHERE status = 'cancelled') AS cancelled,
       count(*) FILTER (WHERE status = 'no_show') AS no_shows,
       avg(waiting_minutes) AS average_wait_minutes,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY waiting_minutes) AS median_wait_minutes,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY waiting_minutes) AS p90_wait_minutes,
       avg(service_minutes) AS average_service_minutes
FROM token_durations GROUP BY department_id, service_date;
