"""General properties and attachment/symmetry section for LiftingSurfaceEditor."""

from __future__ import annotations

from .host import LiftingSurfaceEditorHost


class GeneralSectionMixin(LiftingSurfaceEditorHost):
    """General metadata and bilateral symmetry logic."""

    def _create_general_section(self) -> None:
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
                ("mirror", "Symmetry / Mirror"),
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _load_general(self) -> None:
        self._set_property_value(self.general_table, "name", str(self._component.get("name") or ""))
        self._set_property_value(
            self.general_table, "type", str(self._component.get("type") or ""), editable=False
        )

        # Symmetry / Mirror
        is_mirror = "true" if self._geometry().get("mirror") is True else "false"
        self._set_property_combo(
            self.general_table,
            "mirror",
            is_mirror,
            [("false", "Single (No Mirror)"), ("true", "Bilateral (Mirror XZ)")],
            lambda val: self._update_mirror(val == "true"),
        )

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return
        key = self._property_key(self.general_table, row)
        val_str = self._property_text(self.general_table, row)

        def change() -> None:
            if key == "name":
                self._component["name"] = val_str.strip()

        self._edit_component(f"Edit {key}", change)

    def _update_mirror(self, is_mirrored: bool) -> None:
        if self._loading:
            return

        def change() -> None:
            if is_mirrored:
                self._geometry()["mirror"] = True
            else:
                self._geometry().pop("mirror", None)

        self._edit_component("Toggle bilateral lifting surface mirror", change)
        self._refresh_planform_table()
