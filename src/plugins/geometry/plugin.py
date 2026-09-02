from typing import ClassVar

from PySide6.QtWidgets import QWidget

from setuav_studio_sdk import (
    PanelContribution,
    SettingsPageContribution,
    StudioAPI,
    StudioEvents,
    WorkspaceContribution,
    WorkspaceLayoutContext,
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


def _apply_design_workspace_layout(layout: WorkspaceLayoutContext) -> None:
    """Set the default Design workspace arrangement owned by this plugin."""
    layout.split("project.explorer", "studio.viewer.opengl")
    layout.split("studio.viewer.opengl", "studio.properties")
    layout.show("project.explorer", "studio.viewer.opengl", "studio.properties")
    layout.raise_dock("studio.viewer.opengl")
    layout.resize(
        ("project.explorer", "studio.viewer.opengl", "studio.properties"),
        (240, 680, 270),
    )


class GeometryPlugin:
    id = "org.setuav.studio.geometry"
    priority = 80
    provides: ClassVar[dict[str, str]] = {"org.setuav.core": "1.0.0"}

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
                default_layout=_apply_design_workspace_layout,
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

        # 2. Component Models
        from .models import ControlSurfaceModel, FuselageModel, LiftingSurfaceModel

        api.register_component_model(
            "org.setuav.core:lifting-surface",
            LiftingSurfaceModel,
        )
        api.register_component_model(
            "org.setuav.core:fuselage",
            FuselageModel,
        )
        api.register_component_model(
            "org.setuav.core:control-surface",
            ControlSurfaceModel,
        )

        # 3. Component & Assembly Editors
        from .editors.structural_system import StructuralSystemEditor

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
        api.register_component_editor(
            "org.setuav.core:structural-system",
            lambda assembly: StructuralSystemEditor(api, assembly),
        )

        # 4. Component & Assembly Icons
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
        api.register_component_icon(
            "org.setuav.core:structural-system",
            "component_structural_system",
        )

        # 5. Geometry Providers
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
        api.remove_component_model("org.setuav.core:lifting-surface")
        api.remove_component_model("org.setuav.core:fuselage")
        api.remove_component_model("org.setuav.core:control-surface")
        api.remove_geometry_provider("org.setuav.core:fuselage")
        api.remove_geometry_provider("org.setuav.core:lifting-surface")
        api.remove_component_icon("org.setuav.core:fuselage")
        api.remove_component_icon("org.setuav.core:lifting-surface")
        api.remove_component_icon("org.setuav.core:control-surface")
        api.remove_component_icon("org.setuav.core:structural-system")
        api.remove_component_editor("org.setuav.core:fuselage")
        api.remove_component_editor("org.setuav.core:lifting-surface")
        api.remove_component_editor("org.setuav.core:control-surface")
        api.remove_component_editor("org.setuav.core:structural-system")
        api.remove_panel("studio.viewer.opengl")
        api.remove_workspace("studio.workspace.design")
        api.remove_settings_page("geometry.settings.viewer")
        api.remove_settings_page("geometry.settings.editor")

    @staticmethod
    def _apply_viewer_settings(api: StudioAPI, page: QWidget) -> None:
        apply_viewer_settings(page)
        api.publish(StudioEvents.GEOMETRY_VIEWER_SETTINGS_CHANGED)
