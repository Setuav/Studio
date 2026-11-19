from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QLine, QModelIndex, QPersistentModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QProxyStyle,
    QStyle,
    QStyledItemDelegate,
    QStyleOption,
    QStyleOptionViewItem,
    QWidget,
)

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


class ProjectExplorerDelegate(QStyledItemDelegate):
    """Delegate ensuring uniform icon slot width and consistent text alignment across all tree nodes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def initStyleOption(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        super().initStyleOption(option, index)
        if option.features & QStyleOptionViewItem.ViewItemFeature.HasDecoration:
            target_size = _ProjectExplorerBranchStyle.ICON_SLOT_SIZE
            view = option.widget
            if isinstance(view, QAbstractItemView):
                isz = view.iconSize()
                if isz.isValid() and isz.width() > 0:
                    target_size = isz.width()
            option.decorationSize = QSize(target_size, target_size)


class _ProjectExplorerBranchStyle(QProxyStyle):
    """Draw classic dotted tree branches with square expand controls and aligned item layout."""

    ICON_SLOT_SIZE = 16
    TEXT_SPACING = 5

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__()
        if parent is not None:
            self.setParent(parent)

    def _icon_slot_width(self, option: QStyleOption, widget: QWidget | None) -> int:
        if isinstance(option, QStyleOptionViewItem) and option.decorationSize.isValid():
            w = option.decorationSize.width()
            if w > 0:
                return w
        if isinstance(widget, QAbstractItemView):
            isz = widget.iconSize()
            if isz.isValid() and isz.width() > 0:
                return isz.width()
        return self.ICON_SLOT_SIZE

    def subElementRect(
        self,
        element: QStyle.SubElement,
        option: QStyleOption,
        widget: QWidget | None = None,
    ) -> QRect:
        # QProxyStyle only forwards this query to its base style. Calling the base
        # style directly also accepts the null widget Qt may pass in.
        base = self.baseStyle()
        if element == QStyle.SubElement.SE_ItemViewItemDecoration:
            r = base.subElementRect(element, option, widget)
            if not r.isEmpty():
                slot_w = self._icon_slot_width(option, widget)
                actual_w = r.width()
                if actual_w < slot_w:
                    offset = (slot_w - actual_w) // 2
                    return QRect(r.x() + offset, r.y(), actual_w, r.height())
            return r

        if element == QStyle.SubElement.SE_ItemViewItemText:
            base_dec = base.subElementRect(
                QStyle.SubElement.SE_ItemViewItemDecoration, option, widget
            )
            r = base.subElementRect(element, option, widget)
            if not base_dec.isEmpty():
                slot_w = self._icon_slot_width(option, widget)
                new_left = base_dec.x() + slot_w + self.TEXT_SPACING
                avail_w = max(0, option.rect.right() - new_left + 1)
                return QRect(new_left, r.y(), avail_w, r.height())
            return r

        return base.subElementRect(element, option, widget)

    def sizeFromContents(
        self,
        contents_type: QStyle.ContentsType,
        option: QStyleOption,
        size: QSize,
        widget: QWidget | None = None,
    ) -> QSize:
        result = self.baseStyle().sizeFromContents(contents_type, option, size, widget)
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


def format_component_name(component: dict[str, Any]) -> str:
    return str(component.get("name") or component.get("id") or "Unnamed")


def format_component_type(
    component: dict[str, Any],
    components: list[dict[str, Any]],
    api: StudioAPI,
) -> str:
    if component.get("kind") == "instance":
        source_id = str(component.get("source") or "")
        source_name = source_id
        for candidate in components:
            if str(candidate.get("id") or "") == source_id:
                source_name = str(candidate.get("name") or source_id)
                break
        return f"Instance of {source_name}" if source_name else "Instance"

    ctype = str(component.get("type", ""))
    contribution = api.get_component_type(ctype)
    if contribution is not None and contribution.describe is not None:
        return contribution.describe(component)
    return api.get_component_type_label(ctype)
