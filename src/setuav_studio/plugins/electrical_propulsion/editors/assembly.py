"""Electric Propulsion System assembly property editor styled after Fuselage/Wing editors."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.icons import get_icon
from setuav_studio.plugin_system import StudioAPI
from setuav_studio.ui.property_tables import PropertyTableMixin


class ElectricPropulsionSystemEditor(PropertyTableMixin, QWidget):
    """Property editor for electric-propulsion-system assemblies styled after Setuav standards."""

    def __init__(
        self,
        api: StudioAPI,
        assembly: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._assembly = assembly
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
        self._create_members_section()

        self._content_layout.addStretch()
        self._load_assembly()

    def _create_section(self, title: str, icon_name: str | None = None) -> QVBoxLayout:
        section = QWidget()
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
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
            pixmap = get_icon(icon_name).pixmap(14, 14)
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(14, 14)
            header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addWidget(header)
        self._content_layout.addWidget(section)
        return layout

    def _create_general_section(self) -> None:
        layout = self._create_section("General", "fa6s.circle-info")
        self.general_table = self._property_table(
            [
                ("name", "Name"),
                ("type", "Type"),
            ]
        )
        self.general_table.cellChanged.connect(self._update_general)
        layout.addWidget(self.general_table)

    def _create_members_section(self) -> None:
        layout = self._create_section("Assembly Members", "fa6s.link")
        self.members_table = self._property_table(
            [
                ("battery", "Battery Pack"),
                ("controller", "Speed Controller (ESC)"),
                ("motor", "Motor"),
                ("propulsor", "Propeller / Rotor"),
            ]
        )
        layout.addWidget(self.members_table)

    def _load_assembly(self) -> None:
        self._loading = True
        try:
            self._set_property_value(
                self.general_table, "name", str(self._assembly.get("name") or "")
            )
            self._set_property_value(
                self.general_table,
                "type",
                str(self._assembly.get("type") or ""),
                editable=False,
            )

            # Retrieve project components for options
            project = self._api.current_project
            components = project.data.get("components", []) if project and project.data else []

            batteries = [
                (c.get("id"), f"{c.get('name', c.get('id'))} ({c.get('id')})")
                for c in components
                if c.get("type") == "org.setuav.core:battery"
            ]
            escs = [
                (c.get("id"), f"{c.get('name', c.get('id'))} ({c.get('id')})")
                for c in components
                if c.get("type") == "org.setuav.core:esc"
            ]
            motors = [
                (c.get("id"), f"{c.get('name', c.get('id'))} ({c.get('id')})")
                for c in components
                if c.get("type") == "org.setuav.core:motor"
            ]
            props = [
                (c.get("id"), f"{c.get('name', c.get('id'))} ({c.get('id')})")
                for c in components
                if c.get("type") in {"org.setuav.core:propeller", "org.setuav.core:rotor"}
            ]

            none_opt = [("", "(None)")]

            members = self._assembly.get("members", {})
            bat_id = members.get("battery", "")
            esc_id = members.get("controllers", [""])[0] if members.get("controllers") else ""
            mot_id = members.get("motors", [""])[0] if members.get("motors") else ""
            prp_id = members.get("propulsors", [""])[0] if members.get("propulsors") else ""

            self._set_property_combo(
                self.members_table,
                "battery",
                bat_id,
                none_opt + [(b[0], b[1]) for b in batteries],
                lambda val: self._on_member_changed("battery", val),
            )
            self._set_property_combo(
                self.members_table,
                "controller",
                esc_id,
                none_opt + [(e[0], e[1]) for e in escs],
                lambda val: self._on_member_changed("controller", val),
            )
            self._set_property_combo(
                self.members_table,
                "motor",
                mot_id,
                none_opt + [(m[0], m[1]) for m in motors],
                lambda val: self._on_member_changed("motor", val),
            )
            self._set_property_combo(
                self.members_table,
                "propulsor",
                prp_id,
                none_opt + [(p[0], p[1]) for p in props],
                lambda val: self._on_member_changed("propulsor", val),
            )
        finally:
            self._loading = False

    def _update_general(self, row: int, column: int) -> None:
        if self._loading or column != 1:
            return

        key = self._property_key(self.general_table, row)
        val_text = self._property_text(self.general_table, row)

        def apply_name() -> None:
            if key == "name":
                self._assembly["name"] = val_text

        self._api.edit_component(
            self._assembly,
            f"Edit {key} of {self._assembly.get('name', 'assembly')}",
            apply_name,
        )

    def _on_member_changed(self, role: str, member_id: str) -> None:
        if self._loading:
            return

        def apply_members() -> None:
            members = self._assembly.setdefault("members", {})
            if role == "battery":
                if member_id:
                    members["battery"] = member_id
                elif "battery" in members:
                    members.pop("battery")
            elif role == "controller":
                if member_id:
                    members["controllers"] = [member_id]
                elif "controllers" in members:
                    members.pop("controllers")
            elif role == "motor":
                if member_id:
                    members["motors"] = [member_id]
                elif "motors" in members:
                    members.pop("motors")
            elif role == "propulsor":
                if member_id:
                    members["propulsors"] = [member_id]
                elif "propulsors" in members:
                    members.pop("propulsors")

        self._api.edit_component(
            self._assembly,
            f"Update {role} in {self._assembly.get('name', 'assembly')}",
            apply_members,
        )

