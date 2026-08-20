from importlib import resources

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QProxyStyle, QStyle


class ComboBoxWheelFilter(QObject):
    """Global event filter that disables mouse wheel value changes on closed QComboBoxes."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel:
            combo = (
                watched
                if isinstance(watched, QComboBox)
                else (watched.parent() if isinstance(watched.parent(), QComboBox) else None)
            )
            if combo is not None:
                view = combo.view()
                if view is None or not view.isVisible():
                    event.ignore()
                    parent = combo.parentWidget()
                    if parent is not None:
                        QApplication.sendEvent(parent, event)
                    return True
        return super().eventFilter(watched, event)


FONT_FAMILY = "Inter"
DEFAULT_FONT_SIZE = 10
ACCENT_COLOR = "#c5a9eb"
INACTIVE_SELECTION_COLOR = "#404040"
STATUS_COLORS = {
    "info": "#cccccc",
    "success": "#6fce9c",
    "warning": "#e5b567",
    "error": "#e06c75",
}
DARK_TOKENS = {
    "window": "#1a1d22",
    "title_bar": "#232323",
    "dock": "#272727",
    "surface": "#181818",
    "surface_alt": "#202020",
    "elevated": "#141414",
    "row_alt": "#1a1a1a",
    "plot": "#111111",
    "grid": "#262626",
    "border": "#282828",
    "border_strong": "#333333",
    "text": "#cccccc",
}


def tokens() -> dict[str, str]:
    return DARK_TOKENS


def accent_color() -> str:
    """Return the current UI accent color as a hex string."""
    return ACCENT_COLOR


def rgba(color: str, alpha: float) -> str:
    qcolor = QColor(color)
    return f"rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, {alpha})"


class DockResizeStyle(QProxyStyle):
    """Draws the dock resize handles in the title bar color."""

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget=None,
    ) -> None:
        if element == QStyle.PrimitiveElement.PE_IndicatorDockWidgetResizeHandle:
            painter.save()
            painter.fillRect(option.rect, QColor(tokens()["title_bar"]))
            painter.restore()
            return
        super().drawPrimitive(element, option, painter, widget)
_STYLESHEET_TEMPLATE = """
QWidget {{
    font-family: \"{font_family}\";
    font-size: {font_size}pt;
}}

QDockWidget,
QComboBox QAbstractItemView,
QAbstractItemView[tableComboPopup="true"] {{
    font-family: \"{font_family}\";
    font-size: {font_size}pt;
}}

QMenuBar {{
    font-family: \"{font_family}\";
    font-size: 10pt;
    padding: 0px 2px;
}}

QMenuBar::item {{
    font-family: \"{font_family}\";
    font-size: 10pt;
    padding: 2px 5px;
    margin: 0px;
    border-radius: 2px;
}}

QMenu {{
    font-family: \"{font_family}\";
    font-size: 10pt;
    padding: 2px 0px;
    border: 1px solid {border_strong};
    border-radius: 2px;
}}

QMenu::item {{
    font-family: \"{font_family}\";
    font-size: 10pt;
    padding: 2px 14px 2px 8px;
    margin: 0px 1px;
    border-radius: 2px;
}}

QMenu::separator {{
    height: 1px;
    background-color: {border_strong};
    margin: 2px 3px;
}}

QDockWidget::title {{
    padding: 1px 4px;
}}

QDockWidget {{
    background-color: {dock};
}}

QWidget#studioDockTitleBar {{
    background-color: {title_bar};
    border-bottom: 1px solid {border_strong};
}}

QWidget#studioDockTitleBar QLabel {{
    color: {text};
    font-weight: 600;
}}

QWidget#studioDockTitleBar QToolButton {{
    background-color: transparent;
    border: none;
    border-radius: 3px;
    margin: 1px;
}}

QWidget#studioDockTitleBar QToolButton:hover {{
    background-color: {dock_hover};
}}

QWidget#studioDockTitleBar QToolButton:pressed {{
    background-color: {dock_pressed};
}}

QWidget[sectionHeader="true"] {{
    background-color: transparent;
}}

QWidget[sectionHeader="true"] QLabel {{
    color: {text};
    font-weight: 600;
    font-size: {font_size}pt;
}}

QTableView,
QTreeView {{
    alternate-background-color: palette(alternate-base);
}}

QTableView:!focus,
QTreeView:!focus {{
    selection-background-color: {inactive_selection};
    selection-color: palette(text);
}}

QTableView::item,
QTreeView::item {{
    padding: 0 4px;
}}

QHeaderView::section {{
    font-family: \"{font_family}\";
    font-size: {font_size}pt;
    padding: 1px 4px;
}}

QScrollBar:vertical {{
    width: 8px;
}}

QScrollBar:horizontal {{
    height: 8px;
}}
"""
_INTER_FONT_FILES = (
    "Inter-VariableFont_opsz,wght.ttf",
    "Inter-Italic-VariableFont_opsz,wght.ttf",
)
_inter_family: str | None = None
_inter_load_attempted = False
_dock_resize_style: DockResizeStyle | None = None
_combobox_wheel_filter: ComboBoxWheelFilter | None = None


def apply_theme(app: QApplication) -> None:
    _apply_accent(app)
    app.setFont(_application_font(DEFAULT_FONT_SIZE))
    app.setStyleSheet(build_stylesheet())
    global _dock_resize_style, _combobox_wheel_filter
    _dock_resize_style = DockResizeStyle(app.style())
    app.setStyle(_dock_resize_style)
    if _combobox_wheel_filter is None:
        _combobox_wheel_filter = ComboBoxWheelFilter(app)
        app.installEventFilter(_combobox_wheel_filter)


def _apply_accent(app: QApplication) -> None:
    palette = app.palette()
    accent = QColor(ACCENT_COLOR)
    accent_text = QColor("#101010")

    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
    ):
        palette.setColor(group, QPalette.ColorRole.Accent, accent)
        palette.setColor(group, QPalette.ColorRole.Highlight, accent)
        palette.setColor(group, QPalette.ColorRole.HighlightedText, accent_text)
        palette.setColor(group, QPalette.ColorRole.Link, accent)
        palette.setColor(group, QPalette.ColorRole.LinkVisited, accent)
    app.setPalette(palette)


def build_stylesheet(font_size: int = DEFAULT_FONT_SIZE) -> str:
    return _STYLESHEET_TEMPLATE.format(
        font_family=FONT_FAMILY,
        font_size=font_size,
        inactive_selection=INACTIVE_SELECTION_COLOR,
        dock_hover="rgba(255, 255, 255, 0.14)",
        dock_pressed="rgba(255, 255, 255, 0.22)",
        **tokens(),
    )


def _application_font(font_size: int) -> QFont:
    inter_family = _load_bundled_inter()
    available = set(QFontDatabase.families())
    family = inter_family or next(
        (name for name in ("Inter", "Ubuntu", "Noto Sans") if name in available),
        QApplication.font().family(),
    )
    font = QFont(QApplication.font())
    font.setFamily(family)
    font.setPointSize(font_size)
    return font


def _load_bundled_inter() -> str | None:
    global _inter_family, _inter_load_attempted
    if _inter_load_attempted:
        return _inter_family
    _inter_load_attempted = True

    font_root = resources.files("setuav_studio").joinpath("assets", "fonts", "Inter")
    for file_name in _INTER_FONT_FILES:
        resource = font_root.joinpath(file_name)
        try:
            with resources.as_file(resource) as font_path:
                font_id = QFontDatabase.addApplicationFont(str(font_path))
        except (FileNotFoundError, OSError):
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families and _inter_family is None:
            _inter_family = families[0]
    return _inter_family
