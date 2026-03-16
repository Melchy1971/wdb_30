from __future__ import annotations

from collections.abc import Mapping

from app.domain.enums import AnalysisRunStatus, ImportRunStatus
from app.domain.exceptions import InvalidTransitionError


IMPORT_RUN_TRANSITIONS: Mapping[ImportRunStatus, set[ImportRunStatus]] = {
    ImportRunStatus.PENDING: {ImportRunStatus.RUNNING, ImportRunStatus.CANCELLED, ImportRunStatus.STALE},
    ImportRunStatus.RUNNING: {
        ImportRunStatus.COMPLETED,
        ImportRunStatus.PARTIAL,
        ImportRunStatus.FAILED,
        ImportRunStatus.CANCELLED,
        ImportRunStatus.STALE,
    },
    ImportRunStatus.PARTIAL: set(),
    ImportRunStatus.COMPLETED: set(),
    ImportRunStatus.FAILED: set(),
    ImportRunStatus.CANCELLED: set(),
    ImportRunStatus.STALE: set(),
}

ANALYSIS_RUN_TRANSITIONS: Mapping[AnalysisRunStatus, set[AnalysisRunStatus]] = {
    AnalysisRunStatus.PENDING: {AnalysisRunStatus.RUNNING, AnalysisRunStatus.CANCELLED, AnalysisRunStatus.STALE},
    AnalysisRunStatus.RUNNING: {
        AnalysisRunStatus.COMPLETED,
        AnalysisRunStatus.FAILED,
        AnalysisRunStatus.CANCELLED,
        AnalysisRunStatus.STALE,
    },
    AnalysisRunStatus.COMPLETED: set(),
    AnalysisRunStatus.FAILED: set(),
    AnalysisRunStatus.CANCELLED: set(),
    AnalysisRunStatus.STALE: set(),
}


def ensure_import_transition(current: ImportRunStatus, target: ImportRunStatus) -> None:
    if target == current:
        return
    allowed = IMPORT_RUN_TRANSITIONS[current]
    if target not in allowed:
        raise InvalidTransitionError(f"invalid import run transition: {current} -> {target}")


def ensure_analysis_transition(current: AnalysisRunStatus, target: AnalysisRunStatus) -> None:
    if target == current:
        return
    allowed = ANALYSIS_RUN_TRANSITIONS[current]
    if target not in allowed:
        raise InvalidTransitionError(f"invalid analysis run transition: {current} -> {target}")
