from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import ExportCandidateStatus
from app.services.review_service import ReviewService

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Schema
# ---------------------------------------------------------------------------

class ExportCandidateResponse(BaseModel):
    """
    Repräsentation des technischen Export-Gates für ein AnalysisResult.

    export_status-Werte:
      NOT_ELIGIBLE  → review_status ist UNREVIEWED, REJECTED oder SUPERSEDED
      BLOCKED       → review_status ist APPROVED, aber normalized_output_json fehlt
      ELIGIBLE      → bereit für Export (APPROVED + normalized vorhanden)
      EXPORTED      → Phase 2: erfolgreich nach Neo4j übertragen
      EXPORT_FAILED → Phase 2: Übertragung fehlgeschlagen

    eligible_at ist unveränderlich nach erstmaliger ELIGIBLE-Setzung.
    Dient als Sortierkriterium für die Export-Reihenfolge in Phase 2.
    """
    id:                 str
    analysis_result_id: str
    export_status:      ExportCandidateStatus
    eligible_at:        Optional[datetime]
    blocked_reason:     Optional[str]
    created_at:         datetime
    updated_at:         datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=list[ExportCandidateResponse],
    summary="Export-Kandidaten auflisten",
    description=(
        "Listet lokal vorbereitete Export-Kandidaten. "
        "Nur Results, die mindestens einmal reviewed wurden, erscheinen hier. "
        "Filter nach export_status, import_run_id oder source_id möglich. "
        "Kein Neo4j-Write in diesem Endpunkt — reine Leseoperation."
    ),
)
def list_export_candidates(
    export_status:  Optional[ExportCandidateStatus] = Query(
        default=None, description="Filter nach Export-Status"
    ),
    import_run_id:  Optional[str] = Query(
        default=None, description="Filter nach ImportRun"
    ),
    source_id:      Optional[str] = Query(
        default=None, description="Filter nach Source"
    ),
    db: Session = Depends(get_db),
) -> list[ExportCandidateResponse]:
    return ReviewService(db).list_export_candidates(
        export_status=export_status,
        import_run_id=import_run_id,
        source_id=source_id,
    )


@router.get(
    "/{result_id}",
    response_model=ExportCandidateResponse,
    summary="Export-Kandidat für ein AnalysisResult abrufen",
)
def get_export_candidate(
    result_id: str,
    db: Session = Depends(get_db),
) -> ExportCandidateResponse:
    try:
        return ReviewService(db).get_export_candidate(result_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
