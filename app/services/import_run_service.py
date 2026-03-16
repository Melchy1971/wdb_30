"""
ImportRunService

Verantwortlichkeiten:
  - Statusübergänge mit Validierung
  - Dateisystem-Scan lokaler Sources
  - Item-Anlage und -Verarbeitung
  - Counter-Aggregation nach jedem Item
  - Kooperativer Cancel über cancel_requested-Flag
  - Recovery von RUNNING-Runs beim App-Start (→ ABANDONED)

Keine Analyse-Logik. Keine Neo4j-Logik. Kein Frontend-Code.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import (
    ImportRun,
    ImportRunItem,
    ImportRunItemStatus,
    ImportRunStatus,
    Source,
    SourceValidationStatus,
)


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".txt", ".eml"})

CONTENT_TYPE_MAP: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt":  "text/plain",
    ".eml":  "message/rfc822",
}

# Größe der Lese-Chunks für SHA-256 (8 MB)
HASH_CHUNK_BYTES: int = 8 * 1024 * 1024

# Statusmaschine: erlaubte Übergänge
_VALID_TRANSITIONS: dict[ImportRunStatus, set[ImportRunStatus]] = {
    ImportRunStatus.CREATED: {
        ImportRunStatus.QUEUED,
        ImportRunStatus.CANCELLED,
    },
    ImportRunStatus.QUEUED: {
        ImportRunStatus.RUNNING,
        ImportRunStatus.CANCELLED,
    },
    ImportRunStatus.RUNNING: {
        ImportRunStatus.COMPLETED,
        ImportRunStatus.PARTIALLY_COMPLETED,
        ImportRunStatus.FAILED,
        ImportRunStatus.CANCELLED,
        ImportRunStatus.ABANDONED,
    },
    # Terminale Zustände – keine Übergänge möglich
    ImportRunStatus.COMPLETED:           set(),
    ImportRunStatus.PARTIALLY_COMPLETED: set(),
    ImportRunStatus.FAILED:              set(),
    ImportRunStatus.CANCELLED:           set(),
    ImportRunStatus.ABANDONED:           set(),
}

_TERMINAL_STATUSES: frozenset[ImportRunStatus] = frozenset({
    ImportRunStatus.COMPLETED,
    ImportRunStatus.PARTIALLY_COMPLETED,
    ImportRunStatus.FAILED,
    ImportRunStatus.CANCELLED,
    ImportRunStatus.ABANDONED,
})


# ---------------------------------------------------------------------------
# Hilfsfunktionen (kein Service-State nötig)
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    """SHA-256-Hash einer Datei. Liest in Chunks für große Dateien."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(HASH_CHUNK_BYTES):
            h.update(chunk)
    return h.hexdigest()


def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ImportRunService:
    """
    Zentraler Service für den ImportRun-Lifecycle.
    Eine Instanz pro Request/Task — bekommt eine DB-Session injiziert.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # -----------------------------------------------------------------------
    # Öffentliche API
    # -----------------------------------------------------------------------

    def create_run(
        self,
        source_id: str,
        restart_of_run_id: Optional[str] = None,
    ) -> ImportRun:
        """
        Legt einen neuen ImportRun an.
        Voraussetzung: Source muss VALID sein.
        """
        source = self._db.get(Source, source_id)
        if source is None:
            raise ValueError(f"Source '{source_id}' nicht gefunden")

        if source.validation_status != SourceValidationStatus.VALID:
            raise ValueError(
                f"Source '{source_id}' ist nicht valide "
                f"(Status: {source.validation_status.value}). "
                "Bitte zuerst /validate aufrufen."
            )

        now = _now()
        run = ImportRun(
            id=str(uuid4()),
            source_id=source_id,
            status=ImportRunStatus.CREATED,
            restart_of_run_id=restart_of_run_id,
            created_at=now,
            updated_at=now,
        )
        self._db.add(run)
        self._db.commit()
        self._db.refresh(run)
        return run

    def execute_run(self, run_id: str) -> ImportRun:
        """
        Führt einen ImportRun vollständig synchron aus.
        Wird als BackgroundTask gestartet — läuft in eigener Session.

        Ablauf:
          1. CREATED/QUEUED → RUNNING
          2. Source scannen → ImportRunItems anlegen
          3. Jedes Item verarbeiten (Metadaten + Hash)
          4. Cancel-Check zwischen den Items
          5. Finalen Status setzen
        """
        run = self._get_or_raise(run_id)

        # Nur nicht-terminale, noch-nicht-laufende Runs starten
        if run.status not in {ImportRunStatus.CREATED, ImportRunStatus.QUEUED}:
            raise ValueError(
                f"Run '{run_id}' hat Status '{run.status.value}' — kann nicht gestartet werden"
            )

        source = self._db.get(Source, run.source_id)
        if source is None:
            self._fail_run(run, "SOURCE_NOT_FOUND", "Source nicht mehr vorhanden")
            return run

        # CREATED → QUEUED → RUNNING (BackgroundTask startet direkt aus CREATED)
        if run.status == ImportRunStatus.CREATED:
            self._transition(run, ImportRunStatus.QUEUED)
            self._save(run)

        # → RUNNING
        self._transition(run, ImportRunStatus.RUNNING)
        run.started_at = _now()
        self._save(run)

        try:
            self._scan_and_process(run, source)
        except Exception as exc:
            # Ungefangene Ausnahme auf Run-Ebene → FAILED
            self._fail_run(run, "UNEXPECTED_ERROR", str(exc))

        return run

    def cancel_run(self, run_id: str) -> ImportRun:
        """
        Kooperativer Abbruch.
        - CREATED / QUEUED → sofort CANCELLED
        - RUNNING          → cancel_requested = True; Job prüft beim nächsten Item
        """
        run = self._get_or_raise(run_id)

        if run.status in _TERMINAL_STATUSES:
            raise ValueError(
                f"Run '{run_id}' ist bereits in terminalem Status '{run.status.value}'"
            )

        if run.status == ImportRunStatus.RUNNING:
            run.cancel_requested = True
            run.updated_at = _now()
            self._save(run)
        else:
            self._transition(run, ImportRunStatus.CANCELLED)
            run.finished_at = _now()
            self._save(run)

        return run

    def retry_run(self, run_id: str) -> ImportRun:
        """
        Erzeugt einen neuen Run als Retry eines terminalen Runs.
        Der ursprüngliche Run bleibt unverändert.
        """
        original = self._get_or_raise(run_id)

        if original.status not in _TERMINAL_STATUSES:
            raise ValueError(
                f"Retry nur für terminale Runs möglich. "
                f"Aktueller Status: '{original.status.value}'"
            )

        return self.create_run(
            source_id=original.source_id,
            restart_of_run_id=original.id,
        )

    def get_run(self, run_id: str) -> ImportRun:
        return self._get_or_raise(run_id)

    def list_runs(self, source_id: Optional[str] = None) -> list[ImportRun]:
        q = self._db.query(ImportRun)
        if source_id:
            q = q.filter(ImportRun.source_id == source_id)
        return q.order_by(ImportRun.created_at.desc()).all()

    def list_items(
        self,
        run_id: str,
        status_filter: Optional[ImportRunItemStatus] = None,
    ) -> list[ImportRunItem]:
        self._get_or_raise(run_id)  # 404-Guard
        q = self._db.query(ImportRunItem).filter(ImportRunItem.import_run_id == run_id)
        if status_filter:
            q = q.filter(ImportRunItem.parse_status == status_filter)
        return q.order_by(ImportRunItem.discovered_at.asc()).all()

    # -----------------------------------------------------------------------
    # Recovery (Startup-Hook, statische Methode für eigene Session)
    # -----------------------------------------------------------------------

    @staticmethod
    def recover_abandoned(db: Session) -> list[ImportRun]:
        """
        Wird beim App-Start aufgerufen.
        Alle RUNNING-Runs → ABANDONED (Prozess wurde unterbrochen).
        PROCESSING-Items dieser Runs → FAILED.

        Design-Entscheidung: RUNNING-Runs können nicht stillschweigend
        verschwinden. Der Zustand muss nachvollziehbar sein.
        """
        now = _now()

        running_runs: list[ImportRun] = (
            db.query(ImportRun)
            .filter(ImportRun.status == ImportRunStatus.RUNNING)
            .all()
        )

        for run in running_runs:
            # Hängende Items auf FAILED setzen
            processing_items: list[ImportRunItem] = (
                db.query(ImportRunItem)
                .filter(
                    ImportRunItem.import_run_id == run.id,
                    ImportRunItem.parse_status == ImportRunItemStatus.PROCESSING,
                )
                .all()
            )
            for item in processing_items:
                item.parse_status  = ImportRunItemStatus.FAILED
                item.error_code    = "PROCESS_INTERRUPTED"
                item.error_message = "Prozess während Verarbeitung unterbrochen (Recovery)"
                item.processed_at  = now
                item.updated_at    = now

            # Run als ABANDONED markieren
            run.status            = ImportRunStatus.ABANDONED
            run.finished_at       = now
            run.last_error_code   = "PROCESS_INTERRUPTED"
            run.last_error_message = (
                f"Prozess während Ausführung unterbrochen. "
                f"Recovery beim Neustart: {now.isoformat()}"
            )
            run.updated_at = now

        if running_runs:
            db.commit()

        return running_runs

    # -----------------------------------------------------------------------
    # Interne Scan- und Verarbeitungslogik
    # -----------------------------------------------------------------------

    def _scan_and_process(self, run: ImportRun, source: Source) -> None:
        """
        1. Alle unterstützten Dateien in der Source finden
        2. Pro Datei ein ImportRunItem anlegen (DISCOVERED)
        3. Jedes Item verarbeiten
        4. Cancel-Check zwischen den Items
        5. Run-Status finalisieren
        """
        source_path = Path(source.location_uri)

        # --- Scan-Phase ---
        files = self._discover_files(source_path)
        run.files_discovered_count = len(files)
        run.updated_at = _now()
        self._save(run)

        if not files:
            self._fail_run(run, "NO_FILES_FOUND", "Keine unterstützten Dateien gefunden")
            return

        # Items anlegen
        base_path = source_path if source_path.is_dir() else source_path.parent
        items: list[ImportRunItem] = []
        now = _now()
        for file_path in files:
            ext = file_path.suffix.lower()
            try:
                rel = str(file_path.relative_to(base_path))
            except ValueError:
                rel = file_path.name

            item = ImportRunItem(
                id=str(uuid4()),
                import_run_id=run.id,
                path=str(file_path),
                relative_path=rel,
                file_extension=ext,
                content_type=CONTENT_TYPE_MAP.get(ext),
                parse_status=ImportRunItemStatus.DISCOVERED,
                discovered_at=now,
                created_at=now,
                updated_at=now,
            )
            self._db.add(item)
            items.append(item)

        self._db.commit()

        # --- Verarbeitungs-Phase ---
        for item in items:
            # Cancel-Check: Run aus DB neu laden, um cancel_requested zu prüfen
            self._db.refresh(run)
            if run.cancel_requested:
                self._transition(run, ImportRunStatus.CANCELLED)
                run.finished_at = _now()
                self._save(run)
                return

            self._process_item(run, item)

        # --- Finalisierung ---
        self._finalize_run(run)

    def _discover_files(self, source_path: Path) -> list[Path]:
        """Gibt alle unterstützten Dateien in der Source zurück."""
        if source_path.is_file():
            if source_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                return [source_path]
            return []

        if source_path.is_dir():
            return sorted(
                f for f in source_path.rglob("*")
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
            )

        return []

    def _process_item(self, run: ImportRun, item: ImportRunItem) -> None:
        """
        Verarbeitet ein einzelnes ImportRunItem.
        Fehler auf Item-Ebene werden isoliert — der Run läuft weiter.
        """
        now = _now()
        item.parse_status = ImportRunItemStatus.PROCESSING
        item.updated_at   = now
        self._db.commit()

        file_path = Path(item.path)

        try:
            # Existenz und Lesbarkeit
            if not file_path.exists():
                raise FileNotFoundError(f"Datei nicht mehr vorhanden: {item.path}")
            if not os.access(file_path, os.R_OK):
                raise PermissionError(f"Kein Lesezugriff: {item.path}")

            # Metadaten
            stat = file_path.stat()
            item.size_bytes = stat.st_size

            # Content-Hash
            item.content_hash = _sha256(file_path)

            # Erfolg
            item.parse_status = ImportRunItemStatus.SUCCEEDED
            run.files_succeeded_count += 1

        except FileNotFoundError as exc:
            self._fail_item(item, "FILE_NOT_FOUND", str(exc))
            run.files_failed_count += 1
            run.error_count        += 1
            run.last_error_code    = "FILE_NOT_FOUND"
            run.last_error_message = str(exc)

        except PermissionError as exc:
            self._fail_item(item, "PERMISSION_DENIED", str(exc))
            run.files_failed_count += 1
            run.error_count        += 1
            run.last_error_code    = "PERMISSION_DENIED"
            run.last_error_message = str(exc)

        except OSError as exc:
            self._fail_item(item, "IO_ERROR", str(exc))
            run.files_failed_count += 1
            run.error_count        += 1
            run.last_error_code    = "IO_ERROR"
            run.last_error_message = str(exc)

        except Exception as exc:
            self._fail_item(item, "PROCESSING_ERROR", str(exc))
            run.files_failed_count += 1
            run.error_count        += 1
            run.last_error_code    = "PROCESSING_ERROR"
            run.last_error_message = str(exc)

        finally:
            item.processed_at = _now()
            item.updated_at   = _now()
            run.files_processed_count = (
                run.files_succeeded_count + run.files_failed_count
            )
            run.updated_at = _now()
            self._db.commit()

    def _finalize_run(self, run: ImportRun) -> None:
        """Setzt den terminalen Status des Runs anhand der Counter."""
        now = _now()

        if run.files_discovered_count == 0:
            target = ImportRunStatus.FAILED
        elif run.files_failed_count == 0:
            target = ImportRunStatus.COMPLETED
        elif run.files_succeeded_count == 0:
            target = ImportRunStatus.FAILED
        else:
            target = ImportRunStatus.PARTIALLY_COMPLETED

        self._transition(run, target)
        run.finished_at = now
        run.updated_at  = now
        self._save(run)

    def _fail_run(self, run: ImportRun, error_code: str, error_message: str) -> None:
        """Setzt Run direkt auf FAILED mit Fehlerinfo."""
        run.last_error_code    = error_code
        run.last_error_message = error_message
        run.finished_at        = _now()
        run.updated_at         = _now()
        # Direktübergang zu FAILED — auch aus RUNNING erlaubt
        run.status = ImportRunStatus.FAILED
        self._save(run)

    @staticmethod
    def _fail_item(
        item: ImportRunItem,
        error_code: str,
        error_message: str,
    ) -> None:
        item.parse_status  = ImportRunItemStatus.FAILED
        item.error_code    = error_code
        item.error_message = error_message

    # -----------------------------------------------------------------------
    # Statusmaschine
    # -----------------------------------------------------------------------

    def _transition(self, run: ImportRun, target: ImportRunStatus) -> None:
        """
        Erzwingt einen validen Statusübergang.
        Wirft ValueError bei ungültigem Übergang.

        Design-Entscheidung: Statusübergänge werden im Service validiert,
        nicht in der Route. Die Route ist nur für HTTP-Belange zuständig.
        """
        allowed = _VALID_TRANSITIONS.get(run.status, set())
        if target not in allowed:
            raise ValueError(
                f"Ungültiger Statusübergang: {run.status.value} → {target.value}. "
                f"Erlaubt: {[s.value for s in allowed] or 'keine (terminaler Status)'}"
            )
        run.status     = target
        run.updated_at = _now()

    # -----------------------------------------------------------------------
    # Datenbankzugriff
    # -----------------------------------------------------------------------

    def _get_or_raise(self, run_id: str) -> ImportRun:
        run = self._db.get(ImportRun, run_id)
        if run is None:
            raise KeyError(f"ImportRun '{run_id}' nicht gefunden")
        return run

    def _save(self, obj: object) -> None:
        self._db.add(obj)
        self._db.commit()
        self._db.refresh(obj)
