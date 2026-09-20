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

from setuav_studio.ui.style.icons import get_icon, set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI
    from setuav_studio.model.analysis_config import AnalysisConfig
    from setuav_studio.solver.results import AnalysisResult


class AnalysisConfigPropertyEditor(PropertyTableMixin, QWidget):
    """Property editor for AnalysisConfig objects matching application UI standards."""

    def __init__(
        self,
        api: StudioAPI,
        config_item: dict[str, Any] | AnalysisConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        if isinstance(config_item, dict):
            self._config_id = str(config_item.get("config_id") or config_item.get("id") or "")
            self._result_id: str | None = config_item.get("result_id")
        else:
            self._config_id = config_item.config_id
            self._result_id = None

        self._loading = False
        self._cached_result: AnalysisResult | None = None

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
        self._create_options_section()
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

    def _create_options_section(self) -> None:
        layout = self._create_section("Execution Options", "fa6s.gear")
        self.options_table = self._property_table([])
        self.options_table.cellChanged.connect(self._on_option_cell_changed)
        layout.addWidget(self.options_table)

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

    def _get_config(self) -> AnalysisConfig | None:
        if self._result_id:
            res = self._api.get_analysis_result(self._result_id)
            if res is not None:
                if hasattr(res, "analysis_config"):
                    return res.analysis_config
                if hasattr(res.config, "to_analysis_config"):
                    return res.config.to_analysis_config()
        if self._api.current_project is None or not self._config_id:
            return None
        return self._api.current_project.get_analysis_config(self._config_id)

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
            param_fields = [(k, k.replace("_", " ").title()) for k in config.parameters]
            if not param_fields:
                param_fields = [("empty", "No Parameters")]
            self._configure_property_table(self.parameters_table, param_fields)
            if "empty" not in dict(param_fields):
                for k, v in config.parameters.items():
                    self._set_property_value(self.parameters_table, k, str(v))
            else:
                self._set_property_value(self.parameters_table, "empty", "—", editable=False)

            # 3. Execution Options
            opt_fields = [(k, k.replace("_", " ").title()) for k in config.options]
            if not opt_fields:
                opt_fields = [("empty", "No Options")]
            self._configure_property_table(self.options_table, opt_fields)
            if "empty" not in dict(opt_fields):
                for k, v in config.options.items():
                    self._set_property_value(self.options_table, k, str(v))
            else:
                self._set_property_value(self.options_table, "empty", "—", editable=False)

            # 4. Results Summary
            matching = [
                r
                for r in self._api.get_analysis_results().values()
                if getattr(getattr(r, "config", None), "config_id", None) == config.config_id
                or getattr(r, "solver_id", None) == config.solver_id
            ]
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
        self._api.show_panel("core:result")
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
        self._api.show_panel("core:result")
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
            self._api.add_analysis_config(config)

    def _on_parameter_cell_changed(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.parameters_table, row)
        if key == "empty":
            return
        val_text = self._property_text(self.parameters_table, row)
        config = self._get_config()
        if config is None:
            return

        parsed_val: Any = val_text
        try:
            parsed_val = float(val_text) if "." in val_text else int(val_text)
        except ValueError:
            parsed_val = val_text

        config.parameters[key] = parsed_val
        self._api.add_analysis_config(config)

    def _on_option_cell_changed(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.options_table, row)
        if key == "empty":
            return
        val_text = self._property_text(self.options_table, row)
        config = self._get_config()
        if config is None:
            return

        parsed_val: Any = val_text
        try:
            parsed_val = float(val_text) if "." in val_text else int(val_text)
        except ValueError:
            parsed_val = val_text

        config.options[key] = parsed_val
        self._api.add_analysis_config(config)
