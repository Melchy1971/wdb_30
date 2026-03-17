from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import Base, engine, SessionLocal
from app.routes import sources, import_runs, analysis_runs, analysis_results, export_candidates
from app.services.import_run_service import ImportRunService
from app.services.analysis_run_service import AnalysisRunService


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    # Tabellen anlegen (idempotent)
    Base.metadata.create_all(bind=engine)

    # Recovery: alle RUNNING-Runs → ABANDONED
    with SessionLocal() as db:
        recovered_imports = ImportRunService.recover_abandoned(db)
        if recovered_imports:
            print(
                f"[startup] {len(recovered_imports)} ImportRun(s) als ABANDONED markiert: "
                + ", ".join(r.id for r in recovered_imports)
            )

        recovered_analyses = AnalysisRunService.recover_abandoned(db)
        if recovered_analyses:
            print(
                f"[startup] {len(recovered_analyses)} AnalysisRun(s) als ABANDONED markiert: "
                + ", ".join(r.id for r in recovered_analyses)
            )

    yield
    # --- Shutdown ---


app = FastAPI(title="WDB Phase1 Backend", lifespan=lifespan)

app.include_router(sources.router,          prefix="/api/sources",          tags=["sources"])
app.include_router(import_runs.router,      prefix="/api/import-runs",      tags=["import-runs"])
app.include_router(analysis_runs.router,    prefix="/api/analysis-runs",    tags=["analysis-runs"])
app.include_router(analysis_results.router,   prefix="/api/analysis-results",  tags=["analysis-results"])
app.include_router(export_candidates.router,  prefix="/api/export-candidates",  tags=["export-candidates"])
