from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import uuid4

from app.dependencies import get_db
from app.models import AnalysisRun, ImportRun, RunStatus

router = APIRouter()


# ---------- Schemas ----------

class AnalysisRunCreate(BaseModel):
    import_run_id: str


class AnalysisRunStatusUpdate(BaseModel):
    status: RunStatus


class AnalysisRunResponse(BaseModel):
    id: str
    import_run_id: str
    status: RunStatus

    model_config = ConfigDict(from_attributes=True)


# ---------- Routes ----------

@router.get("/", response_model=list[AnalysisRunResponse])
def list_analysis_runs(db: Session = Depends(get_db)):
    return db.query(AnalysisRun).all()


@router.post("/", response_model=AnalysisRunResponse, status_code=status.HTTP_201_CREATED)
def create_analysis_run(body: AnalysisRunCreate, db: Session = Depends(get_db)):
    import_run = db.query(ImportRun).filter(ImportRun.id == body.import_run_id).first()
    if not import_run:
        raise HTTPException(status_code=404, detail=f"ImportRun '{body.import_run_id}' nicht gefunden")

    terminal = {RunStatus.COMPLETED, RunStatus.PARTIALLY_COMPLETED, RunStatus.FAILED, RunStatus.ABANDONED}
    if import_run.status not in terminal:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"ImportRun hat Status '{import_run.status}' — muss abgeschlossen sein",
        )

    run = AnalysisRun(
        id=str(uuid4()),
        import_run_id=body.import_run_id,
        status=RunStatus.CREATED,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.get("/{run_id}", response_model=AnalysisRunResponse)
def get_analysis_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"AnalysisRun '{run_id}' nicht gefunden")
    return run


@router.patch("/{run_id}/status", response_model=AnalysisRunResponse)
def update_analysis_run_status(run_id: str, body: AnalysisRunStatusUpdate, db: Session = Depends(get_db)):
    run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"AnalysisRun '{run_id}' nicht gefunden")
    run.status = body.status
    db.commit()
    db.refresh(run)
    return run
