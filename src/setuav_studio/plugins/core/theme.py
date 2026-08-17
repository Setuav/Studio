from importlib import resources

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPalette
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle


FONT_FAMILY = "Inter"
DEFAULT_FONT_SIZE = 10
ACCENT_COLOR = "#7fc4d1"
INACTIVE_SELECTION_COLORS = {
    "dark": "#404040",
    "light": "#c5e2e7",
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
LIGHT_TOKENS = {
    "window": "#f4f5f7",
    "title_bar": "#e8eaed",
    "dock": "#f4f5f7",
    "surface": "#ffffff",
    "surface_alt": "#e8eaed",
    "elevated": "#ffffff",
    "row_alt": "#f2f3f5",
    "plot": "#fafbfc",
    "grid": "#d9dce0",
    "border": "#d3d6db",
    "border_strong": "#bfc4ca",
    "text": "#1f2329",
}


def tokens(theme: str = "dark") -> dict[str, str]:
    if theme == "light":
        return LIGHT_TOKENS
    return DARK_TOKENS


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

QMenuBar,
QMenuBar::item,
QMenu,
QMenu::item {{
    font-family: \"{font_family}\";
    font-size: 10pt;
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


def apply_theme(app: QApplication, theme: str, font_size: int) -> None:
    color_scheme = (
        Qt.ColorScheme.Light if theme == "light" else Qt.ColorScheme.Dark
    )
    app.styleHints().setColorScheme(color_scheme)
    _apply_accent(app)
    app.setFont(_application_font(font_size))
    app.setStyleSheet(build_stylesheet(font_size, theme))
    global _dock_resize_style
    _dock_resize_style = DockResizeStyle(app.style())
    app.setStyle(_dock_resize_style)


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


def build_stylesheet(font_size: int, theme: str = "dark") -> str:
    theme_tokens = tokens(theme)
    if theme == "light":
        dock_hover = "rgba(0, 0, 0, 0.08)"
        dock_pressed = "rgba(0, 0, 0, 0.14)"
    else:
        dock_hover = "rgba(255, 255, 255, 0.14)"
        dock_pressed = "rgba(255, 255, 255, 0.22)"
    return _STYLESHEET_TEMPLATE.format(
        font_family=FONT_FAMILY,
        font_size=font_size,
        inactive_selection=INACTIVE_SELECTION_COLORS.get(
            theme,
            INACTIVE_SELECTION_COLORS["dark"],
        ),
        dock_hover=dock_hover,
        dock_pressed=dock_pressed,
        **theme_tokens,
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
