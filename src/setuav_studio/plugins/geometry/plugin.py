from setuav_studio.plugin_system import StudioAPI
from setuav_studio.plugins.geometry.fuselage import FuselageEditor
from setuav_studio.plugins.geometry.fuselage_geometry import build_fuselage_geometry
from setuav_studio.plugins.geometry.lifting_surface_geometry import (
    build_lifting_surface_geometry,
)
from setuav_studio.plugins.geometry.propulsor_geometry import build_propulsor_geometry


class GeometryPlugin:
    id = "org.setuav.studio.geometry"
    provides = {"org.setuav.core": "1.0.0"}

    def activate(self, api: StudioAPI) -> None:
        api.register_component_editor(
            "org.setuav.core:fuselage",
            lambda component: FuselageEditor(api, component),
        )
        api.register_geometry_provider(
            "org.setuav.core:fuselage",
            build_fuselage_geometry,
        )
        api.register_geometry_provider(
            "org.setuav.core:lifting-surface",
            build_lifting_surface_geometry,
        )
        api.register_geometry_provider(
            "org.setuav.core:propeller",
            build_propulsor_geometry,
        )
        api.register_geometry_provider(
            "org.setuav.core:rotor",
            build_propulsor_geometry,
        )
