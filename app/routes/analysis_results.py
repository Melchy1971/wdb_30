from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import ReviewStatus
from app.services.analysis_run_service import AnalysisRunService
from app.services.review_service import ReviewService

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class ReviewUpdate(BaseModel):
    review_status: ReviewStatus
    changed_by:    Optional[str] = None
    comment:       Optional[str] = None
    reason_code:   Optional[str] = None


class ReviewEventResponse(BaseModel):
    id:                     str
    analysis_result_id:     str
    previous_review_status: Optional[ReviewStatus]
    new_review_status:      ReviewStatus
    changed_by:             Optional[str]
    changed_at:             datetime
    comment:                Optional[str]
    reason_code:            Optional[str]

    model_config = ConfigDict(from_attributes=True)


class AnalysisResultResponse(BaseModel):
    id:                     str
    analysis_run_id:        str
    import_run_item_id:     str
    result_type:            str
    review_status:          ReviewStatus
    schema_version:         str
    input_hash:             Optional[str]
    raw_output_json:        dict[str, Any]
    normalized_output_json: Optional[dict[str, Any]]
    confidence_score:       Optional[str]
    provider:               str
    provider_model:         str
    generated_at:           datetime
    approved_at:            Optional[datetime]
    approved_by:            Optional[str]
    supersedes_result_id:   Optional[str]
    created_at:             datetime
    updated_at:             datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------

@router.get(
    "/{result_id}",
    response_model=AnalysisResultResponse,
    summary="Einzelnes AnalysisResult abrufen",
)
def get_result(result_id: str, db: Session = Depends(get_db)) -> AnalysisResultResponse:
    try:
        return AnalysisRunService(db).get_result(result_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post(
    "/{result_id}/review",
    response_model=AnalysisResultResponse,
    summary="Review-Status setzen",
    description=(
        "Ändert den Review-Status eines AnalysisResults und schreibt einen unveränderlichen "
        "ReviewEvent ins Audit-Log. Erlaubte Übergänge: UNREVIEWED↔APPROVED, "
        "UNREVIEWED↔REJECTED, APPROVED↔REJECTED. "
        "SUPERSEDED kann nicht manuell gesetzt werden — wird automatisch durch Retry gesetzt."
    ),
)
def review_result(
    result_id: str,
    body: ReviewUpdate,
    db: Session = Depends(get_db),
) -> AnalysisResultResponse:
    if body.review_status == ReviewStatus.SUPERSEDED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "SUPERSEDED kann nicht manuell gesetzt werden — "
                "wird automatisch durch einen Retry-Run gesetzt."
            ),
        )
    try:
        return ReviewService(db).set_review_status(
            result_id=result_id,
            new_status=body.review_status,
            changed_by=body.changed_by,
            comment=body.comment,
            reason_code=body.reason_code,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "/{result_id}/history",
    response_model=list[ReviewEventResponse],
    summary="Review-Historie abrufen",
    description=(
        "Gibt alle ReviewEvents für ein AnalysisResult chronologisch zurück. "
        "Enthält sowohl manuelle Review-Entscheidungen (changed_by=Nutzer) als auch "
        "systemseitige Ereignisse wie Supersession durch Retry (changed_by=null, "
        "reason_code=SUPERSEDED_BY_RETRY)."
    ),
)
def get_result_history(
    result_id: str,
    db: Session = Depends(get_db),
) -> list[ReviewEventResponse]:
    try:
        return ReviewService(db).get_history(result_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
