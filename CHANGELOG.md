# Changelog

All notable changes to Setuav Studio are documented in this file. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Breaking changes

- Project files record a format version (`format_version`, currently `1.0`)
  and the Studio version that saved them. Files without a format version, such
  as those saved by 0.1.0, no longer open. To open one, add
  `"format_version": "1.0"` to its `project.json` (inside the `.suav` archive).
- The workspaces are gone: Studio has one window with a toolbar, the Project
  Explorer, Properties, the 3D Viewer and the Result area.
- AeroSandbox is a regular dependency; the `aerodynamics` extra is removed.
  Install with `uv sync --locked`.
- Components are drawn in their own color, gray by default. The fixed color
  palette (yellow wings, red control surfaces) is gone.

### Added

- Analyses as part of the project: Alpha Sweep, Beta Sweep, Control
  Deflection and Operating Point (aerodynamics), Throttle Sweep, Airspeed Sweep
  and Operating Point (propulsion), and Flight Performance, each with tables,
  plots and a results summary.
- Flight Performance: the level-flight envelope with power, climb, endurance
  and range.
- Electric propulsion components: propulsors with motors and propellers from a
  catalog, and batteries built from chemistry profiles.
- Lifting surfaces edited as a root and sections, with planform drivers and
  formulas.
- A color for every component, set in the Transform tab or from the Project
  Explorer menu.
- Formulas in the Mass tab and in airfoil shaping, tip cap and polygon vertex
  fields; plugin features such as structural skins in formulas and in the
  Formula Assistant.
- A new isometric icon set and one toolbar per workflow stage.
- Documentation for every modeling page and analysis, and a guide to writing
  plugins.

### Changed

- Aerodynamic coefficients, the drag breakdown, the static margin and Flight
  Performance use one reference: the main wing's planform area, span and mean
  aerodynamic chord.
- Sweep stability is evaluated at zero angle of attack (Alpha Sweep) and zero
  sideslip (Beta Sweep).
- Control surface area, area ratio and the aerodynamic hinge follow the hinge
  line drawn in the 3D Viewer.
- NACA airfoils use the same point order as imported airfoils and keep their
  open trailing edge.
- Battery series and parallel counts are limited by the model (32S, 64P), and
  out-of-range values are reported instead of crashing the editor.

### Fixed

- Deflected ailerons and mixed ruddervator commands no longer split a wing
  into two halves of half the aspect ratio in AeroBuildup.
- The Mass tab no longer counts control surfaces twice, keeps formulas, and
  stores only the edited value.
- Propulsor and battery masses follow formula changes.
- Constraints and formulas on measured geometry evaluate in the constraint
  status, the Problems list, and when a project opens or is saved.
- The Formula Assistant only inserts names the formula engine evaluates.

### Removed

- Settings that nothing used: the default loft method, the viewport palette,
  and the PyThrust data folder setting (use `PYTHRUST_DATA_DIR`).

## [0.1.0] - 2026-09-16

First public release.

[Unreleased]: https://github.com/Setuav/Studio/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Setuav/Studio/releases/tag/v0.1.0
