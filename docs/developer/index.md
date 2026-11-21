# Setuav Studio Developer Documentation

Build Python packages that extend Setuav Studio with panels, toolbar items,
tools, settings pages, component types, editors, solvers, and project-tree
nodes.

Plugins use three modules:

- `setuav_studio.api` — `StudioAPI`, the contribution descriptors, and
  `StudioPlugin`.
- `setuav_studio.solver` — `AbstractSolver`, `SolverConfig`, and
  `SolverResult` for analyses.
- `setuav_studio.ui.style.icons` — `register_plugin_icons` and
  `unregister_plugin_icons`.

Other application modules are implementation details and may change at any
time. The bundled plugins in `src/plugins/` are complete reference
implementations; `src/plugins/flight_performance/` is the smallest.

## Start here

1. Implement the `StudioPlugin` lifecycle contract: `id`, `activate`, and
   `deactivate`.
2. Register contributions through the `StudioAPI` received by `activate`.
3. Undo every registration in `deactivate`.
4. Publish the plugin through the `setuav_studio.plugins` entry-point group.

```python
from PySide6.QtWidgets import QLabel

from setuav_studio.api import PanelContribution, StudioAPI, ToolbarContribution

PANEL_ID = "com.example.demo.panel"
TOOLBAR_ID = "com.example.demo.hello"


class ExamplePlugin:
    id = "com.example.demo"
    priority = 100

    def activate(self, api: StudioAPI) -> None:
        api.register_panel(
            PanelContribution(
                id=PANEL_ID,
                title="Demo",
                factory=lambda: QLabel("Hello from a plugin"),
            )
        )
        api.register_toolbar_item(
            ToolbarContribution(
                id=TOOLBAR_ID,
                title="Say Hello",
                icon="fa6s.hand",
                callback=lambda: api.show_status("Hello", "success"),
                group="example",
                order=500,
            )
        )

    def deactivate(self, api: StudioAPI) -> None:
        api.unregister_toolbar_item(TOOLBAR_ID)
        api.unregister_panel(PANEL_ID)
```

## API overview

Every `register_*` method has a matching `unregister_*` method.

| Area | `StudioAPI` members | Descriptor |
|---|---|---|
| Panels | `register_panel`, `show_panel` | `PanelContribution` |
| Toolbar | `register_toolbar_item`, `refresh_toolbar_states` | `ToolbarContribution`, `ToolbarMenuItemContribution` |
| Menus | `register_tool` (Tools menu), `register_action` (any menu path) | `ToolContribution`, `ActionContribution` |
| Settings | `register_settings_page` | `SettingsPageContribution` |
| Components | `register_component_type`, `register_component_editor`, `register_component_model`, `register_component_deriver` | `ComponentTypeContribution`, `ComponentDeriver` |
| Project tree | `register_project_tree_provider`, `register_component_tree_provider`, `register_component_menu_provider` | `ProjectTreeNodeContribution`, `ComponentTreeNodeContribution`, `ComponentMenuItemContribution` |
| Analyses | `register_solver`, `add_solver_config`, `run_solver`, `get_solver_results` | `AbstractSolver`, `SolverConfig` |
| Project data | `project`, `edit_component`, `edit_project`, `transaction`, `undo`, `redo` | — |
| Events | `subscribe`, `publish`, `on_project_changed`, `on_selection_changed`, `set_selection` | `StudioEvents` |
| Feedback | `show_status`, `report_progress`, `tasks.submit` | — |

Numeric editor fields are described with `ParameterField` and
`TableParameterField`; a field can hold a number or a formula that uses the
project constants.

Run long work through `api.tasks.submit` so the Qt UI thread never blocks.

## Analyses

An analysis is a solver class plus a toolbar item that adds a configuration to
the project. The solver declares its editable parameters in
`PARAMETER_FIELDS` and returns a `SolverResult` with summary values, tables,
and plots:

```python
from typing import ClassVar

from setuav_studio.api import ParameterField
from setuav_studio.solver import AbstractSolver, SolverResult


class HoverSolver(AbstractSolver):
    PARAMETER_FIELDS: ClassVar[list[ParameterField]] = [
        ParameterField(key="altitude", label="Altitude", unit="m", quantity="length"),
    ]

    def run(self) -> SolverResult:
        return SolverResult(solver_id="com.example.hover", config=self.config, name="Hover")
```

Register it in `activate` with
`api.register_solver("com.example.hover", HoverSolver, icon="...")`. The icon
is shown next to the solver's analyses in the Project Explorer. Add a toolbar
item in the `"analysis"` group whose callback calls `api.add_solver_config`
with a `SolverConfig` for the solver.

## Icons

An `icon` field accepts an icon name, a file path, or a `QIcon`. Names resolve
in this order: icons registered by plugins, the core icons in
`src/setuav_studio/assets/icons/`, then QtAwesome specifiers such as
`fa6s.chart-line`.

To ship icons, put one SVG per icon, named after the icon, in a folder of the
plugin and register the folder:

```python
from pathlib import Path

from setuav_studio.ui.style.icons import register_plugin_icons, unregister_plugin_icons

register_plugin_icons(self.id, Path(__file__).parent / "assets" / "icons")
...
unregister_plugin_icons(self.id)  # in deactivate
```

`assets/icons/hover.svg` then becomes the icon `hover`. The isometric style of
the bundled icons is generated by `src/setuav_studio/assets/icons/tools/iso.py`.

## Plugin discovery and loading

### Installed packages

Declare the entry point in the package's `pyproject.toml`:

```toml
[project]
name = "acme-uav-tools"
dependencies = ["setuav-studio"]

[project.entry-points."setuav_studio.plugins"]
"com.acme.uav-tools" = "acme_uav_tools.plugin:AcmePlugin"
```

The target may be a plugin class or instance with:

- `id`: stable reverse-domain identifier.
- `priority`: optional integer; lower values activate first, default `100`.
- `activate(api)` and `deactivate(api)`.

### User plugin folder

Plugins can also be placed in the user plugin folder, either as a single
`.py` file or as a folder with a `pyproject.toml` entry point, a package
`__init__.py`, or a `plugin.py`. The folder is set by the
`SETUAV_STUDIO_PLUGINS_DIR` environment variable, otherwise it is the
application data folder's `plugins` directory. The Plugin Manager can install
a plugin archive into it.

### Startup and activation

On startup the host collects the bundled plugins, installed entry points, and
user plugins, orders them by `(priority, id)`, and calls `activate(api)`.
Contributions become available only after activation returns. Remove all of
them in `deactivate(api)` so the plugin can be disabled and re-enabled safely
from the Plugin Manager.

### Project requirements

A plugin that stores data in projects can declare
`provides = {"com.acme.uav-tools": "1.2.0"}`. A project lists the plugins it
needs under `plugins` as `{"id": ..., "version": ...}`; a missing or
incompatible plugin is reported as a project issue, and the project still
opens.

### Failure scenarios

- An import or entry-point error is logged and the plugin is skipped.
- An exception from `activate` is isolated; other plugins still start.
- A duplicate plugin ID is ignored after the first successful activation.

The host records these failures as load issues shown in the Plugin Manager.
Plugins should check their optional dependencies before registering UI and
report actionable errors with `api.show_status`.

## Testing a plugin

Verify that the plugin can be activated, deactivated, and activated again.
Every registration made in `activate` needs a matching cleanup in
`deactivate`: panels, toolbar items, actions, settings pages, component
types, editors, solvers, icons, providers, and listeners.

## Security

Plugins run inside the Setuav Studio process with the application's file,
network, and operating-system permissions. Plugins are not sandboxed; install
them only from publishers you trust.
