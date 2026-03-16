from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import SourceModel
from app.domain.exceptions import ConflictError, NotFoundError


class SourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, source: SourceModel) -> SourceModel:
        self.session.add(source)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(f"source '{source.source_id}' already exists") from exc
        self.session.refresh(source)
        return source

    def get(self, source_id: str) -> SourceModel:
        source = self.session.get(SourceModel, source_id)
        if source is None:
            raise NotFoundError(f"source '{source_id}' not found")
        return source

    def list_all(self) -> list[SourceModel]:
        stmt = select(SourceModel).order_by(SourceModel.updated_at.desc())
        return list(self.session.scalars(stmt))

    def save(self, source: SourceModel) -> SourceModel:
        self.session.add(source)
        self.session.commit()
        self.session.refresh(source)
        return source
