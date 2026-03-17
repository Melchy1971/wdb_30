"""
ReviewService

Verantwortlichkeiten:
  - Validierung und Durchführung von review_status-Übergängen
  - Erstellung von ReviewEvents (append-only Audit-Log)
  - Berechnung und Persistenz von ExportCandidate-Einträgen
  - Systemseitige Supersession (aufgerufen von AnalysisRunService)
  - Abfrage der Review-Historie
  - Abfrage der Export-Kandidaten

Drei-Stufen-Trennung (unveränderlich):
  1. Fachliche Freigabe   → review_status auf AnalysisResult  (dieser Service)
  2. Technische Eignung   → export_status auf ExportCandidate (dieser Service)
  3. Tatsächlicher Export → Phase 2, separater ExportService, kein Code hier

Keine AnalysisRun-Logik. Keine Neo4j-Logik. Kein Frontend-Code.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import (
    AnalysisResult,
    AnalysisRun,
    ExportCandidate,
    ExportCandidateStatus,
    ReviewEvent,
    ReviewStatus,
)


# ---------------------------------------------------------------------------
# Zulässige Review-Statusübergänge (manuell durch Reviewer)
#
# Design-Entscheidung: SUPERSEDED ist aus dieser Tabelle ausgeschlossen.
# Es ist ein systemseitiger Status (gesetzt durch Retry-Run-Logik),
# kein Review-Ergebnis. Reviewer sehen es als Signal, nicht als Aktion.
# ---------------------------------------------------------------------------

_VALID_REVIEW_TRANSITIONS: dict[ReviewStatus, set[ReviewStatus]] = {
    ReviewStatus.UNREVIEWED: {ReviewStatus.APPROVED, ReviewStatus.REJECTED},
    ReviewStatus.APPROVED:   {ReviewStatus.REJECTED, ReviewStatus.UNREVIEWED},
    ReviewStatus.REJECTED:   {ReviewStatus.APPROVED, ReviewStatus.UNREVIEWED},
    ReviewStatus.SUPERSEDED: set(),   # Terminal — nur durch System gesetzt
}


# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ReviewService:
    """
    Zentraler Service für Review-Workflow und Export-Vorbereitung.
    Eine Instanz pro Request/Task — bekommt eine DB-Session injiziert.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # -----------------------------------------------------------------------
    # Öffentliche API — Review
    # -----------------------------------------------------------------------

    def set_review_status(
        self,
        result_id: str,
        new_status: ReviewStatus,
        changed_by: Optional[str] = None,
        comment: Optional[str] = None,
        reason_code: Optional[str] = None,
    ) -> AnalysisResult:
        """
        Ändert den review_status eines AnalysisResults.

        Regeln:
        - SUPERSEDED darf nie manuell gesetzt werden (nur durch das System via Retry)
        - Nur zulässige Übergänge gemäß _VALID_REVIEW_TRANSITIONS erlaubt
        - Jede Änderung erzeugt einen unveränderlichen ReviewEvent
        - Nach jeder Änderung wird der ExportCandidate neu bewertet (upsert)
        - approved_at / approved_by werden bei APPROVED gesetzt, bei Rücknahme gelöscht

        Design-Entscheidung: Review-Status ist vollständig entkoppelt von
        Rohdaten (ImportRunItem) und Analyse-Lauf (AnalysisRun). Ein Review
        verändert ausschließlich AnalysisResult.review_status, einen ReviewEvent
        und den abgeleiteten ExportCandidate.
        """
        result = self._get_result_or_raise(result_id)

        # Systemstatus: manuell nicht setzbar
        if new_status == ReviewStatus.SUPERSEDED:
            raise ValueError(
                "SUPERSEDED darf nicht manuell gesetzt werden — "
                "wird automatisch durch einen Retry-Run gesetzt."
            )

        # Übergangsvalidierung
        allowed = _VALID_REVIEW_TRANSITIONS.get(result.review_status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Ungültiger Review-Übergang: {result.review_status.value} → {new_status.value}. "
                f"Erlaubt: {[s.value for s in allowed] or 'keine (terminaler Status)'}"
            )

        previous_status = result.review_status

        # AnalysisResult aktualisieren
        result.review_status = new_status
        result.updated_at = _now()

        if new_status == ReviewStatus.APPROVED:
            result.approved_at = _now()
            result.approved_by = changed_by
        else:
            # Genehmigung zurückgenommen: Felder löschen
            result.approved_at = None
            result.approved_by = None

        # Audit-Log
        self._create_review_event(
            result=result,
            previous_status=previous_status,
            new_status=new_status,
            changed_by=changed_by,
            comment=comment,
            reason_code=reason_code,
        )

        # Export-Eignung neu berechnen
        self._upsert_export_candidate(result)

        self._db.commit()
        self._db.refresh(result)
        return result

    def get_history(self, result_id: str) -> list[ReviewEvent]:
        """
        Gibt alle ReviewEvents für ein AnalysisResult chronologisch zurück.
        Wirft KeyError wenn das Result nicht existiert.
        """
        self._get_result_or_raise(result_id)   # 404-Guard
        return (
            self._db.query(ReviewEvent)
            .filter(ReviewEvent.analysis_result_id == result_id)
            .order_by(ReviewEvent.changed_at.asc())
            .all()
        )

    # -----------------------------------------------------------------------
    # Öffentliche API — Export-Kandidaten
    # -----------------------------------------------------------------------

    def list_export_candidates(
        self,
        export_status: Optional[ExportCandidateStatus] = None,
        import_run_id: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> list[ExportCandidate]:
        """
        Listet ExportCandidates mit optionalen Filtern.

        Für import_run_id / source_id wird über AnalysisResult → AnalysisRun gejoint,
        da AnalysisRun source_id denormalisiert enthält.

        Design-Entscheidung: Die Abfrage gibt nur Results zurück, die mindestens
        einmal reviewed wurden (ExportCandidate-Eintrag existiert). Ergebnisse
        im Status UNREVIEWED ohne je einen Review-Schritt sind implizit NOT_ELIGIBLE
        und erscheinen nicht in dieser Liste — das ist korrekt und beabsichtigt.
        """
        q = self._db.query(ExportCandidate)

        if export_status is not None:
            q = q.filter(ExportCandidate.export_status == export_status)

        if import_run_id is not None or source_id is not None:
            q = q.join(
                AnalysisResult,
                ExportCandidate.analysis_result_id == AnalysisResult.id,
            ).join(
                AnalysisRun,
                AnalysisResult.analysis_run_id == AnalysisRun.id,
            )
            if import_run_id:
                q = q.filter(AnalysisRun.import_run_id == import_run_id)
            if source_id:
                q = q.filter(AnalysisRun.source_id == source_id)

        return q.order_by(ExportCandidate.updated_at.desc()).all()

    def get_export_candidate(self, result_id: str) -> ExportCandidate:
        """Gibt den ExportCandidate für ein AnalysisResult zurück."""
        candidate = (
            self._db.query(ExportCandidate)
            .filter(ExportCandidate.analysis_result_id == result_id)
            .first()
        )
        if candidate is None:
            raise KeyError(
                f"Kein ExportCandidate für AnalysisResult '{result_id}' — "
                "noch kein Review durchgeführt."
            )
        return candidate

    # -----------------------------------------------------------------------
    # Systemseitige Supersession (aufgerufen von AnalysisRunService)
    # -----------------------------------------------------------------------

    def supersede_result(self, result: AnalysisResult) -> None:
        """
        Setzt ein AnalysisResult auf SUPERSEDED (systemseitig, durch Retry-Run).

        Erzeugt einen ReviewEvent mit changed_by=None und reason_code="SUPERSEDED_BY_RETRY".
        Aktualisiert den ExportCandidate auf NOT_ELIGIBLE.

        Design-Entscheidung: Auch systemseitige Status-Änderungen werden im
        Audit-Log erfasst. Der Reviewer kann so die vollständige Historie eines
        Results nachvollziehen, auch wenn er selbst nie aktiv geworden ist.
        """
        previous_status = result.review_status

        result.review_status = ReviewStatus.SUPERSEDED
        result.updated_at = _now()

        self._create_review_event(
            result=result,
            previous_status=previous_status,
            new_status=ReviewStatus.SUPERSEDED,
            changed_by=None,           # System-Aktion, kein menschlicher Akteur
            comment=None,
            reason_code="SUPERSEDED_BY_RETRY",
        )

        self._upsert_export_candidate(result)
        # Kein commit hier — AnalysisRunService commitet nach _store_result()

    # -----------------------------------------------------------------------
    # Interne Logik
    # -----------------------------------------------------------------------

    def _evaluate_eligibility(
        self,
        result: AnalysisResult,
    ) -> tuple[ExportCandidateStatus, Optional[str]]:
        """
        Berechnet export_status und blocked_reason aus dem aktuellen Result-Zustand.

        Drei-Stufen-Trennung — diese Methode implementiert nur Stufe 2:
          Stufe 1: review_status (fachliche Freigabe) — wird als Input gelesen
          Stufe 2: export_status (technische Eignung) — wird hier berechnet
          Stufe 3: tatsächlicher Export — findet hier nicht statt

        Regeln:
          NOT_ELIGIBLE  → review_status ist UNREVIEWED, REJECTED oder SUPERSEDED
          BLOCKED       → review_status ist APPROVED, aber normalized_output_json fehlt
          ELIGIBLE      → review_status ist APPROVED UND normalized_output_json vorhanden

        EXPORTED / EXPORT_FAILED werden nur durch den Phase-2-ExportService gesetzt.
        """
        if result.review_status in {
            ReviewStatus.UNREVIEWED,
            ReviewStatus.REJECTED,
            ReviewStatus.SUPERSEDED,
        }:
            return ExportCandidateStatus.NOT_ELIGIBLE, result.review_status.value

        # review_status == APPROVED
        if result.normalized_output_json is None:
            # Design-Entscheidung: BLOCKED statt NOT_ELIGIBLE, damit der Unterschied
            # zwischen "fachlich abgelehnt" und "technisch noch nicht bereit" sichtbar ist.
            # Phase 2 fügt den Normalisierungsschritt hinzu und setzt dann auf ELIGIBLE.
            return ExportCandidateStatus.BLOCKED, "NORMALIZED_OUTPUT_MISSING"

        return ExportCandidateStatus.ELIGIBLE, None

    def _upsert_export_candidate(self, result: AnalysisResult) -> ExportCandidate:
        """
        Erzeugt oder aktualisiert den ExportCandidate für ein AnalysisResult.

        eligible_at: wird beim ersten Übergang auf ELIGIBLE gesetzt und danach
        nie mehr verändert. Ermöglicht FIFO-Sortierung bei der Exportwarteschlange.
        """
        new_status, blocked_reason = self._evaluate_eligibility(result)

        candidate = (
            self._db.query(ExportCandidate)
            .filter(ExportCandidate.analysis_result_id == result.id)
            .first()
        )

        now = _now()
        if candidate is None:
            candidate = ExportCandidate(
                id=str(uuid4()),
                analysis_result_id=result.id,
                export_status=new_status,
                eligible_at=now if new_status == ExportCandidateStatus.ELIGIBLE else None,
                blocked_reason=blocked_reason,
                created_at=now,
                updated_at=now,
            )
            self._db.add(candidate)
        else:
            # Schutz: EXPORTED / EXPORT_FAILED nicht durch Review-Änderungen überschreiben
            # (Phase 2: ExportService ist alleiniger Eigentümer dieser Zustände)
            if candidate.export_status in {
                ExportCandidateStatus.EXPORTED,
                ExportCandidateStatus.EXPORT_FAILED,
            }:
                return candidate

            # eligible_at nur beim ersten Mal auf ELIGIBLE setzen
            if (
                new_status == ExportCandidateStatus.ELIGIBLE
                and candidate.eligible_at is None
            ):
                candidate.eligible_at = now

            candidate.export_status = new_status
            candidate.blocked_reason = blocked_reason
            candidate.updated_at = now

        return candidate

    def _create_review_event(
        self,
        result: AnalysisResult,
        previous_status: Optional[ReviewStatus],
        new_status: ReviewStatus,
        changed_by: Optional[str],
        comment: Optional[str],
        reason_code: Optional[str],
    ) -> ReviewEvent:
        """Erzeugt einen unveränderlichen ReviewEvent-Eintrag."""
        event = ReviewEvent(
            id=str(uuid4()),
            analysis_result_id=result.id,
            previous_review_status=previous_status,
            new_review_status=new_status,
            changed_by=changed_by,
            changed_at=_now(),
            comment=comment,
            reason_code=reason_code,
        )
        self._db.add(event)
        return event

    def _get_result_or_raise(self, result_id: str) -> AnalysisResult:
        result = self._db.get(AnalysisResult, result_id)
        if result is None:
            raise KeyError(f"AnalysisResult '{result_id}' nicht gefunden")
        return result
