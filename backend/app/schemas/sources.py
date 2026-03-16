from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import SourceSystem, SourceValidationStatus
from app.schemas.common import TimestampedResponse


class CreateSourceRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=255)
    source_system: SourceSystem = SourceSystem.LOCAL
    location_uri: str = Field(min_length=1, max_length=2048)
    is_active: bool = True


class UpdateSourceRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    location_uri: str | None = Field(default=None, min_length=1, max_length=2048)
    is_active: bool | None = None


class SourceResponse(TimestampedResponse):
    source_id: str
    display_name: str
    source_system: SourceSystem
    location_uri: str
    is_active: bool
    validation_status: SourceValidationStatus
    validation_message: str | None
    last_validated_at: datetime | None


class SourceValidationResponse(BaseModel):
    source_id: str
    validation_status: SourceValidationStatus
    validation_message: str | None
    last_validated_at: datetime | None


class ApiErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None
