"""
SourceValidationService

Serverseitige Prüfung lokaler Quellpfade.
Kein Frontend-Zugriff, keine Neo4j-Integration in dieser Phase.

Prüfreihenfolge:
  1. Pfad existiert           → INACCESSIBLE wenn nicht
  2. Lesezugriff vorhanden    → INACCESSIBLE wenn nicht
  3. Pfad ist Datei           → Dateiendung prüfen
  4. Pfad ist Verzeichnis     → mindestens eine unterstützte Datei prüfen
  5. Weder noch               → INVALID
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Source, SourceValidationStatus


# Unterstützte Dateiendungen (Kleinschreibung)
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".txt", ".eml"})


@dataclass(frozen=True, slots=True)
class ValidationResult:
    status: SourceValidationStatus
    message: str


class SourceValidationService:
    """
    Führt alle Pfad- und Inhaltsvalidierungen durch und persistiert das Ergebnis.

    Verwendung:
        service = SourceValidationService(db)
        source  = service.validate(source)
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def validate(self, source: Source) -> Source:
        """
        Validiert die location_uri der Source, speichert Status und Nachricht
        und gibt die aktualisierte Source zurück.
        """
        result = self._run_checks(source.location_uri)

        source.validation_status  = result.status
        source.validation_message = result.message
        source.last_validated_at  = datetime.utcnow()

        self._db.commit()
        self._db.refresh(source)
        return source

    # ------------------------------------------------------------------
    # Interne Prüflogik
    # ------------------------------------------------------------------

    def _run_checks(self, location_uri: str) -> ValidationResult:
        path = Path(location_uri)

        # 1. Pfad existiert?
        if not path.exists():
            return ValidationResult(
                status=SourceValidationStatus.INACCESSIBLE,
                message=f"Pfad nicht gefunden: '{location_uri}'",
            )

        # 2. Lesezugriff vorhanden?
        if not os.access(path, os.R_OK):
            return ValidationResult(
                status=SourceValidationStatus.INACCESSIBLE,
                message=f"Kein Lesezugriff auf: '{location_uri}'",
            )

        # 3. Einzelne Datei
        if path.is_file():
            return self._check_file(path)

        # 4. Verzeichnis
        if path.is_dir():
            return self._check_directory(path)

        # 5. Sonderfälle (Symlink-Loop, Device-File, …)
        return ValidationResult(
            status=SourceValidationStatus.INVALID,
            message=f"Pfad ist weder Datei noch Verzeichnis: '{location_uri}'",
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _check_file(path: Path) -> ValidationResult:
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            return ValidationResult(
                status=SourceValidationStatus.INVALID,
                message=(
                    f"Dateityp '{ext}' wird nicht unterstützt. "
                    f"Unterstützte Typen: {supported}"
                ),
            )
        return ValidationResult(
            status=SourceValidationStatus.VALID,
            message=f"Datei ist valide: '{path.name}' ({ext})",
        )

    @staticmethod
    def _check_directory(path: Path) -> ValidationResult:
        try:
            entries = list(path.iterdir())
        except PermissionError:
            return ValidationResult(
                status=SourceValidationStatus.INACCESSIBLE,
                message=f"Lesezugriff auf Verzeichnisinhalt verweigert: '{path}'",
            )

        supported_files = [
            e for e in entries
            if e.is_file() and e.suffix.lower() in SUPPORTED_EXTENSIONS
        ]

        if not supported_files:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            total_files = sum(1 for e in entries if e.is_file())
            detail = (
                f"{total_files} Datei(en) gefunden, aber keine mit unterstützter Endung."
                if total_files > 0
                else "Verzeichnis ist leer."
            )
            return ValidationResult(
                status=SourceValidationStatus.INVALID,
                message=(
                    f"Keine unterstützten Dateien gefunden. "
                    f"{detail} Unterstützte Typen: {supported}"
                ),
            )

        type_counts: dict[str, int] = {}
        for f in supported_files:
            ext = f.suffix.lower()
            type_counts[ext] = type_counts.get(ext, 0) + 1

        summary = ", ".join(
            f"{count}× {ext}" for ext, count in sorted(type_counts.items())
        )
        return ValidationResult(
            status=SourceValidationStatus.VALID,
            message=f"{len(supported_files)} unterstützte Datei(en) gefunden: {summary}",
        )
