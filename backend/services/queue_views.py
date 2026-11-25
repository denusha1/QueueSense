"""Shared wait and position fields for queue list responses."""

from uuid import UUID

from backend.database import DatabaseConnection, Row


def decorate_queue_rows(conn: DatabaseConnection, rows: list[Row]) -> list[Row]:
    from backend.services.prediction import live_predictions

    estimates: dict[UUID, dict[str, Row]] = {}
    for row in rows:
        if row['status'] == 'waiting':
            dep = row['department_id']
            if dep not in estimates:
                estimates[dep] = live_predictions(conn, dep)
            prediction = estimates[dep].get(str(row['id']), {})
            row.update(
                position=prediction.get('position'),
                patients_ahead=prediction.get('patients_ahead'),
                estimated_wait=prediction.get('minutes'),
                prediction_source=prediction.get('source'),
                prediction_notice=prediction.get('reason'),
            )
        else:
            row.update(position=None, patients_ahead=None, estimated_wait=None)
        row['actual_wait'] = (
            round(
                (row['service_start_at'] - row['check_in_at']).total_seconds() / 60, 1
            )
            if row['service_start_at']
            else None
        )
        row['prediction_error'] = (
            round(row['actual_wait'] - row['initial_wait_minutes'], 1)
            if row['actual_wait'] is not None
            and row['initial_wait_minutes'] is not None
            else None
        )
    return rows
