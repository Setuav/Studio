from setuav_studio.plugin_system import StudioAPI, WorkspaceContribution
from setuav_studio.plugins.viewer.workspace import ViewerWorkspace


class OpenGLViewerPlugin:
    id = "org.setuav.studio.viewer.opengl"

    def activate(self, api: StudioAPI) -> None:
        api.set_workspace(
            WorkspaceContribution(
                id="studio.viewer.opengl",
                title="3D Viewer",
                factory=lambda: ViewerWorkspace(api),
            )
        )
