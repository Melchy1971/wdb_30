from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.dependencies import get_db
from app.models import ImportRunItemStatus, ImportRunStatus
from app.services.import_run_service import ImportRunService

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class ImportRunCreate(BaseModel):
    source_id: str


class ImportRunResponse(BaseModel):
    id:                     str
    source_id:              str
    status:                 ImportRunStatus
    started_at:             Optional[datetime]
    finished_at:            Optional[datetime]
    files_discovered_count: int
    files_processed_count:  int
    files_succeeded_count:  int
    files_failed_count:     int
    warning_count:          int
    error_count:            int
    last_error_code:        Optional[str]
    last_error_message:     Optional[str]
    cancel_requested:       bool
    restart_of_run_id:      Optional[str]
    created_at:             datetime
    updated_at:             datetime

    model_config = ConfigDict(from_attributes=True)


class ImportRunItemResponse(BaseModel):
    id:            str
    import_run_id: str
    path:          str
    relative_path: Optional[str]
    content_type:  Optional[str]
    file_extension: Optional[str]
    size_bytes:    Optional[int]
    content_hash:  Optional[str]
    parse_status:  ImportRunItemStatus
    discovered_at: datetime
    processed_at:  Optional[datetime]
    error_code:    Optional[str]
    error_message: Optional[str]
    created_at:    datetime
    updated_at:    datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Background-Task Ausführung (eigene Session — nicht die des Requests)
# ---------------------------------------------------------------------------

def _execute_in_background(run_id: str) -> None:
    """
    Läuft nach dem HTTP-Response-Return.
    Eigene Session, da die Request-Session nach Response geschlossen ist.
    """
    db = SessionLocal()
    try:
        ImportRunService(db).execute_run(run_id)
    except Exception:
        # Fehler werden im Service auf Run-Ebene persistiert;
        # hier kein weiterer Aufwand — Logging-Hook wäre Phase-2-Thema
        pass
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------

@router.post(
    "/",
    response_model=ImportRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="ImportRun starten",
    description=(
        "Legt einen neuen ImportRun an und startet den Scan asynchron im Hintergrund. "
        "Die Source muss zuvor erfolgreich validiert worden sein (status=VALID). "
        "Statusabfrage über GET /{run_id}."
    ),
)
def create_import_run(
    body: ImportRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ImportRunResponse:
    try:
        service = ImportRunService(db)
        run = service.create_run(body.source_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    background_tasks.add_task(_execute_in_background, run.id)
    return run


@router.get(
    "/",
    response_model=list[ImportRunResponse],
    summary="Alle ImportRuns auflisten",
)
def list_import_runs(
    source_id: Optional[str] = Query(default=None, description="Filter nach Source"),
    db: Session = Depends(get_db),
) -> list[ImportRunResponse]:
    return ImportRunService(db).list_runs(source_id=source_id)


@router.get(
    "/{run_id}",
    response_model=ImportRunResponse,
    summary="ImportRun-Status abrufen",
)
def get_import_run(run_id: str, db: Session = Depends(get_db)) -> ImportRunResponse:
    try:
        return ImportRunService(db).get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get(
    "/{run_id}/items",
    response_model=list[ImportRunItemResponse],
    summary="Items eines ImportRuns auflisten",
)
def list_items(
    run_id: str,
    item_status: Optional[ImportRunItemStatus] = Query(
        default=None, alias="status", description="Filter nach Item-Status"
    ),
    db: Session = Depends(get_db),
) -> list[ImportRunItemResponse]:
    try:
        return ImportRunService(db).list_items(run_id, status_filter=item_status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/{run_id}/cancel",
    response_model=ImportRunResponse,
    summary="ImportRun abbrechen",
    description=(
        "CREATED/QUEUED → sofort CANCELLED. "
        "RUNNING → cancel_requested=True; der laufende Job bricht beim nächsten Item ab."
    ),
)
def cancel_import_run(run_id: str, db: Session = Depends(get_db)) -> ImportRunResponse:
    try:
        return ImportRunService(db).cancel_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "/{run_id}/retry",
    response_model=ImportRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="ImportRun neu starten",
    description=(
        "Erzeugt einen neuen Run für dieselbe Source. "
        "Nur für terminale Runs (COMPLETED, PARTIALLY_COMPLETED, FAILED, CANCELLED, ABANDONED). "
        "Der neue Run referenziert den Original-Run über restart_of_run_id."
    ),
)
def retry_import_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ImportRunResponse:
    try:
        service = ImportRunService(db)
        new_run = service.retry_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    background_tasks.add_task(_execute_in_background, new_run.id)
    return new_run
