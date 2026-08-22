from importlib import resources

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QLabel


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

DARK_CHART_COLORS: dict[str, str] = {
    "blue": "#61afef",
    "green": "#6fce9c",
    "orange": "#e5b567",
    "magenta": "#c678dd",
    "red": "#e06c75",
    "cyan": "#56b6c2",
}

LIGHT_CHART_COLORS: dict[str, str] = {
    "blue": "#0969da",
    "green": "#1a7f37",
    "orange": "#bc4c00",
    "magenta": "#8250df",
    "red": "#cf222e",
    "cyan": "#0a7f8c",
}

LIGHT_STATUS_COLORS: dict[str, str] = {
    "info": "#57606a",
    "success": "#1a7f37",
    "warning": "#9a6700",
    "error": "#cf222e",
}

DARK_TOKENS: dict[str, str] = {
    "window": "#242424",
    "title_bar": "#303030",
    "dock": "#242424",
    "surface": "#1c1c1c",
    "surface_alt": "#303030",
    "elevated": "#181818",
    "row_alt": "#222222",
    "plot": "#141414",
    "grid": "#333333",
    "border": "#282828",
    "border_strong": "#555555",
    "text": "#e0e0e0",
    "text_muted": "#999999",
    "text_dim": "#777777",
    "text_bright": "#ffffff",
    "axis": "#666666",
    "accent": "#c5a9eb",
    "accent_text": "#101010",
    "inactive_selection": "#333333",
    "viewer_surface": "#4a7090",
    "viewer_surface_edge": "#8db3cf",
    "viewer_fuselage": "#555866",
    "viewer_fuselage_edge": "#9a9dab",
    "viewer_panel_edge": "#e0e0e0",
}

LIGHT_TOKENS: dict[str, str] = {
    "window": "#f4f4f4",
    "title_bar": "#e8e8e8",
    "dock": "#f4f4f4",
    "surface": "#ffffff",
    "surface_alt": "#e8e8e8",
    "elevated": "#f5f5f5",
    "row_alt": "#fafafa",
    "plot": "#ffffff",
    "grid": "#e0e0e0",
    "border": "#dddddd",
    "border_strong": "#b0b0b0",
    "text": "#1e1e1e",
    "text_muted": "#555555",
    "text_dim": "#777777",
    "text_bright": "#1a73e8",
    "axis": "#777777",
    "accent": "#7048e8",
    "accent_text": "#ffffff",
    "inactive_selection": "#e4e4e4",
    "viewer_surface": "#7894aa",
    "viewer_surface_edge": "#2b4860",
    "viewer_fuselage": "#8b8e99",
    "viewer_fuselage_edge": "#4b4e58",
    "viewer_panel_edge": "#303030",
}

_current_mode: str = "dark"


def set_theme_mode(mode: str) -> None:
    """Set the active theme mode ('dark' or 'light')."""
    global _current_mode
    if mode in ("dark", "light"):
        _current_mode = mode


def current_theme_mode() -> str:
    """Return the active theme mode ('dark' or 'light')."""
    return _current_mode


def tokens() -> dict[str, str]:
    """Return active theme tokens dictionary."""
    return LIGHT_TOKENS if _current_mode == "light" else DARK_TOKENS


def accent_color() -> str:
    """Return the current UI accent color as a hex string."""
    return tokens()["accent"]


def chart_color(role: str) -> str:
    """Return a data-series color with sufficient contrast for the active theme."""
    palette = LIGHT_CHART_COLORS if _current_mode == "light" else DARK_CHART_COLORS
    return palette.get(role, palette["blue"])


def status_color(level: str) -> str:
    """Return a semantic status color suitable for the active theme."""
    palette = LIGHT_STATUS_COLORS if _current_mode == "light" else STATUS_COLORS
    return palette.get(level, palette["info"])


def rgba(color: str, alpha: float) -> str:
    qcolor = QColor(color)
    return f"rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, {alpha})"


def _create_dark_palette() -> QPalette:
    """Create complete robust dark palette for Qt Fusion."""
    dark_palette = QPalette()

    window = QColor("#242424")
    base = QColor("#1c1c1c")
    alt_base = QColor("#222222")
    text = QColor("#e0e0e0")
    disabled_text = QColor("#757575")
    button = QColor("#303030")
    highlight = QColor(DARK_TOKENS["accent"])
    highlighted_text = QColor(DARK_TOKENS["accent_text"])

    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        dark_palette.setColor(group, QPalette.ColorRole.Window, window)
        dark_palette.setColor(group, QPalette.ColorRole.WindowText, text)
        dark_palette.setColor(group, QPalette.ColorRole.Base, base)
        dark_palette.setColor(group, QPalette.ColorRole.AlternateBase, alt_base)
        dark_palette.setColor(group, QPalette.ColorRole.ToolTipBase, window)
        dark_palette.setColor(group, QPalette.ColorRole.ToolTipText, text)
        dark_palette.setColor(group, QPalette.ColorRole.Text, text)
        dark_palette.setColor(group, QPalette.ColorRole.Button, button)
        dark_palette.setColor(group, QPalette.ColorRole.ButtonText, text)
        dark_palette.setColor(group, QPalette.ColorRole.BrightText, QColor("#ffffff"))
        dark_palette.setColor(group, QPalette.ColorRole.Light, QColor("#3c3c3c"))
        dark_palette.setColor(group, QPalette.ColorRole.Midlight, QColor("#303030"))
        dark_palette.setColor(group, QPalette.ColorRole.Dark, QColor("#1c1c1c"))
        dark_palette.setColor(group, QPalette.ColorRole.Mid, QColor("#282828"))
        dark_palette.setColor(group, QPalette.ColorRole.Shadow, QColor("#181818"))
        dark_palette.setColor(group, QPalette.ColorRole.Highlight, highlight)
        dark_palette.setColor(group, QPalette.ColorRole.HighlightedText, highlighted_text)
        dark_palette.setColor(group, QPalette.ColorRole.Link, QColor("#61afef"))
        dark_palette.setColor(group, QPalette.ColorRole.LinkVisited, QColor("#c678dd"))
        dark_palette.setColor(group, QPalette.ColorRole.Accent, highlight)
        dark_palette.setColor(group, QPalette.ColorRole.PlaceholderText, disabled_text)

    disabled = QPalette.ColorGroup.Disabled
    dark_palette.setColor(disabled, QPalette.ColorRole.Window, window)
    dark_palette.setColor(disabled, QPalette.ColorRole.WindowText, disabled_text)
    dark_palette.setColor(disabled, QPalette.ColorRole.Base, base)
    dark_palette.setColor(disabled, QPalette.ColorRole.AlternateBase, alt_base)
    dark_palette.setColor(disabled, QPalette.ColorRole.ToolTipBase, window)
    dark_palette.setColor(disabled, QPalette.ColorRole.ToolTipText, disabled_text)
    dark_palette.setColor(disabled, QPalette.ColorRole.Text, disabled_text)
    dark_palette.setColor(disabled, QPalette.ColorRole.Button, button)
    dark_palette.setColor(disabled, QPalette.ColorRole.ButtonText, disabled_text)
    dark_palette.setColor(disabled, QPalette.ColorRole.BrightText, disabled_text)
    dark_palette.setColor(disabled, QPalette.ColorRole.Light, QColor("#3c3c3c"))
    dark_palette.setColor(disabled, QPalette.ColorRole.Midlight, QColor("#303030"))
    dark_palette.setColor(disabled, QPalette.ColorRole.Dark, QColor("#1c1c1c"))
    dark_palette.setColor(disabled, QPalette.ColorRole.Mid, QColor("#282828"))
    dark_palette.setColor(disabled, QPalette.ColorRole.Shadow, QColor("#181818"))
    dark_palette.setColor(disabled, QPalette.ColorRole.Highlight, QColor("#353535"))
    dark_palette.setColor(disabled, QPalette.ColorRole.HighlightedText, disabled_text)
    dark_palette.setColor(disabled, QPalette.ColorRole.Link, disabled_text)
    dark_palette.setColor(disabled, QPalette.ColorRole.LinkVisited, disabled_text)
    dark_palette.setColor(disabled, QPalette.ColorRole.Accent, QColor("#353535"))
    dark_palette.setColor(disabled, QPalette.ColorRole.PlaceholderText, disabled_text)

    return dark_palette


def _create_light_palette() -> QPalette:
    """Create complete robust clean light palette for Qt Fusion."""
    light_palette = QPalette()

    window = QColor("#f4f4f4")
    base = QColor("#ffffff")
    alt_base = QColor("#fafafa")
    text = QColor("#1e1e1e")
    disabled_text = QColor("#8a8a8a")
    button = QColor("#e8e8e8")
    highlight = QColor("#7048e8")
    highlighted_text = QColor("#ffffff")

    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        light_palette.setColor(group, QPalette.ColorRole.Window, window)
        light_palette.setColor(group, QPalette.ColorRole.WindowText, text)
        light_palette.setColor(group, QPalette.ColorRole.Base, base)
        light_palette.setColor(group, QPalette.ColorRole.AlternateBase, alt_base)
        light_palette.setColor(group, QPalette.ColorRole.ToolTipBase, QColor("#ffffdc"))
        light_palette.setColor(group, QPalette.ColorRole.ToolTipText, text)
        light_palette.setColor(group, QPalette.ColorRole.Text, text)
        light_palette.setColor(group, QPalette.ColorRole.Button, button)
        light_palette.setColor(group, QPalette.ColorRole.ButtonText, text)
        light_palette.setColor(group, QPalette.ColorRole.BrightText, QColor("#ffffff"))
        light_palette.setColor(group, QPalette.ColorRole.Light, QColor("#ffffff"))
        light_palette.setColor(group, QPalette.ColorRole.Midlight, QColor("#f0f0f0"))
        light_palette.setColor(group, QPalette.ColorRole.Dark, QColor("#cccccc"))
        light_palette.setColor(group, QPalette.ColorRole.Mid, QColor("#dddddd"))
        light_palette.setColor(group, QPalette.ColorRole.Shadow, QColor("#b8b8b8"))
        light_palette.setColor(group, QPalette.ColorRole.Highlight, highlight)
        light_palette.setColor(group, QPalette.ColorRole.HighlightedText, highlighted_text)
        light_palette.setColor(group, QPalette.ColorRole.Link, QColor("#0969da"))
        light_palette.setColor(group, QPalette.ColorRole.LinkVisited, QColor("#8250df"))
        light_palette.setColor(group, QPalette.ColorRole.Accent, highlight)
        light_palette.setColor(group, QPalette.ColorRole.PlaceholderText, disabled_text)

    disabled = QPalette.ColorGroup.Disabled
    light_palette.setColor(disabled, QPalette.ColorRole.Window, window)
    light_palette.setColor(disabled, QPalette.ColorRole.WindowText, disabled_text)
    light_palette.setColor(disabled, QPalette.ColorRole.Base, base)
    light_palette.setColor(disabled, QPalette.ColorRole.AlternateBase, alt_base)
    light_palette.setColor(disabled, QPalette.ColorRole.ToolTipBase, QColor("#ffffdc"))
    light_palette.setColor(disabled, QPalette.ColorRole.ToolTipText, disabled_text)
    light_palette.setColor(disabled, QPalette.ColorRole.Text, disabled_text)
    light_palette.setColor(disabled, QPalette.ColorRole.Button, button)
    light_palette.setColor(disabled, QPalette.ColorRole.ButtonText, disabled_text)
    light_palette.setColor(disabled, QPalette.ColorRole.BrightText, disabled_text)
    light_palette.setColor(disabled, QPalette.ColorRole.Light, QColor("#ffffff"))
    light_palette.setColor(disabled, QPalette.ColorRole.Midlight, QColor("#f0f0f0"))
    light_palette.setColor(disabled, QPalette.ColorRole.Dark, QColor("#cccccc"))
    light_palette.setColor(disabled, QPalette.ColorRole.Mid, QColor("#dddddd"))
    light_palette.setColor(disabled, QPalette.ColorRole.Shadow, QColor("#b8b8b8"))
    light_palette.setColor(disabled, QPalette.ColorRole.Highlight, QColor("#d0d0d0"))
    light_palette.setColor(disabled, QPalette.ColorRole.HighlightedText, disabled_text)
    light_palette.setColor(disabled, QPalette.ColorRole.Link, disabled_text)
    light_palette.setColor(disabled, QPalette.ColorRole.LinkVisited, disabled_text)
    light_palette.setColor(disabled, QPalette.ColorRole.Accent, QColor("#d0d0d0"))
    light_palette.setColor(disabled, QPalette.ColorRole.PlaceholderText, disabled_text)

    return light_palette


def apply_theme(app: QApplication, mode: str | None = None) -> None:
    """Pure 100% native Qt Fusion styling with instant dynamic light/dark palette."""
    if mode is not None:
        set_theme_mode(mode)

    if app.style().objectName().lower() != "fusion":
        app.setStyle("Fusion")
    palette = _create_dark_palette() if current_theme_mode() == "dark" else _create_light_palette()
    if app.styleSheet():
        app.setStyleSheet("")
    app.setPalette(palette)
    application_font = _application_font(DEFAULT_FONT_SIZE)
    if app.font() != application_font:
        app.setFont(application_font)

    from setuav_studio.ui.icons import refresh_label_icon

    for widget in app.allWidgets():
        # Application palette propagation preserves intentional per-widget
        # palette overrides and emits Qt's normal palette-change events.
        if isinstance(widget, QLabel):
            refresh_label_icon(widget)
        widget.update()

    global _combobox_wheel_filter
    if _combobox_wheel_filter is None:
        _combobox_wheel_filter = ComboBoxWheelFilter(app)
        app.installEventFilter(_combobox_wheel_filter)


def build_stylesheet(font_size: int = DEFAULT_FONT_SIZE) -> str:
    """Return empty stylesheet to allow pure native Qt Fusion rendering."""
    return ""


_INTER_FONT_FILES = (
    "Inter-VariableFont_opsz,wght.ttf",
    "Inter-Italic-VariableFont_opsz,wght.ttf",
)
_inter_family: str | None = None
_inter_load_attempted = False
_combobox_wheel_filter: ComboBoxWheelFilter | None = None


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
