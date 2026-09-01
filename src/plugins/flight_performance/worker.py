"""Background analysis worker utilizing QRunnable and QThreadPool for flight performance."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from .engine.models import FlightEnvelopeResult
from .engine.solver import FlightPerformanceSolver

logger = logging.getLogger(__name__)


class FlightPerformanceSignals(QObject):
    """Signals emitted by FlightPerformanceWorker during computation."""

    finished = Signal(object)  # FlightEnvelopeResult
    error = Signal(str)
    progress = Signal(int, int, str)  # completed, total, message


class FlightPerformanceWorker(QRunnable):
    """Executes flight performance envelope analysis in a background thread pool."""

    def __init__(
        self,
        context: dict[str, Any],
    ) -> None:
        super().__init__()
        self.signals = FlightPerformanceSignals()
        self._context = context
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:

            def on_progress(curr: int, total: int, msg: str) -> None:
                self.signals.progress.emit(curr, total, msg)

            self.signals.progress.emit(0, 100, "Starting flight performance analysis...")
            result: FlightEnvelopeResult = FlightPerformanceSolver.run_analysis(
                self._context,
                progress_callback=on_progress,
            )
            self.signals.progress.emit(100, 100, "Done")
            self.signals.finished.emit(result)
        except Exception as exc:
            logger.exception("Flight performance analysis failed: %s", exc)
            self.signals.error.emit(str(exc))
