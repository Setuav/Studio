from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.project import ProjectDocument


class ProjectExplorerPanel(QWidget):
    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(ProjectExplorer(api))


class ProjectExplorer(QTreeWidget):
    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self.setColumnCount(2)
        self.setHeaderLabels(["Component / Assembly", "Type"])
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setAnimated(True)
        self.setIndentation(16)
        self.header().setFixedHeight(23)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.currentItemChanged.connect(self._publish_selection)
        self._api = api
        self._item_map: dict[str, QTreeWidgetItem] = {}
        self._element_map: dict[QTreeWidgetItem, dict[str, Any]] = {}

        api.on_project_changed(self.set_project)
        api.on_project_content_changed(self.refresh_project)
        api.on_selection_changed(self._sync_selection)

    def set_project(self, project: ProjectDocument) -> None:
        current_sel_id = (
            self._api.current_selection.get("id")
            if isinstance(self._api.current_selection, dict)
            else None
        )

        self.blockSignals(True)
        try:
            self.clear()
            self._item_map.clear()
            self._element_map.clear()

            components = project.data.get("components", []) if project else []
            raw_components = [item for item in components if isinstance(item, dict)]
            assemblies = project.data.get("assemblies", []) if project else []
            raw_assemblies = [item for item in assemblies if isinstance(item, dict)]

            # Map member component IDs to their containing assembly ID
            comp_to_assembly: dict[str, str] = {}
            for asm in raw_assemblies:
                asm_id = str(asm.get("id") or "")
                members = asm.get("members", {}) if isinstance(asm.get("members"), dict) else {}
                for member_val in members.values():
                    if isinstance(member_val, str):
                        comp_to_assembly[member_val] = asm_id
                    elif isinstance(member_val, list):
                        for mid in member_val:
                            if isinstance(mid, str):
                                comp_to_assembly[mid] = asm_id

            # 1. Create Assembly Tree Items
            for asm in raw_assemblies:
                aid = str(asm.get("id") or "")
                aname = str(asm.get("name") or aid or "Unnamed Assembly")
                atype = self._assembly_type_text(asm)

                tree_item = QTreeWidgetItem([aname, atype])
                tree_item.setData(0, Qt.ItemDataRole.UserRole, aid)
                self._item_map[aid] = tree_item
                self._element_map[tree_item] = asm
                self.addTopLevelItem(tree_item)

            # 2. Create Component Tree Items
            for comp in raw_components:
                cid = str(comp.get("id") or "")
                cname = self._component_name_text(comp)
                ctype = self._component_type_text(comp, raw_components)

                tree_item = QTreeWidgetItem([cname, ctype])
                tree_item.setData(0, Qt.ItemDataRole.UserRole, cid)
                self._item_map[cid] = tree_item
                self._element_map[tree_item] = comp

            # 3. Attach Component Tree Items to Parents / Assemblies / Top-Level
            for comp in raw_components:
                cid = str(comp.get("id") or "")
                tree_item = self._item_map.get(cid)
                if tree_item is None:
                    continue

                parent_id = str(comp.get("parent") or "")
                parent_item = self._item_map.get(parent_id) if parent_id else None

                if parent_item is not None and parent_item is not tree_item:
                    parent_item.addChild(tree_item)
                elif cid in comp_to_assembly:
                    asm_item = self._item_map.get(comp_to_assembly[cid])
                    if asm_item is not None:
                        asm_item.addChild(tree_item)
                    else:
                        self.addTopLevelItem(tree_item)
                else:
                    self.addTopLevelItem(tree_item)

            self.expandAll()
            if current_sel_id and current_sel_id in self._item_map:
                self.setCurrentItem(self._item_map[current_sel_id])
        finally:
            self.blockSignals(False)

    def refresh_project(self, project: ProjectDocument) -> None:
        self.set_project(project)

    @staticmethod
    def _component_name_text(component: dict[str, object]) -> str:
        ctype = str(component.get("type") or component.get("kind") or "")
        params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
        geom = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}

        if ctype == "org.setuav.core:control-surface":
            name = str(component.get("name") or "").strip()
            tag = str(geom.get("tag") or "").strip()
            return name or tag or str(component.get("id") or "Unnamed")

        return str(component.get("name") or component.get("id") or "Unnamed")

    @staticmethod
    def _assembly_type_text(assembly: dict[str, object]) -> str:
        atype = str(assembly.get("type") or "Assembly")
        if atype == "org.setuav.core:electric-propulsion-system":
            return "Electric Propulsion System"
        return atype

    @staticmethod
    def _component_type_text(
        component: dict[str, object],
        components: list[dict[str, object]],
    ) -> str:
        if component.get("kind") == "instance":
            source_id = str(component.get("source") or "")
            source_name = source_id
            for candidate in components:
                if str(candidate.get("id") or "") == source_id:
                    source_name = str(candidate.get("name") or source_id)
                    break
            return f"Instance of {source_name}" if source_name else "Instance"

        ctype = str(component.get("type") or component.get("kind") or "")
        params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
        geom = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}

        if ctype == "org.setuav.core:control-surface":
            cs_type = str(geom.get("type", "aileron")).capitalize()
            return f"Control Surface ({cs_type})"
        if ctype == "org.setuav.core:lifting-surface":
            is_mirrored = geom.get("mirror") is True or component.get("mirror") is True
            return "Lifting Surface (Bilateral)" if is_mirrored else "Lifting Surface"
        if ctype == "org.setuav.core:fuselage":
            return "Fuselage"
        if ctype == "org.setuav.core:motor":
            return "Electric Motor"
        if ctype == "org.setuav.core:propeller":
            return "Propeller"
        if ctype == "org.setuav.core:rotor":
            return "Rotor"
        if ctype == "org.setuav.core:esc":
            return "ESC (Speed Controller)"
        if ctype == "org.setuav.core:battery":
            return "Battery"
        return ctype

    def _publish_selection(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        element = self._element_map.get(current) if current else None
        self._api.set_selection(element)

    def _sync_selection(self, selection: object | None) -> None:
        elem_id = selection.get("id") if isinstance(selection, dict) else None
        if not isinstance(elem_id, str):
            self.clearSelection()
            return
        item = self._item_map.get(elem_id)
        if item is not None:
            if self.currentItem() is not item:
                self.setCurrentItem(item)
        else:
            self.clearSelection()
