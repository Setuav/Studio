"""Result panel hosting resizable, side-by-side analysis tables and charts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.solver.results import AnalysisResult, PlotDefinition, TableDefinition
from setuav_studio.ui.style.icons import get_icon

from .chart_panel import AnalysisChartPanel
from .table_panel import AnalysisTablePanel

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class ResultPanel(QWidget):
    """Integrated Result panel providing side-by-side resizable inspection of analysis tables & charts."""

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._panes: dict[str, QWidget] = {}

        self._init_ui()
        self._api.on_selection_changed(self._on_selection_changed)
        self._api.on_project_changed(self._on_project_changed)

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Top Panel Toolbar
        self._toolbar = QWidget()
        tb_layout = QHBoxLayout(self._toolbar)
        tb_layout.setContentsMargins(4, 2, 4, 2)
        tb_layout.setSpacing(6)

        self._count_label = QLabel()
        self._count_label.setStyleSheet(
            "color: #888888; font-size: 10px; background: rgba(128,128,128,0.15); "
            "padding: 2px 6px; border-radius: 3px;"
        )
        tb_layout.addWidget(self._count_label)

        tb_layout.addStretch()

        # Split orientation toggle button (Horizontal vs Vertical)
        self._orientation_btn = QPushButton()
        self._orientation_btn.setIcon(get_icon("fa6s.table-columns"))
        self._orientation_btn.setToolTip("Toggle view orientation: Side by side / Stacked")
        self._orientation_btn.setFixedSize(26, 26)
        self._orientation_btn.clicked.connect(self._toggle_orientation)
        tb_layout.addWidget(self._orientation_btn)

        # Equalize view sizes button
        self._equalize_btn = QPushButton()
        self._equalize_btn.setIcon(get_icon("fa6s.arrows-left-right"))
        self._equalize_btn.setToolTip("Distribute view sizes equally")
        self._equalize_btn.setFixedSize(26, 26)
        self._equalize_btn.clicked.connect(self.equalize_sizes)
        tb_layout.addWidget(self._equalize_btn)

        # Clear all views button
        self._clear_btn = QPushButton()
        self._clear_btn.setIcon(get_icon("fa6s.trash-can"))
        self._clear_btn.setToolTip("Close all result views")
        self._clear_btn.setFixedSize(26, 26)
        self._clear_btn.clicked.connect(self.clear_all)
        tb_layout.addWidget(self._clear_btn)

        main_layout.addWidget(self._toolbar)

        # Stacked Widget: Page 0 = Empty state, Page 1 = Splitter Container
        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack)

        # 1. Empty Placeholder (matching Properties panel style)
        self._empty_view = QLabel("No result views open")
        self._empty_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_view.setWordWrap(True)
        self._stack.addWidget(self._empty_view)

        # 2. Splitter Container
        self._splitter_container = QWidget()
        splitter_layout = QVBoxLayout(self._splitter_container)
        splitter_layout.setContentsMargins(0, 0, 0, 0)
        splitter_layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setStyleSheet(
            "QSplitter::handle { background: rgba(128, 128, 128, 0.2); width: 4px; height: 4px; } "
            "QSplitter::handle:hover { background: rgba(0, 122, 255, 0.6); }"
        )
        splitter_layout.addWidget(self._splitter)

        self._stack.addWidget(self._splitter_container)
        self._stack.setCurrentWidget(self._empty_view)
        self._update_toolbar()

    @property
    def open_pane_keys(self) -> tuple[str, ...]:
        """Return tuple of currently open pane identifier keys."""
        return tuple(self._panes.keys())

    def show_plot(
        self,
        result: AnalysisResult,
        plot: PlotDefinition,
        table: TableDefinition,
    ) -> None:
        """Display a plot definition in a dedicated pane inside the splitter."""
        key = f"plot:{result.id}:{plot.id}"
        if key in self._panes:
            pane = self._panes[key]
            pane.setFocus()
            return

        chart_panel = AnalysisChartPanel(
            self._api,
            auto_sync_selection=False,
            show_close_button=True,
            parent=self._splitter,
        )
        chart_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        chart_panel.close_requested.connect(lambda: self.close_pane(key))
        chart_panel.load_plot(plot, table, result)

        self._splitter.addWidget(chart_panel)
        self._panes[key] = chart_panel

        self.equalize_sizes()
        self._stack.setCurrentWidget(self._splitter_container)
        self._update_toolbar()

    def show_table(
        self,
        result: AnalysisResult,
        table: TableDefinition,
    ) -> None:
        """Display a tabular dataset in a dedicated pane inside the splitter."""
        key = f"table:{result.id}:{table.id}"
        if key in self._panes:
            pane = self._panes[key]
            pane.setFocus()
            return

        table_panel = AnalysisTablePanel(
            self._api,
            auto_sync_selection=False,
            show_close_button=True,
            parent=self._splitter,
        )
        table_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        table_panel.close_requested.connect(lambda: self.close_pane(key))
        table_panel.load_table(table, result)

        self._splitter.addWidget(table_panel)
        self._panes[key] = table_panel

        self.equalize_sizes()
        self._stack.setCurrentWidget(self._splitter_container)
        self._update_toolbar()

    def close_pane(self, key: str) -> None:
        """Close and remove a specific pane from the splitter."""
        if key not in self._panes:
            return
        pane = self._panes.pop(key)
        pane.setParent(None)
        pane.deleteLater()

        if not self._panes:
            self._stack.setCurrentWidget(self._empty_view)
        else:
            self.equalize_sizes()
        self._update_toolbar()

    def clear_all(self) -> None:
        """Close all open result panes and reset to empty state."""
        for key in list(self._panes.keys()):
            self.close_pane(key)

    def equalize_sizes(self) -> None:
        """Distribute available space equally between all open panes."""
        count = len(self._panes)
        if count > 0:
            total_size = 10000
            share = total_size // count
            self._splitter.setSizes([share] * count)

    def _toggle_orientation(self) -> None:
        """Toggle splitter layout between horizontal (side-by-side) and vertical (stacked)."""
        if self._splitter.orientation() == Qt.Orientation.Horizontal:
            self._splitter.setOrientation(Qt.Orientation.Vertical)
            self._orientation_btn.setIcon(get_icon("fa6s.bars"))
            self._orientation_btn.setToolTip("Layout: Stacked (click to switch to Side by side)")
        else:
            self._splitter.setOrientation(Qt.Orientation.Horizontal)
            self._orientation_btn.setIcon(get_icon("fa6s.table-columns"))
            self._orientation_btn.setToolTip("Layout: Side by side (click to switch to Stacked)")
        self.equalize_sizes()

    def _update_toolbar(self) -> None:
        """Update toolbar visibility, badges, and controls based on open pane count."""
        count = len(self._panes)
        if count == 0:
            self._toolbar.setVisible(False)
        else:
            self._toolbar.setVisible(True)
            self._count_label.setText(f"{count} view{'s' if count != 1 else ''}")
            self._orientation_btn.setEnabled(True)
            self._equalize_btn.setEnabled(True)
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
