"""Aerodynamics Analysis Solvers integrating AeroSandbox with Core Studio Solver Architecture."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from plugins.aerodynamics.engine.aerosandbox_analysis import DEFAULT_SOLVER_SETTINGS
from plugins.aerodynamics.engine.aerosandbox_engine import AeroSandboxEngine
from plugins.aerodynamics.engine.base import (
    CONTROL_CHANNELS,
    AeroAnalysisError,
    AeroResult,
    AnalysisMethod,
    FlightCondition,
    control_channels_for_components,
)
from setuav_studio.api import ParameterField
from setuav_studio.solver.base import AbstractSolver, SolverConfig, SolverStatus
from setuav_studio.solver.results import (
    PlotDefinition,
    PlotSeriesDef,
    SolverResult,
    SummaryItem,
    TableColumn,
    TableDefinition,
)
from setuav_studio.task.types import TaskCancelledError

logger = logging.getLogger(__name__)

SOLVER_ID_ALPHA_SWEEP = "org.setuav.aerodynamics.alpha_sweep"
SOLVER_ID_BETA_SWEEP = "org.setuav.aerodynamics.beta_sweep"
SOLVER_ID_CONTROL_DEFLECTION = "org.setuav.aerodynamics.control_deflection"
SOLVER_ID_OPERATING_POINT = "org.setuav.aerodynamics.operating_point"


class BaseAerodynamicsSolver(AbstractSolver):
    """Base solver providing shared AeroSandbox execution, component extraction, and result formatting."""

    def __init__(self, config: SolverConfig) -> None:
        super().__init__(config)
        self.engine = AeroSandboxEngine()

    def _extract_components(self) -> list[dict[str, Any]]:
        project = self.project
        if project is None and self.api is not None:
            project = self.api.project

        if project is None:
            raise RuntimeError("No active project available for aerodynamic analysis.")

        components = project.data["components"]
        if not isinstance(components, list):
            raise RuntimeError("Project components collection is invalid.")

        lifting_surfaces = [
            c
            for c in components
            if isinstance(c, dict) and c.get("type") == "org.setuav.core:lifting-surface"
        ]
        if not lifting_surfaces:
            raise RuntimeError(
                "Project contains no lifting surfaces. Please add at least one wing before running aerodynamic analysis."
            )

        return components

    def _parameter(self, key: str) -> float:
        return float(self.config.parameters[key])

    def _sweep(self, name: str) -> tuple[float, float, int]:
        """Return the bounds and point count of the ``name`` sweep parameters."""
        low = self._parameter(f"{name}_min")
        high = self._parameter(f"{name}_max")
        step = self._parameter(f"{name}_step")
        if step <= 0.0:
            raise ValueError(f"The {name} step must be positive.")
        if high <= low:
            raise ValueError(f"The {name} maximum ({high:g}) must exceed its minimum ({low:g}).")
        # A sweep always keeps both of its ends, however large the step.
        return low, high, max(round((high - low) / step) + 1, 2)

    def _velocity(self) -> float:
        velocity = self._parameter("velocity")
        if velocity <= 0.0:
            raise ValueError("The airspeed must be positive.")
        return velocity

    def _method(self) -> AnalysisMethod:
        return AnalysisMethod.from_value(self.config.parameters["method"])

    def _settings(self, spanwise_resolution: int, chordwise_resolution: int) -> dict[str, Any]:
        return {
            **DEFAULT_SOLVER_SETTINGS,
            "spanwise_resolution": spanwise_resolution,
            "chordwise_resolution": chordwise_resolution,
        }

    def _configured_settings(self) -> dict[str, Any]:
        params = self.config.parameters
        return self._settings(
            int(params["spanwise_resolution"]), int(params["chordwise_resolution"])
        )

    def _create_progress_callback(self):
        def progress_cb(current: int, total: int, message: str) -> None:
            if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
                self.status = SolverStatus.CANCELLED
                raise TaskCancelledError("Aerodynamic analysis cancelled by user.")
            if self.token is not None:
                self.token.report_progress(current, total, message)

        return progress_cb


class AlphaSweepSolver(BaseAerodynamicsSolver):
    """Evaluates aerodynamic polars and stability across an angle of attack (AoA) range."""

    PARAMETER_FIELDS: ClassVar[list[ParameterField]] = [
        ParameterField(
            key="alpha_min",
            label="AoA Min",
            unit="°",
            quantity="angle",
            field_type=float,
            default=-5.0,
            min_value=-90.0,
            max_value=90.0,
            decimals=1,
            tooltip="Starting angle of attack.",
        ),
        ParameterField(
            key="alpha_max",
            label="AoA Max",
            unit="°",
            quantity="angle",
            field_type=float,
            default=15.0,
            min_value=-90.0,
            max_value=90.0,
            decimals=1,
            tooltip="Ending angle of attack.",
        ),
        ParameterField(
            key="alpha_step",
            label="AoA Step",
            unit="°",
            quantity="angle",
            field_type=float,
            default=1.0,
            min_value=0.1,
            max_value=20.0,
            decimals=1,
            tooltip="Angle of attack increment.",
        ),
        ParameterField(
            key="velocity",
            label="Airspeed",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=25.0,
            min_value=1.0,
            max_value=300.0,
            decimals=1,
            tooltip="Constant flight airspeed for polar sweep.",
        ),
        ParameterField(
            key="altitude",
            label="Altitude",
            unit="m",
            quantity="length",
            field_type=float,
            default=0.0,
            min_value=-500.0,
            max_value=25000.0,
            decimals=0,
            tooltip="Atmospheric flight altitude.",
        ),
        ParameterField(
            key="beta",
            label="Sideslip (β)",
            unit="°",
            quantity="angle",
            field_type=float,
            default=0.0,
            min_value=-45.0,
            max_value=45.0,
            decimals=1,
            tooltip="Constant sideslip angle.",
        ),
        ParameterField(
            key="method",
            label="Solver Method",
            field_type=str,
            default="aero_buildup",
            options=(
                ("aero_buildup", "AeroBuildup (Fast)"),
                ("vlm", "Vortex Lattice (VLM)"),
                ("lifting_line", "Lifting Line (LLT)"),
            ),
            tooltip="Aerodynamic solver calculation method.",
        ),
        ParameterField(
            key="spanwise_resolution",
            label="Spanwise Panels",
            field_type=float,
            default=12.0,
            min_value=4.0,
            max_value=50.0,
            decimals=0,
            tooltip="Mesh panel resolution along span for VLM / LLT.",
        ),
        ParameterField(
            key="chordwise_resolution",
            label="Chordwise Panels",
            field_type=float,
            default=8.0,
            min_value=2.0,
            max_value=30.0,
            decimals=0,
            tooltip="Mesh panel resolution along chord for VLM.",
        ),
    ]

    def run(self) -> SolverResult:
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Analysis cancelled before execution.")

        components = self._extract_components()

        alpha_min, alpha_max, num_steps = self._sweep("alpha")
        condition = FlightCondition(
            velocity=self._velocity(),
            # Stability derivatives are evaluated at zero angle of attack.
            alpha=0.0,
            beta=self._parameter("beta"),
            altitude=self._parameter("altitude"),
            sweep_variable="alpha",
            sweep_min=alpha_min,
            sweep_max=alpha_max,
            sweep_steps=num_steps,
        )

        aero_result = self.engine.analyze(
            components=components,
            condition=condition,
            method=self._method(),
            settings=self._configured_settings(),
            progress_callback=self._create_progress_callback(),
        )

        return self._build_result(aero_result)

    def _build_result(self, res: AeroResult) -> SolverResult:
        pts = [p for p in res.polar_points if p.converged]

        alpha_col = [p.alpha for p in pts]
        cl_col = [p.cl for p in pts]
        cd_col = [p.cd for p in pts]
        cm_col = [p.cm for p in pts]
        ld_col = [p.cl_over_cd for p in pts]
        cd_i_col = [p.cd_induced if p.cd_induced is not None else 0.0 for p in pts]
        cd_p_col = [p.cd_profile if p.cd_profile is not None else 0.0 for p in pts]
        lift_col = [p.forces_moments.lift if p.forces_moments else 0.0 for p in pts]
        drag_col = [p.forces_moments.drag if p.forces_moments else 0.0 for p in pts]

        table = TableDefinition(
            id="alpha_polar",
            title="Polar",
            columns=[
                TableColumn("alpha", "AoA (α)", unit="°", quantity_id="angle"),
                TableColumn("cl", "CL"),
                TableColumn("cd", "CD"),
                TableColumn("cm", "Cm"),
                TableColumn("cl_over_cd", "L/D"),
                TableColumn("cd_induced", "CDi"),
                TableColumn("cd_profile", "CDp"),
                TableColumn("lift", "Lift", unit="N", quantity_id="force"),
                TableColumn("drag", "Drag", unit="N", quantity_id="force"),
            ],
            data={
                "alpha": alpha_col,
                "cl": cl_col,
                "cd": cd_col,
                "cm": cm_col,
                "cl_over_cd": ld_col,
                "cd_induced": cd_i_col,
                "cd_profile": cd_p_col,
                "lift": lift_col,
                "drag": drag_col,
            },
        )

        plots = [
            PlotDefinition(
                id="cl_alpha",
                title="CL vs α",
                table_id="alpha_polar",
                x_column="alpha",
                series=[PlotSeriesDef("cl", "CL", color="#3b82f6")],
                x_label="Angle of Attack α",
                y_label="Lift Coefficient CL",
            ),
            PlotDefinition(
                id="cd_alpha",
                title="CD vs α",
                table_id="alpha_polar",
                x_column="alpha",
                series=[
                    PlotSeriesDef("cd", "Total CD", color="#ef4444"),
                    PlotSeriesDef("cd_induced", "Induced CDi", color="#8b5cf6", style="dash"),
                    PlotSeriesDef("cd_profile", "Profile CDp", color="#f97316", style="dash"),
                ],
                x_label="Angle of Attack α",
                y_label="Drag Coefficient CD",
            ),
            PlotDefinition(
                id="drag_polar",
                title="CL vs CD",
                table_id="alpha_polar",
                x_column="cd",
                series=[PlotSeriesDef("cl", "Polar", color="#10b981")],
                x_label="Drag Coefficient CD",
                y_label="Lift Coefficient CL",
            ),
            PlotDefinition(
                id="cl_over_cd",
                title="L/D vs α",
                table_id="alpha_polar",
                x_column="alpha",
                series=[PlotSeriesDef("cl_over_cd", "L/D", color="#06b6d4")],
                x_label="Angle of Attack α",
                y_label="Lift-to-Drag Ratio L/D",
            ),
            PlotDefinition(
                id="cm_alpha",
                title="Cm vs α",
                table_id="alpha_polar",
                x_column="alpha",
                series=[PlotSeriesDef("cm", "Cm", color="#f59e0b")],
                x_label="Angle of Attack α",
                y_label="Pitching Moment Coefficient Cm",
            ),
        ]

        summary = [
            SummaryItem("cl_max", round(res.cl_max, 4), "Max Lift (CL,max)"),
            SummaryItem(
                "cl_max_alpha",
                round(res.cl_max_alpha, 2),
                "AoA at CL,max",
                unit="°",
                quantity_id="angle",
            ),
            SummaryItem("cd_min", round(res.cd_min, 4), "Min Drag (CD,min)"),
            SummaryItem("ld_max", round(res.ld_max, 2), "Max Efficiency (L/D,max)"),
            SummaryItem(
                "ld_max_alpha",
                round(res.ld_max_alpha, 2),
                "AoA at (L/D)max",
                unit="°",
                quantity_id="angle",
            ),
        ]

        if res.oswald_efficiency is not None:
            summary.append(
                SummaryItem("oswald_e", round(res.oswald_efficiency, 3), "Oswald Efficiency (e)")
            )

        stab = res.stability_derivatives
        if stab is not None:
            x_np = stab.x_np
            sm = stab.static_margin
            summary.append(SummaryItem("x_np", round(float(x_np), 4), "Neutral Point", unit="m"))
            summary.append(
                SummaryItem("static_margin", round(float(sm), 2), "Static Margin", unit="%")
            )

        return SolverResult(
            solver_id=self.config.solver_id,
            config=self.config,
            name=self.config.name,
            status=SolverStatus.COMPLETED,
            summary={item.key: item for item in summary},
            tables={table.id: table},
            plots={plot.id: plot for plot in plots},
        )


class BetaSweepSolver(BaseAerodynamicsSolver):
    """Evaluates lateral-directional aerodynamic characteristics across a sideslip angle range."""

    PARAMETER_FIELDS: ClassVar[list[ParameterField]] = [
        ParameterField(
            key="beta_min",
            label="Sideslip Min",
            unit="°",
            quantity="angle",
            field_type=float,
            default=-15.0,
            min_value=-90.0,
            max_value=90.0,
            decimals=1,
            tooltip="Starting sideslip angle (β).",
        ),
        ParameterField(
            key="beta_max",
            label="Sideslip Max",
            unit="°",
            quantity="angle",
            field_type=float,
            default=15.0,
            min_value=-90.0,
            max_value=90.0,
            decimals=1,
            tooltip="Ending sideslip angle (β).",
        ),
        ParameterField(
            key="beta_step",
            label="Sideslip Step",
            unit="°",
            quantity="angle",
            field_type=float,
            default=1.0,
            min_value=0.1,
            max_value=20.0,
            decimals=1,
            tooltip="Sideslip evaluation increment.",
        ),
        ParameterField(
            key="alpha",
            label="Angle of Attack",
            unit="°",
            quantity="angle",
            field_type=float,
            default=2.0,
            min_value=-20.0,
            max_value=30.0,
            decimals=1,
            tooltip="Constant flight angle of attack during sideslip sweep.",
        ),
        ParameterField(
            key="velocity",
            label="Airspeed",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=25.0,
            min_value=1.0,
            max_value=300.0,
            decimals=1,
            tooltip="Constant flight airspeed.",
        ),
        ParameterField(
            key="altitude",
            label="Altitude",
            unit="m",
            quantity="length",
            field_type=float,
            default=0.0,
            min_value=-500.0,
            max_value=25000.0,
            decimals=0,
            tooltip="Atmospheric flight altitude.",
        ),
        ParameterField(
            key="method",
            label="Solver Method",
            field_type=str,
            default="aero_buildup",
            options=(
                ("aero_buildup", "AeroBuildup (Fast)"),
                ("vlm", "Vortex Lattice (VLM)"),
                ("lifting_line", "Lifting Line (LLT)"),
            ),
            tooltip="Aerodynamic solver calculation method.",
        ),
        ParameterField(
            key="spanwise_resolution",
            label="Spanwise Panels",
            field_type=float,
            default=12.0,
            min_value=4.0,
            max_value=50.0,
            decimals=0,
            tooltip="Mesh panel resolution along span for VLM / LLT.",
        ),
        ParameterField(
            key="chordwise_resolution",
            label="Chordwise Panels",
            field_type=float,
            default=8.0,
            min_value=2.0,
            max_value=30.0,
            decimals=0,
            tooltip="Mesh panel resolution along chord for VLM.",
        ),
    ]

    def run(self) -> SolverResult:
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Analysis cancelled before execution.")

        components = self._extract_components()

        beta_min, beta_max, num_steps = self._sweep("beta")
        condition = FlightCondition(
            velocity=self._velocity(),
            alpha=self._parameter("alpha"),
            # Lateral-directional derivatives are evaluated at zero sideslip.
            beta=0.0,
            altitude=self._parameter("altitude"),
            sweep_variable="beta",
            sweep_min=beta_min,
            sweep_max=beta_max,
            sweep_steps=num_steps,
        )

        aero_result = self.engine.analyze(
            components=components,
            condition=condition,
            method=self._method(),
            settings=self._configured_settings(),
            progress_callback=self._create_progress_callback(),
        )

        return self._build_result(aero_result)

    def _build_result(self, res: AeroResult) -> SolverResult:
        pts = [p for p in res.polar_points if p.converged]

        beta_col = [p.beta for p in pts]
        cy_col = [p.cy for p in pts]
        cl_roll_col = [p.cl_roll for p in pts]
        cn_col = [p.cn for p in pts]
        sideforce_col = [p.forces_moments.sideforce if p.forces_moments else 0.0 for p in pts]

        table = TableDefinition(
            id="beta_polar",
            title="Sideslip",
            columns=[
                TableColumn("beta", "Sideslip (β)", unit="°", quantity_id="angle"),
                TableColumn("cy", "CY"),
                TableColumn("cl_roll", "Cl"),
                TableColumn("cn", "Cn"),
                TableColumn("sideforce", "Side Force", unit="N", quantity_id="force"),
            ],
            data={
                "beta": beta_col,
                "cy": cy_col,
                "cl_roll": cl_roll_col,
                "cn": cn_col,
                "sideforce": sideforce_col,
            },
        )

        plots = [
            PlotDefinition(
                id="cy_beta",
                title="CY vs β",
                table_id="beta_polar",
                x_column="beta",
                series=[PlotSeriesDef("cy", "CY", color="#3b82f6")],
                x_label="Sideslip Angle β",
                y_label="Sideforce Coefficient CY",
            ),
            PlotDefinition(
                id="cl_roll_beta",
                title="Cl vs β",
                table_id="beta_polar",
                x_column="beta",
                series=[PlotSeriesDef("cl_roll", "Cl (Roll)", color="#8b5cf6")],
                x_label="Sideslip Angle β",
                y_label="Rolling Moment Coefficient Cl",
            ),
            PlotDefinition(
                id="cn_beta",
                title="Cn vs β",
                table_id="beta_polar",
                x_column="beta",
                series=[PlotSeriesDef("cn", "Cn (Yaw)", color="#f59e0b")],
                x_label="Sideslip Angle β",
                y_label="Yawing Moment Coefficient Cn",
            ),
        ]

        summary = []
        stab = res.stability_derivatives
        if stab is not None:
            cyb = stab.c_Y_beta_deg
            clb = stab.c_l_beta_deg
            cnb = stab.c_n_beta_deg
            summary.append(
                SummaryItem(
                    "cy_beta", round(float(cyb), 5), "CY_beta (Sideforce slope)", unit="1/°"
                )
            )
            summary.append(
                SummaryItem(
                    "cl_beta", round(float(clb), 5), "Cl_beta (Dihedral Effect)", unit="1/°"
                )
            )
            summary.append(
                SummaryItem(
                    "cn_beta",
                    round(float(cnb), 5),
                    "Cn_beta (Directional Stability)",
                    unit="1/°",
                )
            )

        if not summary and len(pts) >= 2:
            d_beta = pts[-1].beta - pts[0].beta
            if abs(d_beta) > 1e-4:
                summary.append(
                    SummaryItem(
                        "cy_beta_est",
                        round((pts[-1].cy - pts[0].cy) / d_beta, 5),
                        "CY_beta (estimated)",
                        unit="1/°",
                    )
                )
                summary.append(
                    SummaryItem(
                        "cl_beta_est",
                        round((pts[-1].cl_roll - pts[0].cl_roll) / d_beta, 5),
                        "Cl_beta (estimated)",
                        unit="1/°",
                    )
                )
                summary.append(
                    SummaryItem(
                        "cn_beta_est",
                        round((pts[-1].cn - pts[0].cn) / d_beta, 5),
                        "Cn_beta (estimated)",
                        unit="1/°",
                    )
                )

        return SolverResult(
            solver_id=self.config.solver_id,
            config=self.config,
            name=self.config.name,
            status=SolverStatus.COMPLETED,
            summary={item.key: item for item in summary},
            tables={table.id: table},
            plots={plot.id: plot for plot in plots},
        )


class ControlDeflectionSolver(BaseAerodynamicsSolver):
    """Evaluates control surface authority and aerodynamic moments across deflection angles."""

    PARAMETER_FIELDS: ClassVar[list[ParameterField]] = [
        ParameterField(
            key="channel",
            label="Control Channel",
            field_type=str,
            default="elevator",
            options=tuple((channel, channel.capitalize()) for channel in CONTROL_CHANNELS),
            tooltip="Control channel to deflect.",
        ),
        ParameterField(
            key="deflection_min",
            label="Deflection Min",
            unit="°",
            quantity="angle",
            field_type=float,
            default=-20.0,
            min_value=-90.0,
            max_value=90.0,
            decimals=1,
            tooltip="Starting control deflection angle (δ).",
        ),
        ParameterField(
            key="deflection_max",
            label="Deflection Max",
            unit="°",
            quantity="angle",
            field_type=float,
            default=20.0,
            min_value=-90.0,
            max_value=90.0,
            decimals=1,
            tooltip="Ending control deflection angle (δ).",
        ),
        ParameterField(
            key="deflection_step",
            label="Deflection Step",
            unit="°",
            quantity="angle",
            field_type=float,
            default=2.0,
            min_value=0.5,
            max_value=20.0,
            decimals=1,
            tooltip="Control deflection increment.",
        ),
        ParameterField(
            key="alpha",
            label="Angle of Attack",
            unit="°",
            quantity="angle",
            field_type=float,
            default=2.0,
            min_value=-20.0,
            max_value=30.0,
            decimals=1,
            tooltip="Constant flight angle of attack during deflection sweep.",
        ),
        ParameterField(
            key="beta",
            label="Sideslip (β)",
            unit="°",
            quantity="angle",
            field_type=float,
            default=0.0,
            min_value=-45.0,
            max_value=45.0,
            decimals=1,
            tooltip="Constant sideslip angle.",
        ),
        ParameterField(
            key="velocity",
            label="Airspeed",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=25.0,
            min_value=1.0,
            max_value=300.0,
            decimals=1,
            tooltip="Constant flight airspeed.",
        ),
        ParameterField(
            key="altitude",
            label="Altitude",
            unit="m",
            quantity="length",
            field_type=float,
            default=0.0,
            min_value=-500.0,
            max_value=25000.0,
            decimals=0,
            tooltip="Atmospheric flight altitude.",
        ),
        ParameterField(
            key="method",
            label="Solver Method",
            field_type=str,
            default="aero_buildup",
            options=(
                ("aero_buildup", "AeroBuildup (Fast)"),
                ("vlm", "Vortex Lattice (VLM)"),
            ),
            tooltip="Aerodynamic solver calculation method.",
        ),
    ]

    def run(self) -> SolverResult:
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Analysis cancelled before execution.")

        components = self._extract_components()

        channel = str(self.config.parameters["channel"])
        available_channels = control_channels_for_components(components)
        if channel not in available_channels:
            available = ", ".join(available_channels) or "none"
            raise AeroAnalysisError(
                f"Aircraft has no '{channel}' control channel (available: {available})."
            )

        def_min, def_max, num_steps = self._sweep("deflection")
        condition = FlightCondition(
            velocity=self._velocity(),
            alpha=self._parameter("alpha"),
            beta=self._parameter("beta"),
            altitude=self._parameter("altitude"),
            sweep_variable=channel,
            sweep_min=def_min,
            sweep_max=def_max,
            sweep_steps=num_steps,
            control_deflections={channel: 0.0},
        )

        aero_result = self.engine.analyze(
            components=components,
            condition=condition,
            method=self._method(),
            settings=self._settings(12, 8),
            progress_callback=self._create_progress_callback(),
        )

        return self._build_result(aero_result, channel)

    def _build_result(self, res: AeroResult, channel: str) -> SolverResult:
        pts = [p for p in res.polar_points if p.converged]

        deflection_col = [p.control_deflections.get(channel, 0.0) for p in pts]
        cl_col = [p.cl for p in pts]
        cd_col = [p.cd for p in pts]
        cm_col = [p.cm for p in pts]
        cl_roll_col = [p.cl_roll for p in pts]
        cn_col = [p.cn for p in pts]

        table = TableDefinition(
            id="control_polar",
            title="Response",
            columns=[
                TableColumn(
                    "deflection", f"Deflection δ ({channel})", unit="°", quantity_id="angle"
                ),
                TableColumn("cl", "CL"),
                TableColumn("cd", "CD"),
                TableColumn("cm", "Cm"),
                TableColumn("cl_roll", "Cl"),
                TableColumn("cn", "Cn"),
            ],
            data={
                "deflection": deflection_col,
                "cl": cl_col,
                "cd": cd_col,
                "cm": cm_col,
                "cl_roll": cl_roll_col,
                "cn": cn_col,
            },
        )

        plots = [
            PlotDefinition(
                id="cm_delta",
                title="Cm vs δ",
                table_id="control_polar",
                x_column="deflection",
                series=[PlotSeriesDef("cm", "Cm", color="#f59e0b")],
                x_label=f"Deflection Angle δ ({channel})",
                y_label="Pitching Moment Coefficient Cm",
            ),
            PlotDefinition(
                id="cl_delta",
                title="CL vs δ",
                table_id="control_polar",
                x_column="deflection",
                series=[PlotSeriesDef("cl", "CL", color="#3b82f6")],
                x_label=f"Deflection Angle δ ({channel})",
                y_label="Lift Coefficient CL",
            ),
            PlotDefinition(
                id="roll_yaw_delta",
                title="Cl, Cn vs δ",
                table_id="control_polar",
                x_column="deflection",
                series=[
                    PlotSeriesDef("cl_roll", "Cl (Roll)", color="#8b5cf6"),
                    PlotSeriesDef("cn", "Cn (Yaw)", color="#ef4444"),
                ],
                x_label=f"Deflection Angle δ ({channel})",
                y_label="Moment Coefficients",
            ),
        ]

        summary = [
            SummaryItem("channel", channel.capitalize(), "Control Channel"),
        ]

        if res.control_analysis is not None:
            derivatives = res.control_analysis.derivatives_per_deg
            if "Cm" in derivatives:
                summary.append(
                    SummaryItem(
                        "cm_delta",
                        round(derivatives["Cm"], 5),
                        "Cm_delta (Pitch Authority)",
                        unit="1/°",
                    )
                )
            if "CL" in derivatives:
                summary.append(
                    SummaryItem(
                        "cl_delta",
                        round(derivatives["CL"], 5),
                        "CL_delta (Lift Authority)",
                        unit="1/°",
                    )
                )
            if "Cl" in derivatives:
                summary.append(
                    SummaryItem(
                        "cl_roll_delta",
                        round(derivatives["Cl"], 5),
                        "Cl_delta (Roll Authority)",
                        unit="1/°",
                    )
                )
            if "Cn" in derivatives:
                summary.append(
                    SummaryItem(
                        "cn_delta",
                        round(derivatives["Cn"], 5),
                        "Cn_delta (Yaw Authority)",
                        unit="1/°",
                    )
                )
        elif len(pts) >= 2:
            d_delta = deflection_col[-1] - deflection_col[0]
            if abs(d_delta) > 1e-4:
                summary.append(
                    SummaryItem(
                        "cm_delta_est",
                        round((cm_col[-1] - cm_col[0]) / d_delta, 5),
                        "Cm_delta (estimated)",
                        unit="1/°",
                    )
                )
                summary.append(
                    SummaryItem(
                        "cl_delta_est",
                        round((cl_col[-1] - cl_col[0]) / d_delta, 5),
                        "CL_delta (estimated)",
                        unit="1/°",
                    )
                )

        return SolverResult(
            solver_id=self.config.solver_id,
            config=self.config,
            name=self.config.name,
            status=SolverStatus.COMPLETED,
            summary={item.key: item for item in summary},
            tables={table.id: table},
            plots={plot.id: plot for plot in plots},
        )


class OperatingPointSolver(BaseAerodynamicsSolver):
    """Evaluates complete 3D aerodynamic forces, moments, and coefficients at a discrete operating condition."""

    PARAMETER_FIELDS: ClassVar[list[ParameterField]] = [
        ParameterField(
            key="alpha",
            label="Angle of Attack",
            unit="°",
            quantity="angle",
            field_type=float,
            default=2.0,
            min_value=-20.0,
            max_value=30.0,
            decimals=1,
            tooltip="Flight angle of attack.",
        ),
        ParameterField(
            key="beta",
            label="Sideslip (β)",
            unit="°",
            quantity="angle",
            field_type=float,
            default=0.0,
            min_value=-45.0,
            max_value=45.0,
            decimals=1,
            tooltip="Flight sideslip angle.",
        ),
        ParameterField(
            key="velocity",
            label="Airspeed",
            unit="m/s",
            quantity="velocity",
            field_type=float,
            default=25.0,
            min_value=1.0,
            max_value=300.0,
            decimals=1,
            tooltip="Flight airspeed.",
        ),
        ParameterField(
            key="altitude",
            label="Altitude",
            unit="m",
            quantity="length",
            field_type=float,
            default=0.0,
            min_value=-500.0,
            max_value=25000.0,
            decimals=0,
            tooltip="Atmospheric flight altitude.",
        ),
        ParameterField(
            key="method",
            label="Solver Method",
            field_type=str,
            default="aero_buildup",
            options=(
                ("aero_buildup", "AeroBuildup (Fast)"),
                ("vlm", "Vortex Lattice (VLM)"),
                ("lifting_line", "Lifting Line (LLT)"),
            ),
            tooltip="Aerodynamic solver calculation method.",
        ),
        ParameterField(
            key="spanwise_resolution",
            label="Spanwise Panels",
            field_type=float,
            default=12.0,
            min_value=4.0,
            max_value=50.0,
            decimals=0,
            tooltip="Mesh panel resolution along span for VLM / LLT.",
        ),
        ParameterField(
            key="chordwise_resolution",
            label="Chordwise Panels",
            field_type=float,
            default=8.0,
            min_value=2.0,
            max_value=30.0,
            decimals=0,
            tooltip="Mesh panel resolution along chord for VLM.",
        ),
    ]

    def run(self) -> SolverResult:
        if self.is_cancel_requested or (self.token is not None and self.token.is_cancelled):
            self.status = SolverStatus.CANCELLED
            raise TaskCancelledError("Analysis cancelled before execution.")

        components = self._extract_components()

        alpha = self._parameter("alpha")
        beta = self._parameter("beta")
        velocity = self._velocity()
        condition = FlightCondition(
            velocity=velocity,
            alpha=alpha,
            beta=beta,
            altitude=self._parameter("altitude"),
            sweep_variable="alpha",
            sweep_min=alpha,
            sweep_max=alpha,
            sweep_steps=1,
        )

        aero_result = self.engine.analyze(
            components=components,
            condition=condition,
            method=self._method(),
            settings=self._configured_settings(),
            progress_callback=self._create_progress_callback(),
        )

        return self._build_result(aero_result, alpha, beta, velocity)

    def _build_result(
        self, res: AeroResult, alpha: float, beta: float, velocity: float
    ) -> SolverResult:
        pt = res.polar_points[0] if res.polar_points else None

        cl = pt.cl if pt else 0.0
        cd = pt.cd if pt else 0.0
        cm = pt.cm if pt else 0.0
        cy = pt.cy if pt else 0.0
        cl_roll = pt.cl_roll if pt else 0.0
        cn = pt.cn if pt else 0.0
        ld = pt.cl_over_cd if pt else 0.0
        lift = pt.forces_moments.lift if pt and pt.forces_moments else 0.0
        drag = pt.forces_moments.drag if pt and pt.forces_moments else 0.0
        sideforce = pt.forces_moments.sideforce if pt and pt.forces_moments else 0.0

        table = TableDefinition(
            id="operating_point_data",
            title="State",
            columns=[
                TableColumn("alpha", "AoA (α)", unit="°", quantity_id="angle"),
                TableColumn("beta", "Sideslip (β)", unit="°", quantity_id="angle"),
                TableColumn("velocity", "Airspeed", unit="m/s", quantity_id="velocity"),
                TableColumn("cl", "CL"),
                TableColumn("cd", "CD"),
                TableColumn("cm", "Cm"),
                TableColumn("cl_over_cd", "L/D"),
                TableColumn("cy", "CY"),
                TableColumn("cl_roll", "Cl"),
                TableColumn("cn", "Cn"),
                TableColumn("lift", "Lift", unit="N", quantity_id="force"),
                TableColumn("drag", "Drag", unit="N", quantity_id="force"),
                TableColumn("sideforce", "Side Force", unit="N", quantity_id="force"),
            ],
            data={
                "alpha": [alpha],
                "beta": [beta],
                "velocity": [velocity],
                "cl": [cl],
                "cd": [cd],
                "cm": [cm],
                "cl_over_cd": [ld],
                "cy": [cy],
                "cl_roll": [cl_roll],
                "cn": [cn],
                "lift": [lift],
                "drag": [drag],
                "sideforce": [sideforce],
            },
        )

        summary = [
            SummaryItem("cl", round(cl, 4), "Lift Coefficient (CL)"),
            SummaryItem("cd", round(cd, 4), "Drag Coefficient (CD)"),
            SummaryItem("cm", round(cm, 4), "Pitching Moment (Cm)"),
            SummaryItem("cl_over_cd", round(ld, 2), "L/D Ratio"),
            SummaryItem("lift", round(lift, 2), "Lift Force", unit="N", quantity_id="force"),
            SummaryItem("drag", round(drag, 2), "Drag Force", unit="N", quantity_id="force"),
            SummaryItem(
                "sideforce", round(sideforce, 2), "Side Force", unit="N", quantity_id="force"
            ),
        ]

        if pt and pt.dynamic_pressure:
            summary.append(
                SummaryItem(
                    "q_inf",
                    round(pt.dynamic_pressure, 1),
                    "Dynamic Pressure",
                    unit="Pa",
                    quantity_id="pressure",
                )
            )
        if pt and pt.mach:
            summary.append(SummaryItem("mach", round(pt.mach, 3), "Mach Number"))
        if pt and pt.reynolds:
            summary.append(SummaryItem("reynolds", f"{pt.reynolds:.2e}", "Reynolds Number"))

        stab = res.stability_derivatives
        if stab is not None:
            x_np = stab.x_np
            sm = stab.static_margin
            summary.append(SummaryItem("x_np", round(float(x_np), 4), "Neutral Point", unit="m"))
            summary.append(
                SummaryItem("static_margin", round(float(sm), 2), "Static Margin", unit="%")
            )

        return SolverResult(
            solver_id=self.config.solver_id,
            config=self.config,
            name=self.config.name,
            status=SolverStatus.COMPLETED,
            summary={item.key: item for item in summary},
            tables={table.id: table},
            plots={},
        )
