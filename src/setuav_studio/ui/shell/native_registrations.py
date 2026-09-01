from __future__ import annotations

from typing import TYPE_CHECKING

from setuav_studio.ui.editors import (
    EnvelopeEditor,
    InstanceEditor,
    TransformEditor,
)
from setuav_studio.ui.parameters import ProjectParametersPanel
from setuav_studio.ui.project_explorer import ProjectExplorerPanel
from setuav_studio.ui.properties import PropertiesPanel
from setuav_studio.ui.settings import (
    GeneralSettingsPage,
    UnitsSettingsPage,
)
from setuav_studio_sdk import PanelContribution, SettingsPageContribution

if TYPE_CHECKING:
    from setuav_studio.plugin_system import StudioAPI


def register_native_contributions(api: StudioAPI) -> None:
    """Register built-in native panels, kind editors, and settings pages into the StudioAPI."""
    # 1. Native Panels
    api.add_panel(
        PanelContribution(
            id="core:project-explorer",
            title="Project Explorer",
            factory=lambda: ProjectExplorerPanel(api),
            area="left",
            icon="fa6s.folder-tree",
        )
    )
    api.add_panel(
        PanelContribution(
            id="core:properties",
            title="Properties",
            factory=lambda: PropertiesPanel(api),
            area="right",
            icon="fa6s.sliders",
        )
    )
    api.add_panel(
        PanelContribution(
            id="core:parameters",
            title="Project Parameters",
            factory=lambda: ProjectParametersPanel(api),
            area="bottom",
            icon="constant",
            hidden=True,
        )
    )

    # 2. Native Kind Editors
    api.register_kind_editor("transform", TransformEditor)
    api.register_kind_editor("envelope", EnvelopeEditor)
    api.register_kind_editor("instance", InstanceEditor)

    # 3. Native Settings Pages
    api.register_settings_page(
        SettingsPageContribution(
            id="core:general",
            title="General",
            factory=GeneralSettingsPage,
        )
    )
    api.register_settings_page(
        SettingsPageContribution(
            id="core:units",
            title="Units",
            factory=UnitsSettingsPage,
        )
    )
