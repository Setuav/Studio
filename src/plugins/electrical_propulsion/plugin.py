"""Electrical Propulsion Plugin for Setuav Studio."""

from __future__ import annotations

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

        # Register Propulsion Solver
        from plugins.electrical_propulsion.solver import (
            SOLVER_ID_PROPULSION,
            ElectricalPropulsionSolver,
        )
        from setuav_studio.api import ToolbarContribution

        api.register_solver(SOLVER_ID_PROPULSION, ElectricalPropulsionSolver)

        def add_propulsion_analysis() -> None:
            if api.current_project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            from setuav_studio.solver import SolverConfig

            config = SolverConfig(
                solver_id=SOLVER_ID_PROPULSION,
                name="Propulsion Analysis",
                parameters={
                    "mode": "airspeed_sweep",
                    "v_min": 0.0,
                    "v_max": 35.0,
                    "v_step": 1.0,
                    "throttle": 100.0,
                    "altitude": 0.0,
                    "temperature": 15.0,
                },
            )
            api.add_solver_config(config)
            api.show_status("Added Propulsion Analysis configuration.", "success", 3000)

        self._analysis_toolbar_id = "propulsion.add-analysis"
        api.register_toolbar_item(
            ToolbarContribution(
                id=self._analysis_toolbar_id,
                title="Add Propulsion Analysis",
                icon="fa6s.chart-line",
                callback=add_propulsion_analysis,
                enabled_when=lambda: api.current_project is not None,
                group="propulsion-creation",
                order=120,
            )
        )

        self._analysis_tool = ToolContribution(
            group="Electrical Propulsion",
            title="Add Propulsion Analysis",
            callback=add_propulsion_analysis,
            icon="fa6s.chart-line",
        )
        api.register_tool(self._analysis_tool)

    def deactivate(self, api: StudioAPI) -> None:
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

        if getattr(self, "_analysis_tool", None) is not None:
            api.unregister_tool(self._analysis_tool)

        from plugins.electrical_propulsion.solver import SOLVER_ID_PROPULSION

        api.unregister_solver(SOLVER_ID_PROPULSION)
