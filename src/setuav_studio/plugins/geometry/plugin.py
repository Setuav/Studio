from setuav_studio.plugin_system import StudioAPI
from setuav_studio.plugins.geometry.fuselage import FuselageEditor


class GeometryPlugin:
    id = "org.setuav.studio.geometry"

    def activate(self, api: StudioAPI) -> None:
        api.register_component_editor(
            "org.setuav.core:fuselage",
            FuselageEditor,
        )
