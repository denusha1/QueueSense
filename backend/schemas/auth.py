"""Validation and workspace metadata for the existing staff API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.security import Role
from backend.schemas.text import SingleLine


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: SingleLine = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    role: Role
    otp: str | None = Field(default=None, max_length=6)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if value.count('@') != 1 or any(c.isspace() for c in value):
            raise ValueError('Enter a valid work email')
        return value


class DemoRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Role


class Session(BaseModel):
    id: UUID
    email: str
    role: Role
    expires_at: datetime
    access_expires_at: datetime | None = None


class WorkspaceInfo(BaseModel):
    title: str
    description: str
    capabilities: list[str]
    next: str


class WorkspaceResponse(BaseModel):
    user: Session
    workspace: WorkspaceInfo


WORKSPACES = {
    'reception': {
        'title': 'Reception workspace',
        'description': 'Your place to welcome arrivals and coordinate the queue.',
        'capabilities': ['Patient check-in', 'Queue coordination', 'Token status'],
        'next': 'Open your live queue to coordinate today’s arrivals.',
    },
    'doctor': {
        'title': 'Doctor workspace',
        'description': 'A focused space for your service queue and availability.',
        'capabilities': [
            'Call next token',
            'Record service events',
            'Manage availability',
        ],
        'next': 'Open your assigned clinician queue to call and serve patients.',
    },
    'manager': {
        'title': 'Manager workspace',
        'description': 'Understand patient flow and plan clinic capacity.',
        'capabilities': [
            'Operational analytics',
            'Bottleneck insights',
            'Staffing scenarios',
        ],
        'next': 'Explore analytics, recommendations, reports and observed prediction performance.',
    },
    'admin': {
        'title': 'Administrator workspace',
        'description': 'Manage access and the foundations of your clinic.',
        'capabilities': [
            'User and role management',
            'Department configuration',
            'Audit history',
        ],
        'next': 'Manage clinic access, review audit history and monitor operations.',
    },
}
