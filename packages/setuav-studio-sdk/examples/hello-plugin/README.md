# Hello plugin template

This is a minimal, installable plugin project built against
`setuav-studio-sdk`. Copy this directory as the starting point for a new
plugin and replace the example identifiers and UI.

## Layout

```text
hello-plugin/
├── pyproject.toml                 # package metadata and entry point
├── src/setuav_example_plugin/
│   ├── __init__.py
│   └── plugin.py                  # activate/deactivate implementation
└── tests/test_plugin.py           # lifecycle contract test
```

The entry-point key (`com.example.hello`) and every contribution ID must be
unique to the plugin. Use a reverse-domain prefix owned by your project.

## Install and test

Install it into a Setuav Studio development environment with:

```bash
uv pip install -e .
python -m unittest discover -s tests
```

The `setuav_studio.plugins` entry point makes `HelloPlugin` discoverable by the
application. The plugin registers a workspace and a panel in `activate`, then
removes both registrations in `deactivate`. Follow the same cleanup pattern
for listeners, providers, actions, and other resources.
