import pytest

from app.domain.enums import AnalysisRunStatus, ImportRunStatus
from app.domain.exceptions import InvalidTransitionError
from app.schemas.runs import (
    CreateAnalysisRunRequest,
    CreateImportRunRequest,
    RunCounters,
    StoreAnalysisResultRequest,
    UpdateAnalysisRunRequest,
    UpdateImportRunRequest,
)
from app.services.run_service import AnalysisRunService, ImportRunService


def test_import_run_creation_is_idempotent(session):
    service = ImportRunService(session)

    first = service.create_run(CreateImportRunRequest(source_id="source-a", idempotency_key="key-1"))
    second = service.create_run(CreateImportRunRequest(source_id="source-a", idempotency_key="key-1"))

    assert first.id == second.id
    assert first.status == ImportRunStatus.PENDING.value


def test_import_run_rejects_invalid_transition(session):
    service = ImportRunService(session)
    run = service.create_run(CreateImportRunRequest(source_id="source-a"))

    with pytest.raises(InvalidTransitionError):
        service.update_run(
            run.id,
            UpdateImportRunRequest(
                status=ImportRunStatus.COMPLETED,
                counters=RunCounters(file_count=4, success_count=4, error_count=0),
            ),
        )


def test_import_run_recovery_marks_pending_or_running_as_stale(session):
    service = ImportRunService(session)
    pending = service.create_run(CreateImportRunRequest(source_id="source-a"))
    running = service.create_run(CreateImportRunRequest(source_id="source-b"))
    service.update_run(running.id, UpdateImportRunRequest(status=ImportRunStatus.RUNNING))

    recovered = service.recover_stale_runs()

    recovered_ids = {run.id for run in recovered}
    assert pending.id in recovered_ids
    assert running.id in recovered_ids
    assert service.get_run(pending.id).status == ImportRunStatus.STALE.value
    assert service.get_run(running.id).finished_at is not None


def test_analysis_result_is_persisted_separately_from_run(session):
    service = AnalysisRunService(session)
    run = service.create_run(CreateAnalysisRunRequest(source_id="source-a", idempotency_key="analysis-1"))
    service.update_run(run.id, UpdateAnalysisRunRequest(status=AnalysisRunStatus.RUNNING))

    result = service.store_result(
        run.id,
        StoreAnalysisResultRequest(result_type="entity-extraction", payload={"entities": ["Alpha"]}),
    )
    updated = service.update_run(
        run.id,
        UpdateAnalysisRunRequest(
            status=AnalysisRunStatus.COMPLETED,
            counters=RunCounters(file_count=1, success_count=1, error_count=0),
        ),
    )

    assert result.analysis_run_id == run.id
    assert result.source_id == run.source_id
    assert updated.status == AnalysisRunStatus.COMPLETED.value
    assert len(service.get_run(run.id).results) == 1
    assert service.get_run(run.id).results[0].payload["entities"] == ["Alpha"]
