from PySide6.QtWidgets import QWidget

from setuav_studio.plugin_system import (
    PanelContribution,
    SettingsPageContribution,
    StudioAPI,
    WorkspaceContribution,
)

from .creation import GeometryCreationController
from .editors.control_surface import ControlSurfaceEditor
from .editors.fuselage import FuselageEditor
from .editors.lifting_surface import LiftingSurfaceEditor
from .engine.fuselage_geometry import build_fuselage_geometry
from .engine.lifting_surface_geometry import build_lifting_surface_geometry
from .settings import (
    apply_editor_settings,
    apply_viewer_settings,
    create_editor_settings_page,
    create_viewer_settings_page,
)
from .workspace import ViewerWorkspace


class GeometryPlugin:
    id = "org.setuav.studio.geometry"
    provides = {"org.setuav.core": "1.0.0"}

    def activate(self, api: StudioAPI) -> None:
        self._creation_controller = GeometryCreationController(api)
        for contribution in self._creation_controller.contributions():
            api.add_toolbar_item(contribution)

        # 1. 3D Design Workspace & Viewport
        api.add_workspace(
            WorkspaceContribution(
                id="studio.workspace.design",
                title="Design",
                order=0,
            )
        )
        api.add_panel(
            PanelContribution(
                id="studio.viewer.opengl",
                title="3D Viewer",
                factory=lambda: ViewerWorkspace(api),
                workspace_id="studio.workspace.design",
                icon="viewer_3d",
            )
        )
        api.add_settings_page(
            SettingsPageContribution(
                id="geometry.settings.viewer",
                title="3D Viewer",
                factory=create_viewer_settings_page,
                apply=lambda page: self._apply_viewer_settings(api, page),
                group="Geometry Engine",
                order=10,
            )
        )
        api.add_settings_page(
            SettingsPageContribution(
                id="geometry.settings.editor",
                title="Geometry Editor",
                factory=create_editor_settings_page,
                apply=apply_editor_settings,
                group="Geometry Engine",
                order=20,
            )
        )

        # 2. Component Editors
        api.register_component_editor(
            "org.setuav.core:fuselage",
            lambda component: FuselageEditor(api, component),
        )
        api.register_component_editor(
            "org.setuav.core:lifting-surface",
            lambda component: LiftingSurfaceEditor(api, component),
        )
        api.register_component_editor(
            "org.setuav.core:control-surface",
            lambda component: ControlSurfaceEditor(api, component),
        )

        # 3. Component Icons
        api.register_component_icon(
            "org.setuav.core:fuselage",
            "geometry_add_fuselage",
        )
        api.register_component_icon(
            "org.setuav.core:lifting-surface",
            "geometry_add_lifting_surface",
        )
        api.register_component_icon(
            "org.setuav.core:control-surface",
            "geometry_add_control_surface",
        )

        # 4. Geometry Providers
        api.register_geometry_provider(
            "org.setuav.core:fuselage",
            build_fuselage_geometry,
        )
        api.register_geometry_provider(
            "org.setuav.core:lifting-surface",
            build_lifting_surface_geometry,
        )

    def deactivate(self, api: StudioAPI) -> None:
        controller = getattr(self, "_creation_controller", None)
        if controller is not None:
            for contribution_id in controller.toolbar_ids:
                api.remove_toolbar_item(contribution_id)
        api.remove_geometry_provider("org.setuav.core:fuselage")
        api.remove_geometry_provider("org.setuav.core:lifting-surface")
        api.remove_component_icon("org.setuav.core:fuselage")
        api.remove_component_icon("org.setuav.core:lifting-surface")
        api.remove_component_icon("org.setuav.core:control-surface")
        api.remove_component_editor("org.setuav.core:fuselage")
        api.remove_component_editor("org.setuav.core:lifting-surface")
        api.remove_component_editor("org.setuav.core:control-surface")
        api.remove_panel("studio.viewer.opengl")
        api.remove_workspace("studio.workspace.design")
        api.remove_settings_page("geometry.settings.viewer")
        api.remove_settings_page("geometry.settings.editor")

    @staticmethod
    def _apply_viewer_settings(api: StudioAPI, page: QWidget) -> None:
        apply_viewer_settings(page)
        api.publish("geometry.viewer.settings.changed")
