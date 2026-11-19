"""Properties panel editor for a selected Analysis Configuration styled as a property table."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.model.expression import set_expression
from setuav_studio.ui.style.icons import get_icon, set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin

if TYPE_CHECKING:
    from collections.abc import Sequence

    from setuav_studio.api import ParameterField, StudioAPI
    from setuav_studio.solver.base import SolverConfig
    from setuav_studio.solver.results import SolverResult


class SolverConfigPropertyEditor(PropertyTableMixin, QWidget):
    """Property editor for SolverConfig objects matching application UI standards."""

    def __init__(
        self,
        api: StudioAPI,
        config_item: dict[str, Any] | SolverConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        if isinstance(config_item, dict):
            self._config_id = str(config_item["config_id"])
            self._result_id: str | None = config_item.get("result_id")
        else:
            self._config_id = config_item.config_id
            self._result_id = None

        self._loading = False
        self._cached_result: SolverResult | None = None

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

        self._create_general_section()
        self._create_parameters_section()
        self._create_results_section()
        self._content_layout.addStretch()
        self._load_data()

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
        layout.setSpacing(3)

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

    def _create_general_section(self) -> None:
        layout = self._create_section("Analysis Details", "fa6s.gears")
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("solver_id", "Solver ID"),
                ("config_id", "Config ID"),
            ]
        )
        self.general_table.cellChanged.connect(self._on_general_cell_changed)
        layout.addWidget(self.general_table)

    def _create_parameters_section(self) -> None:
        layout = self._create_section("Analysis Parameters", "fa6s.sliders")
        self.parameters_table = self._property_table([])
        self.parameters_table.cellChanged.connect(self._on_parameter_cell_changed)
        layout.addWidget(self.parameters_table)

    def _create_results_section(self) -> None:
        layout = self._create_section("Results Summary", "fa6s.square-poll-vertical")
        self.results_table = self._property_table([])
        layout.addWidget(self.results_table)

        btn_bar = QWidget()
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(6)

        self._open_chart_btn = QPushButton("View Plot")
        self._open_chart_btn.setIcon(get_icon("fa6s.chart-line"))
        self._open_chart_btn.clicked.connect(self._on_open_chart_clicked)
        btn_layout.addWidget(self._open_chart_btn)

        self._open_table_btn = QPushButton("View Table")
        self._open_table_btn.setIcon(get_icon("fa6s.table"))
        self._open_table_btn.clicked.connect(self._on_open_table_clicked)
        btn_layout.addWidget(self._open_table_btn)

        self._export_btn = QPushButton("Export All")
        self._export_btn.setIcon(get_icon("fa6s.file-export"))
        self._export_btn.clicked.connect(self._on_export_results_clicked)
        btn_layout.addWidget(self._export_btn)

        layout.addWidget(btn_bar)
        parent_widget = layout.parentWidget()
        self._results_section_widget = parent_widget if parent_widget is not None else btn_bar

    def _get_config(self) -> SolverConfig | None:
        if self._result_id:
            res = self._api.get_solver_result(self._result_id)
            if res is not None:
                return res.config
        if self._api.project is None or not self._config_id:
            return None
        return self._api.project.get_solver_config(self._config_id)

    def _load_data(self) -> None:
        config = self._get_config()
        if config is None:
            return

        self._loading = True
        try:
            # 1. General Details
            self._set_property_value(self.general_table, "name", config.name)
            self._set_property_value(
                self.general_table, "solver_id", config.solver_id, editable=False
            )
            self._set_property_value(
                self.general_table, "config_id", config.config_id, editable=False
            )

            # 2. Analysis Parameters
            fields = self._parameter_fields(config)
            if fields:
                self.bind_parametric_properties(
                    self.parameters_table,
                    config.parameters,
                    fields,
                    on_changed=self._on_schema_parameter_changed,
                    api=self._api,
                )
            else:
                self._configure_property_table(self.parameters_table, [("empty", "No Parameters")])
                self._set_property_value(self.parameters_table, "empty", "—", editable=False)

            # 3. Results Summary
            project = self._api.project
            matching = project.results_of_config(config.config_id) if project is not None else []
            result = matching[-1] if matching else None
            self._cached_result = result
            if result is not None and result.summary:
                summary_fields: list[tuple[str, str]] = []
                for k, item in result.summary.items():
                    summary_fields.append((k, item.label))
                self._configure_property_table(self.results_table, summary_fields)
                for k, item in result.summary.items():
                    val, unit = item.display_value_and_unit()
                    unit_str = f" {unit}" if unit else ""
                    disp_str = (
                        f"{val:.4f}{unit_str}" if isinstance(val, float) else f"{val}{unit_str}"
                    )
                    self._set_property_value(self.results_table, k, disp_str, editable=False)
                self._results_section_widget.setVisible(True)
            else:
                self._results_section_widget.setVisible(False)
        finally:
            self._loading = False

    def _on_open_chart_clicked(self) -> None:
        self._api.show_panel("studio:result")
        if self._cached_result and self._cached_result.plots:
            first_plot_id = next(iter(self._cached_result.plots))
            self._api.set_selection(
                {
                    "kind": "analysis_plot",
                    "result_id": self._cached_result.id,
                    "plot_id": first_plot_id,
                }
            )

    def _on_open_table_clicked(self) -> None:
        self._api.show_panel("studio:result")
        if self._cached_result and self._cached_result.tables:
            first_table_id = next(iter(self._cached_result.tables))
            self._api.set_selection(
                {
                    "kind": "analysis_table",
                    "result_id": self._cached_result.id,
                    "table_id": first_table_id,
                }
            )

    def _on_export_results_clicked(self) -> None:
        if not self._cached_result:
            return
        target_dir = QFileDialog.getExistingDirectory(self, "Export Results Directory")
        if target_dir:
            exported = self._cached_result.export_csv(target_dir, use_display_units=True)
            self._api.show_status(f"Exported {len(exported)} files to {target_dir}", "success")

    def _on_general_cell_changed(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.general_table, row)
        val_text = self._property_text(self.general_table, row)
        config = self._get_config()
        if config is None:
            return

        if key == "name" and val_text.strip():
            config.name = val_text.strip()
            self._api.add_solver_config(config)

    def _parameter_fields(self, config: SolverConfig) -> Sequence[ParameterField]:
        solver_cls = self._api.solvers.get_solver_class(config.solver_id)
        return solver_cls.PARAMETER_FIELDS if solver_cls is not None else ()

    def _on_parameter_cell_changed(self, row: int, column: int) -> None:
        """Commit a user edit of a plain-text parameter item.

        Numeric, choice and color parameters commit through their cell widget;
        read-only parameters are displayed only and never written back.
        """
        if (
            self._loading
            or column != 1
            or self.parameters_table.cellWidget(row, column) is not None
        ):
            return
        config = self._get_config()
        item = self.parameters_table.item(row, column)
        if config is None or item is None:
            return
        key = self._property_key(self.parameters_table, row)
        field = next((f for f in self._parameter_fields(config) if f.key == key), None)
        if field is None or field.readonly:
            return
        self._on_schema_parameter_changed(key, item.text(), None)

    def _on_schema_parameter_changed(self, key: str, new_val: Any, expression: str | None) -> None:
        if self._loading:
            return
        config = self._get_config()
        if config is None:
            return
        config.parameters[key] = new_val
        set_expression(config.parameters, key, expression)
        self._api.add_solver_config(config)
