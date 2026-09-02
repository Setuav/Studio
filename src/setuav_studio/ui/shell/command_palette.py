"""Command palette modal dialog for searching and executing actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QFont, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.theme import tokens

if TYPE_CHECKING:
    from setuav_studio.api.api import StudioAPI
    from setuav_studio.ui.shell.actions import ActionManager
    from setuav_studio.ui.shell.window import MainWindow


@dataclass
class CommandItem:
    """A single executable command in the palette."""

    id: str
    title: str
    category: str
    shortcut: str = ""
    icon: QIcon | None = None
    callback: Callable[[], Any] | None = None
    enabled: bool = True


class _CommandItemWidget(QWidget):
    """Custom rendering widget for a command palette list row."""

    def __init__(self, command: CommandItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        # Icon
        self.icon_label = QLabel(self)
        if command.icon is not None and not command.icon.isNull():
            self.icon_label.setPixmap(command.icon.pixmap(16, 16))
        else:
            self.icon_label.setFixedWidth(16)
        layout.addWidget(self.icon_label)

        # Category badge
        if command.category:
            cat_label = QLabel(f"[{command.category}]", self)
            cat_label.setFont(QFont("Inter", 8, QFont.Weight.Bold))
            tok = tokens()
            cat_color = tok.get("accent", "#c5a9eb")
            cat_label.setStyleSheet(f"color: {cat_color}; background: transparent;")
            layout.addWidget(cat_label)

        # Title
        title_label = QLabel(command.title, self)
        title_label.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        title_label.setStyleSheet("background: transparent;")
        layout.addWidget(title_label, 1)

        # Shortcut badge
        if command.shortcut:
            shortcut_label = QLabel(command.shortcut, self)
            shortcut_label.setFont(QFont("Inter", 8))
            tok = tokens()
            border_color = tok.get("border", "#3d3d3d")
            text_color = tok.get("text_muted", "#888888")
            shortcut_label.setStyleSheet(
                f"color: {text_color}; border: 1px solid {border_color}; "
                f"border-radius: 4px; padding: 2px 6px; background: rgba(255, 255, 255, 0.05);"
            )
            layout.addWidget(shortcut_label)


class CommandPaletteDialog(QDialog):
    """Modern modal command search palette (Ctrl+Shift+P / F1)."""

    def __init__(self, window: MainWindow, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent or window)
        self._window = window
        self._api = api
        self._commands: list[CommandItem] = []
        self._filtered_commands: list[CommandItem] = []

        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedWidth(620)
        self.setFixedHeight(380)

        self._setup_ui()
        self.installEventFilter(self)

    def _setup_ui(self) -> None:
        tok = tokens()
        bg_color = tok.get("surface", "#1e1e1e")
        border_color = tok.get("border", "#3d3d3d")

        self.setStyleSheet(
            f"QDialog {{ background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Search box
        search_box = QWidget()
        search_layout = QHBoxLayout(search_box)
        search_layout.setContentsMargins(6, 4, 6, 4)
        search_layout.setSpacing(8)

        search_icon = QLabel()
        search_icon.setPixmap(get_icon("fa6s.magnifying-glass").pixmap(16, 16))
        search_layout.addWidget(search_icon)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Type a command or action name…")
        self.search_edit.setFont(QFont("Inter", 10))
        self.search_edit.setStyleSheet(
            "QLineEdit { border: none; background: transparent; padding: 4px; }"
        )
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self.search_edit, 1)

        layout.addWidget(search_box)

        # Separator line
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {border_color};")
        layout.addWidget(sep)

        # List of matching commands
        self.list_widget = QListWidget(self)
        self.list_widget.setFont(QFont("Inter", 9))
        self.list_widget.setStyleSheet(
            f"QListWidget {{ border: none; background: transparent; }} "
            f"QListWidget::item {{ border-radius: 4px; padding: 0px; }} "
            f"QListWidget::item:selected {{ background-color: {tok.get('surface_alt', '#2d2d2d')}; }}"
        )
        self.list_widget.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self.list_widget, 1)

    def eventFilter(self, watched: Any, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key_event = event if isinstance(event, QKeyEvent) else None
            if key_event:
                if key_event.key() == Qt.Key.Key_Down:
                    curr = self.list_widget.currentRow()
                    if curr < self.list_widget.count() - 1:
                        self.list_widget.setCurrentRow(curr + 1)
                    return True
                elif key_event.key() == Qt.Key.Key_Up:
                    curr = self.list_widget.currentRow()
                    if curr > 0:
                        self.list_widget.setCurrentRow(curr - 1)
                    return True
                elif key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    curr = self.list_widget.currentRow()
                    if 0 <= curr < len(self._filtered_commands):
                        self._execute_command(self._filtered_commands[curr])
                    return True
                elif key_event.key() == Qt.Key.Key_Escape:
                    self.reject()
                    return True
        return super().eventFilter(watched, event)

    def populate_and_show(self, action_manager: ActionManager) -> None:
        """Collect all active commands across menus, toolbars, and workspaces, then show."""
        self._commands = self._collect_commands(action_manager)
        self.search_edit.clear()
        self._filter_commands("")

        # Position centered near the top of the parent window
        if self._window is not None:
            parent_geom = self._window.geometry()
            x = parent_geom.x() + (parent_geom.width() - self.width()) // 2
            y = parent_geom.y() + 60
            self.move(QPoint(max(0, x), max(0, y)))

        self.show()
        self.raise_()
        self.activateWindow()
        self.search_edit.setFocus()

    def _collect_commands(self, action_manager: ActionManager) -> list[CommandItem]:
        commands: list[CommandItem] = []
        seen_titles: set[str] = set()
        self._collect_menu_commands(action_manager, commands, seen_titles)
        self._collect_workspace_commands(commands, seen_titles)
        self._collect_toolbar_commands(commands, seen_titles)
        return commands

    def _collect_menu_commands(
        self,
        action_manager: ActionManager,
        commands: list[CommandItem],
        seen_titles: set[str],
    ) -> None:
        menu_categories = {
            "file": "File",
            "edit": "Edit",
            "view": "View",
            "tools": "Tools",
            "help": "Help",
        }
        for cmd_id, action in action_manager.command_actions.items():
            if not action.isVisible() or not action.isEnabled():
                continue
            cat = "Tools" if any(k in cmd_id for k in ("plugins", "tasks", "constraints")) else "Command"
            for prefix, cat_name in menu_categories.items():
                if cmd_id.startswith(prefix) or f".{prefix}." in cmd_id:
                    cat = cat_name
                    break

            title = action.text().replace("&", "").strip()
            shortcut = action.shortcut().toString() if action.shortcut() else ""
            if title and title not in seen_titles:
                seen_titles.add(title)
                commands.append(
                    CommandItem(
                        id=cmd_id,
                        title=title,
                        category=cat,
                        shortcut=shortcut,
                        icon=action.icon(),
                        callback=action.trigger,
                        enabled=action.isEnabled(),
                    )
                )

    def _collect_workspace_commands(
        self,
        commands: list[CommandItem],
        seen_titles: set[str],
    ) -> None:
        if not hasattr(self._window, "_workspace_manager"):
            return
        wm = self._window._workspace_manager
        for ws_id, ws_contrib in wm._workspaces.items():
            title = f"Switch to {ws_contrib.title} Workspace"
            if title not in seen_titles:
                seen_titles.add(title)
                commands.append(
                    CommandItem(
                        id=f"workspace.switch.{ws_id}",
                        title=title,
                        category="Workspace",
                        icon=get_icon("view_fit"),
                        callback=lambda wid=ws_id: self._window.switch_workspace(wid),
                    )
                )

    def _collect_toolbar_commands(
        self,
        commands: list[CommandItem],
        seen_titles: set[str],
    ) -> None:
        if not hasattr(self._window, "_toolbar_manager"):
            return
        for group, tb in self._window._toolbar_manager.toolset_bars.items():
            group_title = group.replace("-", " ").title()
            for action in tb.actions():
                if not action.isVisible() or not action.isEnabled():
                    continue
                t = action.text().replace("&", "").strip()
                if t and t not in seen_titles:
                    seen_titles.add(t)
                    commands.append(
                        CommandItem(
                            id=f"tool.{action.objectName() or t.lower()}",
                            title=t,
                            category=group_title,
                            shortcut=action.shortcut().toString() if action.shortcut() else "",
                            icon=action.icon(),
                            callback=action.trigger,
                            enabled=action.isEnabled(),
                        )
                    )

        return commands

    def _on_search_text_changed(self, text: str) -> None:
        self._filter_commands(text.strip().lower())

    def _filter_commands(self, query: str) -> None:
        self.list_widget.clear()
        if not query:
            self._filtered_commands = list(self._commands)
        else:
            scored: list[tuple[int, CommandItem]] = []
            for cmd in self._commands:
                title_lower = cmd.title.lower()
                cat_lower = cmd.category.lower()
                id_lower = cmd.id.lower()

                score = 0
                if query in title_lower:
                    score += 100 - title_lower.index(query)
                if query in cat_lower:
                    score += 50
                if query in id_lower:
                    score += 20

                if score > 0:
                    scored.append((score, cmd))

            scored.sort(key=lambda x: x[0], reverse=True)
            self._filtered_commands = [item[1] for item in scored]

        for cmd in self._filtered_commands:
            list_item = QListWidgetItem(self.list_widget)
            item_widget = _CommandItemWidget(cmd)
            list_item.setSizeHint(item_widget.sizeHint())
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, item_widget)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        row = self.list_widget.row(item)
        if 0 <= row < len(self._filtered_commands):
            self._execute_command(self._filtered_commands[row])

    def _execute_command(self, command: CommandItem) -> None:
        self.accept()
        if command.callback is not None:
            command.callback()


__all__ = ["CommandItem", "CommandPaletteDialog"]
