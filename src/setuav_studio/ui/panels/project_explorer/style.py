from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QLine, QRect, QSize, Qt
from PySide6.QtGui import QPainter, QPalette, QPen
from PySide6.QtWidgets import QProxyStyle, QStyle, QWidget

from setuav_studio.ui.icons import get_icon

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI

_GEOMETRY_COMPONENT_ICONS = {
    "org.setuav.core:fuselage": "geometry_add_fuselage",
    "org.setuav.core:lifting-surface": "geometry_add_lifting_surface",
    "org.setuav.core:control-surface": "geometry_add_control_surface",
}


class _ProjectExplorerBranchStyle(QProxyStyle):
    """Draw classic dotted tree branches with square expand controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__()
        if parent is not None:
            self.setParent(parent)

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
                painter.drawLine(QLine(center_x, rect.top(), center_x, rect.bottom()))
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
                painter.drawLine(QLine(box.left() + 2, center_y, box.right() - 2, center_y))
                if not is_open:
                    painter.drawLine(QLine(center_x, box.top() + 2, center_x, box.bottom() - 2))
        finally:
            painter.restore()


def format_component_name(component: dict[str, object]) -> str:
    ctype = str(component.get("type") or component.get("kind") or "")
    params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
    geom = params.get("geometry") if isinstance(params.get("geometry"), dict) else {}

    if ctype == "org.setuav.core:control-surface":
        name = str(component.get("name") or "").strip()
        tag = str(geom.get("tag") or "").strip()
        return name or tag or str(component.get("id") or "Unnamed")

    return str(component.get("name") or component.get("id") or "Unnamed")


def format_assembly_type(assembly: dict[str, object]) -> str:
    atype = str(assembly.get("type") or "Assembly")
    if atype == "org.setuav.core:electric-propulsion-system":
        return "Electric Propulsion System"
    return atype


def format_assembly_icon(assembly: dict[str, object], api: StudioAPI | None = None) -> Any:
    atype = str(assembly.get("type") or "")
    if atype == "org.setuav.core:electric-propulsion-system":
        return get_icon("component_propulsion_system")
    if api is not None and hasattr(api, "_component_icons") and atype in api._component_icons:
        return get_icon(api._component_icons[atype])
    return get_icon("assembly_generic")


def format_component_type(
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
    labels = {
        "org.setuav.core:fuselage": "Fuselage",
        "org.setuav.core:motor": "Electric Motor",
        "org.setuav.core:propeller": "Propeller",
        "org.setuav.core:rotor": "Rotor",
        "org.setuav.core:esc": "ESC (Speed Controller)",
        "org.setuav.core:battery": "Battery",
    }
    return labels.get(ctype, ctype)


def get_geometry_icon_source(
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
        (candidate for candidate in components if candidate.get("id") == source_id),
        None,
    )
    if source is None:
        return None
    source_type = source.get("type")
    return _GEOMETRY_COMPONENT_ICONS.get(source_type) if isinstance(source_type, str) else None
