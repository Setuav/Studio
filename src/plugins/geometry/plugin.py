import contextlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, ClassVar

from setuav_studio.api import (
    ComponentTypeContribution,
    SettingsPageContribution,
    StudioAPI,
)
from setuav_studio.ui.style.icons import register_plugin_icons

from .creation import AirframeCreationController
from .editors.control_surface import ControlSurfaceEditor
from .editors.fuselage import FuselageEditor
from .editors.lifting_surface import LiftingSurfaceEditor
from .scene_controller import AirframeSceneController
from .settings import (
    apply_editor_settings,
    create_editor_settings_page,
)


class AirframeDesignPlugin:
    id = "org.setuav.studio.airframe_design"
    priority = 80
    provides: ClassVar[dict[str, str]] = {"org.setuav.core": "1.0.0"}

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._providers: dict[str, Any] = {}
        self._scene_controller: AirframeSceneController | None = None
        self._unsubscribers: list[Callable[[], None]] = []
        self._component_types: list[ComponentTypeContribution] = []

    def activate(self, api: StudioAPI) -> None:
        register_plugin_icons(
            "org.setuav.studio.airframe_design", Path(__file__).parent / "assets" / "icons"
        )
        self._api = api
        self._creation_controller = AirframeCreationController(api)
        for contribution in self._creation_controller.contributions():
            api.register_toolbar_item(contribution)

        # 1. Settings
        api.register_settings_page(
            SettingsPageContribution(
                id="airframe_design.settings.editor",
                title="Airframe Editor",
                factory=create_editor_settings_page,
                apply=apply_editor_settings,
                group="Airframe Design",
                order=20,
            )
        )

        # 2. Component Types (models, editors, icons)
        from .models import ControlSurfaceModel, FuselageModel, LiftingSurfaceModel

        self._component_types = [
            ComponentTypeContribution(
                id="org.setuav.core:fuselage",
                name="Fuselage",
                icon="geometry_add_fuselage",
                model=FuselageModel,
                editor=lambda component: FuselageEditor(api, component),
                category="Airframe Design",
            ),
            ComponentTypeContribution(
                id="org.setuav.core:lifting-surface",
                name="Lifting Surface",
                icon="geometry_add_lifting_surface",
                model=LiftingSurfaceModel,
                editor=lambda component: LiftingSurfaceEditor(api, component),
                category="Airframe Design",
            ),
            ComponentTypeContribution(
                id="org.setuav.core:control-surface",
                name="Control Surface",
                icon="geometry_add_control_surface",
                model=ControlSurfaceModel,
                editor=lambda component: ControlSurfaceEditor(api, component),
                category="Airframe Design",
                subpart=True,
            ),
        ]
        for contrib in self._component_types:
            api.register_component_type(contrib)

        # 5. Geometry Providers (internal — not exposed through StudioAPI)
        from .engine.fuselage_geometry import build_fuselage_geometry
        from .engine.lifting_surface_geometry import build_lifting_surface_geometry

        self._providers = {
            "org.setuav.core:fuselage": build_fuselage_geometry,
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry,
        }

        # 6. Central Viewport Synchronization
        self._scene_controller = AirframeSceneController(api, self._providers)
        self._unsubscribers.append(
            api.on_project_changed(self._scene_controller.on_project_changed)
        )
        self._unsubscribers.append(
            api.on_project_content_changed(self._scene_controller.on_project_content_changed)
        )
        if api.project is not None:
            self._scene_controller.sync(api.project)

        # 7. Envelopes derived from each geometry component's parameters
        for type_id in _GEOMETRY_TYPES:
            api.register_component_deriver(type_id, _derive_envelope)
        api.derive_components()

    def get_geometry(self, project: Any = None) -> Any:
        """Build and return geometry data for the given project.

        Returns an empty GeometryData when no project is available.
        """
        from .engine.data import GeometryData
        from .engine.scene import build_project_geometry

        api = getattr(self, "_api", None)
        doc = project if project is not None else (api.project if api is not None else None)
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

    def deactivate(self, api: StudioAPI) -> None:
        controller = getattr(self, "_creation_controller", None)
        if controller is not None:
            for contribution_id in controller.toolbar_ids:
                api.unregister_toolbar_item(contribution_id)
        for contrib in getattr(self, "_component_types", []):
            api.unregister_component_type(contrib.id)
        self._component_types = []
        self._providers = {}
        if self._scene_controller is not None:
            self._scene_controller.dispose()
            self._scene_controller = None
        for unsub in getattr(self, "_unsubscribers", []):
            with contextlib.suppress(Exception):
                unsub()
        self._unsubscribers = []
        self._api = None
        api.unregister_settings_page("airframe_design.settings.editor")
        for type_id in _GEOMETRY_TYPES:
            api.unregister_component_deriver(type_id)


_GEOMETRY_TYPES = (
    "org.setuav.core:fuselage",
    "org.setuav.core:lifting-surface",
    "org.setuav.core:control-surface",
)


def _derive_envelope(component: dict[str, Any], components: Mapping[str, dict[str, Any]]) -> None:
    from .engine.envelope import sync_component_envelope

    sync_component_envelope(component, components.get(str(component.get("attach_to"))))
