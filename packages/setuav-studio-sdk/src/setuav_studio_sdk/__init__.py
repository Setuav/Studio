"""Public API for Setuav Studio plugin authors.

Third-party plugins should import contracts from this package instead of
application implementation modules.
"""

from .api import (
    ComponentTreeProvider,
    GeometryProvider,
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
from .models import ProjectDocument
from .plugin import PLUGIN_ENTRY_POINT_GROUP, StudioPlugin
from .version import PLUGIN_API_VERSION

__all__ = [
    "PLUGIN_API_VERSION",
    "PLUGIN_ENTRY_POINT_GROUP",
    "ActionContribution",
    "ComponentTreeNodeContribution",
    "ComponentTreeProvider",
    "GeometryProvider",
    "PanelContribution",
    "ParameterField",
    "ProjectDocument",
    "ProjectTreeNodeContribution",
    "ProjectTreeProvider",
    "SettingsPageContribution",
    "StudioAPI",
    "StudioPlugin",
    "ToolContribution",
    "ToolbarContribution",
    "ToolbarMenuItemContribution",
    "WorkspaceContribution",
    "WorkspaceLayoutContext",
]
