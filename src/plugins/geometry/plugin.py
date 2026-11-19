from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, ClassVar

from setuav_studio.api import (
    ComponentTypeContribution,
    SettingsPageContribution,
    StudioAPI,
)
from setuav_studio.ui.style.icons import register_plugin_icons, unregister_plugin_icons

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
        self._creation_controller: AirframeCreationController | None = None

    def activate(self, api: StudioAPI) -> None:
        register_plugin_icons(
            "org.setuav.studio.airframe_design", Path(__file__).parent / "assets" / "icons"
        )
        self._api = api
        self._creation_controller = AirframeCreationController(api)
        for contribution in self._creation_controller.contributions():
            api.register_toolbar_item(contribution)

        # Settings
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

        # Component Types (models, editors, icons)
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
                describe=_describe_lifting_surface,
            ),
            ComponentTypeContribution(
                id="org.setuav.core:control-surface",
                name="Control Surface",
                icon="geometry_add_control_surface",
                model=ControlSurfaceModel,
                editor=lambda component: ControlSurfaceEditor(api, component),
                category="Airframe Design",
                subpart=True,
                describe=_describe_control_surface,
            ),
        ]
        for contrib in self._component_types:
            api.register_component_type(contrib)

        # Geometry providers
        from .engine.fuselage_geometry import build_fuselage_geometry
        from .engine.lifting_surface_geometry import build_lifting_surface_geometry

        self._providers = {
            "org.setuav.core:fuselage": build_fuselage_geometry,
            "org.setuav.core:lifting-surface": build_lifting_surface_geometry,
        }

        # Central Viewport Synchronization
        self._scene_controller = AirframeSceneController(api, self._providers)
        self._unsubscribers.append(
            api.on_project_changed(self._scene_controller.on_project_changed)
        )
        self._unsubscribers.append(
            api.on_project_content_changed(self._scene_controller.on_project_content_changed)
        )
        if api.project is not None:
            self._scene_controller.sync(api.project)

        # Envelopes derived from each geometry component's parameters
        for type_id in _GEOMETRY_TYPES:
            api.register_component_deriver(type_id, _derive_envelope)
        api.derive_components()

    def deactivate(self, api: StudioAPI) -> None:
        if self._creation_controller is not None:
            for contribution_id in self._creation_controller.toolbar_ids:
                api.unregister_toolbar_item(contribution_id)
            self._creation_controller = None
        for contrib in self._component_types:
            api.unregister_component_type(contrib.id)
        self._component_types = []
        self._providers = {}
        if self._scene_controller is not None:
            self._scene_controller.dispose()
            self._scene_controller = None
        for unsub in self._unsubscribers:
            unsub()
        self._unsubscribers = []
        self._api = None
        api.unregister_settings_page("airframe_design.settings.editor")
        for type_id in _GEOMETRY_TYPES:
            api.unregister_component_deriver(type_id)
        unregister_plugin_icons("org.setuav.studio.airframe_design")


def _describe_lifting_surface(component: dict[str, Any]) -> str:
    bilateral = component["parameters"]["geometry"].get("mirror") is True
    return "Lifting Surface (Bilateral)" if bilateral else "Lifting Surface"


def _describe_control_surface(component: dict[str, Any]) -> str:
    kind = str(component["parameters"]["geometry"]["type"])
    return f"Control Surface ({kind.capitalize()})"


_GEOMETRY_TYPES = (
    "org.setuav.core:fuselage",
    "org.setuav.core:lifting-surface",
    "org.setuav.core:control-surface",
)


def _derive_envelope(component: dict[str, Any], components: Mapping[str, dict[str, Any]]) -> None:
    from .engine.envelope import sync_component_envelope

    sync_component_envelope(component, components.get(str(component.get("attach_to"))))
