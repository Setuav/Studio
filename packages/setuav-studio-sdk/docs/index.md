# Setuav Studio SDK

The SDK is the supported boundary for third-party Python plugins. Import
plugin contracts from the SDK package only; do not import Setuav Studio
implementation modules.

## Start here

1. Implement `StudioPlugin`.
2. Register UI and project features through `StudioAPI`.
3. Publish the plugin through the `setuav_studio.plugins` entry-point group.
4. Remove registrations and release resources in `deactivate`.

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

    def deactivate(self, api: StudioAPI) -> None:
        api.remove_panel("com.example.demo.panel")
```

## API reference

- [Plugin API](@ref plugin_api)
- [Contributions](@ref contributions)
- [Provider contracts](@ref providers)
- [Plugin lifecycle](@ref lifecycle)

## Package discovery

```toml
[project.entry-points."setuav_studio.plugins"]
"com.example.demo" = "example_plugin.plugin:ExamplePlugin"
```
