"""Electrical Propulsion Plugin for Setuav Studio."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
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
from plugins.electrical_propulsion.models.battery import battery_pack
from plugins.electrical_propulsion.models.propulsor import PROPULSOR_TYPE, propulsor_mass
from plugins.electrical_propulsion.powertrain import BATTERY_TYPE
from plugins.electrical_propulsion.scene_controller import PropulsionSceneController
from setuav_studio.api import (
    ComponentTreeNodeContribution,
    ComponentTypeContribution,
    StudioAPI,
    StudioPlugin,
    ToolContribution,
)
from setuav_studio.ui.style.icons import register_plugin_icons, unregister_plugin_icons

_ANALYSIS_TOOLBAR_PREFIX = "propulsion.add-"
_ANALYSIS_KEYS = ("throttle-sweep", "airspeed-sweep", "operating-point")
_TREE_PROVIDER_ID = "org.setuav.studio.electrical_propulsion.propulsor-parts"
_PART_ICONS = {
    MOTOR_SELECTION_KIND: "propulsion_motor",
    PROPELLER_SELECTION_KIND: "propulsion_propeller",
}


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
        self._creation_controller: PropulsionCreationController | None = None
        self._component_types: list[ComponentTypeContribution] = []
        self._tool_contribution: ToolContribution | None = None

    def activate(self, api: StudioAPI) -> None:
        register_plugin_icons(self.id, Path(__file__).parent / "assets" / "icons")
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
                icon="propulsion_propulsor",
                model=PropulsorModel,
                editor=lambda comp: PropulsorEditor(api, comp),
                category="Propulsion",
                derived_mass=True,
            ),
            ComponentTypeContribution(
                id=BATTERY_TYPE,
                name="Battery",
                icon="propulsion_battery",
                model=BatteryModel,
                editor=lambda comp: BatteryEditor(api, comp),
                category="Electrical",
                derived_mass=True,
            ),
        ]
        for ct in self._component_types:
            api.register_component_type(ct)
        # A propulsor's and a battery's mass follow from their parameters,
        # including parameters given by formulas.
        api.register_component_deriver(PROPULSOR_TYPE, _derive_propulsor_mass)
        api.register_component_deriver(BATTERY_TYPE, _derive_battery_mass)
        api.derive_components()

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
            icon="propulsion_component_database",
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
        from setuav_studio.api import ToolbarContribution
        from setuav_studio.solver import SolverConfig
        from setuav_studio.solver.launch import analysis_available

        api.register_solver(
            SOLVER_ID_THROTTLE_SWEEP, ThrottleSweepSolver, icon="propulsion_throttle_sweep"
        )
        api.register_solver(
            SOLVER_ID_AIRSPEED_SWEEP, AirspeedSweepSolver, icon="propulsion_airspeed_sweep"
        )
        api.register_solver(
            SOLVER_ID_OPERATING_POINT, OperatingPointSolver, icon="propulsion_operating_point"
        )

        def add_throttle_sweep_analysis() -> None:
            if api.project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_THROTTLE_SWEEP,
                name="Throttle Sweep",
                parameters=ThrottleSweepSolver.default_parameters(),
            )
            api.add_solver_config(config)
            api.show_status("Added Throttle Sweep configuration.", "success", 3000)

        def add_airspeed_sweep_analysis() -> None:
            if api.project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_AIRSPEED_SWEEP,
                name="Airspeed Sweep",
                parameters=AirspeedSweepSolver.default_parameters(),
            )
            api.add_solver_config(config)
            api.show_status("Added Airspeed Sweep configuration.", "success", 3000)

        def add_operating_point_analysis() -> None:
            if api.project is None:
                api.show_status("Open or create a project first.", "warning", 3000)
                return
            config = SolverConfig(
                solver_id=SOLVER_ID_OPERATING_POINT,
                name="Operating Point",
                parameters=OperatingPointSolver.default_parameters(),
            )
            api.add_solver_config(config)
            api.show_status("Added Operating Point configuration.", "success", 3000)

        analyses = (
            (
                ThrottleSweepSolver,
                "Add Throttle Sweep Analysis",
                add_throttle_sweep_analysis,
                "propulsion_throttle_sweep",
            ),
            (
                AirspeedSweepSolver,
                "Add Airspeed Sweep Analysis",
                add_airspeed_sweep_analysis,
                "propulsion_airspeed_sweep",
            ),
            (
                OperatingPointSolver,
                "Add Propulsion Operating Point Analysis",
                add_operating_point_analysis,
                "propulsion_operating_point",
            ),
        )
        for index, (key, (solver_cls, title, callback, icon)) in enumerate(
            zip(_ANALYSIS_KEYS, analyses, strict=True)
        ):
            api.register_toolbar_item(
                ToolbarContribution(
                    id=f"{_ANALYSIS_TOOLBAR_PREFIX}{key}",
                    title=title,
                    callback=callback,
                    icon=icon,
                    enabled_when=lambda solver_cls=solver_cls: analysis_available(api, solver_cls),
                    group="analysis",
                    order=210 + index,
                )
            )

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

        for unsub in self._unsubscribers:
            unsub()
        self._unsubscribers = []

        if self._creation_controller is not None:
            for toolbar_id in self._creation_controller.toolbar_ids:
                api.unregister_toolbar_item(toolbar_id)
            self._creation_controller = None
        for key in _ANALYSIS_KEYS:
            api.unregister_toolbar_item(f"{_ANALYSIS_TOOLBAR_PREFIX}{key}")
        unregister_plugin_icons(self.id)

        api.unregister_component_deriver(PROPULSOR_TYPE)
        api.unregister_component_deriver(BATTERY_TYPE)
        for ct in self._component_types:
            api.unregister_component_type(ct.id)
        self._component_types = []
        api.unregister_component_tree_provider(_TREE_PROVIDER_ID)
        api.unregister_kind_editor(MOTOR_SELECTION_KIND)
        api.unregister_kind_editor(PROPELLER_SELECTION_KIND)

        if self._tool_contribution is not None:
            api.unregister_tool(self._tool_contribution)
            self._tool_contribution = None

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


def _derive_propulsor_mass(component: dict[str, Any], _components: Mapping[str, Any]) -> None:
    """Set the propulsor's mass to its motor and propeller masses."""
    component["mass"] = propulsor_mass(component["parameters"])


def _derive_battery_mass(component: dict[str, Any], _components: Mapping[str, Any]) -> None:
    """Set the battery's mass to its pack mass."""
    component["mass"] = battery_pack(component["parameters"]).mass_g
