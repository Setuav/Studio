"""Result panel hosting nested dockable analysis tables and charts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api.events import StudioEvents
from setuav_studio.solver.results import PlotDefinition, SolverResult, TableDefinition

from .chart_panel import AnalysisChartPanel
from .table_panel import AnalysisTablePanel

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


class ResultDockWidget(QDockWidget):
    """Clean, native Qt dock widget for analysis charts and tables."""

    closed = Signal()
    activated = Signal()

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self.closed.emit()
        super().closeEvent(event)


class ResultPanel(QWidget):
    """Integrated Result panel providing nested docking inspection of analysis tables & charts."""

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._panes: dict[str, ResultDockWidget] = {}
        self._layout_docks: list[ResultDockWidget] = []

        self._init_ui()
        self._api.on_selection_changed(self._on_selection_changed)
        self._api.on_project_changed(self._on_project_changed)
        self._api.subscribe(str(StudioEvents.ANALYSIS_PLOT_UPDATED), self._on_plot_updated)
        self._api.subscribe(str(StudioEvents.ANALYSIS_PLOT_ACTION), self._on_plot_action)
        self._api.subscribe(str(StudioEvents.ANALYSIS_ADD_TO_VIEW), self._on_add_to_view)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

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
        self._dock_window.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks | QMainWindow.DockOption.AllowNestedDocks
        )
        dummy_central = QWidget(self._dock_container)
        dummy_central.setMaximumSize(0, 0)
        self._dock_window.setCentralWidget(dummy_central)
        dock_container_layout.addWidget(self._dock_window)
        self._dock_window.show()

        self._stack.addWidget(self._dock_container)
        self._stack.setCurrentWidget(self._empty_view)

    def show_plot(
        self,
        result: SolverResult,
        plot: PlotDefinition,
        table: TableDefinition,
        mode: str = "replace",
    ) -> None:
        """Display a plot definition in a dedicated dock widget."""
        key = f"plot:{result.id}:{plot.id}"
        if mode == "replace":
            if len(self._panes) == 1 and key in self._panes:
                dock = self._panes[key]
                dock.raise_()
                dock.setFocus()
                self._stack.setCurrentWidget(self._dock_container)
                return

            for other_key in list(self._panes.keys()):
                if other_key != key:
                    self.close_pane(other_key)

            if key in self._panes:
                dock = self._panes[key]
                dock.raise_()
                dock.setFocus()
                self._stack.setCurrentWidget(self._dock_container)
                return
        elif mode == "add":
            if key in self._panes:
                dock = self._panes[key]
                dock.raise_()
                dock.setFocus()
                self._stack.setCurrentWidget(self._dock_container)
                title = plot.title or plot.id
                self._api.show_status(f"'{title}' is already in view.", "info", 2000)
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
        self._place_dock_progressive(dock)

        self._stack.setCurrentWidget(self._dock_container)

    def show_table(
        self,
        result: SolverResult,
        table: TableDefinition,
        mode: str = "replace",
    ) -> None:
        """Display a tabular dataset in a dedicated dock widget."""
        key = f"table:{result.id}:{table.id}"
        if mode == "replace":
            if len(self._panes) == 1 and key in self._panes:
                dock = self._panes[key]
                dock.raise_()
                dock.setFocus()
                self._stack.setCurrentWidget(self._dock_container)
                return

            for other_key in list(self._panes.keys()):
                if other_key != key:
                    self.close_pane(other_key)

            if key in self._panes:
                dock = self._panes[key]
                dock.raise_()
                dock.setFocus()
                self._stack.setCurrentWidget(self._dock_container)
                return
        elif mode == "add":
            if key in self._panes:
                dock = self._panes[key]
                dock.raise_()
                dock.setFocus()
                self._stack.setCurrentWidget(self._dock_container)
                title = table.title or table.id
                self._api.show_status(f"'{title}' is already in view.", "info", 2000)
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
        self._place_dock_progressive(dock)

        self._stack.setCurrentWidget(self._dock_container)

    def _place_dock_progressive(self, dock: ResultDockWidget) -> None:
        """Place dock into a 2-row x 3-column progressive layout."""
        self._layout_docks = [d for d in self._layout_docks if d in self._panes.values()]
        n = len(self._layout_docks)

        def _safe_split(
            base: ResultDockWidget, target: ResultDockWidget, orientation: Qt.Orientation
        ) -> None:
            if base in self._panes.values():
                self._dock_window.splitDockWidget(base, target, orientation)
            elif self._layout_docks:
                self._dock_window.splitDockWidget(self._layout_docks[-1], target, orientation)
            else:
                self._dock_window.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, target)

        if n == 0:
            self._dock_window.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, dock)
        elif n == 1:
            d0 = self._layout_docks[0]
            _safe_split(d0, dock, Qt.Orientation.Vertical)
            self._dock_window.resizeDocks([d0, dock], [5000, 5000], Qt.Orientation.Vertical)
        elif n == 2:
            d0 = self._layout_docks[0]
            d1 = self._layout_docks[1]
            _safe_split(d0, dock, Qt.Orientation.Horizontal)
            self._dock_window.resizeDocks([d0, dock], [5000, 5000], Qt.Orientation.Horizontal)
            self._dock_window.resizeDocks([d0, d1], [5000, 5000], Qt.Orientation.Vertical)
        elif n == 3:
            d0 = self._layout_docks[0]
            d1 = self._layout_docks[1]
            d2 = self._layout_docks[2]
            _safe_split(d1, dock, Qt.Orientation.Horizontal)
            self._dock_window.resizeDocks([d0, d2], [5000, 5000], Qt.Orientation.Horizontal)
            self._dock_window.resizeDocks([d1, dock], [5000, 5000], Qt.Orientation.Horizontal)
            self._dock_window.resizeDocks([d0, d1], [5000, 5000], Qt.Orientation.Vertical)
        elif n == 4:
            d0 = self._layout_docks[0]
            d1 = self._layout_docks[1]
            d2 = self._layout_docks[2]
            d3 = self._layout_docks[3]
            _safe_split(d2, dock, Qt.Orientation.Horizontal)
            self._dock_window.resizeDocks(
                [d0, d2, dock], [3333, 3333, 3333], Qt.Orientation.Horizontal
            )
            self._dock_window.resizeDocks([d1, d3], [5000, 5000], Qt.Orientation.Horizontal)
            self._dock_window.resizeDocks([d0, d1], [5000, 5000], Qt.Orientation.Vertical)
        elif n == 5:
            d0 = self._layout_docks[0]
            d1 = self._layout_docks[1]
            d2 = self._layout_docks[2]
            d3 = self._layout_docks[3]
            d4 = self._layout_docks[4]
            _safe_split(d3, dock, Qt.Orientation.Horizontal)
            self._dock_window.resizeDocks(
                [d0, d2, d4], [3333, 3333, 3333], Qt.Orientation.Horizontal
            )
            self._dock_window.resizeDocks(
                [d1, d3, dock], [3333, 3333, 3333], Qt.Orientation.Horizontal
            )
            self._dock_window.resizeDocks([d0, d1], [5000, 5000], Qt.Orientation.Vertical)
        else:
            self._dock_window.tabifyDockWidget(self._layout_docks[-1], dock)
            dock.raise_()

        dock.show()
        self._layout_docks.append(dock)

    def close_pane(self, key: str) -> None:
        """Close and remove a specific dock pane."""
        if key not in self._panes:
            return
        dock = self._panes.pop(key)
        if dock in self._layout_docks:
            self._layout_docks.remove(dock)
        self._dock_window.removeDockWidget(dock)
        dock.setParent(None)
        dock.deleteLater()

        if not self._panes:
            self._layout_docks.clear()
            self._stack.setCurrentWidget(self._empty_view)

    def clear_all(self) -> None:
        """Close all open result dock panes and reset to empty state."""
        self._layout_docks.clear()
        for key in list(self._panes.keys()):
            self.close_pane(key)

    def get_chart_panel(self, result_id: str, plot_id: str) -> AnalysisChartPanel | None:
        """Return the active AnalysisChartPanel instance for a given plot if open."""
        key = f"plot:{result_id}:{plot_id}"
        dock = self._panes.get(key)
        if dock is not None:
            widget = dock.widget()
            if isinstance(widget, AnalysisChartPanel):
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
            res = self._api.get_solver_result(result_id)
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
        res: SolverResult | None,
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
        res: SolverResult | None,
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
        res: SolverResult | None,
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
        res = self._api.get_solver_result(result_id)

        if action in ("reset_plot", "reset_view"):
            self._handle_reset_action(action, res, chart, plot_id)
        elif action == "export_png":
            self._handle_export_png_action(res, chart, result_id, plot_id)
        elif action == "export_csv":
            self._handle_export_csv_action(res, chart, plot_id)

    def _open_plots_group(self, result: SolverResult, mode: str = "add") -> None:
        """Open all plots belonging to a solver result."""
        if not result.plots:
            if mode == "replace":
                self.clear_all()
                self._api.show_status("No plots available for this analysis.", "info", 2000)
            return
        if mode == "replace":
            self.clear_all()
        for plot in result.plots.values():
            table = result.tables.get(plot.table_id)
            if table is None and result.tables:
                table = next(iter(result.tables.values()))
            if table:
                self.show_plot(result, plot, table, mode="add")

    def _open_tables_group(self, result: SolverResult, mode: str = "add") -> None:
        """Open all tables belonging to a solver result."""
        if not result.tables:
            if mode == "replace":
                self.clear_all()
                self._api.show_status("No tables available for this analysis.", "info", 2000)
            return
        if mode == "replace":
            self.clear_all()
        for table in result.tables.values():
            self.show_table(result, table, mode="add")

    def _on_selection_changed(self, selection: Any | None) -> None:
        """Respond to global selection changes to open selected tables or plots in single-view mode."""
        if not isinstance(selection, dict):
            return
        kind = selection.get("kind")
        res_id = str(selection.get("result_id", ""))
        result = self._api.get_solver_result(res_id)
        if not result:
            return

        if kind == "analysis_plot":
            plot_id = str(selection.get("plot_id", ""))
            if plot_id in result.plots:
                plot = result.plots[plot_id]
                table = result.tables.get(plot.table_id)
                if table:
                    self.show_plot(result, plot, table, mode="replace")
        elif kind == "analysis_table":
            table_id = str(selection.get("table_id", ""))
            if table_id in result.tables:
                self.show_table(result, result.tables[table_id], mode="replace")
        elif kind == "analysis_plots_group":
            self._open_plots_group(result, mode="replace")
        elif kind == "analysis_tables_group":
            self._open_tables_group(result, mode="replace")

    def _on_add_to_view(self, payload: Any) -> None:
        """Handle 'Add to View' action triggered from context menu to append to 2x3 grid."""
        if not isinstance(payload, dict):
            return
        kind = payload.get("kind")
        res_id = str(payload.get("result_id", ""))
        result = self._api.get_solver_result(res_id)
        if not result:
            return
        if kind == "analysis_plot":
            plot_id = str(payload.get("plot_id", ""))
            if plot_id in result.plots:
                plot = result.plots[plot_id]
                table = result.tables.get(plot.table_id)
                if table:
                    self.show_plot(result, plot, table, mode="add")
        elif kind == "analysis_table":
            table_id = str(payload.get("table_id", ""))
            if table_id in result.tables:
                self.show_table(result, result.tables[table_id], mode="add")
        elif kind == "analysis_plots_group":
            self._open_plots_group(result, mode="add")
        elif kind == "analysis_tables_group":
            self._open_tables_group(result, mode="add")

    def _on_project_changed(self, _project: Any) -> None:
        """Clear all active result panes when switching or closing projects."""
        self.clear_all()
