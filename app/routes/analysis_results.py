from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from uuid import uuid4

from app.dependencies import get_db
from app.models import AnalysisResult, AnalysisRun, ReviewStatus

router = APIRouter()


# ---------- Schemas ----------

class AnalysisResultCreate(BaseModel):
    analysis_run_id: str
    payload: dict[str, Any]


class ReviewUpdate(BaseModel):
    review_status: ReviewStatus


class AnalysisResultResponse(BaseModel):
    id: str
    analysis_run_id: str
    payload: dict[str, Any]
    review_status: ReviewStatus

    model_config = ConfigDict(from_attributes=True)


# ---------- Routes ----------

@router.get("/", response_model=list[AnalysisResultResponse])
def list_results(analysis_run_id: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(AnalysisResult)
    if analysis_run_id:
        q = q.filter(AnalysisResult.analysis_run_id == analysis_run_id)
    return q.all()


@router.post("/", response_model=AnalysisResultResponse, status_code=status.HTTP_201_CREATED)
def create_result(body: AnalysisResultCreate, db: Session = Depends(get_db)):
    run = db.query(AnalysisRun).filter(AnalysisRun.id == body.analysis_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"AnalysisRun '{body.analysis_run_id}' nicht gefunden")

    result = AnalysisResult(
        id=str(uuid4()),
        analysis_run_id=body.analysis_run_id,
        payload=body.payload,
        review_status=ReviewStatus.UNREVIEWED,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


@router.get("/{result_id}", response_model=AnalysisResultResponse)
def get_result(result_id: str, db: Session = Depends(get_db)):
    result = db.query(AnalysisResult).filter(AnalysisResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail=f"AnalysisResult '{result_id}' nicht gefunden")
    return result


@router.patch("/{result_id}/review", response_model=AnalysisResultResponse)
def review_result(result_id: str, body: ReviewUpdate, db: Session = Depends(get_db)):
    result = db.query(AnalysisResult).filter(AnalysisResult.id == result_id).first()
    if not result:
        raise HTTPException(status_code=404, detail=f"AnalysisResult '{result_id}' nicht gefunden")
    result.review_status = body.review_status
    db.commit()
    db.refresh(result)
    return result
