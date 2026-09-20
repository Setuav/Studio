"""Descriptors used to contribute UI and project features.

@defgroup contributions Contributions
@brief Immutable descriptors registered by a plugin during activation.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from setuav_studio.project.document import ProjectDocument

__all__ = [
    "ActionContribution",
    "ComponentTreeNodeContribution",
    "ComponentTreeProvider",
    "PanelContribution",
    "ParameterField",
    "ProjectTreeNodeContribution",
    "ProjectTreeProvider",
    "SettingsPageContribution",
    "ToolContribution",
    "ToolbarContribution",
    "ToolbarMenuItemContribution",
]

IconSource = str | Path | QIcon | None


@dataclass(frozen=True)
class ParameterField:
    """Descriptor for a component or plugin parameter field in a property editor."""

    key: str = ""
    label: str = ""
    unit: str = ""
    quantity: str | None = None
    field_type: type = float
    default: Any = 0.0
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    decimals: int = 2
    tooltip: str = ""
    options: tuple[tuple[str, str], ...] | tuple[str, ...] | None = None
    allow_formula: bool = True
    readonly: bool = False
    widget_type: str | None = None

    def __set_name__(self, owner: type, name: str) -> None:
        if not self.key:
            object.__setattr__(self, "key", name)
        if not self.label:
            object.__setattr__(self, "label", name.replace("_", " ").title())

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        if instance is None:
            return self
        params = getattr(instance, "parameters", None)
        if isinstance(params, dict):
            return params.get(self.key, self.default)
        return self.default

    def __set__(self, instance: Any, value: Any) -> None:
        params = getattr(instance, "parameters", None)
        if isinstance(params, dict):
            params[self.key] = value


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


#: Callback that contributes virtual nodes beneath a component.
ComponentTreeProvider = Callable[
    [dict[str, Any]],
    tuple[ComponentTreeNodeContribution, ...],
]

#: Callback that contributes plugin-owned nodes beneath the project root.
ProjectTreeProvider = Callable[
    ["ProjectDocument"],
    tuple[ProjectTreeNodeContribution, ...],
]


@dataclass(frozen=True)
class PanelContribution:
    """Dockable panel supplied by a plugin.

    The factory is called lazily on the Qt UI thread.

    @ingroup contributions
    @param id Globally unique, stable panel identifier.
    @param title User-visible panel title.
    @param factory Zero-argument widget factory.
    @param area Initial Qt dock area.
    @param icon Optional icon name, file path, or ``QIcon``.
    """

    id: str
    title: str
    factory: Callable[[], QWidget]
    area: Qt.DockWidgetArea = Qt.DockWidgetArea.LeftDockWidgetArea
    icon: IconSource = None


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
    ``menu_items``. Ordering is optional.

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
