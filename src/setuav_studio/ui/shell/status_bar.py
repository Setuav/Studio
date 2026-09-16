from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QToolButton,
    QWidget,
)

from setuav_studio.model.constraint import ConstraintChecker
from setuav_studio.ui.dialog.log import install_log_buffer
from setuav_studio.ui.dialog.problems import Problem, ProblemsDialog
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.theme import status_color

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI
    from setuav_studio.project import ProjectDocument


class ProblemsBadge(QFrame):
    """Clickable status bar badge displaying error.svg and warning.svg icons with live counts."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("studioProblemsBadge")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Problems & Rule Violations")
        self.setStyleSheet(
            "#studioProblemsBadge { border-radius: 4px; padding: 0px 4px; }"
            "#studioProblemsBadge:hover { background-color: rgba(255, 255, 255, 0.1); }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        self.error_icon_label = QLabel(self)
        self.error_icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.error_count_label = QLabel("0", self)
        self.error_count_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.warning_icon_label = QLabel(self)
        self.warning_icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.warning_count_label = QLabel("0", self)
        self.warning_count_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(self.error_icon_label)
        layout.addWidget(self.error_count_label)
        layout.addSpacing(6)
        layout.addWidget(self.warning_icon_label)
        layout.addWidget(self.warning_count_label)

        self.refresh_icons()

    def refresh_icons(self) -> None:
        self.error_icon_label.setPixmap(get_icon("error").pixmap(14, 14))
        self.warning_icon_label.setPixmap(get_icon("warning").pixmap(14, 14))

    def update_counts(self, errors: int, warnings: int) -> None:
        self.error_count_label.setText(str(errors))
        self.warning_count_label.setText(str(warnings))

    def text(self) -> str:
        """Return formatted badge text containing count substring for compatibility with test assertions."""
        return f"🔴 {self.error_count_label.text()}  ⚠️ {self.warning_count_label.text()}"

    def click(self) -> None:
        self.clicked.emit()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class StatusBarManager:
    """Manages status messages, progress indicator, logs button, task monitor, and problems badge."""

    def __init__(self, window: QMainWindow, api: StudioAPI) -> None:
        self._window = window
        self._api = api
        self._host = api._host
        self._log_window: QDialog | None = None
        self._task_monitor_window: QDialog | None = None
        self._problems_dialog: QDialog | None = None
        self._status_level = "info"
        self._problems: list[Problem] = []
        self._checker = ConstraintChecker()

        status_bar = self._window.statusBar()

        # 1. Left side widgets (Badges en solda, ardindan anlik mesaj)
        self.problems_badge = ProblemsBadge(self._window)
        self.problems_badge.clicked.connect(self.open_problems_window)
        status_bar.addWidget(self.problems_badge)

        self.error_icon_label = self.problems_badge.error_icon_label
        self.error_count_label = self.problems_badge.error_count_label
        self.warning_icon_label = self.problems_badge.warning_icon_label
        self.warning_count_label = self.problems_badge.warning_count_label

        self.status_label = QLabel(self._window)
        self.status_label.setObjectName("studioStatusMessage")
        status_bar.addWidget(self.status_label)

        # 2. Right side permanent widgets (Progress -> Cancel -> Command Palette -> Tasks -> Log en sağda)
        self.progress_bar = QProgressBar(self._window)
        self.progress_bar.setObjectName("studioStatusProgress")
        self.progress_bar.setFixedWidth(260)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.hide()
        status_bar.addPermanentWidget(self.progress_bar)

        self.cancel_button = QToolButton(self._window)
        self.cancel_button.setObjectName("studioStatusCancelTask")
        self.cancel_button.setIcon(get_icon("mdi6.close-circle"))
        self.cancel_button.setToolTip("Cancel background task")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setAutoRaise(True)
        self.cancel_button.setFixedSize(18, 18)
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self._on_cancel_tasks_clicked)
        status_bar.addPermanentWidget(self.cancel_button)

        self.command_palette_button = QToolButton(self._window)
        self.command_palette_button.setObjectName("studioStatusCommandPaletteButton")
        self.command_palette_button.setIcon(get_icon("fa6s.terminal"))
        self.command_palette_button.setToolTip("Command Palette (Ctrl+Shift+P)")
        self.command_palette_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.command_palette_button.setAutoRaise(True)
        self.command_palette_button.setFixedSize(22, 22)
        self.command_palette_button.clicked.connect(self.open_command_palette_window)
        status_bar.addPermanentWidget(self.command_palette_button)

        self.tasks_button = QToolButton(self._window)
        self.tasks_button.setObjectName("studioStatusTasksButton")
        self.tasks_button.setIcon(get_icon("fa6s.list-check"))
        self.tasks_button.setToolTip("Background Tasks Manager")
        self.tasks_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tasks_button.setAutoRaise(True)
        self.tasks_button.setFixedSize(22, 22)
        self.tasks_button.clicked.connect(self.open_task_monitor_window)
        status_bar.addPermanentWidget(self.tasks_button)

        self.log_button = QToolButton(self._window)
        self.log_button.setObjectName("studioStatusLogButton")
        self.log_button.setIcon(get_icon("log"))
        self.log_button.setToolTip("Application logs")
        self.log_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.log_button.setAutoRaise(True)
        self.log_button.setFixedSize(22, 22)
        self.log_button.clicked.connect(self.open_log_window)
        status_bar.addPermanentWidget(self.log_button)

        self._status_timer = QTimer(self._window)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self.clear_status_message)

        self._host.bind_progress_handler(self.show_progress)
        self._host.bind_status_handler(self.show_status_message)
        self._api.show_status("Ready", "info", 0)
        install_log_buffer()

        if hasattr(self._api, "tasks"):
            self._connect_task_manager()

    @property
    def degraded_badge(self) -> ProblemsBadge:
        """Alias for backward compatibility pointing to problems_badge."""
        return self.problems_badge

    def _connect_task_manager(self) -> None:
        try:
            tm = self._api.tasks
            if hasattr(tm, "task_started"):
                tm.task_started.connect(self._on_task_started)
            if hasattr(tm, "task_finished"):
                tm.task_finished.connect(self._on_task_finished)
            if hasattr(tm, "task_failed"):
                tm.task_failed.connect(self._on_task_failed)
        except Exception:
            pass

    def _on_task_started(self, task: object) -> None:
        self.cancel_button.show()

    def _on_task_finished(self, task: object) -> None:
        self._check_hide_cancel_button()

    def _on_task_failed(self, task: object, error: str) -> None:
        self._check_hide_cancel_button()

    def _check_hide_cancel_button(self) -> None:
        try:
            tm = getattr(self._api, "tasks", None)
            if tm and hasattr(tm, "running_tasks"):
                if not tm.running_tasks():
                    self.cancel_button.hide()
            else:
                self.cancel_button.hide()
        except Exception:
            self.cancel_button.hide()

    def _on_cancel_tasks_clicked(self) -> None:
        try:
            tm = getattr(self._api, "tasks", None)
            if tm and hasattr(tm, "cancel_all"):
                tm.cancel_all()
            self.cancel_button.hide()
            self.show_status_message("Background task cancelled", "warning", 3000)
        except Exception:
            self.cancel_button.hide()

    def show_status_message(
        self, message: str, level: str = "info", timeout_ms: int = 5000
    ) -> None:
        self._status_timer.stop()
        self._status_level = level
        self.status_label.setText(message)
        self.refresh_status_color()
        if timeout_ms > 0:
            self._status_timer.start(timeout_ms)

    def show_progress(self, completed: int, total: int, label: str = "") -> None:
        if total <= 0 or completed >= total:
            self.progress_bar.hide()
            return
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(completed)
        self.progress_bar.setFormat(f"{label} %p%" if label else "%p%")
        self.progress_bar.show()

    def clear_status_message(self) -> None:
        self._status_timer.stop()
        self.status_label.clear()

    def refresh_status_color(self) -> None:
        palette = self.status_label.palette()
        palette.setColor(QPalette.ColorRole.WindowText, status_color(self._status_level))
        self.status_label.setPalette(palette)

    def evaluate_problems(self, project: ProjectDocument | None = None) -> list[Problem]:
        """Evaluate project constraints and system/plugin warnings, updating the status bar badge."""
        proj = project or getattr(self._window, "_project", None)
        problems: list[Problem] = []

        if proj is not None:
            # 1. Evaluate project design rules & constraints
            results = self._checker.evaluate_project(proj.data)
            for r in results:
                if not r.passed and r.enabled:
                    sev = "error" if r.severity == "error" else "warning"
                    msg = r.message or f"Rule violated: {r.expression}"
                    problems.append(
                        Problem(
                            id=r.id,
                            title=r.name,
                            message=msg,
                            severity=sev,
                            source="Constraint",
                        )
                    )

            # 2. Check plugin issues / degraded mode
            if proj.plugin_issues:
                for idx, issue in enumerate(proj.plugin_issues, start=1):
                    problems.append(
                        Problem(
                            id=f"plugin_issue_{idx}",
                            title="Missing or Incompatible Plugin",
                            message=issue,
                            severity="warning",
                            source="Plugin",
                        )
                    )

        self._problems = problems
        self._update_problems_badge()
        return problems

    def _update_problems_badge(self) -> None:
        errors = sum(1 for p in self._problems if p.severity == "error")
        warnings = sum(1 for p in self._problems if p.severity == "warning")

        self.problems_badge.refresh_icons()
        self.problems_badge.update_counts(errors, warnings)

        if not self._problems:
            self.problems_badge.setToolTip("No problems or rule violations detected")
        else:
            details = "\n".join(f"[{p.source}] {p.title}: {p.message}" for p in self._problems)
            self.problems_badge.setToolTip(details)

    def open_problems_window(self) -> None:
        """Open the Problems dialog displaying all current problems line by line."""
        self.evaluate_problems()
        dialog = ProblemsDialog(self._problems, parent=self._window, api=self._api)
        dialog.exec()

    def open_command_palette_window(self) -> None:
        if hasattr(self._window, "open_command_palette"):
            self._window.open_command_palette()

    def open_log_window(self) -> None:
        if self._log_window is None:
            from setuav_studio.ui.dialog.log import LogWindow

            self._log_window = LogWindow(self._window)
        self._log_window.show()
        self._log_window.raise_()
        self._log_window.activateWindow()

    def open_task_monitor_window(self) -> None:
        if self._task_monitor_window is None:
            from setuav_studio.ui.dialog.task_monitor import TaskMonitorDialog

            self._task_monitor_window = TaskMonitorDialog(self._api, self._window)
        self._task_monitor_window.show()
        self._task_monitor_window.raise_()
        self._task_monitor_window.activateWindow()

    def show_degraded_details(self, project: ProjectDocument | None = None) -> None:
        self.open_problems_window()


__all__ = ["ProblemsBadge", "StatusBarManager"]
