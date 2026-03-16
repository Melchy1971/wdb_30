from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, JSON
from datetime import datetime
import enum
from .db import Base

class RunStatus(str, enum.Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    ABANDONED = "ABANDONED"

class ReviewStatus(str, enum.Enum):
    UNREVIEWED = "UNREVIEWED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class Source(Base):
    __tablename__ = "sources"
    id = Column(String, primary_key=True)
    display_name = Column(String)
    location_uri = Column(String)
    validation_status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class ImportRun(Base):
    __tablename__ = "import_runs"
    id = Column(String, primary_key=True)
    source_id = Column(String, ForeignKey("sources.id"))
    status = Column(Enum(RunStatus))
    started_at = Column(DateTime)
    finished_at = Column(DateTime)

class ImportRunItem(Base):
    __tablename__ = "import_run_items"
    id = Column(String, primary_key=True)
    import_run_id = Column(String, ForeignKey("import_runs.id"))
    path = Column(String)
    status = Column(String)
    error_message = Column(String)

class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id = Column(String, primary_key=True)
    import_run_id = Column(String)
    status = Column(Enum(RunStatus))

class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id = Column(String, primary_key=True)
    analysis_run_id = Column(String)
    payload = Column(JSON)
    review_status = Column(Enum(ReviewStatus))