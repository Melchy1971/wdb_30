from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Source, SourceValidationStatus
from app.services.source_validation_service import SourceValidationService

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class SourceCreate(BaseModel):
    display_name: str
    location_uri: str


class SourceUpdate(BaseModel):
    display_name: Optional[str] = None
    location_uri: Optional[str] = None


class SourceResponse(BaseModel):
    id: str
    display_name: str
    location_uri: str
    validation_status: SourceValidationStatus
    validation_message: Optional[str]
    last_validated_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------

def _get_or_404(db: Session, source_id: str) -> Source:
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' nicht gefunden",
        )
    return source


# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=list[SourceResponse],
    summary="Alle Sources auflisten",
)
def list_sources(db: Session = Depends(get_db)) -> list[Source]:
    return db.query(Source).order_by(Source.created_at.desc()).all()


@router.post(
    "/",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Source registrieren",
    description=(
        "Legt eine neue Source an. Der Validierungsstatus wird auf UNKNOWN gesetzt. "
        "Validierung erfolgt explizit über POST /{source_id}/validate."
    ),
)
def create_source(body: SourceCreate, db: Session = Depends(get_db)) -> Source:
    source = Source(
        id=str(uuid4()),
        display_name=body.display_name,
        location_uri=body.location_uri,
        validation_status=SourceValidationStatus.UNKNOWN,
        created_at=datetime.utcnow(),
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get(
    "/{source_id}",
    response_model=SourceResponse,
    summary="Einzelne Source abrufen",
)
def get_source(source_id: str, db: Session = Depends(get_db)) -> Source:
    return _get_or_404(db, source_id)


@router.patch(
    "/{source_id}",
    response_model=SourceResponse,
    summary="Source-Metadaten aktualisieren",
    description="Aktualisiert display_name und/oder location_uri. "
                "Setzt bei URI-Änderung den Validierungsstatus auf UNKNOWN zurück.",
)
def update_source(
    source_id: str,
    body: SourceUpdate,
    db: Session = Depends(get_db),
) -> Source:
    source = _get_or_404(db, source_id)

    if body.display_name is not None:
        source.display_name = body.display_name

    if body.location_uri is not None and body.location_uri != source.location_uri:
        source.location_uri = body.location_uri
        # Pfad hat sich geändert → bisherige Validierung ist ungültig
        source.validation_status  = SourceValidationStatus.UNKNOWN
        source.validation_message = "Pfad wurde geändert – erneute Validierung erforderlich"
        source.last_validated_at  = None

    db.commit()
    db.refresh(source)
    return source


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Source löschen",
)
def delete_source(source_id: str, db: Session = Depends(get_db)) -> None:
    source = _get_or_404(db, source_id)
    db.delete(source)
    db.commit()


@router.post(
    "/{source_id}/validate",
    response_model=SourceResponse,
    summary="Source serverseitig validieren",
    description=(
        "Prüft den lokalen Pfad auf Existenz, Lesbarkeit, Typ und unterstützte Dateitypen. "
        "Das Ergebnis wird persistent in validation_status und validation_message gespeichert."
    ),
)
def validate_source(source_id: str, db: Session = Depends(get_db)) -> Source:
    source = _get_or_404(db, source_id)
    service = SourceValidationService(db)
    return service.validate(source)
