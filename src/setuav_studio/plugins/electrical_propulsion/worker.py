"""Background analysis worker utilizing QRunnable and QThreadPool for electrical propulsion."""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from .engine.solver import PropulsionSolverEngine

logger = logging.getLogger(__name__)


class PropulsionWorkerSignals(QObject):
    """Signals emitted by PropulsionWorker during computation."""

    finished = Signal(object)  # dict[str, Any]
    error = Signal(str)
    progress = Signal(int, int, str)  # completed, total, message


class PropulsionWorker(QRunnable):
    """Executes electrical propulsion analysis in a background thread pool."""

    def __init__(
        self,
        context: dict[str, Any],
    ) -> None:
        super().__init__()
        self.signals = PropulsionWorkerSignals()
        self._context = context
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            def on_progress(curr: int, total: int, msg: str) -> None:
                self.signals.progress.emit(curr, total, msg)

            self.signals.progress.emit(0, 100, "Starting...")
            res = PropulsionSolverEngine.run_analysis(
                self._context,
                progress_callback=on_progress,
            )
            self.signals.progress.emit(100, 100, "Done")
            self.signals.finished.emit(res)
        except Exception as exc:
            logger.exception("Propulsion analysis failed: %s", exc)
            self.signals.error.emit(str(exc))
