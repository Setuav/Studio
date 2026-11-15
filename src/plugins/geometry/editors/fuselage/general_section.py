"""General metadata section for the Fuselage Editor."""

from __future__ import annotations

from .host import FuselageEditorHost


class GeneralSectionMixin(FuselageEditorHost):
    """Manages the General metadata table (name, type) for FuselageEditor."""

    def _create_general_section(self) -> None:
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table([("name", "Name"), ("type", "Type")])
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return

        key = self._property_key(self.general_table, row)
        value = self._property_text(self.general_table, row)
        if key != "name":
            return

        def change() -> None:
            if key == "name":
                self._component["name"] = value.strip()

        self._edit_component("Edit fuselage properties", change)
