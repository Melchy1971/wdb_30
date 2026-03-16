from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.runs import CreateImportRunRequest, ImportRunResponse, UpdateImportRunRequest
from app.services.run_service import ImportRunService


router = APIRouter(prefix="/import-runs", tags=["import-runs"])


@router.post("", response_model=ImportRunResponse, status_code=status.HTTP_201_CREATED)
def create_import_run(request: CreateImportRunRequest, session: Session = Depends(get_session)) -> ImportRunResponse:
    run = ImportRunService(session).create_run(request)
    return ImportRunResponse.model_validate(run)


@router.get("", response_model=list[ImportRunResponse])
def list_import_runs(session: Session = Depends(get_session)) -> list[ImportRunResponse]:
    runs = ImportRunService(session).list_runs()
    return [ImportRunResponse.model_validate(run) for run in runs]


@router.get("/{run_id}", response_model=ImportRunResponse)
def get_import_run(run_id: str, session: Session = Depends(get_session)) -> ImportRunResponse:
    run = ImportRunService(session).get_run(run_id)
    return ImportRunResponse.model_validate(run)


@router.patch("/{run_id}", response_model=ImportRunResponse)
def update_import_run(
    run_id: str,
    request: UpdateImportRunRequest,
    session: Session = Depends(get_session),
) -> ImportRunResponse:
    run = ImportRunService(session).update_run(run_id, request)
    return ImportRunResponse.model_validate(run)
