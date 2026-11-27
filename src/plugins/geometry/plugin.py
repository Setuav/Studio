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
        api.register_component_menu_provider(
            self.id,
            self._creation_controller.component_menu_items,
        )

        # Settings
        api.register_settings_page(
            SettingsPageContribution(
                id="airframe_design.settings.editor",
                title="Airframe Editor",
                factory=create_editor_settings_page,
                apply=apply_editor_settings,
                icon="settings_general",
                group="Airframe Design",
                group_icon="vehicle",
                order=20,
            )
        )

        # Component Types (models, editors, icons)
        from .models import ControlSurfaceModel, FuselageModel, LiftingSurfaceModel

        self._component_types = [
            ComponentTypeContribution(
                id=_FUSELAGE_TYPE,
                name="Fuselage",
                icon="geometry_add_fuselage",
                model=FuselageModel,
                editor=lambda component: FuselageEditor(api, component),
                category="Airframe Design",
            ),
            ComponentTypeContribution(
                id=_LIFTING_SURFACE_TYPE,
                name="Lifting Surface",
                icon="geometry_add_lifting_surface",
                model=LiftingSurfaceModel,
                editor=lambda component: LiftingSurfaceEditor(api, component),
                category="Airframe Design",
                describe=_describe_lifting_surface,
            ),
            ComponentTypeContribution(
                id=_CONTROL_SURFACE_TYPE,
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
            _FUSELAGE_TYPE: build_fuselage_geometry,
            _LIFTING_SURFACE_TYPE: build_lifting_surface_geometry,
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

        # Data derived from each geometry component's parameters
        api.register_component_deriver(_FUSELAGE_TYPE, _derive_envelope)
        api.register_component_deriver(_LIFTING_SURFACE_TYPE, _derive_lifting_surface)
        api.register_component_deriver(_CONTROL_SURFACE_TYPE, _derive_control_surface)
        api.derive_components()

    def deactivate(self, api: StudioAPI) -> None:
        if self._creation_controller is not None:
            api.unregister_component_menu_provider(self.id)
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


_FUSELAGE_TYPE = "org.setuav.core:fuselage"
_LIFTING_SURFACE_TYPE = "org.setuav.core:lifting-surface"
_CONTROL_SURFACE_TYPE = "org.setuav.core:control-surface"
_GEOMETRY_TYPES = (_FUSELAGE_TYPE, _LIFTING_SURFACE_TYPE, _CONTROL_SURFACE_TYPE)


def _derive_envelope(component: dict[str, Any], components: Mapping[str, dict[str, Any]]) -> None:
    from .engine.envelope import sync_component_envelope

    sync_component_envelope(component, components.get(str(component.get("attach_to"))))


def _derive_lifting_surface(
    component: dict[str, Any], components: Mapping[str, dict[str, Any]]
) -> None:
    """Build the profiles from the wing's sections, then derive its envelope."""
    from setuav_studio.utilities.transform import get_local_transform

    from .engine.lifting_surface_layout import derive_profiles

    geometry = component["parameters"]["geometry"]
    (_x, y_offset, _z), _rotation = get_local_transform(component)
    derive_profiles(geometry, symmetric=geometry.get("mirror") is True, y_offset=y_offset)
    _derive_envelope(component, components)


def _derive_control_surface(
    component: dict[str, Any], components: Mapping[str, dict[str, Any]]
) -> None:
    """Size the control surface on its lifting surface, then derive its envelope."""
    from .engine.control_surface_geometry import surface_span_info, sync_sizing_values

    surface = components.get(str(component.get("attach_to")))
    if surface is not None and surface.get("type") == _LIFTING_SURFACE_TYPE:
        semi_span, root_chord, _tip_chord, _area = surface_span_info(
            surface["parameters"]["geometry"]["profiles"]
        )
        sync_sizing_values(component["parameters"]["geometry"], semi_span, root_chord)
    _derive_envelope(component, components)
