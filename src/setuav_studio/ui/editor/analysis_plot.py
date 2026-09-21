"""Properties panel editor for a selected Analysis Plot, supporting multi-series curves and exports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api.events import StudioEvents
from setuav_studio.solver.results import (
    AnalysisResult,
    PlotDefinition,
    PlotSeriesDef,
    TableDefinition,
)
from setuav_studio.ui.style.icons import get_icon, set_label_icon
from setuav_studio.ui.widget.color_picker import ColorPickerWidget
from setuav_studio.ui.widget.table import PropertyTableMixin

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI

DEFAULT_PALETTE = ["#2196F3", "#4CAF50", "#FF9800", "#E91E63", "#9C27B0", "#00BCD4"]


class AnalysisPlotPropertyEditor(PropertyTableMixin, QWidget):
    """Property editor for AnalysisPlot objects providing axes, curve styling and export controls."""

    def __init__(
        self,
        api: StudioAPI,
        plot_item: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._result_id = str(plot_item.get("result_id") or "")
        self._plot_id = str(plot_item.get("plot_id") or "")
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 8)
        self._content_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._create_details_section()
        self._create_axes_section()
        self._create_series_section()
        self._create_actions_section()
        self._content_layout.addStretch()

        self._load_data()

    def _get_result_and_plot(
        self,
    ) -> tuple[AnalysisResult | None, PlotDefinition | None, TableDefinition | None]:
        if not self._result_id or not self._plot_id:
            return None, None, None
        res = self._api.get_analysis_result(self._result_id)
        if res is None or self._plot_id not in res.plots:
            return None, None, None
        plot = res.plots[self._plot_id]
        table = res.tables.get(plot.table_id)
        return res, plot, table

    def _create_section(
        self,
        title: str,
        icon_name: str | None = None,
        action_widget: QWidget | None = None,
    ) -> QVBoxLayout:
        section = QWidget()
        section.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QWidget()
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

        if icon_name:
            icon_label = QLabel()
            set_label_icon(icon_label, icon_name)
            icon_label.setFixedSize(14, 14)
            header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        if action_widget is not None:
            header_layout.addWidget(action_widget)

        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_details_section(self) -> None:
        layout = self._create_section("Plot Details", "fa6s.chart-line")
        self.details_table = self._property_table(
            [
                ("title", "Title"),
                ("result_name", "Result"),
                ("table_name", "Data Table"),
            ]
        )
        self.details_table.cellChanged.connect(self._on_details_cell_changed)
        layout.addWidget(self.details_table)

    def _create_axes_section(self) -> None:
        layout = self._create_section("Axes Configuration", "fa6s.arrows-left-right")
        self.axes_table = self._property_table(
            [
                ("x_column", "X-Axis Column"),
            ]
        )
        layout.addWidget(self.axes_table)

    def _create_series_section(self) -> None:
        self._add_curve_btn = QPushButton("+ Add Curve")
        self._add_curve_btn.setIcon(get_icon("fa6s.plus"))
        self._add_curve_btn.setToolTip("Add a new data series / curve to this plot")
        self._add_curve_btn.clicked.connect(self._on_add_curve_clicked)

        layout = self._create_section(
            "Curves & Series", "fa6s.chart-simple", action_widget=self._add_curve_btn
        )

        self._series_container = QWidget()
        self._series_layout = QVBoxLayout(self._series_container)
        self._series_layout.setContentsMargins(0, 0, 0, 0)
        self._series_layout.setSpacing(8)
        layout.addWidget(self._series_container)

    def _create_actions_section(self) -> None:
        layout = self._create_section("Actions", "fa6s.wrench")

        btn_bar = QWidget()
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(0, 2, 0, 0)
        btn_layout.setSpacing(6)

        self._reset_btn = QPushButton("Reset Plot")
        self._reset_btn.setIcon(get_icon("fa6s.rotate-left"))
        self._reset_btn.setToolTip("Reset plot configuration to initial analysis output")
        self._reset_btn.clicked.connect(self._on_reset_plot_clicked)
        btn_layout.addWidget(self._reset_btn)

        self._export_png_btn = QPushButton("Export PNG")
        self._export_png_btn.setIcon(get_icon("fa6s.image"))
        self._export_png_btn.setToolTip("Export chart as a high-resolution PNG image")
        self._export_png_btn.clicked.connect(self._on_export_png_clicked)
        btn_layout.addWidget(self._export_png_btn)

        self._export_csv_btn = QPushButton("Export CSV")
        self._export_csv_btn.setIcon(get_icon("fa6s.file-csv"))
        self._export_csv_btn.setToolTip("Export underlying table data to CSV")
        self._export_csv_btn.clicked.connect(self._on_export_csv_clicked)
        btn_layout.addWidget(self._export_csv_btn)

        layout.addWidget(btn_bar)

    def _load_data(self) -> None:
        res, plot, table = self._get_result_and_plot()
        if res is None or plot is None or table is None:
            return

        self._loading = True
        try:
            # 1. Details
            self._set_property_value(
                self.details_table, "title", plot.title or plot.id, editable=True
            )
            self._set_property_value(
                self.details_table, "result_name", res.name or res.id, editable=False
            )
            self._set_property_value(
                self.details_table, "table_name", table.title or table.id, editable=False
            )

            # 2. X-Axis combo
            col_options = [(c.key, c.header_text(use_display_units=True)) for c in table.columns]
            self._set_property_combo(
                self.axes_table,
                "x_column",
                plot.x_column,
                col_options,
                on_changed=self._on_x_column_changed,
            )

            # 3. Build curves list
            self._build_series_ui()
        finally:
            self._loading = False

    def _build_series_ui(self) -> None:
        # Clear existing series widgets
        while self._series_layout.count():
            item = self._series_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()

        _, plot, table = self._get_result_and_plot()
        if plot is None or table is None:
            return

        col_options = [(c.key, c.header_text(use_display_units=True)) for c in table.columns]

        for i, series in enumerate(plot.series):
            card = self._create_series_card(i, series, col_options, table)
            self._series_layout.addWidget(card)

    def _create_series_card(
        self,
        index: int,
        series: PlotSeriesDef,
        col_options: list[tuple[str, str]],
        table: TableDefinition,
    ) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Row 1: Label + Delete button (if > 1 curve)
        r1 = QWidget()
        r1_layout = QHBoxLayout(r1)
        r1_layout.setContentsMargins(0, 0, 0, 0)
        r1_layout.setSpacing(6)

        lbl_name = QLabel("Label:")
        lbl_name.setFixedWidth(64)
        r1_layout.addWidget(lbl_name)

        y_col_def = table.get_column_def(series.y_column)
        default_label = series.label or (y_col_def.label if y_col_def else series.y_column)
        label_edit = QLineEdit(default_label)
        label_edit.textChanged.connect(
            lambda text, idx=index: self._on_curve_label_changed(idx, text)
        )
        r1_layout.addWidget(label_edit, 1)

        _, plot, _ = self._get_result_and_plot()
        if plot is not None and len(plot.series) > 1:
            del_btn = QPushButton()
            del_btn.setIcon(get_icon("fa6s.trash-can"))
            del_btn.setToolTip("Remove curve")
            del_btn.setFixedSize(22, 22)
            del_btn.clicked.connect(lambda _=False, idx=index: self._on_delete_curve(idx))
            r1_layout.addWidget(del_btn)

        layout.addWidget(r1)

        # Row 2: Y Column
        r2 = QWidget()
        r2_layout = QHBoxLayout(r2)
        r2_layout.setContentsMargins(0, 0, 0, 0)
        r2_layout.setSpacing(6)

        lbl_y = QLabel("Y Column:")
        lbl_y.setFixedWidth(64)
        r2_layout.addWidget(lbl_y)

        y_combo = QComboBox()
        for key, text in col_options:
            y_combo.addItem(text, key)
        cur_idx = y_combo.findData(series.y_column)
        if cur_idx >= 0:
            y_combo.setCurrentIndex(cur_idx)
        y_combo.currentTextChanged.connect(
            lambda _text, idx=index, cb=y_combo: self._on_curve_y_changed(idx, cb)
        )
        r2_layout.addWidget(y_combo, 1)
        layout.addWidget(r2)

        # Row 3: Color & Style
        r3 = QWidget()
        r3_layout = QHBoxLayout(r3)
        r3_layout.setContentsMargins(0, 0, 0, 0)
        r3_layout.setSpacing(6)

        lbl_color = QLabel("Color:")
        lbl_color.setFixedWidth(64)
        r3_layout.addWidget(lbl_color)

        c_hex = series.color or DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)]
        color_picker = ColorPickerWidget(
            initial_color=c_hex,
            on_changed=lambda col_hex, idx=index: self._on_curve_color_changed(idx, col_hex),
        )
        r3_layout.addWidget(color_picker)

        lbl_style = QLabel("Style:")
        r3_layout.addWidget(lbl_style)

        style_combo = QComboBox()
        style_combo.addItems(["Solid", "Dashed", "Dotted"])
        current_style = series.style.title() if series.style else "Solid"
        s_idx = style_combo.findText(current_style)
        if s_idx >= 0:
            style_combo.setCurrentIndex(s_idx)
        style_combo.currentTextChanged.connect(
            lambda s_text, idx=index: self._on_curve_style_changed(idx, s_text)
        )
        r3_layout.addWidget(style_combo)

        layout.addWidget(r3)

        # Separator line if multiple curves
        if plot is not None and index < len(plot.series) - 1:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFrameShadow(QFrame.Shadow.Sunken)
            layout.addWidget(sep)

        return container

    def _on_details_cell_changed(self, row: int, _col: int) -> None:
        if self._loading:
            return
        prop = self._property_key(self.details_table, row)
        if prop == "title":
            val = self._property_text(self.details_table, row).strip()
            _, plot, _ = self._get_result_and_plot()
            if plot is not None and val != plot.title:
                plot.title = val
                self._notify_plot_changed()
                self._api.notify_project_content_changed()

    def _on_x_column_changed(self, new_x_col: str) -> None:
        if self._loading:
            return
        _, plot, _ = self._get_result_and_plot()
        if plot is not None and plot.x_column != new_x_col:
            plot.x_column = new_x_col
            self._notify_plot_changed()

    def _on_curve_y_changed(self, index: int, combo: QComboBox) -> None:
        if self._loading:
            return
        key = combo.currentData()
        if not key:
            return
        _, plot, table = self._get_result_and_plot()
        if plot is not None and 0 <= index < len(plot.series):
            series = plot.series[index]
            if series.y_column != str(key):
                series.y_column = str(key)
                if table is not None:
                    col_def = table.get_column_def(str(key))
                    if col_def and (not series.label or series.label == series.y_column):
                        series.label = col_def.label
                self._build_series_ui()
                self._notify_plot_changed()

    def _on_curve_label_changed(self, index: int, new_label: str) -> None:
        if self._loading:
            return
        _, plot, _ = self._get_result_and_plot()
        if plot is not None and 0 <= index < len(plot.series):
            plot.series[index].label = new_label
            self._notify_plot_changed()

    def _on_curve_color_changed(self, index: int, new_color: str) -> None:
        if self._loading:
            return
        _, plot, _ = self._get_result_and_plot()
        if plot is not None and 0 <= index < len(plot.series):
            plot.series[index].color = new_color
            self._notify_plot_changed()

    def _on_curve_style_changed(self, index: int, style_text: str) -> None:
        if self._loading:
            return
        _, plot, _ = self._get_result_and_plot()
        if plot is not None and 0 <= index < len(plot.series):
            plot.series[index].style = style_text.lower()
            self._notify_plot_changed()

    def _on_add_curve_clicked(self) -> None:
        _, plot, table = self._get_result_and_plot()
        if plot is None or table is None:
            return

        used_cols = {s.y_column for s in plot.series}
        candidate_col = next(
            (c.key for c in table.columns if c.key not in used_cols and c.key != plot.x_column),
            table.columns[0].key if table.columns else "y",
        )
        col_def = table.get_column_def(candidate_col)
        label = col_def.label if col_def else candidate_col
        color = DEFAULT_PALETTE[len(plot.series) % len(DEFAULT_PALETTE)]

        new_series = PlotSeriesDef(
            y_column=candidate_col,
            label=label,
            style="solid",
            color=color,
        )
        plot.series.append(new_series)
        self._build_series_ui()
        self._notify_plot_changed()

    def _on_delete_curve(self, index: int) -> None:
        _, plot, _ = self._get_result_and_plot()
        if plot is not None and len(plot.series) > 1 and 0 <= index < len(plot.series):
            plot.series.pop(index)
            self._build_series_ui()
            self._notify_plot_changed()

    def _on_reset_plot_clicked(self) -> None:
        res = self._api.get_analysis_result(self._result_id)
        if res is not None and hasattr(res, "reset_plot"):
            res.reset_plot(self._plot_id)
            if self._api.current_project is not None:
                self._api.current_project.add_analysis_result(res)
        self._load_data()
        self._notify_plot_changed()
        self._api.publish(
            str(StudioEvents.ANALYSIS_PLOT_ACTION),
            {"result_id": self._result_id, "plot_id": self._plot_id, "action": "reset_plot"},
        )

    def _on_reset_view_clicked(self) -> None:
        self._on_reset_plot_clicked()

    def _on_export_png_clicked(self) -> None:
        self._api.publish(
            str(StudioEvents.ANALYSIS_PLOT_ACTION),
            {"result_id": self._result_id, "plot_id": self._plot_id, "action": "export_png"},
        )

    def _on_export_csv_clicked(self) -> None:
        self._api.publish(
            str(StudioEvents.ANALYSIS_PLOT_ACTION),
            {"result_id": self._result_id, "plot_id": self._plot_id, "action": "export_csv"},
        )

    def _notify_plot_changed(self) -> None:
        if self._loading:
            return
        res, _, _ = self._get_result_and_plot()
        if res is not None and self._api.current_project is not None:
            self._api.current_project.add_analysis_result(res)
        self._api.publish(
            str(StudioEvents.ANALYSIS_PLOT_UPDATED),
            {"result_id": self._result_id, "plot_id": self._plot_id},
        )
