from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.sources import (
    CreateSourceRequest,
    SourceResponse,
    SourceValidationResponse,
    UpdateSourceRequest,
)
from app.services.source_service import SourceService


router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(request: CreateSourceRequest, session: Session = Depends(get_session)) -> SourceResponse:
    source = SourceService(session).create_source(request)
    return SourceResponse.model_validate(source)


@router.get("", response_model=list[SourceResponse])
def list_sources(session: Session = Depends(get_session)) -> list[SourceResponse]:
    sources = SourceService(session).list_sources()
    return [SourceResponse.model_validate(source) for source in sources]


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(source_id: str, session: Session = Depends(get_session)) -> SourceResponse:
    source = SourceService(session).get_source(source_id)
    return SourceResponse.model_validate(source)


@router.patch("/{source_id}", response_model=SourceResponse)
def update_source(
    source_id: str,
    request: UpdateSourceRequest,
    session: Session = Depends(get_session),
) -> SourceResponse:
    source = SourceService(session).update_source(source_id, request)
    return SourceResponse.model_validate(source)


@router.post("/{source_id}/validate", response_model=SourceValidationResponse)
def validate_source(source_id: str, session: Session = Depends(get_session)) -> SourceValidationResponse:
    source = SourceService(session).validate_source(source_id)
    return SourceValidationResponse(
        source_id=source.source_id,
        validation_status=source.validation_status,
        validation_message=source.validation_message,
        last_validated_at=source.last_validated_at,
    )
