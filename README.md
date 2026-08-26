<p align="center">
  <img src="src/setuav_studio/assets/icons/studio.png" width="160" alt="Setuav Studio icon">
</p>

<h1 align="center">Setuav Studio</h1>

<p align="center">
  A plugin-based desktop application for parametric UAV design and analysis.
</p>

<p align="center">
  <a href="https://github.com/Setuav/studio/actions/workflows/ci.yml">
    <img src="https://github.com/Setuav/studio/actions/workflows/ci.yml/badge.svg" alt="CI status">
  </a>
</p>

Setuav Studio brings geometry design, engineering analysis, and project data into
one extensible desktop workspace. It is built with Python and PySide6 and uses a
plugin architecture so design and analysis capabilities can evolve independently.

## Features

- Parametric fuselage, lifting-surface, and control-surface design.
- Interactive OpenGL geometry viewer with selection and section editing.
- Aerodynamic analysis, stability results, polar charts, airfoil tools, and a
  native AeroSandbox VLM viewer.
- Electrical propulsion modeling and result visualization.
- Flight-performance envelope analysis.
- Weight-and-balance analysis with component-level mass properties.
- Extensible workspaces, panels, tools, component editors, and project schemas.
- Folder, `project.json`, and portable `.suav` project support.

## Requirements

- Python 3.11 or newer.
- [`uv`](https://docs.astral.sh/uv/) for locked dependency management.
- A desktop environment supported by PySide6.

The aerodynamics extra installs AeroSandbox and PyVista. These dependencies are
included by `--all-extras` in the commands below.

## Quick start

Clone the repository and install the locked runtime environment:

```bash
git clone https://github.com/Setuav/studio.git
cd studio
uv sync --locked --all-extras
```

Start the application:

```bash
uv run --locked setuav-studio
```

Open an existing project directly:

```bash
uv run --locked setuav-studio path/to/project
uv run --locked setuav-studio path/to/project.suav
```

## Development

Install the development dependencies:

```bash
uv sync --locked --all-extras --group dev
```

Run the code checks and test suite:

```bash
uv run --locked pre-commit run --all-files
uv run --locked python -m tests.suites all
```

Automatic checks before each commit can be enabled optionally:

```bash
uv run --locked pre-commit install
```

Tests can also be run for a single area while developing:

```bash
uv run --locked python -m tests.suites geometry
uv run --locked python -m tests.suites aerodynamics
```

Run `uv run --locked python -m tests.suites --help` to list all test groups.

## Desktop build

Create a local PyInstaller build:

```bash
uv sync --locked --all-extras --group desktop
uv run --locked --all-extras --group desktop \
  pyinstaller --noconfirm --clean setuav-studio.spec
```

The application is created under `dist/setuav-studio/`. CI runs the full package,
startup, security, and dependency checks automatically.

## Plugin development

Plugins extend Setuav Studio through the `StudioAPI`. A plugin can register
workspaces, panels, toolbar actions, tools, component editors, project schemas,
geometry providers, and project-tree nodes. Each plugin owns its activation and
cleanup lifecycle, allowing capabilities to be added without changing the
application core.

## License

Setuav Studio is released under the [MIT License](LICENSE).
