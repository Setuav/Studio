from importlib import resources

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication


FONT_FAMILY = "Inter"
DEFAULT_FONT_SIZE = 10
ACCENT_COLOR = "#7fc4d1"
INACTIVE_SELECTION_COLORS = {
    "dark": "#38555a",
    "light": "#c5e2e7",
}
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


def apply_theme(app: QApplication, theme: str, font_size: int) -> None:
    color_scheme = (
        Qt.ColorScheme.Light if theme == "light" else Qt.ColorScheme.Dark
    )
    app.styleHints().setColorScheme(color_scheme)
    _apply_accent(app)
    app.setFont(_application_font(font_size))
    app.setStyleSheet(build_stylesheet(font_size, theme))


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
    return _STYLESHEET_TEMPLATE.format(
        font_family=FONT_FAMILY,
        font_size=font_size,
        inactive_selection=INACTIVE_SELECTION_COLORS.get(
            theme,
            INACTIVE_SELECTION_COLORS["dark"],
        ),
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
