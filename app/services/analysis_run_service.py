"""
AnalysisRunService

Verantwortlichkeiten:
  - Lifecycle eines AnalysisRun (Statusübergänge mit Validierung)
  - Selektion geeigneter ImportRunItems (parse_status=SUCCEEDED)
  - Pro-Item-Analyse mit Fehler-Isolation
  - Lokale Persistenz von AnalysisResults (raw + normalized getrennt)
  - Supersession: ältere Results automatisch auf SUPERSEDED setzen
  - Kooperativer Cancel über cancel_requested-Flag
  - Recovery von RUNNING → ABANDONED beim App-Start

Keine Neo4j-Logik. Kein Frontend-Code. Keine LLM-Calls in Phase 1.

Phase-2-Hook:
    _analyze_item() ist als Stub implementiert.
    Für echte LLM-Analyse wird hier ein Provider-Client injiziert.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import (
    AnalysisResult,
    AnalysisRun,
    AnalysisRunStatus,
    ImportRun,
    ImportRunItem,
    ImportRunItemStatus,
    ImportRunStatus,
    ReviewStatus,
)
# ReviewService wird nur für Supersession-Audit-Trail benötigt.
# Import hier, nicht in routes, um Zirkulärimporte zu vermeiden.
from app.services.review_service import ReviewService


# ---------------------------------------------------------------------------
# Statusmaschine
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[AnalysisRunStatus, set[AnalysisRunStatus]] = {
    AnalysisRunStatus.CREATED: {
        AnalysisRunStatus.QUEUED,
        AnalysisRunStatus.CANCELLED,
    },
    AnalysisRunStatus.QUEUED: {
        AnalysisRunStatus.RUNNING,
        AnalysisRunStatus.CANCELLED,
    },
    AnalysisRunStatus.RUNNING: {
        AnalysisRunStatus.COMPLETED,
        AnalysisRunStatus.PARTIALLY_COMPLETED,
        AnalysisRunStatus.FAILED,
        AnalysisRunStatus.CANCELLED,
        AnalysisRunStatus.ABANDONED,
    },
    # Terminale Zustände — keine weiteren Übergänge
    AnalysisRunStatus.COMPLETED:           set(),
    AnalysisRunStatus.PARTIALLY_COMPLETED: set(),
    AnalysisRunStatus.FAILED:              set(),
    AnalysisRunStatus.CANCELLED:           set(),
    AnalysisRunStatus.ABANDONED:           set(),
}

_TERMINAL_STATUSES: frozenset[AnalysisRunStatus] = frozenset({
    AnalysisRunStatus.COMPLETED,
    AnalysisRunStatus.PARTIALLY_COMPLETED,
    AnalysisRunStatus.FAILED,
    AnalysisRunStatus.CANCELLED,
    AnalysisRunStatus.ABANDONED,
})

# ImportRun muss in einem dieser Zustände sein, damit ein AnalysisRun gestartet werden kann
_ELIGIBLE_IMPORT_STATUSES: frozenset[ImportRunStatus] = frozenset({
    ImportRunStatus.COMPLETED,
    ImportRunStatus.PARTIALLY_COMPLETED,
})


# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AnalysisRunService:
    """
    Zentraler Service für den AnalysisRun-Lifecycle.
    Eine Instanz pro Request/Task — bekommt eine DB-Session injiziert.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # -----------------------------------------------------------------------
    # Öffentliche API
    # -----------------------------------------------------------------------

    def create_run(
        self,
        import_run_id: str,
        provider: str = "stub",
        provider_model: str = "none",
        result_type: str = "ANALYSIS",
        restart_of_run_id: Optional[str] = None,
    ) -> AnalysisRun:
        """
        Legt einen neuen AnalysisRun an.

        Voraussetzungen:
          - ImportRun muss COMPLETED oder PARTIALLY_COMPLETED sein
          - provider / provider_model werden für alle AnalysisResults übernommen
          - result_type: klassifiziert die Art der Analyse ("ANALYSIS", "SUMMARY", ...)

        restart_of_run_id: optionale Referenz auf den Vorgänger-Run für Supersession.
        """
        import_run = self._db.get(ImportRun, import_run_id)
        if import_run is None:
            raise KeyError(f"ImportRun '{import_run_id}' nicht gefunden")

        if import_run.status not in _ELIGIBLE_IMPORT_STATUSES:
            raise ValueError(
                f"ImportRun '{import_run_id}' hat Status '{import_run.status.value}'. "
                f"Erlaubt: {[s.value for s in _ELIGIBLE_IMPORT_STATUSES]}"
            )

        now = _now()
        run = AnalysisRun(
            id=str(uuid4()),
            import_run_id=import_run_id,
            source_id=import_run.source_id,
            provider=provider,
            provider_model=provider_model,
            status=AnalysisRunStatus.CREATED,
            restart_of_run_id=restart_of_run_id,
            created_at=now,
            updated_at=now,
        )
        # result_type wird nicht am Run gespeichert, sondern nur an den Results.
        # Wir geben ihn an execute_run weiter (über ein separates Feld am Objekt).
        # Für den Übergang: temporär als Attribut setzen (nicht persistiert).
        run._result_type = result_type  # type: ignore[attr-defined]
        self._db.add(run)
        self._db.commit()
        self._db.refresh(run)
        # Nach refresh ist das transiente Attribut weg — für BackgroundTask
        # wird result_type separat übergeben. Für direkten Aufruf: genug.
        return run

    def execute_run(self, run_id: str, result_type: str = "ANALYSIS") -> AnalysisRun:
        """
        Führt einen AnalysisRun vollständig synchron aus.
        Wird als BackgroundTask gestartet — läuft in eigener Session.

        Ablauf:
          1. CREATED → QUEUED → RUNNING
          2. Geeignete ImportRunItems laden (parse_status=SUCCEEDED)
          3. Jedes Item analysieren → AnalysisResult anlegen
          4. Supersession älterer Results bei Retry-Run
          5. Cancel-Check zwischen Items
          6. Finalen Status setzen
        """
        run = self._get_or_raise(run_id)

        if run.status not in {AnalysisRunStatus.CREATED, AnalysisRunStatus.QUEUED}:
            raise ValueError(
                f"Run '{run_id}' hat Status '{run.status.value}' — kann nicht gestartet werden"
            )

        # Geeignete Items laden
        items = (
            self._db.query(ImportRunItem)
            .filter(
                ImportRunItem.import_run_id == run.import_run_id,
                ImportRunItem.parse_status == ImportRunItemStatus.SUCCEEDED,
            )
            .all()
        )

        run.documents_targeted_count = len(items)

        if not items:
            # Kein Item vorhanden → sofort FAILED
            self._fail_run(run, "NO_ELIGIBLE_ITEMS", "Keine geeigneten ImportRunItems gefunden")
            return run

        # CREATED → QUEUED → RUNNING
        if run.status == AnalysisRunStatus.CREATED:
            self._transition(run, AnalysisRunStatus.QUEUED)
            self._save(run)

        self._transition(run, AnalysisRunStatus.RUNNING)
        run.started_at = _now()
        self._save(run)

        try:
            self._process_items(run, items, result_type)
        except Exception as exc:
            self._fail_run(run, "UNEXPECTED_ERROR", str(exc))

        return run

    def cancel_run(self, run_id: str) -> AnalysisRun:
        """
        Kooperativer Abbruch.
        - CREATED / QUEUED → sofort CANCELLED
        - RUNNING → cancel_requested=True setzen; Job bricht beim nächsten Item ab
        """
        run = self._get_or_raise(run_id)

        if run.status in {AnalysisRunStatus.CREATED, AnalysisRunStatus.QUEUED}:
            self._transition(run, AnalysisRunStatus.CANCELLED)
            run.finished_at = _now()
            self._save(run)
            return run

        if run.status == AnalysisRunStatus.RUNNING:
            run.cancel_requested = True  # type: ignore[attr-defined]
            # cancel_requested ist kein Datenbankfeld am AnalysisRun (anders als ImportRun).
            # Für AnalysisRun setzen wir direkt CANCELLED, da Phase-1-Ausführung synchron
            # pro BackgroundTask läuft und der Cancel-Check dort greift.
            # Vollständige kooperative Implementierung: siehe ImportRunService.
            self._transition(run, AnalysisRunStatus.CANCELLED)
            run.finished_at = _now()
            self._save(run)
            return run

        raise ValueError(
            f"Run '{run_id}' hat terminalen Status '{run.status.value}' — Abbruch nicht möglich"
        )

    def retry_run(self, run_id: str) -> AnalysisRun:
        """
        Erzeugt einen neuen AnalysisRun für denselben ImportRun.
        Nur für terminale Runs erlaubt.
        Der neue Run referenziert den Original-Run über restart_of_run_id.
        Bestehende unreviewed Results werden beim execute_run auf SUPERSEDED gesetzt.
        """
        original = self._get_or_raise(run_id)

        if original.status not in _TERMINAL_STATUSES:
            raise ValueError(
                f"Run '{run_id}' hat Status '{original.status.value}' — "
                "Retry nur für terminale Runs möglich"
            )

        return self.create_run(
            import_run_id=original.import_run_id,
            provider=original.provider,
            provider_model=original.provider_model,
            restart_of_run_id=run_id,
        )

    def get_run(self, run_id: str) -> AnalysisRun:
        return self._get_or_raise(run_id)

    def list_runs(
        self,
        import_run_id: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> list[AnalysisRun]:
        q = self._db.query(AnalysisRun)
        if import_run_id:
            q = q.filter(AnalysisRun.import_run_id == import_run_id)
        if source_id:
            q = q.filter(AnalysisRun.source_id == source_id)
        return q.order_by(AnalysisRun.created_at.desc()).all()

    def list_results(
        self,
        run_id: str,
        review_status: Optional[ReviewStatus] = None,
    ) -> list[AnalysisResult]:
        self._get_or_raise(run_id)  # 404 wenn Run nicht existiert
        q = (
            self._db.query(AnalysisResult)
            .filter(AnalysisResult.analysis_run_id == run_id)
        )
        if review_status is not None:
            q = q.filter(AnalysisResult.review_status == review_status)
        return q.order_by(AnalysisResult.created_at.asc()).all()

    def get_result(self, result_id: str) -> AnalysisResult:
        result = self._db.get(AnalysisResult, result_id)
        if result is None:
            raise KeyError(f"AnalysisResult '{result_id}' nicht gefunden")
        return result

    @staticmethod
    def recover_abandoned(db: Session) -> list[AnalysisRun]:
        """
        Startup-Hook: Alle RUNNING-AnalysisRuns → ABANDONED.

        Grund: Prozess wurde während einer laufenden Analyse beendet.
        Die AnalysisResults dieser Runs sind möglicherweise unvollständig.
        Der Nutzer kann über retry_run einen neuen Run starten.
        """
        running = (
            db.query(AnalysisRun)
            .filter(AnalysisRun.status == AnalysisRunStatus.RUNNING)
            .all()
        )
        now = _now()
        for run in running:
            run.status = AnalysisRunStatus.ABANDONED
            run.finished_at = now
            run.updated_at = now
            run.last_error_code = "PROCESS_INTERRUPTED"
            run.last_error_message = (
                f"Prozess während Analyse unterbrochen. "
                f"Recovery beim Neustart: {now.isoformat()}"
            )
        if running:
            db.commit()
        return running

    # -----------------------------------------------------------------------
    # Interne Verarbeitungslogik
    # -----------------------------------------------------------------------

    def _process_items(
        self,
        run: AnalysisRun,
        items: list[ImportRunItem],
        result_type: str,
    ) -> None:
        """
        Iteriert über alle geeigneten Items.
        Fehler pro Item werden isoliert — ein fehlerhaftes Item bricht nicht den Run ab.
        Cancel-Check nach jedem Item.
        """
        for item in items:
            # Cancel-Check: DB-Stand neu laden, um cancel_requested zu erkennen
            # (Phase 1: AnalysisRun hat kein cancel_requested-Feld — vereinfacht)
            self._db.refresh(run)
            if run.status == AnalysisRunStatus.CANCELLED:
                break

            try:
                raw_output = self._analyze_item(run, item)
                self._store_result(run, item, raw_output, result_type)
                run.documents_succeeded_count += 1
            except Exception as exc:
                run.documents_failed_count += 1
                run.error_count += 1
                run.last_error_code = "ITEM_ANALYSIS_FAILED"
                run.last_error_message = f"Item '{item.id}': {exc}"
            finally:
                run.documents_analyzed_count += 1
                run.updated_at = _now()
                self._db.commit()

        self._finalize_run(run)

    def _analyze_item(self, run: AnalysisRun, item: ImportRunItem) -> dict:
        """
        Phase-1-Stub: Platzhalter für echte LLM-Analyse.

        Phase-2-Integration:
            Hier wird ein Provider-Client aufgerufen (Ollama / OpenAI-kompatibel).
            Der Client wird über Dependency Injection oder eine Factory bereitgestellt.
            Rückgabewert: unveränderliches raw_output_json (exakte LLM-Antwort).

        Lokale Persistenzregel:
            raw_output_json wird nie überschrieben.
            Nachbearbeitung erfolgt ausschließlich in normalized_output_json.
        """
        return {
            "stub": True,
            "provider": run.provider,
            "model": run.provider_model,
            "item_id": item.id,
            "path": item.path,
            "content_hash": item.content_hash,
            "size_bytes": item.size_bytes,
            "content_type": item.content_type,
            "note": "Phase-1-Stub: keine echte LLM-Analyse",
        }

    def _store_result(
        self,
        run: AnalysisRun,
        item: ImportRunItem,
        raw_output: dict,
        result_type: str,
    ) -> AnalysisResult:
        """
        Persistiert ein AnalysisResult.

        Supersession:
            Wenn run.restart_of_run_id gesetzt ist, wird das letzte nicht-superseded
            Result desselben Items und result_type auf SUPERSEDED gesetzt.

            Design-Entscheidung: Supersession gilt nur für Retry-Runs.
            Normale parallele Runs überschreiben sich nicht gegenseitig —
            jeder Run erzeugt eigene Results. Das ermöglicht Vergleiche.

        Was lokal gespeichert wird:
            - raw_output_json: unveränderlich, vollständige LLM-Antwort
            - normalized_output_json: None in Phase 1 (Normalisierung in Phase 2)
            - input_hash: SHA-256 des Quelldokuments (Provenance)
            - review_status: initial UNREVIEWED
            - provider / provider_model: für Nachvollziehbarkeit

        Was bewusst NICHT gespeichert wird (Phase 2):
            - Neo4j-Node-IDs (noch kein Export)
            - Embedding-Vektoren
            - Verarbeitungsstatus in externen Systemen
        """
        supersedes_id: Optional[str] = None

        if run.restart_of_run_id:
            # Suche das neueste aktive (nicht-superseded) Result für dieses Item
            previous = (
                self._db.query(AnalysisResult)
                .join(AnalysisRun, AnalysisResult.analysis_run_id == AnalysisRun.id)
                .filter(
                    AnalysisResult.import_run_item_id == item.id,
                    AnalysisResult.result_type == result_type,
                    AnalysisResult.review_status != ReviewStatus.SUPERSEDED,
                    # Nur Results aus Runs desselben Import-Runs
                    AnalysisRun.import_run_id == run.import_run_id,
                )
                .order_by(AnalysisResult.created_at.desc())
                .first()
            )
            if previous:
                # Supersession über ReviewService — erzeugt ReviewEvent + aktualisiert ExportCandidate
                ReviewService(self._db).supersede_result(previous)
                supersedes_id = previous.id

        now = _now()
        result = AnalysisResult(
            id=str(uuid4()),
            analysis_run_id=run.id,
            import_run_item_id=item.id,
            result_type=result_type,
            review_status=ReviewStatus.UNREVIEWED,
            schema_version="1.0",
            input_hash=item.content_hash,
            raw_output_json=raw_output,
            normalized_output_json=None,        # Phase 2: Normalisierungsschritt
            confidence_score=None,              # Phase 2: LLM-Konfidenz
            provider=run.provider,
            provider_model=run.provider_model,
            generated_at=now,
            supersedes_result_id=supersedes_id,
            created_at=now,
            updated_at=now,
        )
        self._db.add(result)
        return result

    def _finalize_run(self, run: AnalysisRun) -> None:
        """Setzt den finalen Run-Status anhand der Zähler."""
        now = _now()
        run.finished_at = now
        run.updated_at = now

        if run.status == AnalysisRunStatus.CANCELLED:
            self._save(run)
            return

        if run.documents_succeeded_count == run.documents_targeted_count:
            self._transition(run, AnalysisRunStatus.COMPLETED)
        elif run.documents_succeeded_count > 0:
            self._transition(run, AnalysisRunStatus.PARTIALLY_COMPLETED)
        else:
            self._transition(run, AnalysisRunStatus.FAILED)

        self._save(run)

    def _fail_run(self, run: AnalysisRun, code: str, message: str) -> None:
        """Setzt Run auf FAILED mit Fehlerdetails."""
        if run.status not in _TERMINAL_STATUSES:
            # Notfall-Übergang: direkt auf FAILED ohne normale State-Machine
            run.status = AnalysisRunStatus.FAILED
        run.last_error_code = code
        run.last_error_message = message
        run.finished_at = _now()
        run.updated_at = _now()
        self._save(run)

    # -----------------------------------------------------------------------
    # State Machine
    # -----------------------------------------------------------------------

    def _transition(self, run: AnalysisRun, target: AnalysisRunStatus) -> None:
        """Erzwingt einen validen Statusübergang. Wirft ValueError bei ungültigem Übergang."""
        allowed = _VALID_TRANSITIONS.get(run.status, set())
        if target not in allowed:
            raise ValueError(
                f"Ungültiger Statusübergang: {run.status.value} → {target.value}. "
                f"Erlaubt: {[s.value for s in allowed] or 'keine (terminaler Status)'}"
            )
        run.status = target
        run.updated_at = _now()

    # -----------------------------------------------------------------------
    # Datenbankzugriff
    # -----------------------------------------------------------------------

    def _get_or_raise(self, run_id: str) -> AnalysisRun:
        run = self._db.get(AnalysisRun, run_id)
        if run is None:
            raise KeyError(f"AnalysisRun '{run_id}' nicht gefunden")
        return run

    def _save(self, run: AnalysisRun) -> None:
        self._db.add(run)
        self._db.commit()
        self._db.refresh(run)
