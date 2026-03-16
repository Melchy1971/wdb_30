from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import AnalysisResultModel, AnalysisRunModel, ImportRunModel
from app.domain.enums import AnalysisRunStatus, ImportRunStatus, RunType
from app.repositories.run_repository import AnalysisResultRepository, AnalysisRunRepository, ImportRunRepository
from app.schemas.runs import (
    CreateAnalysisRunRequest,
    CreateImportRunRequest,
    RunCounters,
    StoreAnalysisResultRequest,
    UpdateAnalysisRunRequest,
    UpdateImportRunRequest,
)
from app.services.state_machine import ensure_analysis_transition, ensure_import_transition


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportRunService:
    def __init__(self, session: Session) -> None:
        self.repository = ImportRunRepository(session)

    def create_run(self, request: CreateImportRunRequest) -> ImportRunModel:
        if request.idempotency_key:
            existing = self.repository.get_by_idempotency(request.source_id, request.idempotency_key)
            if existing is not None:
                return existing

        now = utcnow()
        run = ImportRunModel(
            source_id=request.source_id,
            run_type=RunType.IMPORT.value,
            status=ImportRunStatus.PENDING.value,
            idempotency_key=request.idempotency_key,
            started_at=None,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        return self.repository.create(run)

    def update_run(self, run_id: str, request: UpdateImportRunRequest) -> ImportRunModel:
        run = self.repository.get(run_id)
        current_status = ImportRunStatus(run.status)
        ensure_import_transition(current_status, request.status)
        run.status = request.status.value
        self._apply_lifecycle_timestamps(run, request.status)
        run.error_text = request.error_text
        self._apply_counters(run, request.counters)
        return self.repository.save(run)

    def get_run(self, run_id: str) -> ImportRunModel:
        return self.repository.get(run_id)

    def list_runs(self) -> list[ImportRunModel]:
        return self.repository.list_all()

    def recover_stale_runs(self) -> list[ImportRunModel]:
        stale_runs = self.repository.list_by_statuses([ImportRunStatus.RUNNING.value, ImportRunStatus.PENDING.value])
        now = utcnow()
        updated: list[ImportRunModel] = []
        for run in stale_runs:
            run.status = ImportRunStatus.STALE.value
            if run.started_at is None:
                run.started_at = now
            run.finished_at = now
            run.error_text = run.error_text or "Recovered after restart"
            updated.append(self.repository.save(run))
        return updated

    def _apply_lifecycle_timestamps(self, run: ImportRunModel, target_status: ImportRunStatus) -> None:
        now = utcnow()
        if target_status == ImportRunStatus.RUNNING and run.started_at is None:
            run.started_at = now
            run.finished_at = None
        if target_status in {
            ImportRunStatus.COMPLETED,
            ImportRunStatus.PARTIAL,
            ImportRunStatus.FAILED,
            ImportRunStatus.CANCELLED,
            ImportRunStatus.STALE,
        }:
            if run.started_at is None:
                run.started_at = now
            run.finished_at = now

    @staticmethod
    def _apply_counters(run: ImportRunModel, counters: RunCounters | None) -> None:
        if counters is None:
            return
        run.file_count = counters.file_count
        run.success_count = counters.success_count
        run.error_count = counters.error_count


class AnalysisRunService:
    def __init__(self, session: Session) -> None:
        self.run_repository = AnalysisRunRepository(session)
        self.result_repository = AnalysisResultRepository(session)

    def create_run(self, request: CreateAnalysisRunRequest) -> AnalysisRunModel:
        if request.idempotency_key:
            existing = self.run_repository.get_by_idempotency(request.source_id, request.idempotency_key)
            if existing is not None:
                return existing

        now = utcnow()
        run = AnalysisRunModel(
            source_id=request.source_id,
            run_type=RunType.ANALYSIS.value,
            status=AnalysisRunStatus.PENDING.value,
            idempotency_key=request.idempotency_key,
            started_at=None,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        return self.run_repository.create(run)

    def update_run(self, run_id: str, request: UpdateAnalysisRunRequest) -> AnalysisRunModel:
        run = self.run_repository.get(run_id)
        current_status = AnalysisRunStatus(run.status)
        ensure_analysis_transition(current_status, request.status)
        run.status = request.status.value
        self._apply_lifecycle_timestamps(run, request.status)
        run.error_text = request.error_text
        self._apply_counters(run, request.counters)
        return self.run_repository.save(run)

    def get_run(self, run_id: str) -> AnalysisRunModel:
        return self.run_repository.get(run_id)

    def list_runs(self) -> list[AnalysisRunModel]:
        return self.run_repository.list_all()

    def store_result(self, run_id: str, request: StoreAnalysisResultRequest) -> AnalysisResultModel:
        run = self.run_repository.get(run_id)
        result = AnalysisResultModel(
            analysis_run_id=run.id,
            source_id=run.source_id,
            result_type=request.result_type,
            payload=request.payload,
            status=request.status.value,
        )
        return self.result_repository.create(result)

    def recover_stale_runs(self) -> list[AnalysisRunModel]:
        stale_runs = self.run_repository.list_by_statuses([AnalysisRunStatus.RUNNING.value, AnalysisRunStatus.PENDING.value])
        now = utcnow()
        updated: list[AnalysisRunModel] = []
        for run in stale_runs:
            run.status = AnalysisRunStatus.STALE.value
            if run.started_at is None:
                run.started_at = now
            run.finished_at = now
            run.error_text = run.error_text or "Recovered after restart"
            updated.append(self.run_repository.save(run))
        return updated

    def _apply_lifecycle_timestamps(self, run: AnalysisRunModel, target_status: AnalysisRunStatus) -> None:
        now = utcnow()
        if target_status == AnalysisRunStatus.RUNNING and run.started_at is None:
            run.started_at = now
            run.finished_at = None
        if target_status in {
            AnalysisRunStatus.COMPLETED,
            AnalysisRunStatus.FAILED,
            AnalysisRunStatus.CANCELLED,
            AnalysisRunStatus.STALE,
        }:
            if run.started_at is None:
                run.started_at = now
            run.finished_at = now

    @staticmethod
    def _apply_counters(run: AnalysisRunModel, counters: RunCounters | None) -> None:
        if counters is None:
            return
        run.file_count = counters.file_count
        run.success_count = counters.success_count
        run.error_count = counters.error_count
