from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QToolButton,
)

from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.log_buffer import install_log_buffer
from setuav_studio.ui.theme import status_color

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI
    from setuav_studio.project import ProjectDocument


class StatusBarManager:
    """Manages status messages, progress indicator, logs button, and degraded badge."""

    def __init__(self, window: QMainWindow, api: StudioAPI) -> None:
        self._window = window
        self._api = api
        self._host = api._host
        self._log_window: QDialog | None = None
        self._status_level = "info"

        status_bar = self._window.statusBar()

        self.degraded_badge = QToolButton(self._window)
        self.degraded_badge.setText("⚠ Degraded mode")
        self.degraded_badge.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.degraded_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.degraded_badge.setAutoRaise(True)
        self.degraded_badge.hide()
        self.degraded_badge.clicked.connect(self.show_degraded_details)
        status_bar.addPermanentWidget(self.degraded_badge)

        self.log_button = QToolButton(self._window)
        self.log_button.setObjectName("studioStatusLogButton")
        self.log_button.setIcon(get_icon("log"))
        self.log_button.setToolTip("Application logs")
        self.log_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.log_button.setAutoRaise(True)
        self.log_button.setFixedSize(22, 22)
        self.log_button.clicked.connect(self.open_log_window)

        self.progress_bar = QProgressBar(self._window)
        self.progress_bar.setObjectName("studioStatusProgress")
        self.progress_bar.setFixedWidth(260)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.hide()
        status_bar.addPermanentWidget(self.progress_bar)

        self.status_label = QLabel(self._window)
        self.status_label.setObjectName("studioStatusMessage")
        status_bar.addWidget(self.log_button)
        status_bar.addWidget(self.status_label)

        self._status_timer = QTimer(self._window)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self.clear_status_message)

        self._host.bind_progress_handler(self.show_progress)
        self._host.bind_status_handler(self.show_status_message)
        self._api.show_status("Ready", "info", 0)
        install_log_buffer()

    def show_status_message(
        self,
        message: str,
        level: str = "info",
        timeout_ms: int = 5000,
    ) -> None:
        self._status_timer.stop()
        self._status_level = level
        self.refresh_status_color()
        self.status_label.setText(message)
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

    def open_log_window(self) -> None:
        if self._log_window is None:
            from setuav_studio.ui.log_window import LogWindow

            self._log_window = LogWindow(self._window)
        self._log_window.show()
        self._log_window.raise_()
        self._log_window.activateWindow()

    def show_degraded_details(self, project: ProjectDocument | None = None) -> None:
        proj = project or getattr(self._window, "_project", None)
        if proj is None or not proj.plugin_issues:
            return
        QMessageBox.warning(
            self._window,
            "Degraded Mode",
            "Some plugins required by this project are missing or incompatible:\n\n"
            + "\n".join(f"• {issue}" for issue in proj.plugin_issues),
        )


__all__ = ["StatusBarManager"]
