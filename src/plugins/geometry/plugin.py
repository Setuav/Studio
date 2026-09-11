from typing import Any, ClassVar

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

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._providers: dict[str, Any] = {}

    def activate(self, api: StudioAPI) -> None:
        self._api = api
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
                workspace_id=None,
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

        # 5. Geometry Providers (internal — not exposed through StudioAPI)
        from .engine.fuselage_geometry import build_fuselage_geometry
        from .engine.lifting_surface_geometry import build_lifting_surface_geometry

        self._providers = {
            "org.setuav.core:fuselage": build_fuselage_geometry,
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry,
        }

        # 6. Auto-sync physical envelopes from geometry
        api.subscribe(StudioEvents.PROJECT_OPENED, self._on_project_opened)
        if api.current_project is not None:
            self._on_project_opened()

    def get_geometry(self, project: Any = None) -> Any:
        """Build and return geometry data for the given project.

        Returns an empty GeometryData when no project is available.
        """
        from .engine.data import GeometryData
        from .viewport.scene import build_project_geometry

        api = getattr(self, "_api", None)
        doc = project if project is not None else (api.current_project if api is not None else None)
        if doc is None:
            return GeometryData()
        providers = getattr(self, "_providers", {})
        if not providers:
            from .engine.fuselage_geometry import build_fuselage_geometry
            from .engine.lifting_surface_geometry import build_lifting_surface_geometry

            providers = {
                "org.setuav.core:fuselage": build_fuselage_geometry,
                "org.setuav.core:lifting-surface": build_lifting_surface_geometry,
            }
        return build_project_geometry(doc, providers)

    def get_mount_targets(self, project: Any = None) -> list[Any]:
        """Return available mount targets (wings, fuselage segments) for the project."""
        from .engine.mount import generate_mount_targets

        api = getattr(self, "_api", None)
        doc = project if project is not None else (api.current_project if api is not None else None)
        return generate_mount_targets(doc)

    def compute_mount_point(
        self,
        project: Any = None,
        target_id: str = "",
        position: str = "front",
        offset: dict[str, float] | None = None,
        orientation: dict[str, float] | None = None,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Calculate the 3D mount point and orientation for a given target and configuration."""
        from .engine.mount import resolve_mount_point

        targets = self.get_mount_targets(project)
        target = next((t for t in targets if t.id == target_id), None)
        if target is None:
            return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
        return resolve_mount_point(target, position, offset, orientation)

    def check_propeller_clearance(
        self,
        project: Any = None,
        target_id: str = "",
        position: str = "front",
        offset: dict[str, float] | None = None,
        orientation: dict[str, float] | None = None,
        propeller_diameter: float = 250.0,
    ) -> dict[str, Any]:
        """Check clearance between propeller disk and aircraft geometry."""
        from .engine.mount import compute_propeller_clearance

        api = getattr(self, "_api", None)
        doc = project if project is not None else (api.current_project if api is not None else None)
        return compute_propeller_clearance(
            doc,
            target_id=target_id,
            position=position,
            offset=offset or {},
            orientation=orientation or {},
            propeller_diameter=propeller_diameter,
        )

    def get_clearance_circle(
        self,
        mount_point: tuple[float, float, float],
        orientation: tuple[float, float, float],
        propeller_diameter: float,
        num_points: int = 36,
    ) -> tuple[tuple[float, float, float], ...]:
        """Generate 3D points representing the propeller clearance circle."""
        from .engine.mount import generate_clearance_circle_points

        return generate_clearance_circle_points(
            mount_point=mount_point,
            orientation=orientation,
            diameter=propeller_diameter,
            num_points=num_points,
        )

    def deactivate(self, api: StudioAPI) -> None:
        controller = getattr(self, "_creation_controller", None)
        if controller is not None:
            for contribution_id in controller.toolbar_ids:
                api.remove_toolbar_item(contribution_id)
        api.remove_component_model("org.setuav.core:lifting-surface")
        api.remove_component_model("org.setuav.core:fuselage")
        api.remove_component_model("org.setuav.core:control-surface")
        self._providers = {}
        self._api = None
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
        api.unsubscribe(StudioEvents.PROJECT_OPENED, self._on_project_opened)

    def _on_project_opened(self, *args: Any) -> None:
        if self._api is not None and self._api.current_project is not None:
            from .engine.envelope import sync_project_geometry_envelopes

            sync_project_geometry_envelopes(self._api.current_project)

    @staticmethod
    def _apply_viewer_settings(api: StudioAPI, page: QWidget) -> None:
        apply_viewer_settings(page)
        api.publish(StudioEvents.GEOMETRY_VIEWER_SETTINGS_CHANGED)
