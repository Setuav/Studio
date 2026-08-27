# Hello plugin

This is a minimal plugin project built against `setuav-studio-sdk`.

Install it into a Setuav Studio development environment with:

```bash
uv pip install -e .
```

The `setuav_studio.plugins` entry point makes `HelloPlugin` discoverable by the
application. The plugin registers a workspace and a panel in `activate`, then
removes both registrations in `deactivate`.
