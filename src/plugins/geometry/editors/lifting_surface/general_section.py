"""General properties and attachment/symmetry section for LiftingSurfaceEditor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTableWidget, QVBoxLayout

    from setuav_studio.api import StudioAPI


class GeneralSectionMixin:
    """General metadata, parent attachment, and bilateral symmetry logic."""

    _api: StudioAPI
    _component: dict[str, Any]
    _loading: bool
    general_table: QTableWidget

    def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout: ...
    def _property_table(self, rows: list[tuple[str, str]]) -> QTableWidget: ...
    def _property_key(self, table: QTableWidget, row: int) -> str: ...
    def _property_text(self, table: QTableWidget, row: int) -> str: ...
    def _set_property_value(
        self, table: QTableWidget, key: str, value: str, editable: bool = True
    ) -> None: ...
    def _set_property_combo(
        self,
        table: QTableWidget,
        key: str,
        current_value: str,
        items: list[tuple[str, str]],
        on_changed: Any,
    ) -> None: ...
    def _edit_component(self, description: str, change_fn: Any) -> None: ...
    def _geometry(self) -> dict[str, Any]: ...

    def _create_general_section(self) -> None:
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
                ("attach_to", "Attach to"),
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

        # Mounting Target Combo (attach_to fuselage or lifting surface)
        current_attach = str(self._component.get("attach_to") or "")
        parent_options = [("", "(None)")]
        project = getattr(self._api, "current_project", None) or getattr(self._api, "project", None)
        if project and isinstance(project.data.get("components"), list):
            for comp in project.data["components"]:
                if isinstance(comp, dict) and comp.get("type") in (
                    "org.setuav.core:fuselage",
                    "org.setuav.core:lifting-surface",
                ):
                    cid = str(comp.get("id") or "")
                    if cid and cid != self._component.get("id"):
                        cname = str(comp.get("name") or cid)
                        parent_options.append((cid, f"{cname} ({cid})"))
        self._set_property_combo(
            self.general_table,
            "attach_to",
            current_attach,
            parent_options,
            lambda val: self._update_attach_to(val if val else None),
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
        if getattr(self, "_loading", False) or column != 1:
            return
        key = self._property_key(self.general_table, row)
        val_str = self._property_text(self.general_table, row)

        def change() -> None:
            if key == "name":
                self._component["name"] = val_str.strip()

        self._edit_component(f"Edit {key}", change)

    def _update_mirror(self, is_mirrored: bool) -> None:
        if getattr(self, "_loading", False):
            return

        def change() -> None:
            if is_mirrored:
                self._geometry()["mirror"] = True
            else:
                self._geometry().pop("mirror", None)

        self._edit_component("Toggle bilateral lifting surface mirror", change)
        if hasattr(self, "_refresh_planform_table"):
            self._refresh_planform_table()

    def _update_attach_to(self, target_id: str | None) -> None:
        if getattr(self, "_loading", False):
            return

        def change() -> None:
            self._component["attach_to"] = target_id

        self._edit_component("Change component attach_to", change)
