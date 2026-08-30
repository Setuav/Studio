"""Minimal plugin demonstrating SDK discovery and lifecycle hooks."""

from PySide6.QtWidgets import QLabel

from setuav_studio_sdk import (
    PanelContribution,
    StudioAPI,
    WorkspaceContribution,
    WorkspaceLayoutContext,
)


def default_layout(layout: WorkspaceLayoutContext) -> None:
    """Set the example workspace's initial panel arrangement."""
    layout.show("com.example.hello.panel")
    layout.resize(("com.example.hello.panel",), (1000,))


class HelloPlugin:
    """Register one workspace and one panel when the plugin is activated."""

    id = "com.example.hello"
    priority = 1000

    def activate(self, api: StudioAPI) -> None:
        api.add_workspace(
            WorkspaceContribution(
                id="com.example.hello.workspace",
                title="Hello",
                order=1000,
                default_layout=default_layout,
            )
        )
        api.add_panel(
            PanelContribution(
                id="com.example.hello.panel",
                title="Hello Plugin",
                factory=lambda: QLabel("Hello from a Setuav Studio plugin"),
                workspace_id="com.example.hello.workspace",
            )
        )

    def deactivate(self, api: StudioAPI) -> None:
        api.remove_panel("com.example.hello.panel")
        api.remove_workspace("com.example.hello.workspace")
