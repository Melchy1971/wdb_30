from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from datetime import datetime
import enum
from .db import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SourceValidationStatus(str, enum.Enum):
    UNKNOWN      = "UNKNOWN"
    VALID        = "VALID"
    INVALID      = "INVALID"
    INACCESSIBLE = "INACCESSIBLE"


class ImportRunStatus(str, enum.Enum):
    CREATED              = "CREATED"       # angelegt, noch nicht gestartet
    QUEUED               = "QUEUED"        # bereit zur Ausführung
    RUNNING              = "RUNNING"       # Scan läuft aktiv
    COMPLETED            = "COMPLETED"     # alle Dateien erfolgreich
    PARTIALLY_COMPLETED  = "PARTIALLY_COMPLETED"  # mindestens ein Item fehlgeschlagen
    FAILED               = "FAILED"        # Run selbst fehlgeschlagen (kein Item verarbeitbar)
    CANCELLED            = "CANCELLED"     # kooperativ abgebrochen
    ABANDONED            = "ABANDONED"     # Prozess abgebrochen; Recovery beim Neustart


class ImportRunItemStatus(str, enum.Enum):
    DISCOVERED  = "DISCOVERED"   # gefunden, noch nicht verarbeitet
    PROCESSING  = "PROCESSING"   # wird gerade verarbeitet
    SUCCEEDED   = "SUCCEEDED"    # erfolgreich verarbeitet
    FAILED      = "FAILED"       # Fehler bei Verarbeitung
    SKIPPED     = "SKIPPED"      # explizit übersprungen (z. B. Duplikat)


# Für AnalysisRun und AnalysisResult — unveränderter Bestand
class RunStatus(str, enum.Enum):
    CREATED              = "CREATED"
    QUEUED               = "QUEUED"
    RUNNING              = "RUNNING"
    COMPLETED            = "COMPLETED"
    FAILED               = "FAILED"
    PARTIALLY_COMPLETED  = "PARTIALLY_COMPLETED"
    ABANDONED            = "ABANDONED"


class ReviewStatus(str, enum.Enum):
    UNREVIEWED = "UNREVIEWED"
    APPROVED   = "APPROVED"
    REJECTED   = "REJECTED"


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

class Source(Base):
    __tablename__ = "sources"

    id                 = Column(String, primary_key=True)
    display_name       = Column(String, nullable=False)
    location_uri       = Column(String, nullable=False)
    validation_status  = Column(Enum(SourceValidationStatus), nullable=False,
                                default=SourceValidationStatus.UNKNOWN)
    validation_message = Column(Text, nullable=True)
    last_validated_at  = Column(DateTime, nullable=True)
    created_at         = Column(DateTime, nullable=False, default=datetime.utcnow)


class ImportRun(Base):
    __tablename__ = "import_runs"

    id                     = Column(String, primary_key=True)
    source_id              = Column(String, ForeignKey("sources.id"), nullable=False)
    status                 = Column(Enum(ImportRunStatus), nullable=False,
                                    default=ImportRunStatus.CREATED)
    # Lifecycle-Timestamps
    started_at             = Column(DateTime, nullable=True)
    finished_at            = Column(DateTime, nullable=True)
    # Counters — werden laufend aggregiert
    files_discovered_count = Column(Integer, nullable=False, default=0)
    files_processed_count  = Column(Integer, nullable=False, default=0)
    files_succeeded_count  = Column(Integer, nullable=False, default=0)
    files_failed_count     = Column(Integer, nullable=False, default=0)
    warning_count          = Column(Integer, nullable=False, default=0)
    error_count            = Column(Integer, nullable=False, default=0)
    # Letzter Fehler auf Run-Ebene
    last_error_code        = Column(String, nullable=True)
    last_error_message     = Column(Text, nullable=True)
    # Kooperativer Abbruch
    cancel_requested       = Column(Boolean, nullable=False, default=False)
    # Retry-Referenz
    restart_of_run_id      = Column(String, nullable=True)
    # Metadaten
    created_at             = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at             = Column(DateTime, nullable=False, default=datetime.utcnow)


class ImportRunItem(Base):
    __tablename__ = "import_run_items"

    id              = Column(String, primary_key=True)
    import_run_id   = Column(String, ForeignKey("import_runs.id"), nullable=False)
    # Dateipfade
    path            = Column(String, nullable=False)
    relative_path   = Column(String, nullable=True)
    # Dateimetadaten
    content_type    = Column(String, nullable=True)
    file_extension  = Column(String, nullable=True)
    size_bytes      = Column(Integer, nullable=True)
    content_hash    = Column(String, nullable=True)   # SHA-256
    # Verarbeitungsstatus
    parse_status    = Column(Enum(ImportRunItemStatus), nullable=False,
                             default=ImportRunItemStatus.DISCOVERED)
    # Zeitstempel
    discovered_at   = Column(DateTime, nullable=False, default=datetime.utcnow)
    processed_at    = Column(DateTime, nullable=True)
    # Fehlerinformation
    error_code      = Column(String, nullable=True)
    error_message   = Column(Text, nullable=True)
    # Metadaten
    created_at      = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at      = Column(DateTime, nullable=False, default=datetime.utcnow)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id            = Column(String, primary_key=True)
    import_run_id = Column(String, ForeignKey("import_runs.id"), nullable=False)
    status        = Column(Enum(RunStatus), nullable=False)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id              = Column(String, primary_key=True)
    analysis_run_id = Column(String, ForeignKey("analysis_runs.id"), nullable=False)
    payload         = Column(JSON, nullable=True)
    review_status   = Column(Enum(ReviewStatus), nullable=False,
                             default=ReviewStatus.UNREVIEWED)
