from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.schemas.product import Input


class PatientRegistration(Input):
    external_id: str = Field(pattern=r'^[A-Z0-9][A-Z0-9._-]{0,63}$', max_length=64)

    @field_validator('external_id', mode='before')
    @classmethod
    def normalize_identifier(cls, value):
        if isinstance(value, str) and value.isascii():
            return value.strip().upper()
        return value


class PatientReference(BaseModel):
    id: UUID
