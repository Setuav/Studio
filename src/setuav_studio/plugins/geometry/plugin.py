from setuav_studio.plugin_system import (
    PanelContribution,
    StudioAPI,
    WorkspaceContribution,
)
from setuav_studio.plugins.geometry.control_surface import ControlSurfaceEditor
from setuav_studio.plugins.geometry.fuselage import FuselageEditor
from setuav_studio.plugins.geometry.fuselage_geometry import build_fuselage_geometry
from setuav_studio.plugins.geometry.lifting_surface import LiftingSurfaceEditor
from setuav_studio.plugins.geometry.lifting_surface_geometry import (
    build_lifting_surface_geometry,
)
from setuav_studio.plugins.geometry.workspace import ViewerWorkspace


class GeometryPlugin:
    id = "org.setuav.studio.geometry"
    provides = {"org.setuav.core": "1.0.0"}

    def activate(self, api: StudioAPI) -> None:
        # 1. 3D Design Workspace & Viewport
        api.add_workspace(
            WorkspaceContribution(
                id="studio.workspace.design",
                title="Design",
                icon="fa6s.cubes",
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
        api.register_component_icon("org.setuav.core:fuselage", "fa6s.shuttle-space")
        api.register_component_icon("org.setuav.core:lifting-surface", "fa6s.plane")
        api.register_component_icon("org.setuav.core:control-surface", "fa6s.sliders")

        # 4. Geometry Providers
        api.register_geometry_provider(
            "org.setuav.core:fuselage",
            build_fuselage_geometry,
        )
        api.register_geometry_provider(
            "org.setuav.core:lifting-surface",
            build_lifting_surface_geometry,
        )
