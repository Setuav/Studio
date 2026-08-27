"""Descriptors used to contribute UI and project features.

@defgroup contributions Contributions
@brief Immutable descriptors registered by a plugin during activation.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

__all__ = [
    "ActionContribution",
    "ComponentTreeNodeContribution",
    "PanelContribution",
    "ParameterField",
    "ProjectTreeNodeContribution",
    "SettingsPageContribution",
    "ToolContribution",
    "ToolbarContribution",
    "ToolbarMenuItemContribution",
    "WorkspaceContribution",
]

IconSource = str | Path | QIcon | None
WorkspaceScope = str | list[str] | tuple[str, ...] | None


@dataclass(frozen=True)
class ParameterField:
    """Descriptor for a component parameter field in a property editor."""

    key: str
    label: str
    unit: str = ""
    field_type: type = float
    default: Any = 0.0
    min_value: float | None = None
    max_value: float | None = None
    decimals: int = 2
    tooltip: str = ""
    options: tuple[tuple[str, str], ...] | tuple[str, ...] | None = None


def _matches_workspace(scope: WorkspaceScope, workspace_id: str | None) -> bool:
    if scope is None:
        return True
    if isinstance(scope, (list, tuple, set)):
        return workspace_id in scope
    return scope == workspace_id


@dataclass(frozen=True)
class ComponentTreeNodeContribution:
    """Virtual child displayed beneath a project component.

    @ingroup contributions
    @param id Globally unique, stable node identifier.
    @param title User-visible node label.
    @param selection Object published when the node is selected.
    @param icon Optional icon name, file path, or ``QIcon``.
    @param tooltip Optional explanatory text.
    @param rename Optional callback used to rename the node.
    @param delete Optional callback used to delete the node.
    """

    id: str
    title: str
    selection: dict[str, Any]
    icon: IconSource = None
    tooltip: str | None = None
    rename: Callable[[str], None] | None = None
    delete: Callable[[], None] | None = None


@dataclass(frozen=True)
class ProjectTreeNodeContribution:
    """Plugin-owned node displayed beneath the project root.

    @ingroup contributions
    @param id Globally unique, stable node identifier.
    @param title User-visible node label.
    @param selection Object published when the node is selected.
    @param children Nested project-tree nodes.
    @param icon Optional icon name, file path, or ``QIcon``.
    @param tooltip Optional explanatory text.
    @param rename Optional callback used to rename the node.
    @param delete Optional callback used to delete the node.
    """

    id: str
    title: str
    selection: dict[str, Any]
    children: tuple["ProjectTreeNodeContribution", ...] = ()
    icon: IconSource = None
    tooltip: str | None = None
    rename: Callable[[str], None] | None = None
    delete: Callable[[], None] | None = None


@dataclass(frozen=True)
class PanelContribution:
    """Dockable panel supplied by a plugin.

    The factory is called lazily on the Qt UI thread. An omitted
    ``workspace_id`` makes the panel available in every workspace.

    @ingroup contributions
    @param id Globally unique, stable panel identifier.
    @param title User-visible panel title.
    @param factory Zero-argument widget factory.
    @param area Initial Qt dock area.
    @param workspace_id One workspace, multiple workspaces, or all workspaces.
    @param icon Optional icon name, file path, or ``QIcon``.
    """

    id: str
    title: str
    factory: Callable[[], QWidget]
    area: Qt.DockWidgetArea = Qt.DockWidgetArea.LeftDockWidgetArea
    workspace_id: WorkspaceScope = None
    icon: IconSource = None

    def is_in_workspace(self, current_workspace_id: str | None) -> bool:
        """Return whether this panel belongs to the selected workspace."""
        return _matches_workspace(self.workspace_id, current_workspace_id)


@dataclass(frozen=True)
class SettingsPageContribution:
    """Page displayed in the application Settings dialog.

    The factory is called when Settings opens. The optional ``apply`` callback
    runs with the created page after the user accepts the dialog.

    @ingroup contributions
    @param id Globally unique, stable page identifier.
    @param title User-visible page title.
    @param factory Zero-argument page factory.
    @param icon Optional icon name, file path, or ``QIcon``.
    @param order Sort priority; lower values appear first.
    @param apply Optional callback used to persist page values.
    @param group Optional heading shared by related settings pages.
    @param group_icon Optional icon for the shared heading.
    """

    id: str
    title: str
    factory: Callable[[], QWidget]
    icon: IconSource = None
    order: int = 0
    apply: Callable[[QWidget], None] | None = None
    group: str | None = None
    group_icon: IconSource = None


@dataclass(frozen=True)
class WorkspaceContribution:
    """Workspace available from the main workspace selector.

    A workspace may provide a central widget or only group panels and toolbar
    actions by leaving ``factory`` unset.

    @ingroup contributions
    @param id Globally unique, stable workspace identifier.
    @param title User-visible workspace title.
    @param factory Optional zero-argument central-widget factory.
    @param icon Optional icon name, file path, or ``QIcon``.
    @param order Sort priority; lower values appear first.
    """

    id: str
    title: str
    factory: Callable[[], QWidget] | None = None
    icon: IconSource = None
    order: int = 0


@dataclass(frozen=True)
class ToolbarMenuItemContribution:
    """Command inside a contributed toolbar popup menu.

    @ingroup contributions
    @param title User-visible command label.
    @param callback Function invoked when the command is selected.
    @param icon Optional icon name, file path, or ``QIcon``.
    @param enabled_when Optional predicate evaluated during UI refresh.
    """

    title: str
    callback: Callable[[], None]
    icon: IconSource = None
    enabled_when: Callable[[], bool] | None = None


@dataclass(frozen=True)
class ToolbarContribution:
    """Action displayed in the main application toolbar.

    Supply exactly one action form: ``callback``, ``command``, or one or more
    ``menu_items``. Workspace scope and ordering are optional.

    @ingroup contributions
    @param id Globally unique, stable toolbar item identifier.
    @param title User-visible item label.
    @param icon Optional icon name, file path, or ``QIcon``.
    @param callback Function invoked directly by the item.
    @param command Existing application command identifier to invoke.
    @param menu_items Commands displayed in a popup menu.
    @param enabled_when Optional predicate evaluated during UI refresh.
    @param group Toolbar group name.
    @param order Sort priority within the group.
    @param workspace_id One workspace, multiple workspaces, or all workspaces.
    @exception ValueError If conflicting or missing action forms are supplied.
    """

    id: str
    title: str
    icon: IconSource = None
    callback: Callable[[], None] | None = None
    command: str | None = None
    menu_items: tuple[ToolbarMenuItemContribution, ...] = ()
    enabled_when: Callable[[], bool] | None = None
    group: str = "default"
    order: int = 0
    workspace_id: WorkspaceScope = None

    def __post_init__(self) -> None:
        action_forms = sum(
            (
                self.callback is not None,
                self.command is not None,
                bool(self.menu_items),
            )
        )
        if action_forms != 1:
            raise ValueError(
                "Toolbar contributions require exactly one of callback, command, or menu_items"
            )

    def is_in_workspace(self, current_workspace_id: str | None) -> bool:
        """Return whether this item belongs to the selected workspace."""
        return _matches_workspace(self.workspace_id, current_workspace_id)


@dataclass(frozen=True)
class ToolContribution:
    """Command added to the Tools menu.

    @ingroup contributions
    @param title User-visible command label.
    @param callback Function invoked when the command is selected.
    @param group Optional Tools submenu name.
    @param icon Optional icon name, file path, or ``QIcon``.
    @param shortcut Optional Qt key-sequence string.
    """

    title: str
    callback: Callable[[], None]
    group: str | None = None
    icon: IconSource = None
    shortcut: str | None = None


@dataclass(frozen=True)
class ActionContribution:
    """Command inserted into an application menu path.

    @ingroup contributions
    @param menu Slash-separated menu path such as ``Tools/Analysis``.
    @param title User-visible command label.
    @param callback Function invoked when the command is selected.
    @param icon Optional icon name, file path, or ``QIcon``.
    @param shortcut Optional Qt key-sequence string.
    """

    menu: str
    title: str
    callback: Callable[[], None]
    icon: IconSource = None
    shortcut: str | None = None
