from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.api.error_handlers import register_error_handlers
from app.api.routes.analysis_runs import router as analysis_runs_router
from app.api.routes.import_runs import router as import_runs_router
from app.core.config import get_settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.services.run_service import AnalysisRunService, ImportRunService


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as session:
        _recover_runs(session)
    yield


def _recover_runs(session: Session) -> None:
    ImportRunService(session).recover_stale_runs()
    AnalysisRunService(session).recover_stale_runs()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(import_runs_router)
    app.include_router(analysis_runs_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
