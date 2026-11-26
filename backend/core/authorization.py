"""Staff authorization based on the permissions of the current database session."""

from backend.core.errors import ServiceError


def authorize(user, *permissions: str) -> None:
    """Require one of the named permissions. An empty grant set denies access."""
    granted = user.get('permissions', ())
    if not any(permission in granted for permission in permissions):
        raise ServiceError(
            403, 'Your account does not have permission for this action.'
        )


def queue_doctor(user) -> str | None:
    """Return the staff account ID to scope clinician queue queries."""
    return user['id'] if user['role'] == 'doctor' else None
