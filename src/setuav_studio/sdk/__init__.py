"""Public SDK for Setuav Studio plugin authors and internal plugins.

Provides core domain models (Component, Vehicle, Data), API protocols (StudioAPI, ViewportProtocol),
UI contributions (ToolbarContribution, ParameterField, PanelContribution), and 3D visual primitives.
"""

from __future__ import annotations

from setuav_studio.model.component import Component, GenericComponent
from setuav_studio.model.data import Data
from setuav_studio.model.vehicle import Vehicle
from setuav_studio.ui.editor.component import BaseComponentEditor
from setuav_studio_sdk.api import (
    ComponentTreeProvider,
    ProjectTreeProvider,
    StudioAPI,
    ViewportProtocol,
)
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
    WorkspaceLayoutContext,
)
from setuav_studio_sdk.events import StudioEvents
from setuav_studio_sdk.models import ProjectDocument
from setuav_studio_sdk.plugin import PLUGIN_ENTRY_POINT_GROUP, StudioPlugin
from setuav_studio_sdk.primitives import (
    BoxPrimitive,
    ColorRGB,
    ColorRGBA,
    CylinderPrimitive,
    LineSegmentsPrimitive,
    LoftPrimitive,
    PlanePrimitive,
    Point3D,
    RingPrimitive,
    TrianglesPrimitive,
    VisualPrimitive,
)
from setuav_studio_sdk.tasks import (
    CancellationToken,
    TaskCancelledError,
    TaskHandle,
    TaskManagerProtocol,
    TaskProgress,
    TaskStatus,
)
from setuav_studio_sdk.version import PLUGIN_API_VERSION

__all__ = [
    "PLUGIN_API_VERSION",
    "PLUGIN_ENTRY_POINT_GROUP",
    "ActionContribution",
    "BaseComponentEditor",
    "BoxPrimitive",
    "CancellationToken",
    "ColorRGB",
    "ColorRGBA",
    "Component",
    "ComponentTreeNodeContribution",
    "ComponentTreeProvider",
    "CylinderPrimitive",
    "Data",
    "GenericComponent",
    "LineSegmentsPrimitive",
    "LoftPrimitive",
    "PanelContribution",
    "ParameterField",
    "PlanePrimitive",
    "Point3D",
    "ProjectDocument",
    "ProjectTreeNodeContribution",
    "ProjectTreeProvider",
    "RingPrimitive",
    "SettingsPageContribution",
    "StudioAPI",
    "StudioEvents",
    "StudioPlugin",
    "TaskCancelledError",
    "TaskHandle",
    "TaskManagerProtocol",
    "TaskProgress",
    "TaskStatus",
    "ToolContribution",
    "ToolbarContribution",
    "ToolbarMenuItemContribution",
    "TrianglesPrimitive",
    "Vehicle",
    "ViewportProtocol",
    "VisualPrimitive",
    "WorkspaceContribution",
    "WorkspaceLayoutContext",
]
