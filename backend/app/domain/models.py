from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.enums import AnalysisResultStatus, AnalysisRunStatus, ImportRunStatus, RunType


@dataclass(slots=True)
class ImportRun:
    id: str
    source_id: str
    type: RunType
    status: ImportRunStatus
    started_at: datetime | None
    finished_at: datetime | None
    error_text: str | None
    file_count: int
    success_count: int
    error_count: int
    idempotency_key: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class AnalysisRun:
    id: str
    source_id: str
    type: RunType
    status: AnalysisRunStatus
    started_at: datetime | None
    finished_at: datetime | None
    error_text: str | None
    file_count: int
    success_count: int
    error_count: int
    idempotency_key: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class AnalysisResult:
    id: str
    analysis_run_id: str
    source_id: str
    status: AnalysisResultStatus
    result_type: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
