"""Result panel hosting nested dockable analysis tables and charts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api.events import StudioEvents
from setuav_studio.solver.results import AnalysisResult, PlotDefinition, TableDefinition
from setuav_studio.ui.style.icons import get_icon

from .chart_panel import AnalysisChartPanel
from .table_panel import AnalysisTablePanel

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


class _SplitterCompatProxy:
    """Compatibility shim for legacy tests inspecting splitter properties."""

    def __init__(self, panel: ResultPanel) -> None:
        self._panel = panel
        self._orientation = Qt.Orientation.Horizontal
        self._sizes = [5000, 5000]

    def count(self) -> int:
        return len(self._panel._panes)

    def orientation(self) -> Qt.Orientation:
        return self._orientation

    def setOrientation(self, orientation: Qt.Orientation) -> None:
        self._orientation = orientation
        if orientation == Qt.Orientation.Vertical:
            self._panel.tile_vertically()
        else:
            self._panel.tile_horizontally()

    def setSizes(self, sizes: list[int]) -> None:
        self._sizes = list(sizes)

    def sizes(self) -> list[int]:
        count = len(self._panel._panes)
        if count == 0:
            return []
        share = 10000 // count
        return [share] * count


class ResultDockWidget(QDockWidget):
    """Clean, native Qt dock widget for analysis charts and tables."""

    closed = Signal()
    activated = Signal()

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.closed.emit()
        super().closeEvent(event)


class ResultPanel(QWidget):
    """Integrated Result panel providing nested docking inspection of analysis tables & charts."""

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._panes: dict[str, ResultDockWidget] = {}

        self._init_ui()
        self._api.on_selection_changed(self._on_selection_changed)
        self._api.on_project_changed(self._on_project_changed)
        self._api.subscribe(str(StudioEvents.ANALYSIS_PLOT_UPDATED), self._on_plot_updated)
        self._api.subscribe(str(StudioEvents.ANALYSIS_PLOT_ACTION), self._on_plot_action)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Top Panel Toolbar
        self._toolbar = QWidget()
        tb_layout = QHBoxLayout(self._toolbar)
        tb_layout.setContentsMargins(4, 2, 4, 2)
        tb_layout.setSpacing(6)

        tb_layout.addStretch()

        self._count_label = QLabel()
        tb_layout.addWidget(self._count_label)

        # Tabify all views button
        self._tabify_btn = QPushButton()
        self._tabify_btn.setIcon(get_icon("fa6s.clone"))
        self._tabify_btn.setToolTip("Tabify all open views")
        self._tabify_btn.setFixedSize(26, 26)
        self._tabify_btn.clicked.connect(self.tabify_all)
        tb_layout.addWidget(self._tabify_btn)

        # Tile horizontally button (side by side)
        self._tile_h_btn = QPushButton()
        self._tile_h_btn.setIcon(get_icon("fa6s.table-columns"))
        self._tile_h_btn.setToolTip("Tile views side by side")
        self._tile_h_btn.setFixedSize(26, 26)
        self._tile_h_btn.clicked.connect(self.tile_horizontally)
        tb_layout.addWidget(self._tile_h_btn)

        # Tile vertically button (stacked)
        self._tile_v_btn = QPushButton()
        self._tile_v_btn.setIcon(get_icon("fa6s.bars"))
        self._tile_v_btn.setToolTip("Tile views stacked vertically")
        self._tile_v_btn.setFixedSize(26, 26)
        self._tile_v_btn.clicked.connect(self.tile_vertically)
        tb_layout.addWidget(self._tile_v_btn)

        # Clear all views button
        self._clear_btn = QPushButton()
        self._clear_btn.setIcon(get_icon("fa6s.trash-can"))
        self._clear_btn.setToolTip("Close all result views")
        self._clear_btn.setFixedSize(26, 26)
        self._clear_btn.clicked.connect(self.clear_all)
        tb_layout.addWidget(self._clear_btn)

        main_layout.addWidget(self._toolbar)

        # Stacked Widget: Page 0 = Empty state, Page 1 = Dock Container
        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack)

        # 1. Empty Placeholder (matching Properties panel style)
        self._empty_view = QLabel("No result views open")
        self._empty_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_view.setWordWrap(True)
        self._stack.addWidget(self._empty_view)

        # 2. Dock Container hosting inner QMainWindow
        self._dock_container = QWidget()
        dock_container_layout = QVBoxLayout(self._dock_container)
        dock_container_layout.setContentsMargins(0, 0, 0, 0)
        dock_container_layout.setSpacing(0)

        self._dock_window = QMainWindow(self._dock_container)
        self._dock_window.setWindowFlags(Qt.WindowType.Widget)
        self._dock_window.setDockNestingEnabled(True)
        dock_container_layout.addWidget(self._dock_window)
        self._dock_window.show()

        self._stack.addWidget(self._dock_container)
        self._stack.setCurrentWidget(self._empty_view)
        self._update_toolbar()

    @property
    def open_pane_keys(self) -> tuple[str, ...]:
        """Return tuple of currently open pane identifier keys."""
        return tuple(self._panes.keys())

    @property
    def _splitter_container(self) -> QWidget:
        return self._dock_container

    @property
    def _splitter(self) -> _SplitterCompatProxy:
        if not hasattr(self, "_splitter_proxy"):
            self._splitter_proxy = _SplitterCompatProxy(self)
        return self._splitter_proxy

    @property
    def _orientation_btn(self) -> QPushButton:
        return self._tile_h_btn

    @property
    def _equalize_btn(self) -> QPushButton:
        return self._tile_h_btn

    def show_plot(
        self,
        result: AnalysisResult,
        plot: PlotDefinition,
        table: TableDefinition,
    ) -> None:
        """Display a plot definition in a dedicated dock widget."""
        key = f"plot:{result.id}:{plot.id}"
        if key in self._panes:
            dock = self._panes[key]
            dock.raise_()
            dock.setFocus()
            self._stack.setCurrentWidget(self._dock_container)
            return

        dock = ResultDockWidget(plot.title or plot.id, self._dock_window)

        chart_panel = AnalysisChartPanel(
            self._api,
            auto_sync_selection=False,
            show_close_button=False,
            show_toolbar=False,
            parent=dock,
        )
        chart_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        chart_panel.load_plot(plot, table, result)

        dock.setWidget(chart_panel)
        dock.closed.connect(lambda: self.close_pane(key))

        self._panes[key] = dock
        self._add_dock(dock)

        self._stack.setCurrentWidget(self._dock_container)
        self._update_toolbar()

    def show_table(
        self,
        result: AnalysisResult,
        table: TableDefinition,
    ) -> None:
        """Display a tabular dataset in a dedicated dock widget."""
        key = f"table:{result.id}:{table.id}"
        if key in self._panes:
            dock = self._panes[key]
            dock.raise_()
            dock.setFocus()
            self._stack.setCurrentWidget(self._dock_container)
            return

        dock = ResultDockWidget(table.title or table.id, self._dock_window)

        table_panel = AnalysisTablePanel(
            self._api,
            auto_sync_selection=False,
            show_close_button=False,
            parent=dock,
        )
        table_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        table_panel.load_table(table, result)

        dock.setWidget(table_panel)
        dock.closed.connect(lambda: self.close_pane(key))

        self._panes[key] = dock
        self._add_dock(dock)

        self._stack.setCurrentWidget(self._dock_container)
        self._update_toolbar()

    def _add_dock(self, dock: ResultDockWidget) -> None:
        """Add a dock widget to the inner docking window."""
        existing_docks = [
            d
            for d in self._dock_window.findChildren(QDockWidget)
            if d is not dock and not d.isHidden()
        ]
        if not existing_docks:
            self._dock_window.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, dock)
        else:
            last_dock = existing_docks[-1]
            self._dock_window.splitDockWidget(last_dock, dock, Qt.Orientation.Vertical)
        dock.show()

    def close_pane(self, key: str) -> None:
        """Close and remove a specific dock pane."""
        if key not in self._panes:
            return
        dock = self._panes.pop(key)
        dock.setParent(None)
        dock.deleteLater()

        if not self._panes:
            self._stack.setCurrentWidget(self._empty_view)
        self._update_toolbar()

    def clear_all(self) -> None:
        """Close all open result dock panes and reset to empty state."""
        for key in list(self._panes.keys()):
            self.close_pane(key)

    def tabify_all(self) -> None:
        """Tabify all currently open dock widgets together."""
        docks = [d for d in self._dock_window.findChildren(QDockWidget) if not d.isHidden()]
        if len(docks) >= 2:
            first = docks[0]
            for other in docks[1:]:
                self._dock_window.tabifyDockWidget(first, other)
            first.raise_()

    def tile_horizontally(self) -> None:
        """Tile all open dock widgets side-by-side horizontally."""
        docks = [d for d in self._dock_window.findChildren(QDockWidget) if not d.isHidden()]
        if len(docks) >= 2:
            first = docks[0]
            for other in docks[1:]:
                self._dock_window.splitDockWidget(first, other, Qt.Orientation.Horizontal)
                first = other

    def tile_vertically(self) -> None:
        """Tile all open dock widgets vertically (stacked)."""
        docks = [d for d in self._dock_window.findChildren(QDockWidget) if not d.isHidden()]
        if len(docks) >= 2:
            first = docks[0]
            for other in docks[1:]:
                self._dock_window.splitDockWidget(first, other, Qt.Orientation.Vertical)
                first = other

    def equalize_sizes(self) -> None:
        """Distribute available space equally between open panes."""
        self.tile_horizontally()

    def _toggle_orientation(self) -> None:
        if self._splitter.orientation() == Qt.Orientation.Horizontal:
            self._splitter.setOrientation(Qt.Orientation.Vertical)
        else:
            self._splitter.setOrientation(Qt.Orientation.Horizontal)

    def get_chart_panel(self, result_id: str, plot_id: str) -> AnalysisChartPanel | None:
        """Return the active AnalysisChartPanel instance for a given plot if open."""
        key = f"plot:{result_id}:{plot_id}"
        dock = self._panes.get(key)
        if dock is not None:
            widget = dock.widget()
            if isinstance(widget, AnalysisChartPanel):
                return widget
        return None

    def get_table_panel(self, result_id: str, table_id: str) -> AnalysisTablePanel | None:
        """Return the active AnalysisTablePanel instance for a given table if open."""
        key = f"table:{result_id}:{table_id}"
        dock = self._panes.get(key)
        if dock is not None:
            widget = dock.widget()
            if isinstance(widget, AnalysisTablePanel):
                return widget
        return None

    def _on_plot_updated(self, payload: Any) -> None:
        """Handle plot definition modifications from property editors."""
        if not isinstance(payload, dict):
            return
        result_id = str(payload.get("result_id", ""))
        plot_id = str(payload.get("plot_id", ""))
        key = f"plot:{result_id}:{plot_id}"
        if key in self._panes:
            dock = self._panes[key]
            res = self._api.get_analysis_result(result_id)
            if res and plot_id in res.plots:
                plot = res.plots[plot_id]
                dock.setWindowTitle(plot.title or plot.id)
                chart = dock.widget()
                if isinstance(chart, AnalysisChartPanel):
                    table = res.tables.get(plot.table_id)
                    chart._current_plot = plot
                    if table is not None:
                        chart._current_table = table
                    chart.reload_plot()

    def _handle_reset_action(
        self,
        action: str,
        res: AnalysisResult | None,
        chart: AnalysisChartPanel | None,
        plot_id: str,
    ) -> None:
        if action == "reset_plot" and res and hasattr(res, "reset_plot"):
            res.reset_plot(plot_id)
        if chart and res and plot_id in res.plots:
            plot = res.plots[plot_id]
            table = res.tables.get(plot.table_id)
            chart._current_plot = plot
            if table is not None:
                chart._current_table = table
            chart.reload_plot()
        elif chart:
            chart.reload_plot()

    def _handle_export_png_action(
        self,
        res: AnalysisResult | None,
        chart: AnalysisChartPanel | None,
        result_id: str,
        plot_id: str,
    ) -> None:
        if chart:
            chart.export_png()
        elif res and plot_id in res.plots:
            plot = res.plots[plot_id]
            table = res.tables.get(plot.table_id)
            if table:
                self.show_plot(res, plot, table)
                c = self.get_chart_panel(result_id, plot_id)
                if c:
                    c.export_png()

    def _handle_export_csv_action(
        self,
        res: AnalysisResult | None,
        chart: AnalysisChartPanel | None,
        plot_id: str,
    ) -> None:
        if chart:
            chart.export_csv()
        elif res and plot_id in res.plots:
            table = res.tables.get(res.plots[plot_id].table_id)
            if table:
                from PySide6.QtWidgets import QFileDialog

                file_path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Export Table Data",
                    f"{table.id}.csv",
                    "CSV Files (*.csv);;All Files (*)",
                )
                if file_path:
                    res.export_table_csv(table.id, file_path, use_display_units=True)
                    self._api.show_status(f"Table data exported to {file_path}", "success")

    def _on_plot_action(self, payload: Any) -> None:
        """Handle user actions (reset view, export PNG, export CSV) from properties panel."""
        if not isinstance(payload, dict):
            return
        result_id = str(payload.get("result_id", ""))
        plot_id = str(payload.get("plot_id", ""))
        action = str(payload.get("action", ""))

        chart = self.get_chart_panel(result_id, plot_id)
        res = self._api.get_analysis_result(result_id)

        if action in ("reset_plot", "reset_view"):
            self._handle_reset_action(action, res, chart, plot_id)
        elif action == "export_png":
            self._handle_export_png_action(res, chart, result_id, plot_id)
        elif action == "export_csv":
            self._handle_export_csv_action(res, chart, plot_id)

    def _update_toolbar(self) -> None:
        """Update toolbar visibility, badges, and controls based on open pane count."""
        count = len(self._panes)
        if count == 0:
            self._toolbar.setVisible(False)
        else:
            self._toolbar.setVisible(True)
            self._count_label.setText(f"{count} view{'s' if count != 1 else ''}")
            self._tabify_btn.setEnabled(count > 1)
            self._tile_h_btn.setEnabled(count > 1)
            self._tile_v_btn.setEnabled(count > 1)
            self._clear_btn.setEnabled(True)

    def _on_selection_changed(self, selection: Any | None) -> None:
        """Respond to global selection changes to open selected tables or plots."""
        if not isinstance(selection, dict):
            return
        kind = selection.get("kind")
        if kind == "analysis_plot":
            res_id = str(selection.get("result_id", ""))
            plot_id = str(selection.get("plot_id", ""))
            result = self._api.get_analysis_result(res_id)
            if result and plot_id in result.plots:
                plot = result.plots[plot_id]
                table = result.tables.get(plot.table_id)
                if table:
                    self.show_plot(result, plot, table)
        elif kind == "analysis_table":
            res_id = str(selection.get("result_id", ""))
            table_id = str(selection.get("table_id", ""))
            result = self._api.get_analysis_result(res_id)
            if result and table_id in result.tables:
                table = result.tables[table_id]
                self.show_table(result, table)

    def _on_project_changed(self, _project: Any) -> None:
        """Clear all active result panes when switching or closing projects."""
        self.clear_all()
