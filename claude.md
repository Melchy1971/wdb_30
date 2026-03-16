# CLAUDE.md

> Persistent context für Claude Code. Wird am Start jeder Session automatisch geladen.
> Unter 200 Zeilen halten. Für Details auf `docs/` verweisen.

---

## Projekt-Übersicht

- **Name:** Wissens-DB (wdb_30)
- **Zweck:** Lokale Wissens- und Analyseplattform – verwaltet Dokumente (PDF/DOCX/TXT/EML) und Analyse-Ergebnisse
- **Stack:** FastAPI + SQLAlchemy (Backend) · React + Vite + TypeScript (Frontend) · SQLite (Phase 1) · Neo4j (Phase 2) · Ollama (lokal)
- **Architektur-Dokument:** `docs/architecture.md`

---

## Architekturregeln (nicht verhandlungsfähig)

- Kein Frontend-Direktzugriff auf Neo4j, Ollama oder Dateisystem
- Alle Integrationen nur über das Backend (`/api/v1/*`)
- Rohdateien werden nie überschrieben (immutable)
- Analyse-Ergebnisse werden separat in `AnalysisResult` gespeichert, nie in das Quelldokument geschrieben
- Neo4j-Sync nur für approved Results (`is_approved=True` / Status `approved`)

---

## Projektstruktur

```
/
├── backend/
│   └── app/
│       ├── main.py               # FastAPI App, lifespan, startup-Hook
│       ├── api/
│       │   ├── deps.py
│       │   ├── error_handlers.py
│       │   └── routes/           # import_runs.py, analysis_runs.py
│       ├── core/
│       │   └── config.py         # pydantic-settings, liest backend/.env
│       ├── db/
│       │   ├── models.py         # SQLAlchemy ORM-Modelle
│       │   ├── session.py        # Engine + SessionLocal
│       │   ├── base.py
│       │   └── init_db.py        # create_all + stale recovery
│       ├── domain/
│       │   ├── enums.py          # ImportRunStatus, AnalysisRunStatus, etc.
│       │   ├── exceptions.py     # NotFoundError, InvalidTransitionError, ConflictError
│       │   └── models.py         # Dataclasses (Domain-Objekte ohne ORM)
│       ├── repositories/
│       │   └── run_repository.py # Datenzugriff (kein Business-Logik)
│       ├── schemas/
│       │   ├── common.py         # ApiModel, TimestampedResponse
│       │   └── runs.py           # Request/Response-Schemas
│       └── services/
│           ├── run_service.py    # Orchestrierung, Lifecycle-Timestamps
│           └── state_machine.py  # Erlaubte Status-Übergänge
├── frontend/
│   ├── src/
│   │   ├── api/          # client.ts, imports.ts, analysis.ts
│   │   ├── components/   # StatusBadge.tsx, ...
│   │   ├── hooks/        # useImportRuns.ts, ...
│   │   ├── pages/        # Dashboard, ImportPage, AnalysisPage
│   │   └── types/        # runs.ts (TypeScript-Interfaces)
│   ├── vite.config.ts    # Proxy: /api → localhost:8000
│   └── tsconfig.app.json
├── docs/
│   └── decisions/        # ADRs
├── .env.example          # Vorlage → backend/.env kopieren
└── .gitignore
```

---

## Häufige Befehle

```bash
# Backend (aus backend/)
pip install -e ".[dev]"
uvicorn app.main:app --reload

# Frontend (aus frontend/)
npm install
npm run dev

# Tests
cd backend && pytest
cd frontend && npm run typecheck && npm run lint
```

---

## Domänenobjekte

| Modell | Tabelle | Zweck |
|--------|---------|-------|
| ImportRun | import_run | Tracking eines Import-Laufs inkl. Status |
| AnalysisRun | analysis_run | Tracking einer Analyse inkl. Status |
| AnalysisResult | analysis_result | Einzelergebnis, verknüpft mit AnalysisRun |

**Phase 2 (noch nicht implementiert):** SourceSystem, Source, Document, Folder, Email, Attachment, Topic, Entity, MergedCase

---

## Status-Maschine

```
Import:   PENDING → RUNNING → COMPLETED / PARTIAL / FAILED / CANCELLED / STALE
Analysis: PENDING → RUNNING → COMPLETED / FAILED / CANCELLED / STALE
Result:   DRAFT → APPROVED / REJECTED
```

Startup-Hook: Alle PENDING/RUNNING-Runs → STALE (kein verlorener Job-Status nach Neustart)

---

## Coding-Konventionen

- **Sprache:** Deutsch für Kommentare und Commit-Messages
- Kein `any` in TypeScript – stattdessen `unknown` mit Type Guard
- Funktionale React-Komponenten mit Hooks, keine Klassen
- Commits: `type(scope): kurze Beschreibung` (Conventional Commits)
- Typen: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

---

## Phase 1 – Offene Implementierungsschritte

Siehe `docs/architecture.md` für vollständigen Plan. Nächste Schritte:

3. SQLite WAL-Mode + Alembic-Migrationen einrichten
4. Encoding-Bereinigung (chardet-basiert)
5. Parser-Module (PDF/DOCX/TXT/EML) mit Fehler-Isolation
6. AnalysisResult: `raw_prompt_hash`, `neo4j_synced` ergänzen
7. Ollama-Client mit Timeout + Fehlerbehandlung
8. Approval-Flow + Neo4j-Stub
9. Frontend Job-Status mit Polling
