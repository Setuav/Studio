"""Base reusable property editor and parameter descriptors for Setuav components."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import set_label_icon
from setuav_studio.ui.property_tables import PropertyTableMixin
from setuav_studio_sdk import ParameterField

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class BaseComponentEditor(PropertyTableMixin, QWidget):
    """Reusable base property editor for Setuav project components styled after Fuselage/Wing editors."""

    def __init__(
        self,
        api: StudioAPI,
        component: dict[str, Any],
        parameter_fields: Sequence[ParameterField] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._component = component
        self._fields = list(parameter_fields)
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

        self._create_general_section()
        if self._fields:
            self._create_parameters_section()

        self._content_layout.addStretch()
        self._load_component()

    def _create_section(
        self,
        title: str,
        icon_name: str | None = None,
        action_widget: QWidget | None = None,
    ) -> QVBoxLayout:
        section = QWidget()
        # Tables already calculate and fix their content height. Prevent the
        # scroll area's spare vertical space from being distributed into the
        # section and separating its header from its table.
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
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
                ("mass", "Mass (g)"),
                ("manufacturer", "Manufacturer"),
                ("model", "Model"),
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_parameters_section(self) -> None:
        layout = self._create_section("Parameters", "fa6s.sliders")
        defs: list[tuple[str, str]] = []
        for f in self._fields:
            display_label = f"{f.label} ({f.unit})" if f.unit else f.label
            defs.append((f.key, display_label))

        self.parameters_table = self._property_table(defs)
        self.parameters_table.cellChanged.connect(self._update_parameter_cell)
        layout.addWidget(self.parameters_table)

    def _load_component(self) -> None:
        self._loading = True
        try:
            # Load General
            self._set_property_value(
                self.general_table, "name", str(self._component.get("name") or "")
            )
            self._set_property_value(
                self.general_table,
                "type",
                str(self._component.get("type") or ""),
                editable=False,
            )
            params = self._component.get("parameters", {})
            mass = self._component.get("mass", params.get("mass", 0))
            self._set_property_value(self.general_table, "mass", mass)
            self._set_property_value(
                self.general_table, "manufacturer", str(self._component.get("manufacturer") or "")
            )
            self._set_property_value(
                self.general_table, "model", str(self._component.get("model") or "")
            )

            # Load Parameters
            if hasattr(self, "parameters_table"):
                project_data = self._api.current_project.data if self._api.current_project else None
                from setuav_studio.plugins.core.configurations import ConfigurationManager

                cfg_mgr = ConfigurationManager(project_data) if project_data else None
                comp_id = self._component.get("id", "")

                for field in self._fields:
                    override_path = f"{comp_id}.parameters.{field.key}"
                    if cfg_mgr and cfg_mgr.is_overridden(override_path):
                        val = cfg_mgr.get_overrides().get(override_path, field.default)
                    else:
                        val = params.get(field.key, field.default)

                    if field.options:
                        formatted_options: list[tuple[str, str]] = []
                        for opt in field.options:
                            if isinstance(opt, tuple):
                                formatted_options.append((opt[0], opt[1]))
                            else:
                                formatted_options.append((str(opt), str(opt)))
                        self._set_property_combo(
                            self.parameters_table,
                            field.key,
                            str(val),
                            formatted_options,
                            lambda new_val, k=field.key: self._on_combo_changed(k, new_val),
                        )
                    else:
                        if isinstance(val, str) and val.strip().startswith("="):
                            str_val = val.strip()
                        elif field.field_type is float:
                            str_val = (
                                f"{float(val):.{field.decimals}f}" if val is not None else "0.0"
                            )
                        else:
                            str_val = str(val if val is not None else "")
                        self._set_property_value(self.parameters_table, field.key, str_val)
        finally:
            self._loading = False

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return

        key = self._property_key(self.general_table, row)
        val_text = self._property_text(self.general_table, row)

        def apply_edit() -> None:
            if key == "name":
                self._component["name"] = val_text
            elif key == "mass":
                num = self._parse_number(val_text) or 0.0
                self._component["mass"] = num
                if "parameters" in self._component and "mass" in self._component["parameters"]:
                    self._component["parameters"]["mass"] = num
            elif key in {"manufacturer", "model"}:
                if val_text:
                    self._component[key] = val_text
                elif key in self._component:
                    self._component.pop(key)

        self._api.edit_component(
            self._component,
            f"Edit {key} of {self._component.get('name', 'component')}",
            apply_edit,
        )

    def _update_parameter_cell(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return

        key = self._property_key(self.parameters_table, row)
        val_text = self._property_text(self.parameters_table, row)
        field = next((f for f in self._fields if f.key == key), None)
        if field is None:
            return

        if isinstance(val_text, str) and val_text.strip().startswith("="):
            final_val: Any = val_text.strip()
        elif field.field_type is int:
            parsed_num = self._parse_number(val_text)
            final_val = int(parsed_num) if parsed_num is not None else field.default
        elif field.field_type is float:
            parsed_num = self._parse_number(val_text)
            final_val = float(parsed_num) if parsed_num is not None else field.default
        else:
            final_val = val_text

        def apply_param() -> None:
            project_data = self._api.current_project.data if self._api.current_project else None
            from setuav_studio.plugins.core.configurations import ConfigurationManager

            cfg_mgr = ConfigurationManager(project_data) if project_data else None
            active_cid = cfg_mgr.get_active_id() if cfg_mgr else None
            if active_cid:
                comp_id = self._component.get("id", "")
                override_path = f"{comp_id}.parameters.{key}"
                cfg_mgr.set_override(active_cid, override_path, final_val)
            else:
                p = self._component.setdefault("parameters", {})
                p[key] = final_val

        self._api.edit_component(
            self._component,
            f"Set {key} of {self._component.get('name', 'component')}",
            apply_param,
        )

    def _on_combo_changed(self, key: str, value: str) -> None:
        if self._loading:
            return

        def apply_param() -> None:
            project_data = self._api.current_project.data if self._api.current_project else None
            from setuav_studio.plugins.core.configurations import ConfigurationManager

            cfg_mgr = ConfigurationManager(project_data) if project_data else None
            active_cid = cfg_mgr.get_active_id() if cfg_mgr else None
            if active_cid:
                comp_id = self._component.get("id", "")
                override_path = f"{comp_id}.parameters.{key}"
                cfg_mgr.set_override(active_cid, override_path, value)
            else:
                p = self._component.setdefault("parameters", {})
                p[key] = value

        self._api.edit_component(
            self._component,
            f"Set {key} of {self._component.get('name', 'component')}",
            apply_param,
        )
