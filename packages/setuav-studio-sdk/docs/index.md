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

- **Plugin API**
- **Contributions**
- **Provider contracts**
- **Plugin lifecycle**

## Package discovery

```toml
[project.entry-points."setuav_studio.plugins"]
"com.example.demo" = "example_plugin.plugin:ExamplePlugin"
```

## Discovery and loading

The entry point must resolve to a class or instance with a stable `id` and an
`activate(api)` method. An optional integer `priority` controls startup order;
lower values activate first, followed by plugin ID. Register contributions and
listeners in `activate`, and remove them in the required `deactivate` method.

Plugins that add project data also ship a `plugin.json` schema manifest:

```json
{
  "$schema": "https://schemas.setuav.org/core/plugin-manifest.schema.json",
  "id": "com.example.demo",
  "version": "1.0.0",
  "component_types": {},
  "assembly_types": {},
  "analysis_types": {}
}
```

Import, validation, and activation errors are isolated to the failing plugin;
Setuav Studio records the issue and continues loading the remaining plugins.
A duplicate plugin ID is ignored after the first successful activation.
