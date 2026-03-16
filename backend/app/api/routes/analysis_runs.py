from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.runs import (
    AnalysisResultResponse,
    AnalysisRunResponse,
    CreateAnalysisRunRequest,
    StoreAnalysisResultRequest,
    UpdateAnalysisRunRequest,
)
from app.services.run_service import AnalysisRunService


router = APIRouter(prefix="/analysis-runs", tags=["analysis-runs"])


@router.post("", response_model=AnalysisRunResponse, status_code=status.HTTP_201_CREATED)
def create_analysis_run(
    request: CreateAnalysisRunRequest,
    session: Session = Depends(get_session),
) -> AnalysisRunResponse:
    run = AnalysisRunService(session).create_run(request)
    return AnalysisRunResponse.model_validate(run)


@router.get("", response_model=list[AnalysisRunResponse])
def list_analysis_runs(session: Session = Depends(get_session)) -> list[AnalysisRunResponse]:
    runs = AnalysisRunService(session).list_runs()
    return [AnalysisRunResponse.model_validate(run) for run in runs]


@router.get("/{run_id}", response_model=AnalysisRunResponse)
def get_analysis_run(run_id: str, session: Session = Depends(get_session)) -> AnalysisRunResponse:
    run = AnalysisRunService(session).get_run(run_id)
    return AnalysisRunResponse.model_validate(run)


@router.patch("/{run_id}", response_model=AnalysisRunResponse)
def update_analysis_run(
    run_id: str,
    request: UpdateAnalysisRunRequest,
    session: Session = Depends(get_session),
) -> AnalysisRunResponse:
    run = AnalysisRunService(session).update_run(run_id, request)
    return AnalysisRunResponse.model_validate(run)


@router.post("/{run_id}/results", response_model=AnalysisResultResponse, status_code=status.HTTP_201_CREATED)
def store_analysis_result(
    run_id: str,
    request: StoreAnalysisResultRequest,
    session: Session = Depends(get_session),
) -> AnalysisResultResponse:
    result = AnalysisRunService(session).store_result(run_id, request)
    return AnalysisResultResponse.model_validate(result)
