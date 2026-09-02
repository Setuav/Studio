"""Background task manager and monitor dialog for SetUAV Studio."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.theme import status_color

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI
    from setuav_studio.task.manager import TaskManager


class TaskMonitorDialog(QDialog):
    """Dialog displaying active background tasks, live progress, and past task history."""

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._tm: TaskManager = api.tasks
        self.setWindowTitle("Background Task Manager")
        self.setWindowIcon(get_icon("fa6s.list-check"))
        self.setMinimumSize(780, 480)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Top Control Bar
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)

        title_label = QLabel("Background Tasks & Computations")
        title_label.setFont(QFont("Inter", 11, QFont.Weight.Bold))
        top_layout.addWidget(title_label)
        top_layout.addStretch()

        threads_label = QLabel("Max Worker Threads:")
        top_layout.addWidget(threads_label)

        self._spin_workers = QSpinBox()
        self._spin_workers.setRange(1, 64)
        self._spin_workers.setValue(self._tm.max_workers)
        self._spin_workers.valueChanged.connect(self._on_workers_changed)
        top_layout.addWidget(self._spin_workers)

        self._btn_cancel_all = QPushButton("Cancel All")
        self._btn_cancel_all.setIcon(get_icon("mdi6.close-circle"))
        self._btn_cancel_all.clicked.connect(self._tm.cancel_all)
        top_layout.addWidget(self._btn_cancel_all)

        self._btn_clear_history = QPushButton("Clear History")
        self._btn_clear_history.setIcon(get_icon("delete"))
        self._btn_clear_history.clicked.connect(self._on_clear_history)
        top_layout.addWidget(self._btn_clear_history)

        layout.addWidget(top_bar)

        # Tabs: Active vs History
        self._tabs = QTabWidget()
        self._active_table = self._create_active_table()
        self._history_table = self._create_history_table()

        self._tabs.addTab(self._active_table, "Active Tasks (0)")
        self._tabs.addTab(self._history_table, "Task History")
        layout.addWidget(self._tabs)

        # Refresh Timer for live duration / progress
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(400)
        self._refresh_timer.timeout.connect(self._refresh_active_tasks)

        # Connect TaskManager events
        self._tm.tasks_count_changed.connect(self._on_task_count_changed)
        self._tm.task_started.connect(lambda _tid, _n: self._refresh_all())
        self._tm.task_finished.connect(lambda _tid, _r: self._refresh_all())
        self._tm.task_error.connect(lambda _tid, _e: self._refresh_all())
        self._tm.task_cancelled.connect(lambda _tid: self._refresh_all())

        self._refresh_all()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self._refresh_all()
        self._refresh_timer.start()

    def hideEvent(self, event: Any) -> None:
        super().hideEvent(event)
        self._refresh_timer.stop()

    def _create_active_table(self) -> QTableWidget:
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["Task Name", "Priority", "Progress", "Duration", "Action"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        return table

    def _create_history_table(self) -> QTableWidget:
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["Time", "Task Name", "Status", "Duration", "Details / Error"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        return table

    def _on_workers_changed(self, val: int) -> None:
        self._tm.max_workers = val

    def _on_clear_history(self) -> None:
        self._tm.clear_history()
        self._refresh_history_table()

    def _on_task_count_changed(self, count: int) -> None:
        self._tabs.setTabText(0, f"Active Tasks ({count})")
        self._btn_cancel_all.setEnabled(count > 0)
        self._refresh_all()

    def _refresh_all(self) -> None:
        self._refresh_active_tasks()
        self._refresh_history_table()

    def _refresh_active_tasks(self) -> None:
        active = self._tm.active_tasks
        self._active_table.setRowCount(len(active))
        for row, handle in enumerate(active):
            # 0: Name
            name_item = QTableWidgetItem(handle.name)
            name_item.setFont(QFont("Inter", 9, QFont.Weight.DemiBold))
            self._active_table.setItem(row, 0, name_item)

            # 1: Priority
            prio_name = handle.priority.name if hasattr(handle.priority, "name") else str(handle.priority)
            prio_item = QTableWidgetItem(prio_name)
            prio_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._active_table.setItem(row, 1, prio_item)

            # 2: Progress Bar
            prog_widget = self._active_table.cellWidget(row, 2)
            if not isinstance(prog_widget, QProgressBar):
                prog_widget = QProgressBar()
                prog_widget.setFixedHeight(18)
                prog_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
                prog_widget.setTextVisible(True)
                self._active_table.setCellWidget(row, 2, prog_widget)

            if handle.progress is not None:
                prog_widget.setRange(0, handle.progress.total)
                prog_widget.setValue(handle.progress.current)
                msg = handle.progress.message
                prog_widget.setFormat(f"{msg} (%p%)" if msg else "%p%")
            else:
                prog_widget.setRange(0, 0)  # indeterminate
                prog_widget.setFormat("Running...")

            # 3: Duration
            dur_str = f"{handle.duration_seconds:.1f}s"
            dur_item = QTableWidgetItem(dur_str)
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._active_table.setItem(row, 3, dur_item)

            # 4: Cancel Button
            cancel_btn = self._active_table.cellWidget(row, 4)
            if not isinstance(cancel_btn, QToolButton):
                cancel_btn = QToolButton()
                cancel_btn.setIcon(get_icon("mdi6.close-circle"))
                cancel_btn.setToolTip("Cancel task")
                cancel_btn.clicked.connect(lambda _=None, tid=handle.id: self._tm.cancel(tid))
                self._active_table.setCellWidget(row, 4, cancel_btn)

    def _refresh_history_table(self) -> None:
        recent = self._tm.recent_tasks()
        history = [h for h in recent if h.status not in ("pending", "running")]
        self._history_table.setRowCount(len(history))

        for row, handle in enumerate(history):
            # 0: Time
            t_str = datetime.datetime.fromtimestamp(handle.created_at).strftime("%H:%M:%S")
            time_item = QTableWidgetItem(t_str)
            self._history_table.setItem(row, 0, time_item)

            # 1: Name
            self._history_table.setItem(row, 1, QTableWidgetItem(handle.name))

            # 2: Status with color badge
            st = handle.status
            status_item = QTableWidgetItem(st.upper() if hasattr(st, "upper") else str(st))
            color_name = "success" if st == "success" else ("warning" if st == "cancelled" else "error")
            status_item.setForeground(QBrush(QColor(status_color(color_name))))
            status_item.setFont(QFont("Inter", 9, QFont.Weight.Bold))
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._history_table.setItem(row, 2, status_item)

            # 3: Duration
            dur_str = f"{handle.duration_seconds:.2f}s"
            dur_item = QTableWidgetItem(dur_str)
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._history_table.setItem(row, 3, dur_item)

            # 4: Details / Error
            detail = ""
            if handle.error is not None:
                detail = f"Error: {handle.error}"
            elif handle.result is not None:
                detail = "Completed"
            elif st == "cancelled":
                detail = "Cancelled by user"
            detail_item = QTableWidgetItem(detail)
            if handle.error:
                detail_item.setForeground(QBrush(QColor(status_color("error"))))
            self._history_table.setItem(row, 4, detail_item)


__all__ = ["TaskMonitorDialog"]
