from setuav_studio.plugin_system import PanelContribution, StudioAPI, WorkspaceContribution
from setuav_studio.plugins.viewer.workspace import ViewerWorkspace


class OpenGLViewerPlugin:
    id = "org.setuav.studio.viewer.opengl"

    def activate(self, api: StudioAPI) -> None:
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
