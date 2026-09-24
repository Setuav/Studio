import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from setuav_studio.api import (
    SettingsPageContribution,
    StudioAPI,
    StudioEvents,
)
from setuav_studio.ui.style.icons import register_plugin_icons

from .creation import GeometryCreationController, ensure_airframe_component
from .editors.airframe import AirframeEditor
from .editors.control_surface import ControlSurfaceEditor
from .editors.fuselage import FuselageEditor
from .editors.lifting_surface import LiftingSurfaceEditor
from .scene_controller import GeometrySceneController
from .settings import (
    apply_editor_settings,
    create_editor_settings_page,
)


class GeometryPlugin:
    id = "org.setuav.studio.geometry"
    priority = 80
    provides: ClassVar[dict[str, str]] = {"org.setuav.core": "1.0.0"}

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._providers: dict[str, Any] = {}
        self._scene_controller: GeometrySceneController | None = None
        self._unsubscribers: list[Callable[[], None]] = []

    def activate(self, api: StudioAPI) -> None:
        register_plugin_icons(
            "org.setuav.studio.geometry", Path(__file__).parent / "assets" / "icons"
        )
        self._api = api
        self._creation_controller = GeometryCreationController(api)
        for contribution in self._creation_controller.contributions():
            api.register_toolbar_item(contribution)

        # 1. Settings
        api.register_settings_page(
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

        # 3. Component Editors
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
            "org.setuav.core:airframe",
            lambda component: AirframeEditor(api, component),
        )

        # 4. Component Icons
        self._registered_icons: list[str] = []
        for comp_type, icon_name in (
            ("org.setuav.core:fuselage", "geometry_add_fuselage"),
            ("org.setuav.core:lifting-surface", "geometry_add_lifting_surface"),
            ("org.setuav.core:control-surface", "geometry_add_control_surface"),
            ("org.setuav.core:airframe", "component_structural_system"),
        ):
            if comp_type not in getattr(api, "_component_icons", {}):
                api.register_component_icon(comp_type, icon_name)
                self._registered_icons.append(comp_type)

        # 5. Geometry Providers (internal — not exposed through StudioAPI)
        from .engine.fuselage_geometry import build_fuselage_geometry
        from .engine.lifting_surface_geometry import build_lifting_surface_geometry

        self._providers = {
            "org.setuav.core:fuselage": build_fuselage_geometry,
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry,
        }

        # 6. Central Viewport Synchronization
        self._scene_controller = GeometrySceneController(api, self._providers)
        self._unsubscribers.append(
            api.on_project_changed(self._scene_controller.on_project_changed)
        )
        self._unsubscribers.append(
            api.on_project_content_changed(self._scene_controller.on_project_content_changed)
        )
        if api.current_project is not None:
            self._scene_controller.sync(api.current_project)

        # 7. Auto-sync physical envelopes from geometry
        api.subscribe(StudioEvents.PROJECT_OPENED, self._on_project_opened)
        if api.current_project is not None:
            self._on_project_opened()

    def get_geometry(self, project: Any = None) -> Any:
        """Build and return geometry data for the given project.

        Returns an empty GeometryData when no project is available.
        """
        from .engine.data import GeometryData
        from .engine.scene import build_project_geometry

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
                api.unregister_toolbar_item(contribution_id)
        api.unregister_component_model("org.setuav.core:lifting-surface")
        api.unregister_component_model("org.setuav.core:fuselage")
        api.unregister_component_model("org.setuav.core:control-surface")
        self._providers = {}
        if self._scene_controller is not None:
            self._scene_controller.dispose()
            self._scene_controller = None
        for unsub in getattr(self, "_unsubscribers", []):
            with contextlib.suppress(Exception):
                unsub()
        self._unsubscribers = []
        self._api = None
        for comp_type in getattr(self, "_registered_icons", []):
            api.unregister_component_icon(comp_type)
        self._registered_icons = []
        api.unregister_component_editor("org.setuav.core:fuselage")
        api.unregister_component_editor("org.setuav.core:lifting-surface")
        api.unregister_component_editor("org.setuav.core:control-surface")
        api.unregister_component_editor("org.setuav.core:airframe")
        api.unregister_settings_page("geometry.settings.editor")
        api.unsubscribe(StudioEvents.PROJECT_OPENED, self._on_project_opened)

    def _on_project_opened(self, *args: Any) -> None:
        if self._api is not None and self._api.current_project is not None:
            ensure_airframe_component(self._api.current_project)
            from .engine.envelope import sync_project_geometry_envelopes

            sync_project_geometry_envelopes(self._api.current_project)
