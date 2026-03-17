from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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


class AnalysisRunStatus(str, enum.Enum):
    CREATED             = "CREATED"
    QUEUED              = "QUEUED"
    RUNNING             = "RUNNING"
    COMPLETED           = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED              = "FAILED"
    CANCELLED           = "CANCELLED"
    ABANDONED           = "ABANDONED"


class ReviewStatus(str, enum.Enum):
    UNREVIEWED = "UNREVIEWED"
    APPROVED   = "APPROVED"
    REJECTED   = "REJECTED"
    SUPERSEDED = "SUPERSEDED"   # automatisch gesetzt, wenn ein neueres Result dieses ersetzt


class ExportCandidateStatus(str, enum.Enum):
    NOT_ELIGIBLE  = "NOT_ELIGIBLE"   # nicht freigegeben, abgelehnt oder superseded
    ELIGIBLE      = "ELIGIBLE"       # APPROVED + normalized vorhanden → bereit für Export
    BLOCKED       = "BLOCKED"        # APPROVED, aber normalized_output_json fehlt
    EXPORTED      = "EXPORTED"       # Phase 2: erfolgreich nach Neo4j geschrieben
    EXPORT_FAILED = "EXPORT_FAILED"  # Phase 2: Export fehlgeschlagen


# Rückwärtskompatibilität: RunStatus wird nicht mehr aktiv verwendet
class RunStatus(str, enum.Enum):
    CREATED             = "CREATED"
    QUEUED              = "QUEUED"
    RUNNING             = "RUNNING"
    COMPLETED           = "COMPLETED"
    FAILED              = "FAILED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    ABANDONED           = "ABANDONED"


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

    id                        = Column(String, primary_key=True)
    import_run_id             = Column(String, ForeignKey("import_runs.id"), nullable=False)
    # Denormalisiert für schnelle Filterung (kein JOIN über ImportRun nötig)
    source_id                 = Column(String, ForeignKey("sources.id"), nullable=True)
    # Provider-Konfiguration — Phase 1: Stub-Werte
    provider                  = Column(String, nullable=False, default="stub")
    provider_model            = Column(String, nullable=False, default="none")
    # Lifecycle-Status
    status                    = Column(Enum(AnalysisRunStatus), nullable=False,
                                      default=AnalysisRunStatus.CREATED)
    started_at                = Column(DateTime, nullable=True)
    finished_at               = Column(DateTime, nullable=True)
    # Zähler
    documents_targeted_count  = Column(Integer, nullable=False, default=0)
    documents_analyzed_count  = Column(Integer, nullable=False, default=0)
    documents_succeeded_count = Column(Integer, nullable=False, default=0)
    documents_failed_count    = Column(Integer, nullable=False, default=0)
    warning_count             = Column(Integer, nullable=False, default=0)
    error_count               = Column(Integer, nullable=False, default=0)
    # Letzter Fehler auf Run-Ebene
    last_error_code           = Column(String, nullable=True)
    last_error_message        = Column(Text, nullable=True)
    # Retry-Referenz
    restart_of_run_id         = Column(String, nullable=True)
    # Metadaten
    created_at                = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at                = Column(DateTime, nullable=False, default=datetime.utcnow)


class AnalysisResult(Base):
    """
    Persistentes Analyseergebnis für ein einzelnes ImportRunItem.

    Design-Entscheidungen:
    - raw_output_json: unveränderlich — exakte LLM-Antwort, nie überschreiben
    - normalized_output_json: optionale Nachbearbeitung, separat gespeichert
    - supersedes_result_id: verknüpft mit dem ersetzten Vorgänger-Result
    - review_status: vollständig unabhängig vom Rohdatenbestand änderbar
    - input_hash: stellt Nachvollziehbarkeit sicher (hat sich das Dokument geändert?)
    """
    __tablename__ = "analysis_results"

    id                      = Column(String, primary_key=True)
    analysis_run_id         = Column(String, ForeignKey("analysis_runs.id"), nullable=False)
    import_run_item_id      = Column(String, ForeignKey("import_run_items.id"), nullable=False)
    # Klassifikation des Ergebnistyps (z.B. "SUMMARY", "ENTITIES", "TOPICS")
    result_type             = Column(String, nullable=False, default="ANALYSIS")
    # Review-Workflow
    review_status           = Column(Enum(ReviewStatus), nullable=False,
                                    default=ReviewStatus.UNREVIEWED)
    # Versions- und Provenance-Felder
    schema_version          = Column(String, nullable=False, default="1.0")
    input_hash              = Column(String, nullable=True)   # SHA-256 des Eingabetexts
    # Analyseergebnisse — raw ist immutable, normalized optional
    raw_output_json         = Column(JSON, nullable=False)
    normalized_output_json  = Column(JSON, nullable=True)
    confidence_score        = Column(String, nullable=True)   # String für Flexibilität (0.0–1.0)
    # Provider-Tracking
    provider                = Column(String, nullable=False)
    provider_model          = Column(String, nullable=False)
    generated_at            = Column(DateTime, nullable=False, default=datetime.utcnow)
    # Review-Tracking
    approved_at             = Column(DateTime, nullable=True)
    approved_by             = Column(String, nullable=True)
    # Supersession: zeigt auf das ersetzte Vorgänger-Result
    supersedes_result_id    = Column(String, nullable=True)
    # Metadaten
    created_at              = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at              = Column(DateTime, nullable=False, default=datetime.utcnow)


class ReviewEvent(Base):
    """
    Append-only Audit-Log jeder review_status-Änderung an einem AnalysisResult.

    Design-Entscheidungen:
    - Niemals aktualisiert oder gelöscht — rein append-only
    - changed_by = None für systemseitige Ereignisse (Supersession durch Retry)
    - changed_by = Nutzerkennung für manuelle Review-Entscheidungen
    - reason_code: maschinenlesbarer Klassifikationscode (z.B. "QUALITY_INSUFFICIENT")
    - comment: freitextliche Begründung für menschliche Leser

    Was hier NICHT gespeichert wird:
    - Inhalte des Results (nur Referenz über analysis_result_id)
    - Exportstatus (liegt in ExportCandidate)
    - Neo4j-spezifische Informationen
    """
    __tablename__ = "review_events"

    id                     = Column(String, primary_key=True)
    analysis_result_id     = Column(String, ForeignKey("analysis_results.id"), nullable=False)
    # previous_review_status: None nur beim allerersten synthetischen Init-Event
    previous_review_status = Column(Enum(ReviewStatus), nullable=True)
    new_review_status      = Column(Enum(ReviewStatus), nullable=False)
    # changed_by: None = System (Supersession); String = manueller Reviewer
    changed_by             = Column(String, nullable=True)
    changed_at             = Column(DateTime, nullable=False, default=datetime.utcnow)
    comment                = Column(Text, nullable=True)
    # Maschinenlesbarer Grund (z.B. "QUALITY_INSUFFICIENT", "OUTDATED", "SUPERSEDED_BY_RETRY")
    reason_code            = Column(String, nullable=True)


class ExportCandidate(Base):
    """
    Technisches Gate zwischen fachlicher Freigabe und späterem Neo4j-Export.

    Design-Entscheidungen:
    - Ein Datensatz pro AnalysisResult (UNIQUE auf analysis_result_id)
    - Wird upserted, wenn sich review_status ändert
    - ELIGIBLE: review_status=APPROVED UND normalized_output_json vorhanden
    - BLOCKED: review_status=APPROVED, aber normalized_output_json fehlt (Phase-2-Vorbereitung)
    - NOT_ELIGIBLE: UNREVIEWED / REJECTED / SUPERSEDED
    - eligible_at: unveränderlich nach erstmaliger ELIGIBLE-Setzung (Export-Reihenfolge)

    Drei-Stufen-Trennung (nie vermischen):
      1. Fachliche Freigabe  → review_status auf AnalysisResult (APPROVED/REJECTED)
      2. Technische Eignung  → export_status auf ExportCandidate (ELIGIBLE/BLOCKED)
      3. Tatsächlicher Export → Phase 2: EXPORTED/EXPORT_FAILED + Neo4j-Write

    Was bewusst NICHT in ExportCandidate gespeichert wird:
    - Neo4j-Node-IDs (entstehen erst beim Export)
    - Exportierter Payload (liegt in Neo4j, nicht lokal)
    - Graph-Beziehungsstruktur
    """
    __tablename__ = "export_candidates"
    __table_args__ = (
        UniqueConstraint("analysis_result_id", name="uq_export_candidates_result"),
    )

    id                 = Column(String, primary_key=True)
    analysis_result_id = Column(String, ForeignKey("analysis_results.id"), nullable=False)
    export_status      = Column(Enum(ExportCandidateStatus), nullable=False,
                                default=ExportCandidateStatus.NOT_ELIGIBLE)
    # eligible_at: wird beim ersten Übergang nach ELIGIBLE gesetzt und nicht mehr geändert
    eligible_at        = Column(DateTime, nullable=True)
    # blocked_reason: maschinenlesbarer Grund für BLOCKED (z.B. "NORMALIZED_OUTPUT_MISSING")
    blocked_reason     = Column(String, nullable=True)
    created_at         = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at         = Column(DateTime, nullable=False, default=datetime.utcnow)
