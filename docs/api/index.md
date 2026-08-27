# Setuav Studio Plugin SDK

Build Python packages that extend Setuav Studio with panels, workspaces, menu
commands, editors, project-tree nodes, schemas, and analysis providers.

Only symbols imported from `setuav_studio_sdk` are public. Application modules
outside this package are implementation details and may change at any time.

## Start here

1. Implement the `StudioPlugin` lifecycle contract.
2. Register contributions through the `StudioAPI` received by `activate`.
3. Publish the plugin class through the `setuav_studio.plugins` entry-point group.
4. Undo registrations and release resources in `deactivate`.

```python
from PySide6.QtWidgets import QLabel

from setuav_studio_sdk import PanelContribution, StudioAPI


class ExamplePlugin:
    id = "com.example.demo"
    priority = 100

    def activate(self, api: StudioAPI) -> None:
        api.add_panel(
            PanelContribution(
                id="com.example.demo.panel",
                title="Demo",
                factory=lambda: QLabel("Hello from a plugin"),
            )
        )
        api.show_status("Example plugin activated", "success")

    def deactivate(self, api: StudioAPI) -> None:
        api.remove_panel("com.example.demo.panel")
```

## API reference

- [Plugin API](@ref plugin_api) — services available through `StudioAPI`
- [Contributions](@ref contributions) — immutable UI and project descriptors
- [Provider contracts](@ref providers) — callbacks and domain services
- [Plugin lifecycle](@ref lifecycle) — activation and deactivation contract

## Package discovery

Declare the plugin in its package's `pyproject.toml`:

```toml
[project.entry-points."setuav_studio.plugins"]
"com.example.demo" = "example_plugin.plugin:ExamplePlugin"
```

The entry point may resolve to a plugin class or instance. Setuav Studio loads
plugins in priority and plugin-ID order. A plugin that fails to load does not
prevent other plugins from starting.

## Compatibility

`PLUGIN_API_VERSION` versions the public plugin contract independently from the
application. Compatibility metadata and enforcement will be introduced before
third-party distribution is enabled.

## Security

Plugins run inside the Setuav Studio process with the application's file,
network, and operating-system permissions. Plugins are not sandboxed; install
them only from publishers you trust.
