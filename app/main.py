from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import Base, engine, SessionLocal
from app.routes import sources, import_runs, analysis_runs, analysis_results
from app.services.import_run_service import ImportRunService


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    # Tabellen anlegen (idempotent)
    Base.metadata.create_all(bind=engine)

    # Recovery: alle RUNNING-Runs → ABANDONED
    with SessionLocal() as db:
        recovered = ImportRunService.recover_abandoned(db)
        if recovered:
            print(
                f"[startup] {len(recovered)} ImportRun(s) als ABANDONED markiert: "
                + ", ".join(r.id for r in recovered)
            )

    yield
    # --- Shutdown ---


app = FastAPI(title="WDB Phase1 Backend", lifespan=lifespan)

app.include_router(sources.router,          prefix="/api/sources",          tags=["sources"])
app.include_router(import_runs.router,      prefix="/api/import-runs",      tags=["import-runs"])
app.include_router(analysis_runs.router,    prefix="/api/analysis-runs",    tags=["analysis-runs"])
app.include_router(analysis_results.router, prefix="/api/analysis-results", tags=["analysis-results"])
