"""Public API for Setuav Studio plugin authors.

Third-party plugins should import contracts from this package instead of
application implementation modules.
"""

from typing import TYPE_CHECKING, Any

from setuav_studio.model.component import Component, GenericComponent
from setuav_studio.model.data import Data
from setuav_studio.model.vehicle import Vehicle
from setuav_studio.project.document import ProjectDocument

if TYPE_CHECKING:
    from setuav_studio.ui.editor.component import BaseComponentEditor

from .api import (
    ComponentTreeProvider,
    ProjectTreeProvider,
    StudioAPI,
    ViewportProtocol,
)
from .contributions import (
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
from .events import StudioEvents
from .plugin import PLUGIN_ENTRY_POINT_GROUP, StudioPlugin
from .primitives import (
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
from .tasks import (
    CancellationToken,
    TaskCancelledError,
    TaskHandle,
    TaskManagerProtocol,
    TaskProgress,
    TaskStatus,
)
from .version import PLUGIN_API_VERSION

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


def __getattr__(name: str) -> Any:
    if name == "BaseComponentEditor":
        from setuav_studio.ui.editor.component import BaseComponentEditor

        return BaseComponentEditor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
