"""Flight Performance Analysis Plugin for Setuav Studio."""

from __future__ import annotations

from setuav_studio.api import StudioAPI, ToolbarContribution, ToolContribution
from setuav_studio.solver import SolverConfig

from .solver import SOLVER_ID_FLIGHT_PERFORMANCE, FlightPerformanceSolver

_TOOLBAR_ID = "flight_performance.add-analysis"


class FlightPerformancePlugin:
    """Plugin providing the fixed-wing level-flight performance solver."""

    id = "org.setuav.studio.flight_performance"
    priority = 50

    def __init__(self) -> None:
        self._api: StudioAPI | None = None
        self._tool: ToolContribution | None = None

    def activate(self, api: StudioAPI) -> None:
        self._api = api
        api.register_solver(SOLVER_ID_FLIGHT_PERFORMANCE, FlightPerformanceSolver)
        api.register_toolbar_item(
            ToolbarContribution(
                id=_TOOLBAR_ID,
                title="Add Flight Performance Analysis",
                icon="fa6s.gauge-high",
                callback=self._add_analysis,
                enabled_when=lambda: api.project is not None,
                group="performance-creation",
                order=150,
            )
        )
        self._tool = ToolContribution(
            group="Performance",
            title="Add Flight Performance Analysis",
            callback=self._add_analysis,
            icon="fa6s.gauge-high",
        )
        api.register_tool(self._tool)

    def deactivate(self, api: StudioAPI) -> None:
        api.unregister_toolbar_item(_TOOLBAR_ID)
        if self._tool is not None:
            api.unregister_tool(self._tool)
            self._tool = None
        api.unregister_solver(SOLVER_ID_FLIGHT_PERFORMANCE)
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
                name="Flight Performance Analysis",
                parameters=FlightPerformanceSolver.default_parameters(),
            )
        )
        api.show_status("Added Flight Performance configuration.", "success", 3000)


__all__ = ["FlightPerformancePlugin"]
