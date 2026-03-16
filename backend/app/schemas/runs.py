from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import AnalysisResultStatus, AnalysisRunStatus, ImportRunStatus
from app.schemas.common import ApiModel, TimestampedResponse


class RunCounters(BaseModel):
    file_count: int = 0
    success_count: int = 0
    error_count: int = 0


class CreateImportRunRequest(BaseModel):
    source_id: str = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=255)


class UpdateImportRunRequest(BaseModel):
    status: ImportRunStatus
    error_text: str | None = None
    counters: RunCounters | None = None


class ImportRunResponse(TimestampedResponse):
    id: str
    source_id: str
    type: str = Field(validation_alias="run_type")
    status: ImportRunStatus
    started_at: datetime | None
    finished_at: datetime | None
    error_text: str | None
    file_count: int
    success_count: int
    error_count: int
    idempotency_key: str | None


class CreateAnalysisRunRequest(BaseModel):
    source_id: str = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=255)


class UpdateAnalysisRunRequest(BaseModel):
    status: AnalysisRunStatus
    error_text: str | None = None
    counters: RunCounters | None = None


class StoreAnalysisResultRequest(BaseModel):
    result_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any]
    status: AnalysisResultStatus = AnalysisResultStatus.DRAFT


class AnalysisResultResponse(TimestampedResponse):
    id: str
    analysis_run_id: str
    source_id: str
    status: AnalysisResultStatus
    result_type: str
    payload: dict[str, Any]


class AnalysisRunResponse(TimestampedResponse):
    id: str
    source_id: str
    type: str = Field(validation_alias="run_type")
    status: AnalysisRunStatus
    started_at: datetime | None
    finished_at: datetime | None
    error_text: str | None
    file_count: int
    success_count: int
    error_count: int
    idempotency_key: str | None
    results: list[AnalysisResultResponse] = Field(default_factory=list)
