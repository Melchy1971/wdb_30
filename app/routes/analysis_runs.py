from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.dependencies import get_db
from app.models import AnalysisRunStatus, ReviewStatus
from app.routes.analysis_results import AnalysisResultResponse
from app.services.analysis_run_service import AnalysisRunService

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class AnalysisRunCreate(BaseModel):
    import_run_id:  str
    provider:       str = "stub"
    provider_model: str = "none"
    result_type:    str = "ANALYSIS"


class AnalysisRunResponse(BaseModel):
    id:                        str
    import_run_id:             str
    source_id:                 Optional[str]
    provider:                  str
    provider_model:            str
    status:                    AnalysisRunStatus
    started_at:                Optional[datetime]
    finished_at:               Optional[datetime]
    documents_targeted_count:  int
    documents_analyzed_count:  int
    documents_succeeded_count: int
    documents_failed_count:    int
    warning_count:             int
    error_count:               int
    last_error_code:           Optional[str]
    last_error_message:        Optional[str]
    restart_of_run_id:         Optional[str]
    created_at:                datetime
    updated_at:                datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Background-Task Ausführung (eigene Session)
# ---------------------------------------------------------------------------

def _execute_in_background(run_id: str, result_type: str) -> None:
    """
    Läuft nach dem HTTP-Response-Return.
    Eigene Session, da die Request-Session nach Response geschlossen ist.
    """
    db = SessionLocal()
    try:
        AnalysisRunService(db).execute_run(run_id, result_type=result_type)
    except Exception:
        pass
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------

@router.post(
    "/",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="AnalysisRun starten",
    description=(
        "Legt einen neuen AnalysisRun an und startet die Analyse asynchron. "
        "Der ImportRun muss COMPLETED oder PARTIALLY_COMPLETED sein. "
        "provider und provider_model sind in Phase 1 optionale Stub-Werte."
    ),
)
def create_analysis_run(
    body: AnalysisRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AnalysisRunResponse:
    try:
        service = AnalysisRunService(db)
        run = service.create_run(
            import_run_id=body.import_run_id,
            provider=body.provider,
            provider_model=body.provider_model,
            result_type=body.result_type,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    background_tasks.add_task(_execute_in_background, run.id, body.result_type)
    return run


@router.get(
    "/",
    response_model=list[AnalysisRunResponse],
    summary="Alle AnalysisRuns auflisten",
)
def list_analysis_runs(
    import_run_id: Optional[str] = Query(default=None, description="Filter nach ImportRun"),
    source_id:     Optional[str] = Query(default=None, description="Filter nach Source"),
    db: Session = Depends(get_db),
) -> list[AnalysisRunResponse]:
    return AnalysisRunService(db).list_runs(
        import_run_id=import_run_id,
        source_id=source_id,
    )


@router.get(
    "/{run_id}",
    response_model=AnalysisRunResponse,
    summary="AnalysisRun-Status abrufen",
)
def get_analysis_run(run_id: str, db: Session = Depends(get_db)) -> AnalysisRunResponse:
    try:
        return AnalysisRunService(db).get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get(
    "/{run_id}/results",
    response_model=list[AnalysisResultResponse],
    summary="Results eines AnalysisRuns auflisten",
)
def list_run_results(
    run_id: str,
    review_status: Optional[ReviewStatus] = Query(
        default=None, alias="status", description="Filter nach Review-Status"
    ),
    db: Session = Depends(get_db),
) -> list[AnalysisResultResponse]:
    try:
        return AnalysisRunService(db).list_results(run_id, review_status=review_status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/{run_id}/cancel",
    response_model=AnalysisRunResponse,
    summary="AnalysisRun abbrechen",
)
def cancel_analysis_run(run_id: str, db: Session = Depends(get_db)) -> AnalysisRunResponse:
    try:
        return AnalysisRunService(db).cancel_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/{run_id}/retry",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="AnalysisRun wiederholen",
    description=(
        "Erzeugt einen neuen Run für denselben ImportRun. "
        "Nur für terminale Runs (COMPLETED, PARTIALLY_COMPLETED, FAILED, CANCELLED, ABANDONED). "
        "Bestehende unreviewed Results werden beim Ausführen auf SUPERSEDED gesetzt."
    ),
)
def retry_analysis_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    result_type: str = Query(default="ANALYSIS", description="Result-Typ für den neuen Run"),
    db: Session = Depends(get_db),
) -> AnalysisRunResponse:
    try:
        service = AnalysisRunService(db)
        new_run = service.retry_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    background_tasks.add_task(_execute_in_background, new_run.id, result_type)
    return new_run

