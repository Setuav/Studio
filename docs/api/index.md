# Setuav Studio Plugin SDK

The Setuav Studio Plugin SDK is the supported integration surface for third-party
plugins. Plugin code should import public contracts only from `setuav_studio.sdk`.
Modules outside that namespace are implementation details and may change without
following the plugin API compatibility policy.

## Plugin contract

A plugin is a Python class with a stable, namespaced `id` and an `activate`
method. A `deactivate` method is required by the current lifecycle protocol.

```python
from setuav_studio.sdk import StudioAPI


class ExamplePlugin:
    id = "com.example.demo"
    priority = 100

    def activate(self, api: StudioAPI) -> None:
        api.show_status("Example plugin activated")

    def deactivate(self, api: StudioAPI) -> None:
        pass
```

## Package discovery

Third-party plugins are distributed as Python packages. Their `pyproject.toml`
registers the plugin class in the `setuav_studio.plugins` entry-point group:

```toml
[project.entry-points."setuav_studio.plugins"]
"com.example.demo" = "example_plugin.plugin:ExamplePlugin"
```

The entry point may resolve to either a plugin class or a plugin instance.
Setuav Studio loads entry points in priority and plugin-ID order, and isolates
load failures so one plugin cannot prevent the remaining plugins from starting.

## Compatibility

`PLUGIN_API_VERSION` identifies the public SDK contract independently from the
Setuav Studio application version. Compatibility metadata and enforcement will
be added to the plugin lifecycle before third-party distribution is enabled.

## Trust model

Plugins run as Python code inside the Setuav Studio process. They have the same
file, network, and operating-system permissions as the application and are not
sandboxed. Users should install plugins only from publishers they trust.
