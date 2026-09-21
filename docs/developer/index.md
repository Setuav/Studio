# Setuav Studio Developer Documentation

Build Python packages that extend Setuav Studio with panels, workspaces, menu
commands, editors, project-tree nodes, schemas, and analysis providers.

Only symbols imported from `setuav_studio.api` are public. Application modules
outside this package are implementation details and may change at any time.

## Start here

1. Implement the `StudioPlugin` lifecycle contract.
2. Register contributions through the `StudioAPI` received by `activate`.
3. Publish the plugin class through the `setuav_studio.plugins` entry-point group.
4. Undo registrations and release resources in the required `deactivate` method.

```python
from PySide6.QtWidgets import QLabel

from setuav_studio.api import PanelContribution, StudioAPI


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

- **Plugin API** — services available through `StudioAPI`
- **Contributions** — immutable UI and project descriptors
- **Provider contracts** — callbacks and domain services
- **Plugin lifecycle** — activation and deactivation contract

## Package discovery

Declare the plugin in its package's `pyproject.toml`:

```toml
[project.entry-points."setuav_studio.plugins"]
"com.example.demo" = "example_plugin.plugin:ExamplePlugin"
```

The entry point may resolve to a plugin class or instance. Setuav Studio loads
plugins in priority and plugin-ID order. A plugin that fails to load does not
prevent other plugins from starting.

## Plugin discovery and loading

### 1. Package metadata

Declare the plugin package and its entry point in `pyproject.toml`:

```toml
[project]
name = "acme-uav-tools"
dependencies = ["setuav-studio"]

[project.entry-points."setuav_studio.plugins"]
"com.acme.uav-tools" = "acme_uav_tools.plugin:AcmePlugin"
```

The entry-point target must expose a plugin class or instance with:

- `id`: stable reverse-domain identifier.
- `priority`: optional integer; lower values activate first.
- `activate(api)`: required lifecycle method.
- `deactivate(api)`: required cleanup method for every registration.

### 2. Schema manifest (when the plugin adds project data)

Plugins that add component, assembly, or analysis data ship a `plugin.json`
manifest that follows the core plugin-manifest schema. The manifest declares
the plugin ID and version, then maps typed IDs to schema files:

```json
{
  "$schema": "https://schemas.setuav.org/core/plugin-manifest.schema.json",
  "id": "com.acme.uav-tools",
  "version": "1.0.0",
  "component_types": {
    "com.acme.uav-tools:sensor": {
      "schema": "components/sensor.schema.json"
    }
  },
  "assembly_types": {},
  "analysis_types": {}
}
```

Keep schema paths relative to the manifest and use the same plugin ID prefix
for every type. A UI-only plugin does not need a schema manifest.

### 3. Startup and activation

On startup the host discovers bundled plugins and installed entry points,
orders them by `(priority, id)`, and calls `activate(api)`. Contributions,
listeners, providers, and commands become available only after activation
returns successfully. Remove all of them in `deactivate(api)` so the plugin
can be disabled and re-enabled safely.

When a plugin owns a workspace, pass a `default_layout` callback to its
`WorkspaceContribution`. The callback receives a `WorkspaceLayoutContext` and
can show or hide its panels, split them, and set rounded initial widths. The
shell only applies the callback when no user perspective is saved; the layout
definition stays with the plugin.

```python
from setuav_studio.api import WorkspaceContribution, WorkspaceLayoutContext


def default_layout(layout: WorkspaceLayoutContext) -> None:
    layout.split("project.explorer", "com.acme.panel")
    layout.show("project.explorer", "com.acme.panel")
    layout.resize(("project.explorer", "com.acme.panel"), (300, 900))


workspace = WorkspaceContribution(
    id="com.acme.workspace",
    title="Acme Tools",
    default_layout=default_layout,
)
```

### 4. Failure scenarios

- An import or entry-point error is logged and the plugin is skipped.
- A missing `id` or `activate` method is rejected as an invalid plugin.
- An exception from `activate` is isolated; other plugins still start.
- A duplicate plugin ID is ignored after the first successful activation.
- Missing or incompatible project plugin requirements are reported as project
  issues; the application remains usable in degraded mode.

The host records these failures as load issues for diagnostics. Plugins should
validate their own optional dependencies before registering UI and report
actionable errors through the application logger or status service.

## Plugin template and tests

You can use existing plugins in `src/plugins/` as reference implementations.
Copy a plugin as a starting point, configure its reverse-domain identifier, and
declare its dependencies in `pyproject.toml`.

Before publishing, verify that the plugin can be activated, deactivated, and
activated again. Every registration made in `activate` should have a matching
cleanup call in `deactivate`: panels, workspaces, actions, editors, icons,
providers, listeners, and background resources.

## Compatibility

`PLUGIN_API_VERSION` versions the public plugin contract. Plugins declare
their supported compatibility range with Setuav Studio.

## Security

Plugins run inside the Setuav Studio process with the application's file,
network, and operating-system permissions. Plugins are not sandboxed; install
them only from publishers you trust.
