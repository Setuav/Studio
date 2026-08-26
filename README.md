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
