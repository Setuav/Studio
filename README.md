# Setuav Studio

Plugin-based desktop application for parametric UAV design and analysis.

## Tests

Tests are grouped by application area and plugin. Run the complete suite with:

```bash
python -m tests.suites all
```

Run an individual suite while developing a plugin:

```bash
python -m tests.suites core
python -m tests.suites geometry
python -m tests.suites aerodynamics-fast
python -m tests.suites aerodynamics-integration
python -m tests.suites electrical-propulsion
python -m tests.suites flight-performance
python -m tests.suites weight-balance
```

The aggregate aerodynamics suite is also available as
`python -m tests.suites aerodynamics`. Use `python -m tests.suites --help` to
list every suite.

Run the full coverage gate with:

```bash
coverage run -m tests.suites all
coverage report
```

## Quality and packaging

Install the locked development environment and run the local quality gates:

```bash
uv sync --locked --all-extras --group dev
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pyright
uv run --locked python -m tests.suites all
```

Check dependency declarations, known vulnerabilities, and licenses:

```bash
uv run --locked --all-extras --group security deptry src
uv run --locked --all-extras --group security pip-audit --local --progress-spinner=off
uv run --locked --all-extras --group security pip-licenses
```

Build the wheel and source distribution:

```bash
uv run --locked --group package python -m build
```

CI installs the wheel into a clean environment and runs
`scripts/package_smoke_test.py` to verify imports, the command-line entry point,
and bundled icons, fonts, schemas, and airfoil data.

# to-do
- ci-cd
- dökümantasyon

-> vtol roadmap
-> multicopter roadmap

-> openvsp plugin
-> avl plugin ~
-> gazebo plugin
-> jsbsim plugin
-> openfoam/su2 plugin
