"""Electrical Propulsion Plugin for Setuav Studio."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

from plugins.electrical_propulsion.catalog_dialog import ComponentCatalogDialog
from plugins.electrical_propulsion.creation import (
    PropulsionCreationController,
)
from plugins.electrical_propulsion.editors import BatteryEditor, PropulsorEditor
from plugins.electrical_propulsion.editors.propulsor import (
    MOTOR_SELECTION_KIND,
    PROPELLER_SELECTION_KIND,
    PropulsorMotorEditor,
    PropulsorPropellerEditor,
    propulsor_part_nodes,
)
from plugins.electrical_propulsion.models import BatteryModel, PropulsorModel
from plugins.electrical_propulsion.models.propulsor import PROPULSOR_TYPE
from plugins.electrical_propulsion.scene_controller import PropulsionSceneController
from setuav_studio.api import (
    ComponentTreeNodeContribution,
    ComponentTypeContribution,
    StudioAPI,
    StudioPlugin,
    ToolContribution,
)

_TREE_PROVIDER_ID = "org.setuav.studio.electrical_propulsion.propulsor-parts"
_PART_ICONS = {MOTOR_SELECTION_KIND: "fa6s.gear", PROPELLER_SELECTION_KIND: "fa6s.fan"}


class ElectricalPropulsionPlugin(StudioPlugin):
    """Integrates propulsors (a motor and its propeller) and battery packs."""

    id = "org.setuav.studio.electrical_propulsion"
    name = "Electrical Propulsion"
    version = "0.3.0"
    author = "Setuav Team"
    description = "Propulsors, battery packs and electrical propulsion analyses."

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
                id=PROPULSOR_TYPE,
                name="Propulsor",
                icon="component",
                model=PropulsorModel,
                editor=lambda comp: PropulsorEditor(api, comp),
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

        # A propulsor's motor and propeller are nodes beneath it with pages of their own.
        api.register_component_tree_provider(_TREE_PROVIDER_ID, _propulsor_part_tree_nodes)
        api.register_kind_editor(
            MOTOR_SELECTION_KIND,
            lambda selection: PropulsorMotorEditor(api, _selected_propulsor(api, selection)),
        )
        api.register_kind_editor(
            PROPELLER_SELECTION_KIND,
            lambda selection: PropulsorPropellerEditor(api, _selected_propulsor(api, selection)),
        )

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
                parameters=ThrottleSweepSolver.default_parameters(),
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
                parameters=AirspeedSweepSolver.default_parameters(),
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
                parameters=OperatingPointSolver.default_parameters(),
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
            api.unregister_toolbar_item(controller.toolbar_id)

        if hasattr(self, "_analysis_toolbar_id"):
            api.unregister_toolbar_item(self._analysis_toolbar_id)

        for ct in getattr(self, "_component_types", ()):
            api.unregister_component_type(ct.id)
        api.unregister_component_tree_provider(_TREE_PROVIDER_ID)
        api.unregister_kind_editor(MOTOR_SELECTION_KIND)
        api.unregister_kind_editor(PROPELLER_SELECTION_KIND)

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


def _propulsor_part_tree_nodes(
    component: dict[str, Any],
) -> tuple[ComponentTreeNodeContribution, ...]:
    if component.get("type") != PROPULSOR_TYPE:
        return ()
    return tuple(
        ComponentTreeNodeContribution(
            id=selection["id"],
            title=selection["name"],
            selection=selection,
            icon=_PART_ICONS[selection["kind"]],
        )
        for selection in propulsor_part_nodes(component)
    )


def _selected_propulsor(api: StudioAPI, selection: dict[str, Any]) -> dict[str, Any]:
    project = api.project
    component = project.get_component(selection["component_id"]) if project is not None else None
    if component is None:
        raise LookupError(f"Propulsor '{selection['component_id']}' is not in the project.")
    return component
