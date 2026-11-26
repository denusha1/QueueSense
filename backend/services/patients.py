"""Registration and link validation shared by the reception workflows."""

from uuid import UUID

from psycopg.errors import UniqueViolation

from backend.core.authorization import authorize
from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.database import DatabaseConnection, connection, read_snapshot
from backend.repositories import patients
from backend.repositories.audit import audit
from backend.services.auth import StaffSession


def register(
    settings: Settings, external_id: str, user: StaffSession
) -> tuple[UUID, bool]:
    authorize(user, 'patient:register')
    with connection(settings) as conn:
        patient_id, created = patients.register(conn, external_id, user['id'])
        if created:
            audit(conn, user, 'register_patient', 'patient', patient_id)
        return patient_id, created


def validate_link(conn: DatabaseConnection, patient_id: UUID | None) -> None:
    if patient_id is not None and not patients.exists(conn, patient_id):
        raise ServiceError(404, 'Patient not found.')


def list_patients(settings, user, external_id, direction, limit, offset):
    authorize(user, 'patient:read')
    with read_snapshot(settings) as conn:
        return patients.page(
            conn,
            external_id.upper() if external_id else None,
            direction,
            limit,
            offset,
        )


def get_patient(settings, user, patient_id):
    authorize(user, 'patient:read')
    with connection(settings) as conn:
        row = patients.get(conn, patient_id)
        if not row:
            raise ServiceError(404, 'Patient not found.')
        return row


def update_patient(settings, user, patient_id, external_id):
    authorize(user, 'patient:update')
    with connection(settings) as conn:
        row = patients.lock(conn, patient_id)
        if not row:
            raise ServiceError(404, 'Patient not found.')
        if row['external_id'] == external_id:
            return row
        try:
            updated = patients.update_identifier(conn, patient_id, external_id)
        except UniqueViolation as exc:
            if exc.diag.constraint_name == 'patients_external_id_key':
                raise ServiceError(
                    409, 'This clinic identifier is already registered.'
                ) from exc
            raise
        audit(conn, user, 'update_patient_identifier', 'patient', patient_id)
        return updated
