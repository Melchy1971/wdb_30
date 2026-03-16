from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import SourceModel
from app.domain.enums import SourceSystem, SourceValidationStatus
from app.domain.exceptions import SourceValidationError, ValidationErrorCode
from app.repositories.source_repository import SourceRepository
from app.schemas.sources import CreateSourceRequest, UpdateSourceRequest


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceService:
    def __init__(self, session: Session) -> None:
        self.repository = SourceRepository(session)
        self.settings = get_settings()

    def create_source(self, request: CreateSourceRequest) -> SourceModel:
        source = SourceModel(
            source_id=request.source_id,
            display_name=request.display_name,
            source_system=request.source_system.value,
            location_uri=request.location_uri,
            is_active=request.is_active,
            validation_status=SourceValidationStatus.PENDING.value,
        )
        return self.repository.create(source)

    def update_source(self, source_id: str, request: UpdateSourceRequest) -> SourceModel:
        source = self.repository.get(source_id)
        if request.display_name is not None:
            source.display_name = request.display_name
        if request.location_uri is not None:
            source.location_uri = request.location_uri
        if request.is_active is not None:
            source.is_active = request.is_active
        if request.location_uri is not None or request.is_active is not None:
            source.validation_status = SourceValidationStatus.PENDING.value
            source.validation_message = None
            source.last_validated_at = None
        return self.repository.save(source)

    def get_source(self, source_id: str) -> SourceModel:
        return self.repository.get(source_id)

    def list_sources(self) -> list[SourceModel]:
        return self.repository.list_all()

    def validate_source(self, source_id: str) -> SourceModel:
        source = self.repository.get(source_id)
        now = utcnow()
        try:
            self._validate_local_source(source)
        except SourceValidationError as exc:
            source.validation_status = (
                SourceValidationStatus.INACTIVE.value
                if exc.code == ValidationErrorCode.SOURCE_INACTIVE
                else SourceValidationStatus.INVALID.value
            )
            source.validation_message = exc.message
            source.last_validated_at = now
            return self.repository.save(source)

        source.validation_status = SourceValidationStatus.VALID.value
        source.validation_message = "Source validation succeeded"
        source.last_validated_at = now
        return self.repository.save(source)

    def _validate_local_source(self, source: SourceModel) -> None:
        if SourceSystem(source.source_system) is not SourceSystem.LOCAL:
            raise SourceValidationError(
                ValidationErrorCode.LOCATION_UNSUPPORTED_TYPE,
                f"Unsupported source system '{source.source_system}'",
            )
        if not source.is_active:
            raise SourceValidationError(
                ValidationErrorCode.SOURCE_INACTIVE,
                "Source is inactive and cannot be validated",
            )
        if not source.location_uri.strip():
            raise SourceValidationError(
                ValidationErrorCode.LOCATION_MISSING,
                "Source location is missing",
            )

        path = Path(source.location_uri).expanduser()
        if not path.exists():
            raise SourceValidationError(
                ValidationErrorCode.LOCATION_NOT_FOUND,
                f"Path does not exist: {source.location_uri}",
            )
        if not self._is_readable(path):
            raise SourceValidationError(
                ValidationErrorCode.LOCATION_NOT_READABLE,
                f"Path is not readable: {source.location_uri}",
            )

        supported = {ext.lower() for ext in self.settings.supported_source_extensions}
        if path.is_file():
            if path.suffix.lower() not in supported:
                raise SourceValidationError(
                    ValidationErrorCode.LOCATION_UNSUPPORTED_TYPE,
                    f"Unsupported file type: {path.suffix or '<none>'}",
                )
            return
        if path.is_dir():
            matching_files = [
                child for child in path.iterdir() if child.is_file() and child.suffix.lower() in supported
            ]
            if not matching_files:
                raise SourceValidationError(
                    ValidationErrorCode.LOCATION_EMPTY_UNSUPPORTED,
                    "Directory does not contain supported file types",
                )
            return

        raise SourceValidationError(
            ValidationErrorCode.LOCATION_UNSUPPORTED_TYPE,
            "Path is neither a regular file nor a directory",
        )

    @staticmethod
    def _is_readable(path: Path) -> bool:
        try:
            if path.is_dir():
                next(path.iterdir(), None)
                return True
            with path.open("rb") as handle:
                handle.read(1)
            return True
        except (OSError, PermissionError):
            return False
