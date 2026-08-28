# Setuav Studio SDK

The Setuav Studio SDK defines the public Python contracts used by third-party
plugins. It provides the plugin lifecycle, `StudioAPI`, contribution
descriptors, and provider callback types without exposing application
implementation details.

## Installation

```bash
pip install setuav-studio-sdk
```

The SDK supports Python 3.11 and newer.

## Plugin lifecycle

A plugin exposes a stable reverse-domain ID, registers its contributions in
`activate`, and removes them in `deactivate`:

```python
from PySide6.QtWidgets import QLabel

from setuav_studio_sdk import PanelContribution, StudioAPI


class HelloPlugin:
    id = "com.example.hello"
    priority = 100

    def activate(self, api: StudioAPI) -> None:
        api.add_panel(
            PanelContribution(
                id="com.example.hello.panel",
                title="Hello Plugin",
                factory=lambda: QLabel("Hello from a Setuav Studio plugin"),
            )
        )

    def deactivate(self, api: StudioAPI) -> None:
        api.remove_panel("com.example.hello.panel")
```

Plugins are discovered through the `setuav_studio.plugins` Python entry-point
group. Contribution and entry-point IDs must be unique; use a reverse-domain
prefix owned by your project.

Declare the plugin entry point in `pyproject.toml`:

```toml
[project.entry-points."setuav_studio.plugins"]
"com.example.hello" = "my_plugin.plugin:HelloPlugin"
```

## API reference

Read the [online SDK API reference](https://setuav.github.io/Studio/developer/sdk-api-reference/)
for the complete public contract documentation.

The [example plugin](https://github.com/Setuav/Studio/tree/main/packages/example-plugin)
contains package metadata, an entry point, lifecycle implementation, and
tests that can be used as a starting point for a new plugin.

## Development

To regenerate the API reference or run the contract tests, clone the
[Setuav Studio repository](https://github.com/Setuav/Studio) and run these
commands from its root:

```bash
cd packages/setuav-studio-sdk
doxygen Doxyfile
cd ../..
uv run --locked python scripts/sdk_contract_tests.py
```

The generated reference documents only public `setuav_studio_sdk` modules.
