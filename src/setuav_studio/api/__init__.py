"""StudioAPI — clean public service surface for plugins and shell."""

from __future__ import annotations

from setuav_studio.model.component import Component
from setuav_studio.plugin.plugin import StudioPlugin

from .api import StudioAPI, UnsubscribeCallable
from .contributions import (
    ActionContribution,
    ComponentTreeNodeContribution,
    ComponentTreeProvider,
    ComponentTypeContribution,
    PanelContribution,
    ParameterField,
    ProjectTreeNodeContribution,
    ProjectTreeProvider,
    SettingsPageContribution,
    ToolbarContribution,
    ToolbarMenuItemContribution,
    ToolContribution,
)
from .events import StudioEvents
from .hooks import HookRegistry
from .host import _StudioHost
from .undo import _ComponentEditCommand, _ProjectEditCommand

__all__ = [
    "ActionContribution",
    "Component",
    "ComponentTreeNodeContribution",
    "ComponentTreeProvider",
    "ComponentTypeContribution",
    "HookRegistry",
    "PanelContribution",
    "ParameterField",
    "ProjectTreeNodeContribution",
    "ProjectTreeProvider",
    "SettingsPageContribution",
    "StudioAPI",
    "StudioEvents",
    "StudioPlugin",
    "ToolContribution",
    "ToolbarContribution",
    "ToolbarMenuItemContribution",
    "UnsubscribeCallable",
    "_ComponentEditCommand",
    "_ProjectEditCommand",
    "_StudioHost",
]
