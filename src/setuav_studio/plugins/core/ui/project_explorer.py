from typing import Any

from PySide6.QtCore import QLine, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QKeyEvent, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProxyStyle,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.project import ProjectDocument
from setuav_studio.ui.icons import get_icon


_GEOMETRY_COMPONENT_ICONS = {
    "org.setuav.core:fuselage": "geometry_add_fuselage",
    "org.setuav.core:lifting-surface": "geometry_add_lifting_surface",
    "org.setuav.core:control-surface": "geometry_add_control_surface",
}


class _ProjectExplorerBranchStyle(QProxyStyle):
    """Draw classic dotted tree branches with square expand controls."""

    def sizeFromContents(self, contents_type, option, size, widget=None) -> QSize:
        result = super().sizeFromContents(contents_type, option, size, widget)
        if contents_type == QStyle.ContentsType.CT_ItemViewItem:
            result.setHeight(result.height() + 4)
        return result

    def drawPrimitive(self, element, option, painter, widget=None) -> None:
        if element != QStyle.PrimitiveElement.PE_IndicatorBranch:
            super().drawPrimitive(element, option, painter, widget)
            return

        rect = option.rect
        if rect.isEmpty():
            return

        state = option.state
        has_item = bool(state & QStyle.StateFlag.State_Item)
        has_sibling = bool(state & QStyle.StateFlag.State_Sibling)
        has_children = bool(state & QStyle.StateFlag.State_Children)
        is_open = bool(state & QStyle.StateFlag.State_Open)
        center_x = rect.center().x()
        center_y = rect.center().y()

        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

            branch_color = option.palette.color(QPalette.ColorRole.Text)
            branch_color.setAlpha(120)
            branch_pen = QPen(branch_color)
            branch_pen.setWidth(1)
            branch_pen.setCosmetic(True)
            branch_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(branch_pen)

            if has_sibling:
                painter.drawLine(
                    QLine(center_x, rect.top(), center_x, rect.bottom())
                )
            elif has_item:
                painter.drawLine(QLine(center_x, rect.top(), center_x, center_y))

            if has_item:
                painter.drawLine(QLine(center_x, center_y, rect.right(), center_y))

            if has_children:
                box_size = min(9, max(5, rect.height() - 2))
                if box_size % 2 == 0:
                    box_size -= 1
                half = box_size // 2
                box = QRect(
                    center_x - half,
                    center_y - half,
                    box_size,
                    box_size,
                )
                painter.fillRect(box, option.palette.color(QPalette.ColorRole.Base))

                control_pen = QPen(option.palette.color(QPalette.ColorRole.Text))
                control_pen.setWidth(1)
                control_pen.setCosmetic(True)
                painter.setPen(control_pen)
                painter.drawRect(box.adjusted(0, 0, -1, -1))
                painter.drawLine(
                    QLine(box.left() + 2, center_y, box.right() - 2, center_y)
                )
                if not is_open:
                    painter.drawLine(
                        QLine(center_x, box.top() + 2, center_x, box.bottom() - 2)
                    )
        finally:
            painter.restore()


class ProjectExplorerPanel(QWidget):
    """Panel containing search box and the clean model tree."""

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Search bar
        search_box = QWidget()
        s_layout = QHBoxLayout(search_box)
        s_layout.setContentsMargins(2, 2, 2, 2)
        s_layout.setSpacing(4)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter model...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(
            get_icon("fa6s.magnifying-glass"),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        s_layout.addWidget(self.search_edit)
        layout.addWidget(search_box)

        self.explorer = ProjectExplorer(api)
        layout.addWidget(self.explorer, 1)

        self.search_edit.textChanged.connect(self.explorer.filter_items)

    def update_theme_style(self) -> None:
        self.explorer.refresh_project()
        self.explorer.viewport().update()


class ProjectExplorer(QTreeWidget):
    """Clean, single-column model tree with hierarchy."""

    def __init__(self, api: StudioAPI) -> None:
        super().__init__()
        self.setColumnCount(1)
        self.setHeaderHidden(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setAlternatingRowColors(False)
        self.setAnimated(True)
        self.setIndentation(20)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        self._branch_style = _ProjectExplorerBranchStyle()
        self.setStyle(self._branch_style)

        self.currentItemChanged.connect(self._publish_selection)
        self.itemChanged.connect(self._rename_item)
        self.customContextMenuRequested.connect(self._open_context_menu)
        self._api = api
        self._item_map: dict[str, QTreeWidgetItem] = {}
        self._element_map: dict[QTreeWidgetItem, dict[str, Any]] = {}
        self._project_root_item: QTreeWidgetItem | None = None
        self._geometry_group_item: QTreeWidgetItem | None = None

        api.on_project_changed(self.set_project)
        api.on_project_content_changed(self.refresh_project)
        api.on_selection_changed(self._sync_selection)

    def set_project(self, project: ProjectDocument) -> None:
        project_is_selected = self._api.current_selection is project.data
        geometry_group_is_selected = self.currentItem() is self._geometry_group_item
        current_sel_id = (
            self._api.current_selection.get("id")
            if isinstance(self._api.current_selection, dict)
            else None
        )
        fresh_selection: dict[str, Any] | None = None

        self.blockSignals(True)
        try:
            self.clear()
            self._item_map.clear()
            self._element_map.clear()
            self._project_root_item = None
            self._geometry_group_item = None

            project_name = str(
                project.data.get("name")
                or project.location.name
                or "Unnamed Project"
            )
            project_item = QTreeWidgetItem([project_name])
            if not project.read_only:
                project_item.setFlags(
                    project_item.flags() | Qt.ItemFlag.ItemIsEditable
                )
            project_item.setToolTip(0, f"Project: {project_name}")
            self._element_map[project_item] = project.data
            self._project_root_item = project_item
            self.addTopLevelItem(project_item)

            components = project.data.get("components", []) if project else []
            raw_components = [item for item in components if isinstance(item, dict)]
            assemblies = project.data.get("assemblies", []) if project else []
            raw_assemblies = [item for item in assemblies if isinstance(item, dict)]

            if any(
                self._geometry_icon_source(component, raw_components) is not None
                for component in raw_components
            ):
                geometry_group = QTreeWidgetItem(["Geometry"])
                geometry_group.setToolTip(0, "Geometry components")
                self._geometry_group_item = geometry_group
                project_item.addChild(geometry_group)

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

                tree_item = QTreeWidgetItem([aname])
                if not project.read_only:
                    tree_item.setFlags(
                        tree_item.flags() | Qt.ItemFlag.ItemIsEditable
                    )
                tree_item.setToolTip(0, f"{aname} ({atype})")
                tree_item.setData(0, Qt.ItemDataRole.UserRole, aid)
                self._item_map[aid] = tree_item
                self._element_map[tree_item] = asm
                project_item.addChild(tree_item)

            # 2. Create Component Tree Items
            for comp in raw_components:
                cid = str(comp.get("id") or "")
                cname = self._component_name_text(comp)
                ctype = self._component_type_text(comp, raw_components)

                tree_item = QTreeWidgetItem([cname])
                if not project.read_only:
                    tree_item.setFlags(
                        tree_item.flags() | Qt.ItemFlag.ItemIsEditable
                    )
                icon_source = self._geometry_icon_source(comp, raw_components)
                if icon_source is not None:
                    tree_item.setIcon(0, get_icon(icon_source))
                tree_item.setToolTip(0, f"{cname} ({ctype})")
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
                        project_item.addChild(tree_item)
                elif (
                    self._geometry_group_item is not None
                    and self._geometry_icon_source(comp, raw_components) is not None
                ):
                    self._geometry_group_item.addChild(tree_item)
                else:
                    project_item.addChild(tree_item)

            self.expandAll()
            if project_is_selected:
                self.setCurrentItem(project_item)
                fresh_selection = project.data
            elif geometry_group_is_selected and self._geometry_group_item is not None:
                self.setCurrentItem(self._geometry_group_item)
            elif current_sel_id and current_sel_id in self._item_map:
                selected_item = self._item_map[current_sel_id]
                self.setCurrentItem(selected_item)
                fresh_selection = self._element_map.get(selected_item)
        finally:
            self.blockSignals(False)

        if current_sel_id and self._api.current_selection is not fresh_selection:
            self._api.set_selection(fresh_selection)

    def refresh_project(self, project: ProjectDocument) -> None:
        self.set_project(project)

    def filter_items(self, query: str) -> None:
        """Filter tree items based on search query."""
        q = query.strip().lower()

        def apply_filter(item: QTreeWidgetItem) -> bool:
            name = item.text(0).lower()
            tooltip = item.toolTip(0).lower()
            matches_self = (q in name) or (q in tooltip) if q else True

            child_matched = False
            for i in range(item.childCount()):
                child = item.child(i)
                if apply_filter(child):
                    child_matched = True

            visible = matches_self or child_matched
            item.setHidden(not visible)
            if visible and q:
                item.setExpanded(True)
            return visible

        for i in range(self.topLevelItemCount()):
            apply_filter(self.topLevelItem(i))

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

    @staticmethod
    def _geometry_icon_source(
        component: dict[str, Any],
        components: list[dict[str, Any]],
    ) -> str | None:
        component_type = component.get("type")
        if isinstance(component_type, str):
            icon_source = _GEOMETRY_COMPONENT_ICONS.get(component_type)
            if icon_source is not None:
                return icon_source
        if component.get("kind") != "instance":
            return None

        source_id = component.get("source")
        source = next(
            (
                candidate
                for candidate in components
                if candidate.get("id") == source_id
            ),
            None,
        )
        if source is None:
            return None
        source_type = source.get("type")
        return (
            _GEOMETRY_COMPONENT_ICONS.get(source_type)
            if isinstance(source_type, str)
            else None
        )

    def _publish_selection(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current is self._geometry_group_item:
            self._api.set_selection(None)
            return
        element = self._element_map.get(current) if current else None
        self._api.set_selection(element)

    def _sync_selection(self, selection: object | None) -> None:
        if selection is None and self.currentItem() is self._geometry_group_item:
            return
        project = self._api.current_project
        if project is not None and selection is project.data:
            if (
                self._project_root_item is not None
                and self.currentItem() is not self._project_root_item
            ):
                self.setCurrentItem(self._project_root_item)
            return

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

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() == Qt.Key.Key_Delete
            and self.state() != QAbstractItemView.State.EditingState
        ):
            self._delete_item(self.currentItem())
            event.accept()
            return
        super().keyPressEvent(event)

    def _open_context_menu(self, position: QPoint) -> None:
        item = self.itemAt(position)
        if item is None or item is self._geometry_group_item:
            return

        self.setCurrentItem(item)
        can_edit = self._can_edit_project()
        menu = QMenu(self)
        rename_action = menu.addAction(get_icon("edit"), "Rename")
        rename_action.setEnabled(can_edit)
        delete_action = None
        if item is not self._project_root_item:
            delete_action = menu.addAction(get_icon("remove"), "Delete")
            delete_action.setEnabled(can_edit)

        chosen_action = menu.exec(self.viewport().mapToGlobal(position))
        if chosen_action is rename_action:
            self.editItem(item, 0)
        elif delete_action is not None and chosen_action is delete_action:
            self._delete_item(item)

    def _rename_item(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        element = self._element_map.get(item)
        if element is None:
            return

        element_id = str(element.get("id") or "")
        kind = (
            "project"
            if item is self._project_root_item
            else self._element_kind(element_id)
        )
        old_name = str(element.get("name") or "").strip()
        old_label = (
            str(element.get("name") or element_id or "Unnamed Project")
            if kind in {"project", "assembly"}
            else self._component_name_text(element)
        )
        new_name = item.text(0).strip()
        if not self._can_edit_project():
            self._restore_item_text(item, old_label)
            return
        if not new_name:
            self._restore_item_text(item, old_label)
            self._api.show_status("Name cannot be empty", "warning", 3000)
            return
        if new_name == old_name:
            self._restore_item_text(item, new_name)
            return

        def change() -> None:
            fresh_element = self._find_element(element_id, kind)
            if fresh_element is not None:
                fresh_element["name"] = new_name

        description = (
            f"Rename project to {new_name}"
            if kind == "project"
            else f"Rename {old_label} to {new_name}"
        )
        self._api.edit_project(description, change)
        fresh_element = self._find_element(element_id, kind)
        if fresh_element is not None:
            self._api.set_selection(fresh_element)
        self._api.show_status(f'Renamed "{old_label}" to "{new_name}"', "success", 3000)

    def _delete_item(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            return
        if item is self._project_root_item:
            self._api.show_status("The project root cannot be deleted", "warning", 3000)
            return
        if not self._can_edit_project():
            self._api.show_status("This project is read-only", "warning", 3000)
            return

        element = self._element_map.get(item)
        if element is None:
            return
        element_id = str(element.get("id") or "")
        if not element_id:
            return
        element_name = str(element.get("name") or element_id)
        kind = self._element_kind(element_id)

        component_ids: set[str] = set()
        assembly_ids: set[str] = set()
        if kind == "assembly":
            assembly_ids.add(element_id)
        else:
            component_ids = self._dependent_component_ids(element_id)
            assembly_ids = self._assemblies_invalidated_by(component_ids)

        details: list[str] = []
        dependent_count = max(0, len(component_ids) - 1)
        if dependent_count:
            details.append(
                f"{dependent_count} structurally dependent item(s) will also be deleted."
            )
        if assembly_ids and kind != "assembly":
            details.append(
                f"{len(assembly_ids)} assembly group(s) that would become invalid "
                "will also be removed; their remaining components will be kept."
            )
        detail_text = "\n\n" + "\n".join(details) if details else ""
        answer = QMessageBox.question(
            self,
            "Delete Project Item",
            f'Delete "{element_name}"?{detail_text}\n\nThis action can be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def change() -> None:
            project = self._api.current_project
            if project is None:
                return
            components = project.data.get("components")
            if isinstance(components, list) and component_ids:
                components[:] = [
                    component
                    for component in components
                    if not (
                        isinstance(component, dict)
                        and str(component.get("id") or "") in component_ids
                    )
                ]
                for component in components:
                    if not isinstance(component, dict):
                        continue
                    if str(component.get("attach_to") or "") in component_ids:
                        component["attach_to"] = None
                    if str(component.get("parent") or "") in component_ids:
                        component["parent"] = None

            assemblies = project.data.get("assemblies")
            if isinstance(assemblies, list):
                assemblies[:] = [
                    assembly
                    for assembly in assemblies
                    if not (
                        isinstance(assembly, dict)
                        and str(assembly.get("id") or "") in assembly_ids
                    )
                ]
                self._remove_assembly_member_references(assemblies, component_ids)

        self._api.set_selection(None)
        self._api.edit_project(f"Delete {element_name}", change)
        self._api.show_status(f'Deleted "{element_name}"', "success", 3000)

    def _can_edit_project(self) -> bool:
        project = self._api.current_project
        return project is not None and not project.read_only

    def _element_kind(self, element_id: str) -> str:
        project = self._api.current_project
        if project is not None:
            assemblies = project.data.get("assemblies")
            if isinstance(assemblies, list):
                for assembly in assemblies:
                    if (
                        isinstance(assembly, dict)
                        and str(assembly.get("id") or "") == element_id
                    ):
                        return "assembly"
        return "component"

    def _find_element(
        self,
        element_id: str,
        kind: str,
    ) -> dict[str, Any] | None:
        project = self._api.current_project
        if project is None:
            return None
        if kind == "project":
            return project.data
        collection_name = "assemblies" if kind == "assembly" else "components"
        collection = project.data.get(collection_name)
        if not isinstance(collection, list):
            return None
        return next(
            (
                element
                for element in collection
                if isinstance(element, dict)
                and str(element.get("id") or "") == element_id
            ),
            None,
        )

    def _dependent_component_ids(self, root_id: str) -> set[str]:
        project = self._api.current_project
        components = project.data.get("components") if project is not None else None
        if not isinstance(components, list):
            return {root_id}

        deleted_ids = {root_id}
        changed = True
        while changed:
            changed = False
            for component in components:
                if not isinstance(component, dict):
                    continue
                component_id = str(component.get("id") or "")
                if not component_id or component_id in deleted_ids:
                    continue
                structural_parent = str(component.get("parent") or "")
                source = str(component.get("source") or "")
                if structural_parent in deleted_ids or source in deleted_ids:
                    deleted_ids.add(component_id)
                    changed = True
        return deleted_ids

    def _assemblies_invalidated_by(self, component_ids: set[str]) -> set[str]:
        project = self._api.current_project
        assemblies = project.data.get("assemblies") if project is not None else None
        if not isinstance(assemblies, list) or not component_ids:
            return set()

        invalidated: set[str] = set()
        for assembly in assemblies:
            if not isinstance(assembly, dict):
                continue
            members = assembly.get("members")
            if not isinstance(members, dict):
                continue
            for member in members.values():
                if isinstance(member, str) and member in component_ids:
                    invalidated.add(str(assembly.get("id") or ""))
                    break
                if isinstance(member, list):
                    remaining = [value for value in member if value not in component_ids]
                    if member and not remaining:
                        invalidated.add(str(assembly.get("id") or ""))
                        break
        invalidated.discard("")
        return invalidated

    @staticmethod
    def _remove_assembly_member_references(
        assemblies: list[Any],
        component_ids: set[str],
    ) -> None:
        if not component_ids:
            return
        for assembly in assemblies:
            if not isinstance(assembly, dict):
                continue
            members = assembly.get("members")
            if not isinstance(members, dict):
                continue
            for role, member in list(members.items()):
                if isinstance(member, str) and member in component_ids:
                    members.pop(role)
                elif isinstance(member, list):
                    members[role] = [
                        value for value in member if value not in component_ids
                    ]

    def _restore_item_text(self, item: QTreeWidgetItem, text: str) -> None:
        previous = self.blockSignals(True)
        try:
            item.setText(0, text)
        finally:
            self.blockSignals(previous)
