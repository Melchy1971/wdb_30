from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import AnalysisResultModel, AnalysisRunModel, ImportRunModel
from app.domain.exceptions import ConflictError, NotFoundError


class ImportRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, run: ImportRunModel) -> ImportRunModel:
        self.session.add(run)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("import run idempotency conflict") from exc
        self.session.refresh(run)
        return run

    def get(self, run_id: str) -> ImportRunModel:
        run = self.session.get(ImportRunModel, run_id)
        if run is None:
            raise NotFoundError(f"import run '{run_id}' not found")
        return run

    def get_by_idempotency(self, source_id: str, idempotency_key: str) -> ImportRunModel | None:
        stmt = select(ImportRunModel).where(
            ImportRunModel.source_id == source_id,
            ImportRunModel.idempotency_key == idempotency_key,
        )
        return self.session.scalar(stmt)

    def list_all(self) -> list[ImportRunModel]:
        stmt = select(ImportRunModel).order_by(ImportRunModel.created_at.desc())
        return list(self.session.scalars(stmt))

    def list_by_statuses(self, statuses: Iterable[str]) -> list[ImportRunModel]:
        stmt = select(ImportRunModel).where(ImportRunModel.status.in_(list(statuses)))
        return list(self.session.scalars(stmt))

    def save(self, run: ImportRunModel) -> ImportRunModel:
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run


class AnalysisRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, run: AnalysisRunModel) -> AnalysisRunModel:
        self.session.add(run)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("analysis run idempotency conflict") from exc
        self.session.refresh(run)
        return run

    def get(self, run_id: str) -> AnalysisRunModel:
        stmt = (
            select(AnalysisRunModel)
            .options(selectinload(AnalysisRunModel.results))
            .where(AnalysisRunModel.id == run_id)
        )
        run = self.session.scalar(stmt)
        if run is None:
            raise NotFoundError(f"analysis run '{run_id}' not found")
        return run

    def get_by_idempotency(self, source_id: str, idempotency_key: str) -> AnalysisRunModel | None:
        stmt = select(AnalysisRunModel).where(
            AnalysisRunModel.source_id == source_id,
            AnalysisRunModel.idempotency_key == idempotency_key,
        )
        return self.session.scalar(stmt)

    def list_all(self) -> list[AnalysisRunModel]:
        stmt = (
            select(AnalysisRunModel)
            .options(selectinload(AnalysisRunModel.results))
            .order_by(AnalysisRunModel.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def list_by_statuses(self, statuses: Iterable[str]) -> list[AnalysisRunModel]:
        stmt = select(AnalysisRunModel).where(AnalysisRunModel.status.in_(list(statuses)))
        return list(self.session.scalars(stmt))

    def save(self, run: AnalysisRunModel) -> AnalysisRunModel:
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run


class AnalysisResultRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, result: AnalysisResultModel) -> AnalysisResultModel:
        self.session.add(result)
        self.session.commit()
        self.session.refresh(result)
        return result

    def list_for_run(self, run_id: str) -> list[AnalysisResultModel]:
        stmt = (
            select(AnalysisResultModel)
            .where(AnalysisResultModel.analysis_run_id == run_id)
            .order_by(AnalysisResultModel.created_at.asc())
        )
        return list(self.session.scalars(stmt))
