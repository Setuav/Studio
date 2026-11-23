"""Flight Performance Analysis Plugin for Setuav Studio."""

from __future__ import annotations

from pathlib import Path

from setuav_studio.api import StudioAPI, ToolbarContribution
from setuav_studio.solver import SolverConfig
from setuav_studio.ui.style.icons import register_plugin_icons, unregister_plugin_icons

from .solver import SOLVER_ID_FLIGHT_PERFORMANCE, FlightPerformanceSolver

_TOOLBAR_ID = "flight_performance.add-analysis"


class FlightPerformancePlugin:
    """Plugin providing the fixed-wing level-flight performance solver."""

    id = "org.setuav.studio.flight_performance"
    requires = (
        "org.setuav.studio.aerodynamics",
        "org.setuav.studio.electrical_propulsion",
    )

    def __init__(self) -> None:
        self._api: StudioAPI | None = None

    def activate(self, api: StudioAPI) -> None:
        register_plugin_icons(self.id, Path(__file__).parent / "assets" / "icons")
        self._api = api
        api.register_solver(
            SOLVER_ID_FLIGHT_PERFORMANCE, FlightPerformanceSolver, icon="flight_performance"
        )
        api.register_toolbar_item(
            ToolbarContribution(
                id=_TOOLBAR_ID,
                title="Add Flight Performance Analysis",
                icon="flight_performance",
                callback=self._add_analysis,
                enabled_when=lambda: api.project is not None,
                group="analysis",
                order=220,
            )
        )

    def deactivate(self, api: StudioAPI) -> None:
        api.unregister_toolbar_item(_TOOLBAR_ID)
        api.unregister_solver(SOLVER_ID_FLIGHT_PERFORMANCE)
        unregister_plugin_icons(self.id)
        self._api = None

    def _add_analysis(self) -> None:
        api = self._api
        if api is None:
            return
        if api.project is None:
            api.show_status("Open or create a project first.", "warning", 3000)
            return
        api.add_solver_config(
            SolverConfig(
                solver_id=SOLVER_ID_FLIGHT_PERFORMANCE,
                name="Flight Performance",
                parameters=FlightPerformanceSolver.default_parameters(),
            )
        )
        api.show_status("Added Flight Performance configuration.", "success", 3000)


__all__ = ["FlightPerformancePlugin"]
