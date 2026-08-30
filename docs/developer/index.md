# Setuav Studio Developer Documentation

Build Python packages that extend Setuav Studio with panels, workspaces, menu
commands, editors, project-tree nodes, schemas, and analysis providers.

Only symbols imported from `setuav_studio_sdk` are public. Application modules
outside this package are implementation details and may change at any time.

## Start here

1. Implement the `StudioPlugin` lifecycle contract.
2. Register contributions through the `StudioAPI` received by `activate`.
3. Publish the plugin class through the `setuav_studio.plugins` entry-point group.
4. Undo registrations and release resources in the required `deactivate` method.

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
dependencies = ["setuav-studio-sdk>=0.1,<0.2"]

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
from setuav_studio_sdk import WorkspaceContribution, WorkspaceLayoutContext


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

The repository contains a minimal installable plugin in the
[`example-plugin` repository directory](https://github.com/Setuav/Studio/tree/main/packages/example-plugin). Copy it as a
starting point, replace its reverse-domain IDs, and declare the SDK dependency
in `pyproject.toml`.

Run the plugin's lifecycle test from its directory:

```bash
uv pip install -e .
uv run python -m unittest discover -s tests
```

From the repository root, run the SDK contract tests as well:

```bash
uv run --locked python scripts/sdk_contract_tests.py
```

Before publishing, verify that the plugin can be activated, deactivated, and
activated again. Every registration made in `activate` should have a matching
cleanup call in `deactivate`: panels, workspaces, actions, editors, icons,
providers, listeners, and background resources.

## Compatibility

`PLUGIN_API_VERSION` versions the public plugin contract independently from the
application. The SDK package is released independently using the
`sdk-vX.Y.Z` release process documented in the SDK release guide.

## Security

Plugins run inside the Setuav Studio process with the application's file,
network, and operating-system permissions. Plugins are not sandboxed; install
them only from publishers you trust.
