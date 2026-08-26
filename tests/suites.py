"""Named unittest suites grouped by application area and plugin."""

from __future__ import annotations

import argparse
import os
import tempfile
import unittest
from collections.abc import Sequence

CORE_MODULES = (
    "tests.core.test_component_editor",
    "tests.core.test_instance",
    "tests.core.test_main",
    "tests.core.test_plugins",
    "tests.core.test_project",
    "tests.core.test_schema_drift",
    "tests.core.test_theme",
    "tests.core.test_workspaces",
)
GEOMETRY_MODULES = (
    "tests.geometry.test_creation",
    "tests.geometry.test_geometry",
    "tests.geometry.test_wing_driver_solver",
)
AERODYNAMICS_FAST_MODULES = (
    "tests.aerodynamics.test_aero_engine_base",
    "tests.aerodynamics.test_aero_plugin",
)
AERODYNAMICS_INTEGRATION_MODULES = (
    "tests.aerodynamics.integration.test_aero_3d_tool",
    "tests.aerodynamics.integration.test_aerosandbox_engine",
    "tests.aerodynamics.integration.test_airfoil_engine",
    "tests.aerodynamics.integration.test_stability_engine",
    "tests.aerodynamics.integration.test_sweep_infrastructure",
)
ELECTRICAL_PROPULSION_MODULES = (
    "tests.electrical_propulsion.test_creation",
    "tests.electrical_propulsion.test_electrical_propulsion",
)
FLIGHT_PERFORMANCE_MODULES = ("tests.flight_performance.test_flight_performance",)
WEIGHT_BALANCE_MODULES = ("tests.weight_balance.test_weight_balance",)

SUITES: dict[str, tuple[str, ...]] = {
    "core": CORE_MODULES,
    "geometry": GEOMETRY_MODULES,
    "aerodynamics-fast": AERODYNAMICS_FAST_MODULES,
    "aerodynamics-integration": AERODYNAMICS_INTEGRATION_MODULES,
    "aerodynamics": AERODYNAMICS_FAST_MODULES + AERODYNAMICS_INTEGRATION_MODULES,
    "electrical-propulsion": ELECTRICAL_PROPULSION_MODULES,
    "flight-performance": FLIGHT_PERFORMANCE_MODULES,
    "weight-balance": WEIGHT_BALANCE_MODULES,
}
SUITES["all"] = (
    CORE_MODULES
    + GEOMETRY_MODULES
    + AERODYNAMICS_FAST_MODULES
    + AERODYNAMICS_INTEGRATION_MODULES
    + ELECTRICAL_PROPULSION_MODULES
    + FLIGHT_PERFORMANCE_MODULES
    + WEIGHT_BALANCE_MODULES
)


def load_suite(name: str) -> unittest.TestSuite:
    """Load one named suite from its explicit module manifest."""
    return unittest.defaultTestLoader.loadTestsFromNames(SUITES[name])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", nargs="?", default="all", choices=sorted(SUITES))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault(
        "MPLCONFIGDIR",
        os.path.join(tempfile.gettempdir(), "setuav-studio-matplotlib"),
    )

    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(load_suite(args.suite))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
