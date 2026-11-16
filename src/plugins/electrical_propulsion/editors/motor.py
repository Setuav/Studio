"""Motor component property editor with PyThrust database catalog picker."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDialog, QPushButton, QWidget

from plugins.electrical_propulsion.catalog_dialog import ComponentCatalogDialog
from plugins.electrical_propulsion.models.motor import MotorModel
from setuav_studio.api import StudioAPI
from setuav_studio.ui.editor.component import BaseComponentEditor
from setuav_studio.ui.widget.button import set_native_button

_ATTACH_TARGET_TYPES = ("org.setuav.core:fuselage", "org.setuav.core:lifting-surface")


class MotorEditor(BaseComponentEditor):
    """Property editor for brushless and DC motors (org.setuav.core:motor)."""

    FIELDS = MotorModel.get_scalar_fields()

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)

    def _create_general_section(self) -> None:
        catalog_btn = QPushButton("Catalog…", self)
        set_native_button(catalog_btn, "fa6s.database")
        catalog_btn.clicked.connect(self._open_catalog)

        layout = self._create_section("General", "fa6s.circle-info", action_widget=catalog_btn)
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
                ("mass", "Mass"),
                ("manufacturer", "Manufacturer"),
                ("model", "Model"),
                ("attach_to", "Attach to"),
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _load_custom_data(self) -> None:
        self._load_attach_to()

    def _load_attach_to(self) -> None:
        current = str(self._component.get("attach_to") or "")
        options: list[tuple[str, str]] = [("", "(None)")]
        project = self._api.project
        if project is not None and isinstance(project.data.get("components"), list):
            for comp in project.data["components"]:
                if isinstance(comp, dict) and comp.get("type") in _ATTACH_TARGET_TYPES:
                    cid = str(comp.get("id") or "")
                    if cid:
                        cname = str(comp.get("name") or cid)
                        options.append((cid, f"{cname} ({cid})"))
        if current and not any(value == current for value, _label in options):
            options.insert(1, (current, f"⚠ {current} (Not Found)"))
        self._set_property_combo(
            self.general_table,
            "attach_to",
            current,
            options,
            lambda value: self._on_attach_to_changed(value or None),
        )

    def _on_attach_to_changed(self, target_id: str | None) -> None:
        if self._loading or self._component.get("attach_to") == target_id:
            return

        def apply() -> None:
            self._component["attach_to"] = target_id

        self._api.edit_component(self._component, "Change motor attach_to", apply)

    def _load_component(self) -> None:
        super()._load_component()
        self._set_property_value(
            self.general_table,
            "manufacturer",
            str(self._component.get("manufacturer") or ""),
            editable=False,
        )
        self._set_property_value(
            self.general_table,
            "model",
            str(self._component.get("model") or ""),
            editable=False,
        )

    def _open_catalog(self) -> None:
        dialog = ComponentCatalogDialog(component_type="motor", parent=self.window())
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_motor:
            m = dialog.selected_motor

            def apply_catalog_motor() -> None:
                self._component["name"] = m.name
                self._component["manufacturer"] = m.manufacturer
                self._component["model"] = m.name
                self._component["mass"] = m.weight_g
                params = self._component.setdefault("parameters", {})
                params["kv"] = float(m.kv)
                params["resistance"] = float(m.resistance)
                params["no_load_current"] = float(m.io or 0.0)
                params["max_current"] = float(m.max_current)
                params["max_power"] = float(m.max_power)

            self._api.edit_component(
                self._component, f"Apply catalog motor '{m.name}'", apply_catalog_motor
            )
            self._load_component()
