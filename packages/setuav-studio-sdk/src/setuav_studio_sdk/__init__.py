"""Public API for Setuav Studio plugin authors.

Third-party plugins should import contracts from this package instead of
application implementation modules.
"""

from .api import (
    ComponentTreeProvider,
    ProjectTreeProvider,
    StudioAPI,
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
from .models import ProjectDocument
from .plugin import PLUGIN_ENTRY_POINT_GROUP, StudioPlugin
from .tasks import (
    CancellationToken,
    TaskCancelledError,
    TaskHandle,
    TaskManagerProtocol,
    TaskProgress,
    TaskStatus,
)
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
from .version import PLUGIN_API_VERSION

__all__ = [
    "PLUGIN_API_VERSION",
    "PLUGIN_ENTRY_POINT_GROUP",
    "ActionContribution",
    "BoxPrimitive",
    "CancellationToken",
    "ColorRGB",
    "ColorRGBA",
    "ComponentTreeNodeContribution",
    "ComponentTreeProvider",
    "CylinderPrimitive",
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
    "VisualPrimitive",
    "WorkspaceContribution",
    "WorkspaceLayoutContext",
]
