import logging
from functools import cache
from importlib import resources

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QLabel

logger = logging.getLogger(__name__)


class ComboBoxWheelFilter(QObject):
    """Global event filter that disables mouse wheel value changes on closed QComboBoxes."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel:
            if isinstance(watched, QComboBox):
                combo = watched
            else:
                parent = watched.parent()
                combo = parent if isinstance(parent, QComboBox) else None
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
    "purple": "#c678dd",
    "red": "#e06c75",
    "cyan": "#56b6c2",
    "teal": "#56b6c2",
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

BLENDER_TOKENS: dict[str, str] = {
    "window": "#303030",
    "title_bar": "#3d3d3d",
    "dock": "#303030",
    "surface": "#282828",
    "surface_alt": "#3d3d3d",
    "elevated": "#1d1d1d",
    "row_alt": "#303030",
    "plot": "#1d1d1d",
    "grid": "#3d3d3d",
    "border": "#282828",
    "border_strong": "#6c6c6c",
    "text": "#ffffff",
    "text_muted": "#b9b9b9",
    "text_dim": "#989898",
    "text_bright": "#ffffff",
    "axis": "#848484",
    "accent": "#4772b3",
    "accent_text": "#282828",
    "inactive_selection": "#545454",
    "viewer_surface": "#4772b3",
    "viewer_surface_edge": "#5db6ea",
    "viewer_fuselage": "#545454",
    "viewer_fuselage_edge": "#b9b9b9",
    "viewer_panel_edge": "#f1a355",
}

QT_THEME_NAMES: dict[str, str] = {
    "blender": "blender",
    "github": "github_dark",
    "monokai": "monokai",
    "nord": "nord",
}

_current_mode: str = "native"


@cache
def _load_qt_theme(mode: str):
    theme_name = QT_THEME_NAMES.get(mode)
    if theme_name is None:
        return None
    try:
        from qt_themes import get_theme
    except ModuleNotFoundError:
        logger.error("Theme %s requested but qt-themes is not installed", theme_name)
        return None
    return get_theme(theme_name)


@cache
def _named_theme_tokens(mode: str) -> dict[str, str]:
    if mode == "blender":
        return BLENDER_TOKENS

    theme = _load_qt_theme(mode)
    if theme is None:
        return DARK_TOKENS

    def color(name: str, fallback: str) -> str:
        value = getattr(theme, name, None)
        return value.name() if isinstance(value, QColor) else fallback

    text = color("text", "#ffffff")
    primary = color("primary", "#4772b3")
    mantle = color("mantle", "#282828")
    accent_text = mantle if QColor(primary).valueF() > 0.5 else text
    return {
        "window": color("base", "#303030"),
        "title_bar": color("surface0", "#3d3d3d"),
        "dock": color("base", "#303030"),
        "surface": mantle,
        "surface_alt": color("surface0", "#3d3d3d"),
        "elevated": color("crust", "#1d1d1d"),
        "row_alt": color("base", "#303030"),
        "plot": color("crust", "#1d1d1d"),
        "grid": color("surface0", "#3d3d3d"),
        "border": mantle,
        "border_strong": color("surface2", "#6c6c6c"),
        "text": text,
        "text_muted": color("overlay2", "#b9b9b9"),
        "text_dim": color("overlay1", "#989898"),
        "text_bright": text,
        "axis": color("overlay0", "#848484"),
        "accent": primary,
        "accent_text": accent_text,
        "inactive_selection": color("surface1", "#545454"),
        "viewer_surface": primary,
        "viewer_surface_edge": color("blue", primary),
        "viewer_fuselage": color("surface1", "#545454"),
        "viewer_fuselage_edge": color("overlay2", "#b9b9b9"),
        "viewer_panel_edge": color("orange", "#f1a355"),
    }


@cache
def _named_theme_chart_colors(mode: str) -> dict[str, str]:
    theme = _load_qt_theme(mode)
    if theme is None:
        return DARK_CHART_COLORS

    fallback = _named_theme_tokens(mode)["accent"]
    return {
        role: value.name() if isinstance(value, QColor) else fallback
        for role in ("blue", "green", "orange", "magenta", "red", "cyan")
        for value in (getattr(theme, role, None),)
    }


@cache
def _named_theme_status_colors(mode: str) -> dict[str, str]:
    theme = _load_qt_theme(mode)
    if theme is None:
        return STATUS_COLORS

    colors = _named_theme_chart_colors(mode)
    overlay = getattr(theme, "overlay2", None)
    yellow = getattr(theme, "yellow", None)
    return {
        "info": overlay.name() if isinstance(overlay, QColor) else colors["blue"],
        "success": colors["green"],
        "warning": yellow.name() if isinstance(yellow, QColor) else colors["orange"],
        "error": colors["red"],
    }


def set_theme_mode(mode: str) -> None:
    """Set the active built-in or qt-themes mode."""
    global _current_mode
    if mode in {"native", *QT_THEME_NAMES}:
        _current_mode = mode


def current_theme_mode() -> str:
    """Return the active theme mode."""
    return _current_mode


def tokens() -> dict[str, str]:
    """Return active theme tokens dictionary."""
    if _current_mode in QT_THEME_NAMES:
        return _named_theme_tokens(_current_mode)
    return DARK_TOKENS


def accent_color() -> str:
    """Return the current UI accent color as a hex string."""
    return tokens()["accent"]


def chart_color(role: str) -> str:
    """Return a data-series color with sufficient contrast for the active theme."""
    if _current_mode in QT_THEME_NAMES:
        palette = _named_theme_chart_colors(_current_mode)
    else:
        palette = DARK_CHART_COLORS
    return palette.get(role, palette["blue"])


def status_color(level: str) -> str:
    """Return a semantic status color suitable for the active theme."""
    if _current_mode in QT_THEME_NAMES:
        palette = _named_theme_status_colors(_current_mode)
    else:
        palette = STATUS_COLORS
    return palette.get(level, palette["info"])


def semantic_color(role: str) -> str:
    """Return the active theme color for a semantic button/action role."""
    if _current_mode in QT_THEME_NAMES:
        theme = _load_qt_theme(_current_mode)
        if theme is not None:
            attribute = {
                "primary": "primary",
                "secondary": "secondary",
                "success": "green",
                "warning": "yellow",
                "danger": "red",
            }.get(role)
            value = getattr(theme, attribute, None) if attribute else None
            if isinstance(value, QColor):
                return value.name()

    return {
        "primary": accent_color(),
        "secondary": chart_color("blue"),
        "success": status_color("success"),
        "warning": status_color("warning"),
        "danger": status_color("error"),
        "neutral": QApplication.palette().color(QPalette.ColorRole.ButtonText).name(),
    }.get(role, accent_color())


def rgba(color: str, alpha: float) -> str:
    qcolor = QColor(color)
    return f"rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, {alpha})"


def _create_dark_palette() -> QPalette:
    """Create complete robust dark palette for Qt Fusion."""
    palette = QPalette()
    window = QColor("#242424")
    base = QColor("#1c1c1c")
    alt_base = QColor("#222222")
    text = QColor("#e0e0e0")
    disabled_text = QColor("#757575")
    button = QColor("#303030")
    highlight = QColor(DARK_TOKENS["accent"])
    highlighted_text = QColor(DARK_TOKENS["accent_text"])

    active_roles = {
        QPalette.ColorRole.Window: window,
        QPalette.ColorRole.WindowText: text,
        QPalette.ColorRole.Base: base,
        QPalette.ColorRole.AlternateBase: alt_base,
        QPalette.ColorRole.ToolTipBase: window,
        QPalette.ColorRole.ToolTipText: text,
        QPalette.ColorRole.Text: text,
        QPalette.ColorRole.Button: button,
        QPalette.ColorRole.ButtonText: text,
        QPalette.ColorRole.BrightText: QColor("#ffffff"),
        QPalette.ColorRole.Light: QColor("#3c3c3c"),
        QPalette.ColorRole.Midlight: QColor("#303030"),
        QPalette.ColorRole.Dark: QColor("#1c1c1c"),
        QPalette.ColorRole.Mid: QColor("#282828"),
        QPalette.ColorRole.Shadow: QColor("#181818"),
        QPalette.ColorRole.Highlight: highlight,
        QPalette.ColorRole.HighlightedText: highlighted_text,
        QPalette.ColorRole.Link: QColor("#61afef"),
        QPalette.ColorRole.LinkVisited: QColor("#c678dd"),
        QPalette.ColorRole.Accent: highlight,
        QPalette.ColorRole.PlaceholderText: disabled_text,
    }

    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, color in active_roles.items():
            palette.setColor(group, role, color)

    disabled_roles = {
        **active_roles,
        QPalette.ColorRole.WindowText: disabled_text,
        QPalette.ColorRole.ToolTipText: disabled_text,
        QPalette.ColorRole.Text: disabled_text,
        QPalette.ColorRole.ButtonText: disabled_text,
        QPalette.ColorRole.BrightText: disabled_text,
        QPalette.ColorRole.Highlight: QColor("#353535"),
        QPalette.ColorRole.HighlightedText: disabled_text,
        QPalette.ColorRole.Link: disabled_text,
        QPalette.ColorRole.LinkVisited: disabled_text,
        QPalette.ColorRole.Accent: QColor("#353535"),
        QPalette.ColorRole.PlaceholderText: disabled_text,
    }

    for role, color in disabled_roles.items():
        palette.setColor(QPalette.ColorGroup.Disabled, role, color)

    return palette


def _create_named_theme_palette(mode: str) -> QPalette:
    """Create a qt-themes palette without resetting the active Qt style."""
    theme = _load_qt_theme(mode)
    if theme is None:
        return _create_dark_palette()

    from qt_themes import update_palette

    palette = QPalette()
    update_palette(palette, theme)

    disabled = QPalette.ColorGroup.Disabled
    disabled_text = theme.overlay1
    palette.setColor(disabled, QPalette.ColorRole.Window, theme.base)
    palette.setColor(disabled, QPalette.ColorRole.ToolTipBase, theme.mantle)
    palette.setColor(disabled, QPalette.ColorRole.ToolTipText, disabled_text)
    palette.setColor(disabled, QPalette.ColorRole.Light, theme.crust)
    palette.setColor(disabled, QPalette.ColorRole.Midlight, theme.mantle)
    palette.setColor(disabled, QPalette.ColorRole.Mid, theme.surface0)
    palette.setColor(disabled, QPalette.ColorRole.Dark, theme.surface1)
    palette.setColor(disabled, QPalette.ColorRole.Shadow, theme.overlay0)
    return palette


def apply_theme(app: QApplication, mode: str | None = None) -> None:
    """Pure 100% native Qt Fusion styling with instant dynamic palette."""
    if mode is not None:
        set_theme_mode(mode)

    if app.style().objectName().lower() != "fusion":
        app.setStyle("Fusion")
    if current_theme_mode() in QT_THEME_NAMES:
        palette = _create_named_theme_palette(current_theme_mode())
    else:
        palette = _create_dark_palette()
    if app.styleSheet():
        app.setStyleSheet("")
    app.setPalette(palette)
    application_font = _application_font(DEFAULT_FONT_SIZE)
    if app.font() != application_font:
        app.setFont(application_font)

    from setuav_studio.ui.style.icons import refresh_label_icon
    from setuav_studio.ui.widget.button import refresh_all_button_roles

    for widget in app.allWidgets():
        if isinstance(widget, QLabel):
            refresh_label_icon(widget)
        widget.update()
    refresh_all_button_roles(app)

    global _combobox_wheel_filter
    if _combobox_wheel_filter is None:
        _combobox_wheel_filter = ComboBoxWheelFilter(app)
        app.installEventFilter(_combobox_wheel_filter)


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


__all__ = [
    "ACCENT_COLOR",
    "DEFAULT_FONT_SIZE",
    "FONT_FAMILY",
    "STATUS_COLORS",
    "ComboBoxWheelFilter",
    "accent_color",
    "apply_theme",
    "chart_color",
    "current_theme_mode",
    "semantic_color",
    "status_color",
    "tokens",
]
