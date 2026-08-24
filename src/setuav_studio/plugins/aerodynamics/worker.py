"""Background analysis worker utilizing QRunnable and QThreadPool."""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from .engine.base import AeroEngine, AnalysisMethod, FlightCondition

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    """Signals emitted by AnalysisWorker during computation."""
    finished = Signal(object)  # AeroResult
    error = Signal(str)
    progress = Signal(int, int, str)  # completed, total, message


class AnalysisWorker(QRunnable):
    """Executes aerodynamic analysis in a background thread pool."""

    def __init__(
        self,
        engine: AeroEngine,
        components: list[dict[str, Any]],
        condition: FlightCondition,
        method: AnalysisMethod = AnalysisMethod.AERO_BUILDUP,
        settings: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._engine = engine
        self._components = components
        self._condition = condition
        self._method = method
        self._settings = settings or {}
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            def on_step(curr: int, total: int, msg: str) -> None:
                self.signals.progress.emit(curr, total, msg)

            self.signals.progress.emit(0, 100, "Starting...")
            result = self._engine.analyze(
                components=self._components,
                condition=self._condition,
                method=self._method,
                settings=self._settings,
                progress_callback=on_step,
            )
            self.signals.progress.emit(100, 100, "Done")
            self.signals.finished.emit(result)
        except Exception as exc:
            logger.exception("Aerodynamic analysis failed: %s", exc)
            self.signals.error.emit(str(exc))
