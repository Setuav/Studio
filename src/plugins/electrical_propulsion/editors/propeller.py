"""Propeller and rotor component property editor with PyThrust APC database picker."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QDialog, QPushButton, QWidget

from plugins.electrical_propulsion.catalog_dialog import ComponentCatalogDialog
from plugins.electrical_propulsion.models.propeller import PropellerModel
from setuav_studio.api import StudioAPI
from setuav_studio.ui.editor.component import BaseComponentEditor
from setuav_studio.ui.widget.button import set_native_button


class PropellerEditor(BaseComponentEditor):
    """Property editor for propellers and rotors (org.setuav.core:propeller / rotor)."""

    FIELDS = PropellerModel.get_scalar_fields()

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
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

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
        dialog = ComponentCatalogDialog(component_type="propeller", parent=self.window())
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_propeller:
            p = dialog.selected_propeller

            def apply_catalog_propeller() -> None:
                self._component["name"] = f"APC {p.metadata.model}"
                self._component["manufacturer"] = p.metadata.manufacturer
                self._component["model"] = p.metadata.model
                params = self._component.setdefault("parameters", {})
                params["diameter"] = round(p.diameter_m * 1000.0, 1)
                params["pitch"] = round(p.pitch_m * 1000.0, 1)
                params["blade_count"] = int(p.metadata.blade_count)

            self._api.edit_component(
                self._component,
                f"Apply catalog propeller '{p.metadata.id}'",
                apply_catalog_propeller,
            )
            self._load_component()
