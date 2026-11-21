# Installation

Setuav Studio needs Python 3.12 or newer, [`uv`](https://docs.astral.sh/uv/),
and a desktop environment supported by PySide6, with OpenGL for the 3D Viewer.

## Install from source

Clone the repository and install the locked environment:

```bash
git clone https://github.com/Setuav/Studio.git
cd Studio
uv sync --locked
```

All analyses, including the AeroSandbox-based aerodynamics, are part of this
install.

## Start Studio

```bash
uv run --locked setuav-studio
```

To open a project directly, pass its folder, `project.json`, or `.suav` path:

```bash
uv run --locked setuav-studio path/to/project.suav
```

!!! note "Plugins installed by hand"
    `uv sync` makes the environment match the lock file exactly, so it removes
    packages you installed into it yourself, such as a plugin under
    development. Install them again afterwards, or use `uv run --locked`,
    which leaves them in place.

Continue with [First Design](first-design.md).
