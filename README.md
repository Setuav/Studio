<p align="center">
  <img src="docs/images/studio_banner.png" alt="Setuav Studio banner">
</p>

<p align="center">
  <a href="https://github.com/Setuav/Studio/actions/workflows/ci.yml"><img src="https://github.com/Setuav/Studio/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI status"></a>
  <a href="https://github.com/Setuav/Studio/releases"><img src="https://img.shields.io/github/v/release/Setuav/Studio?sort=semver" alt="Latest release"></a>
  <a href="https://setuav.github.io/Studio/"><img src="https://github.com/Setuav/Studio/actions/workflows/docs.yml/badge.svg" alt="Documentation"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Setuav/Studio" alt="MIT license"></a>
</p>

**Setuav Studio** is a desktop application for parametric UAV design and
analysis. Model the airframe, propulsion and masses in one project, drive them
with formulas, and analyze aerodynamics, powertrain and flight performance.
Plugins extend every part of it.

<p align="center">
  <img src="docs/user-guide/images/design.png" alt="Setuav Studio with a vehicle in the 3D Viewer">
</p>

## Features

- Parametric fuselages, lifting surfaces and control surfaces, with NACA and
  imported airfoils.
- Constants, formulas and constraints that drive any numeric field.
- Aerodynamic sweeps and stability with AeroSandbox, electric propulsion with
  a motor and propeller catalog, and the flight-performance envelope.
- Mass, center of gravity and inertia of the whole aircraft.
- A plugin API for panels, toolbar items, component types and analyses.

## Install

Requires Python 3.12 or newer and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Setuav/Studio.git
cd Studio
uv sync --locked
uv run --locked setuav-studio
```

Desktop builds for Windows, macOS and Linux are attached to each
[release](https://github.com/Setuav/Studio/releases).

## Documentation

The [documentation](https://setuav.github.io/Studio/) covers installation, a
first design, every modeling and analysis page, and a guide to writing
plugins. Changes between releases are listed in the [changelog](CHANGELOG.md).

## Development

```bash
uv sync --locked --group dev
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pyright
uv run --locked pytest
```

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

Build the documentation with `uv run --locked --group docs mkdocs build` and the
desktop application with
`uv run --locked --group desktop pyinstaller --noconfirm --clean packaging/setuav-studio.spec`.

## License

Setuav Studio is released under the [MIT License](LICENSE).
