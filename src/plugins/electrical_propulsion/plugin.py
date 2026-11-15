"""Electrical Propulsion Plugin for Setuav Studio."""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from plugins.electrical_propulsion.catalog_dialog import ComponentCatalogDialog
from plugins.electrical_propulsion.creation import (
    PropulsionCreationController,
)
from plugins.electrical_propulsion.editors import (
    BatteryEditor,
    EscEditor,
    MotorEditor,
    PropellerEditor,
    PropulsionSystemEditor,
)
from plugins.electrical_propulsion.models import (
    BatteryModel,
    ESCModel,
    MotorModel,
    PropellerModel,
    PropulsionSystemModel,
)
from plugins.electrical_propulsion.scene_controller import PropulsionSceneController
from setuav_studio.api import (
    ComponentTypeContribution,
    StudioAPI,
    StudioPlugin,
    ToolContribution,
)


class ElectricalPropulsionPlugin(StudioPlugin):
    """Integrates electrical propulsion systems, motors, propellers, ESCs, and batteries."""

    id = "org.setuav.studio.electrical_propulsion"
    name = "Electrical Propulsion"
    version = "0.3.0"
    author = "Setuav Team"
    description = "Electric motors, propellers, ESCs, batteries and fixed propulsion root system."

    def __init__(self) -> None:
        super().__init__()
        self._api: StudioAPI | None = None
        self._scene_controller: PropulsionSceneController | None = None
        self._unsubscribers: list[Callable[[], None]] = []

    def activate(self, api: StudioAPI) -> None:
        self._api = api

        # Register Creation Toolbar Actions
        self._creation_controller = PropulsionCreationController(api)
        for contribution in self._creation_controller.contributions():
            api.register_toolbar_item(contribution)

        # Register Component Types
        self._component_types = [
            ComponentTypeContribution(
                id="org.setuav.core:propulsion-system",
                name="Propulsion",
                icon="component_propulsion_system",
                model=PropulsionSystemModel,
                editor=lambda comp: PropulsionSystemEditor(api, comp),
                category="Propulsion",
            ),
            ComponentTypeContribution(
                id="org.setuav.core:motor",
                name="Electric Motor",
                icon="component",
                model=MotorModel,
                editor=lambda comp: MotorEditor(api, comp),
                category="Propulsion",
            ),
            ComponentTypeContribution(
                id="org.setuav.core:propeller",
                name="Propeller",
                icon="component",
                model=PropellerModel,
                editor=lambda comp: PropellerEditor(api, comp),
                category="Propulsion",
            ),
            ComponentTypeContribution(
                id="org.setuav.core:rotor",
                name="Rotor",
                icon="component",
                model=PropellerModel,
                editor=lambda comp: PropellerEditor(api, comp),
                category="Propulsion",
            ),
            ComponentTypeContribution(
                id="org.setuav.core:esc",
                name="ESC (Speed Controller)",
                icon="component",
                model=ESCModel,
                editor=lambda comp: EscEditor(api, comp),
                category="Propulsion",
            ),
            ComponentTypeContribution(
                id="org.setuav.core:battery",
                name="Battery",
                icon="component",
                model=BatteryModel,
                editor=lambda comp: BatteryEditor(api, comp),
                category="Electrical",
            ),
        ]
        for ct in self._component_types:
            api.register_component_type(ct)

        # Register Component Database Tool
        def open_component_database() -> None:
            dialog = ComponentCatalogDialog(component_type="all")
            dialog.exec()

        self._tool_contribution = ToolContribution(
            group="Electrical Propulsion",
            title="Component Database…",
            callback=open_component_database,
            icon="fa6s.database",
        )
        api.register_tool(self._tool_contribution)

        # Register Propulsion Solvers
        from plugins.electrical_propulsion.solver import (
            SOLVER_ID_AIRSPEED_SWEEP,
            SOLVER_ID_OPERATING_POINT,
            SOLVER_ID_THROTTLE_SWEEP,
            AirspeedSweepSolver,
            OperatingPointSolver,
            ThrottleSweepSolver,
        )
        from setuav_studio.api import (
            ToolbarContribution,
            ToolbarMenuItemContribution,
        )
        from setuav_studio.solver import SolverConfig

        api.register_solver(SOLVER_ID_THROTTLE_SWEEP, ThrottleSweepSolver)
        api.register_solver(SOLVER_ID_AIRSPEED_SWEEP, AirspeedSweepSolver)
        api.register_solver(SOLVER_ID_OPERATING_POINT, OperatingPointSolver)

        def add_throttle_sweep_analysis() -> None:
            if api.project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_THROTTLE_SWEEP,
                name="Throttle Sweep Analysis",
                parameters={
                    "airspeed": 15.0,
                    "t_min": 10.0,
                    "t_max": 100.0,
                    "t_step": 5.0,
                    "altitude": 0.0,
                    "temperature": 15.0,
                },
            )
            api.add_solver_config(config)
            api.show_status("Added Throttle Sweep Analysis configuration.", "success", 3000)

        def add_airspeed_sweep_analysis() -> None:
            if api.project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_AIRSPEED_SWEEP,
                name="Airspeed Sweep Analysis",
                parameters={
                    "v_min": 0.0,
                    "v_max": 35.0,
                    "v_step": 1.0,
                    "throttle": 100.0,
                    "altitude": 0.0,
                    "temperature": 15.0,
                },
            )
            api.add_solver_config(config)
            api.show_status("Added Airspeed Sweep Analysis configuration.", "success", 3000)

        def add_operating_point_analysis() -> None:
            if api.project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_OPERATING_POINT,
                name="Operating Point Analysis",
                parameters={
                    "airspeed": 18.0,
                    "throttle": 75.0,
                    "altitude": 0.0,
                    "temperature": 15.0,
                },
            )
            api.add_solver_config(config)
            api.show_status("Added Operating Point Analysis configuration.", "success", 3000)

        self._analysis_toolbar_id = "propulsion.add-analysis"
        api.register_toolbar_item(
            ToolbarContribution(
                id=self._analysis_toolbar_id,
                title="Add Propulsion Analysis",
                icon="fa6s.chart-line",
                menu_items=(
                    ToolbarMenuItemContribution(
                        title="Throttle Sweep Analysis",
                        callback=add_throttle_sweep_analysis,
                        icon="fa6s.gauge-high",
                        enabled_when=lambda: api.project is not None,
                    ),
                    ToolbarMenuItemContribution(
                        title="Airspeed Sweep Analysis",
                        callback=add_airspeed_sweep_analysis,
                        icon="fa6s.wind",
                        enabled_when=lambda: api.project is not None,
                    ),
                    ToolbarMenuItemContribution(
                        title="Operating Point Analysis",
                        callback=add_operating_point_analysis,
                        icon="fa6s.crosshairs",
                        enabled_when=lambda: api.project is not None,
                    ),
                ),
                enabled_when=lambda: api.project is not None,
                group="propulsion-creation",
                order=120,
            )
        )

        self._analysis_tools = [
            ToolContribution(
                group="Electrical Propulsion",
                title="Add Throttle Sweep Analysis",
                callback=add_throttle_sweep_analysis,
                icon="fa6s.gauge-high",
            ),
            ToolContribution(
                group="Electrical Propulsion",
                title="Add Airspeed Sweep Analysis",
                callback=add_airspeed_sweep_analysis,
                icon="fa6s.wind",
            ),
            ToolContribution(
                group="Electrical Propulsion",
                title="Add Operating Point Analysis",
                callback=add_operating_point_analysis,
                icon="fa6s.crosshairs",
            ),
        ]
        for tool in self._analysis_tools:
            api.register_tool(tool)

        # Viewport 3D Propeller Scene Synchronization
        self._scene_controller = PropulsionSceneController(api)
        self._unsubscribers.append(
            api.on_project_changed(self._scene_controller.on_project_changed)
        )
        self._unsubscribers.append(
            api.on_project_content_changed(self._scene_controller.on_project_content_changed)
        )
        if api.project is not None:
            self._scene_controller.sync(api.project)

    def deactivate(self, api: StudioAPI) -> None:
        if self._scene_controller is not None:
            self._scene_controller.dispose()
            self._scene_controller = None

        for unsub in getattr(self, "_unsubscribers", []):
            with contextlib.suppress(Exception):
                unsub()
        self._unsubscribers = []

        controller = getattr(self, "_creation_controller", None)
        if controller is not None:
            for contribution_id in controller.toolbar_ids:
                api.unregister_toolbar_item(contribution_id)

        if hasattr(self, "_analysis_toolbar_id"):
            api.unregister_toolbar_item(self._analysis_toolbar_id)

        for ct in getattr(self, "_component_types", ()):
            api.unregister_component_type(ct.id)

        if getattr(self, "_tool_contribution", None) is not None:
            api.unregister_tool(self._tool_contribution)

        for tool in getattr(self, "_analysis_tools", ()):
            api.unregister_tool(tool)

        from plugins.electrical_propulsion.solver import (
            SOLVER_ID_AIRSPEED_SWEEP,
            SOLVER_ID_OPERATING_POINT,
            SOLVER_ID_THROTTLE_SWEEP,
        )

        api.unregister_solver(SOLVER_ID_THROTTLE_SWEEP)
        api.unregister_solver(SOLVER_ID_AIRSPEED_SWEEP)
        api.unregister_solver(SOLVER_ID_OPERATING_POINT)
