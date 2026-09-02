"""Plugin management and StudioAPI execution engine."""

from setuav_studio.model.component import Component
from setuav_studio.ui.editor.component import BaseComponentEditor
from setuav_studio_sdk.contributions import (
    ActionContribution,
    ComponentTreeNodeContribution,
    PanelContribution,
    ParameterField,
    ProjectTreeNodeContribution,
    SettingsPageContribution,
    ToolbarContribution,
    ToolbarMenuItemContribution,
    ToolContribution,
    WorkspaceContribution,
)
from setuav_studio_sdk.plugin import StudioPlugin

from .api import StudioAPI
from .hooks import HookRegistry
from .host import _StudioHost
from .manager import PluginManager
from .requirements import (
    PluginLoadIssue,
    _candidate_sort_key,
    _plugin_sort_key,
    _version_satisfies,
)
from .undo import _ComponentEditCommand, _ProjectEditCommand

__all__ = [
    "ActionContribution",
    "BaseComponentEditor",
    "Component",
    "ComponentTreeNodeContribution",
    "HookRegistry",
    "PanelContribution",
    "ParameterField",
    "PluginLoadIssue",
    "PluginManager",
    "ProjectTreeNodeContribution",
    "SettingsPageContribution",
    "StudioAPI",
    "StudioPlugin",
    "ToolContribution",
    "ToolbarContribution",
    "ToolbarMenuItemContribution",
    "WorkspaceContribution",
    "_ComponentEditCommand",
    "_ProjectEditCommand",
    "_StudioHost",
    "_candidate_sort_key",
    "_plugin_sort_key",
    "_version_satisfies",
]
