from fastapi import FastAPI
from .db import Base, engine
from .routes import sources, import_runs, analysis_runs, analysis_results

app = FastAPI(title="WDB Phase1 Backend")

Base.metadata.create_all(bind=engine)

app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
app.include_router(import_runs.router, prefix="/api/import-runs", tags=["import-runs"])
app.include_router(analysis_runs.router, prefix="/api/analysis-runs", tags=["analysis-runs"])
app.include_router(analysis_results.router, prefix="/api/analysis-results", tags=["analysis-results"])