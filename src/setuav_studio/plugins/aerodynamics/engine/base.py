"""Abstract aerodynamic engine interface and shared data models."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import enum
import math
from typing import Any, Sequence


class AnalysisMethod(enum.Enum):
    """Available solver methods."""
    VLM = "vlm"
    AERO_BUILDUP = "aero_buildup"
    PANEL = "panel"
    LIFTING_LINE = "lifting_line"
    NONLINEAR_LIFTING_LINE = "nonlinear_lifting_line"


class AnalysisType(enum.Enum):
    """Types of analysis an engine can perform."""
    SINGLE_POINT = "single_point"
    ALPHA_SWEEP = "alpha_sweep"
    BETA_SWEEP = "beta_sweep"
    MULTI_SWEEP = "multi_sweep"
    STABILITY_DERIVATIVES = "stability_derivatives"


@dataclass(frozen=True)
class FlightCondition:
    """Operating conditions and sweep parameters for aerodynamic analysis."""
    velocity: float = 25.0            # m/s (true airspeed)
    alpha: float = 2.0                # deg (single point or reference AoA)
    beta: float = 0.0                 # deg (sideslip angle)
    altitude: float = 0.0             # m MSL
    p: float = 0.0                    # rad/s (body roll rate)
    q: float = 0.0                    # rad/s (body pitch rate)
    r: float = 0.0                    # rad/s (body yaw rate)
    control_deflections: dict[str, float] = field(default_factory=dict)  # deg per control surface
    # Sweep ranges
    alpha_min: float = -10.0          # deg (polar sweep start)
    alpha_max: float = 18.0           # deg (polar sweep end)
    alpha_steps: int = 29             # number of sweep evaluation points
    beta_min: float = 0.0             # deg
    beta_max: float = 0.0             # deg
    beta_steps: int = 1               # number of beta sweep points

    def to_dict(self) -> dict[str, Any]:
        return {
            "velocity": self.velocity,
            "alpha": self.alpha,
            "beta": self.beta,
            "altitude": self.altitude,
            "p": self.p,
            "q": self.q,
            "r": self.r,
            "control_deflections": dict(self.control_deflections),
            "alpha_min": self.alpha_min,
            "alpha_max": self.alpha_max,
            "alpha_steps": self.alpha_steps,
            "beta_min": self.beta_min,
            "beta_max": self.beta_max,
            "beta_steps": self.beta_steps,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlightCondition:
        return cls(
            velocity=float(data.get("velocity", 25.0)),
            alpha=float(data.get("alpha", 2.0)),
            beta=float(data.get("beta", 0.0)),
            altitude=float(data.get("altitude", 0.0)),
            p=float(data.get("p", 0.0)),
            q=float(data.get("q", 0.0)),
            r=float(data.get("r", 0.0)),
            control_deflections=dict(data.get("control_deflections") or {}),
            alpha_min=float(data.get("alpha_min", -10.0)),
            alpha_max=float(data.get("alpha_max", 18.0)),
            alpha_steps=int(data.get("alpha_steps", 29)),
            beta_min=float(data.get("beta_min", 0.0)),
            beta_max=float(data.get("beta_max", 0.0)),
            beta_steps=int(data.get("beta_steps", 1)),
        )


@dataclass(frozen=True)
class ReferenceValues:
    """Aerodynamic reference geometry."""
    s_ref: float = 0.0    # m² reference area (S)
    b_ref: float = 0.0    # m reference span (b)
    c_ref: float = 0.0    # m mean aerodynamic chord (MAC, c)
    x_cg: float = 0.0     # m moment reference X
    y_cg: float = 0.0     # m moment reference Y
    z_cg: float = 0.0     # m moment reference Z

    def to_dict(self) -> dict[str, Any]:
        return {
            "s_ref": self.s_ref,
            "b_ref": self.b_ref,
            "c_ref": self.c_ref,
            "x_cg": self.x_cg,
            "y_cg": self.y_cg,
            "z_cg": self.z_cg,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceValues:
        return cls(
            s_ref=float(data.get("s_ref", 0.0)),
            b_ref=float(data.get("b_ref", 0.0)),
            c_ref=float(data.get("c_ref", 0.0)),
            x_cg=float(data.get("x_cg", 0.0)),
            y_cg=float(data.get("y_cg", 0.0)),
            z_cg=float(data.get("z_cg", 0.0)),
        )


@dataclass(frozen=True)
class AeroForcesMoments:
    """Dimensional forces and moments in SI units (Newtons and Newton-meters)."""
    # Body-frame forces (N): +X forward, +Y right, +Z down
    fx_b: float = 0.0
    fy_b: float = 0.0
    fz_b: float = 0.0
    # Wind-frame forces (N)
    lift: float = 0.0         # perpendicular to freestream (positive up)
    drag: float = 0.0         # parallel to freestream (positive aft)
    sideforce: float = 0.0    # perpendicular to lift & drag (positive right)
    # Body-frame moments (N·m) about CG/reference point
    mx_b: float = 0.0         # Roll moment (L_b) about body X
    my_b: float = 0.0         # Pitch moment (M_b) about body Y
    mz_b: float = 0.0         # Yaw moment (N_b) about body Z
    # Wind-frame moments (N·m)
    mx_w: float = 0.0
    my_w: float = 0.0
    mz_w: float = 0.0

    @property
    def force_body(self) -> tuple[float, float, float]:
        """Body force vector (Fx, Fy, Fz) in Newtons."""
        return (self.fx_b, self.fy_b, self.fz_b)

    @property
    def moment_body(self) -> tuple[float, float, float]:
        """Body moment vector (Mx, My, Mz) in Newton-meters."""
        return (self.mx_b, self.my_b, self.mz_b)

    @property
    def force_wind(self) -> tuple[float, float, float]:
        """Wind force vector (Lift, Drag, Sideforce) in Newtons."""
        return (self.lift, self.drag, self.sideforce)

    @property
    def moment_wind(self) -> tuple[float, float, float]:
        """Wind moment vector in Newton-meters."""
        return (self.mx_w, self.my_w, self.mz_w)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fx_b": self.fx_b,
            "fy_b": self.fy_b,
            "fz_b": self.fz_b,
            "lift": self.lift,
            "drag": self.drag,
            "sideforce": self.sideforce,
            "mx_b": self.mx_b,
            "my_b": self.my_b,
            "mz_b": self.mz_b,
            "mx_w": self.mx_w,
            "my_w": self.my_w,
            "mz_w": self.mz_w,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AeroForcesMoments:
        return cls(
            fx_b=float(data.get("fx_b", 0.0)),
            fy_b=float(data.get("fy_b", 0.0)),
            fz_b=float(data.get("fz_b", 0.0)),
            lift=float(data.get("lift", 0.0)),
            drag=float(data.get("drag", 0.0)),
            sideforce=float(data.get("sideforce", 0.0)),
            mx_b=float(data.get("mx_b", 0.0)),
            my_b=float(data.get("my_b", 0.0)),
            mz_b=float(data.get("mz_b", 0.0)),
            mx_w=float(data.get("mx_w", 0.0)),
            my_w=float(data.get("my_w", 0.0)),
            mz_w=float(data.get("mz_w", 0.0)),
        )


@dataclass(frozen=True)
class AeroState:
    """Operating flight and flow state at an evaluation point."""
    alpha: float = 0.0                 # deg (angle of attack)
    beta: float = 0.0                  # deg (sideslip angle)
    p: float = 0.0                     # rad/s (roll rate)
    q: float = 0.0                     # rad/s (pitch rate)
    r: float = 0.0                     # rad/s (yaw rate)
    velocity: float = 0.0              # m/s (true airspeed)
    altitude: float = 0.0              # m MSL
    mach: float = 0.0
    reynolds: float = 0.0
    dynamic_pressure: float = 0.0      # Pa (q_inf = 0.5 * rho * V^2)
    control_deflections: dict[str, float] = field(default_factory=dict)  # surface name -> deg

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "beta": self.beta,
            "p": self.p,
            "q": self.q,
            "r": self.r,
            "velocity": self.velocity,
            "altitude": self.altitude,
            "mach": self.mach,
            "reynolds": self.reynolds,
            "dynamic_pressure": self.dynamic_pressure,
            "control_deflections": dict(self.control_deflections),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AeroState:
        return cls(
            alpha=float(data.get("alpha", 0.0)),
            beta=float(data.get("beta", 0.0)),
            p=float(data.get("p", 0.0)),
            q=float(data.get("q", 0.0)),
            r=float(data.get("r", 0.0)),
            velocity=float(data.get("velocity", 0.0)),
            altitude=float(data.get("altitude", 0.0)),
            mach=float(data.get("mach", 0.0)),
            reynolds=float(data.get("reynolds", 0.0)),
            dynamic_pressure=float(data.get("dynamic_pressure", 0.0)),
            control_deflections=dict(data.get("control_deflections") or {}),
        )


@dataclass(frozen=True)
class PolarPoint:
    """Aerodynamic coefficients, 6-DoF values, dimensional forces and moments at an operating point."""
    # Wind/Stability frame coefficients (standard polar)
    alpha: float
    cl: float
    cd: float
    cm: float = 0.0               # Pitching moment coefficient (C_m about Y body)
    cd_induced: float = 0.0       # Induced drag coefficient
    cd_profile: float = 0.0       # Profile / parasite drag coefficient
    cl_over_cd: float = 0.0       # Lift-to-drag ratio (L/D)
    # 6-DoF Non-dimensional body/wind coefficients
    cx: float = 0.0               # Body X force coefficient (C_X)
    cy: float = 0.0               # Side force coefficient (C_Y)
    cz: float = 0.0               # Body Z force coefficient (C_Z)
    cl_roll: float = 0.0          # Rolling moment coefficient (C_l about X body)
    cn: float = 0.0               # Yawing moment coefficient (C_n about Z body)
    cd_wave: float = 0.0          # Compressibility / wave drag coefficient
    # Operating state
    beta: float = 0.0             # deg (sideslip angle)
    p: float = 0.0                # rad/s (roll rate)
    q: float = 0.0                # rad/s (pitch rate)
    r: float = 0.0                # rad/s (yaw rate)
    # Full forces, moments and state containers
    forces_moments: AeroForcesMoments | None = None
    state: AeroState | None = None
    # Quick flow parameters
    velocity: float = 0.0         # m/s
    altitude: float = 0.0         # m
    mach: float = 0.0
    reynolds: float = 0.0
    dynamic_pressure: float = 0.0 # Pa
    control_deflections: dict[str, float] = field(default_factory=dict)
    # Execution & solver status
    converged: bool = True
    notes: str = ""

    # Convenient dimensional properties
    @property
    def lift(self) -> float:
        """Lift force in Newtons."""
        return self.forces_moments.lift if self.forces_moments is not None else 0.0

    @property
    def drag(self) -> float:
        """Drag force in Newtons."""
        return self.forces_moments.drag if self.forces_moments is not None else 0.0

    @property
    def sideforce(self) -> float:
        """Side force in Newtons."""
        return self.forces_moments.sideforce if self.forces_moments is not None else 0.0

    @property
    def force_body(self) -> tuple[float, float, float]:
        """Body force vector (Fx, Fy, Fz) in Newtons."""
        if self.forces_moments is not None:
            return self.forces_moments.force_body
        return (0.0, 0.0, 0.0)

    @property
    def moment_body(self) -> tuple[float, float, float]:
        """Body moment vector (Mx, My, Mz) in Newton-meters."""
        if self.forces_moments is not None:
            return self.forces_moments.moment_body
        return (0.0, 0.0, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha": self.alpha,
            "cl": self.cl,
            "cd": self.cd,
            "cm": self.cm,
            "cd_induced": self.cd_induced,
            "cd_profile": self.cd_profile,
            "cl_over_cd": self.cl_over_cd,
            "cx": self.cx,
            "cy": self.cy,
            "cz": self.cz,
            "cl_roll": self.cl_roll,
            "cn": self.cn,
            "cd_wave": self.cd_wave,
            "beta": self.beta,
            "p": self.p,
            "q": self.q,
            "r": self.r,
            "forces_moments": self.forces_moments.to_dict() if self.forces_moments is not None else None,
            "state": self.state.to_dict() if self.state is not None else None,
            "velocity": self.velocity,
            "altitude": self.altitude,
            "mach": self.mach,
            "reynolds": self.reynolds,
            "dynamic_pressure": self.dynamic_pressure,
            "control_deflections": dict(self.control_deflections),
            "converged": self.converged,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolarPoint:
        fm_data = data.get("forces_moments")
        fm = AeroForcesMoments.from_dict(fm_data) if isinstance(fm_data, dict) else None
        st_data = data.get("state")
        st = AeroState.from_dict(st_data) if isinstance(st_data, dict) else None

        return cls(
            alpha=float(data["alpha"]),
            cl=float(data["cl"]),
            cd=float(data["cd"]),
            cm=float(data.get("cm", 0.0)),
            cd_induced=float(data.get("cd_induced", 0.0)),
            cd_profile=float(data.get("cd_profile", 0.0)),
            cl_over_cd=float(data.get("cl_over_cd", 0.0)),
            cx=float(data.get("cx", 0.0)),
            cy=float(data.get("cy", 0.0)),
            cz=float(data.get("cz", 0.0)),
            cl_roll=float(data.get("cl_roll", 0.0)),
            cn=float(data.get("cn", 0.0)),
            cd_wave=float(data.get("cd_wave", 0.0)),
            beta=float(data.get("beta", 0.0)),
            p=float(data.get("p", 0.0)),
            q=float(data.get("q", 0.0)),
            r=float(data.get("r", 0.0)),
            forces_moments=fm,
            state=st,
            velocity=float(data.get("velocity", 0.0)),
            altitude=float(data.get("altitude", 0.0)),
            mach=float(data.get("mach", 0.0)),
            reynolds=float(data.get("reynolds", 0.0)),
            dynamic_pressure=float(data.get("dynamic_pressure", 0.0)),
            control_deflections=dict(data.get("control_deflections") or {}),
            converged=bool(data.get("converged", True)),
            notes=str(data.get("notes", "")),
        )


# Alias for generalized point results
AeroPointResult = PolarPoint


@dataclass(frozen=True)
class SweepVariable:
    """A parameter varied during multi-dimensional aerodynamic sweeps."""
    name: str                   # Parameter name: 'alpha', 'beta', 'velocity', 'altitude', or control name
    values: list[float]         # Evaluated grid values
    unit: str = ""              # Unit for display (e.g. 'deg', 'm/s', 'm')

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "values": list(self.values),
            "unit": self.unit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SweepVariable:
        return cls(
            name=str(data.get("name", "")),
            values=[float(v) for v in data.get("values", [])],
            unit=str(data.get("unit", "")),
        )


@dataclass
class MultiDimensionalSweepResult:
    """Multi-dimensional dataset containing structured sweep results."""
    variables: list[SweepVariable] = field(default_factory=list)
    points: list[PolarPoint] = field(default_factory=list)
    grid_shape: tuple[int, ...] = ()

    @property
    def variable_names(self) -> list[str]:
        return [v.name for v in self.variables]

    def get_slice(
        self,
        fixed_conditions: dict[str, float],
        tolerance: float = 1e-4,
    ) -> list[PolarPoint]:
        """Extract a 1D or subset slice of points matching fixed variable conditions.

        Example:
            slice_points = sweep.get_slice({"beta": 0.0, "elevator": -5.0})
        """
        result = []
        for pt in self.points:
            match = True
            for key, val in fixed_conditions.items():
                pt_val = None
                if key == "alpha":
                    pt_val = pt.alpha
                elif key == "beta":
                    pt_val = pt.beta
                elif key == "velocity":
                    pt_val = pt.velocity
                elif key == "altitude":
                    pt_val = pt.altitude
                elif key == "mach":
                    pt_val = pt.mach
                elif key in pt.control_deflections:
                    pt_val = pt.control_deflections[key]

                if pt_val is None or not math.isclose(pt_val, val, abs_tol=tolerance):
                    match = False
                    break
            if match:
                result.append(pt)
        return result

    def find_point(self, tolerance: float = 1e-4, **conditions: float) -> PolarPoint | None:
        """Find a specific point in the sweep dataset matching condition values."""
        matches = self.get_slice(conditions, tolerance=tolerance)
        return matches[0] if matches else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "variables": [v.to_dict() for v in self.variables],
            "points": [p.to_dict() for p in self.points],
            "grid_shape": list(self.grid_shape),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MultiDimensionalSweepResult:
        vars_data = data.get("variables", [])
        pts_data = data.get("points", [])
        return cls(
            variables=[SweepVariable.from_dict(v) for v in vars_data if isinstance(v, dict)],
            points=[PolarPoint.from_dict(p) for p in pts_data if isinstance(p, dict)],
            grid_shape=tuple(data.get("grid_shape", ())),
        )


@dataclass(frozen=True)
class PropulsionPoint:
    """Propulsion installation / attachment point and thrust line definition."""
    id: str
    name: str
    component_type: str
    position: tuple[float, float, float]  # (x, y, z) in meters in geometry/body frame
    thrust_vector: tuple[float, float, float] = (1.0, 0.0, 0.0)  # Normalized thrust direction vector
    diameter: float = 0.0                 # Propeller/rotor diameter in meters
    pitch: float = 0.0                    # Propeller pitch in meters or inches
    rotation_direction: str = "CW"        # "CW" or "CCW"
    max_thrust: float = 0.0               # Max static thrust in Newtons (if known)
    motor_kv: float = 0.0                 # Motor KV (RPM/V)
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "component_type": self.component_type,
            "position": list(self.position),
            "thrust_vector": list(self.thrust_vector),
            "diameter": self.diameter,
            "pitch": self.pitch,
            "rotation_direction": self.rotation_direction,
            "max_thrust": self.max_thrust,
            "motor_kv": self.motor_kv,
            "properties": dict(self.properties),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PropulsionPoint:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            component_type=str(data.get("component_type", "")),
            position=tuple(data.get("position", (0.0, 0.0, 0.0))),
            thrust_vector=tuple(data.get("thrust_vector", (1.0, 0.0, 0.0))),
            diameter=float(data.get("diameter", 0.0)),
            pitch=float(data.get("pitch", 0.0)),
            rotation_direction=str(data.get("rotation_direction", "CW")),
            max_thrust=float(data.get("max_thrust", 0.0)),
            motor_kv=float(data.get("motor_kv", 0.0)),
            properties=dict(data.get("properties") or {}),
        )


@dataclass
class AeroResult:
    """Complete analysis result returned by an aerodynamic engine."""
    method: AnalysisMethod
    engine_name: str
    polar_points: list[PolarPoint] = field(default_factory=list)
    # Summary key metrics
    cl_max: float = 0.0
    cl_max_alpha: float = 0.0
    cd_min: float = 0.0
    ld_max: float = 0.0
    ld_max_alpha: float = 0.0
    # Reference geometry & flight numbers
    reference: ReferenceValues = field(default_factory=ReferenceValues)
    reynolds: float = 0.0
    mach: float = 0.0
    dynamic_pressure: float = 0.0
    oswald_efficiency: float | None = None
    # Stability derivatives (longitudinal & lateral-directional)
    stability_derivatives: dict[str, float] = field(default_factory=dict)
    # Multi-dimensional sweep dataset (if sweep performed)
    sweep_result: MultiDimensionalSweepResult | None = None
    # Flight condition specified for this analysis
    condition: FlightCondition = field(default_factory=FlightCondition)
    # Propulsion attachment points and thrust lines identified in project
    propulsion_points: list[PropulsionPoint] = field(default_factory=list)
    # Raw engine specific payload (for custom downstream rendering or debugging)
    raw: dict[str, Any] = field(default_factory=dict)

    def get_point(self, alpha: float, beta: float = 0.0, tolerance: float = 1e-4) -> PolarPoint | None:
        """Find a polar point by alpha and beta."""
        for pt in self.polar_points:
            if math.isclose(pt.alpha, alpha, abs_tol=tolerance) and math.isclose(pt.beta, beta, abs_tol=tolerance):
                return pt
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to a dictionary for persistent storage or JSON output."""
        return {
            "method": self.method.value,
            "engine_name": self.engine_name,
            "polar_points": [p.to_dict() for p in self.polar_points],
            "cl_max": self.cl_max,
            "cl_max_alpha": self.cl_max_alpha,
            "cd_min": self.cd_min,
            "ld_max": self.ld_max,
            "ld_max_alpha": self.ld_max_alpha,
            "reference": self.reference.to_dict(),
            "reynolds": self.reynolds,
            "mach": self.mach,
            "dynamic_pressure": self.dynamic_pressure,
            "oswald_efficiency": self.oswald_efficiency,
            "stability_derivatives": dict(self.stability_derivatives),
            "sweep_result": self.sweep_result.to_dict() if self.sweep_result is not None else None,
            "propulsion_points": [p.to_dict() for p in self.propulsion_points],
            "condition": self.condition.to_dict(),
            # Don't serialize non-JSON raw object instances in to_dict
            "raw": {k: v for k, v in self.raw.items() if isinstance(v, (int, float, str, bool, list, dict))},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AeroResult:
        """Construct an AeroResult instance from a serialized dictionary."""
        method_str = data.get("method", "aero_buildup")
        try:
            method = AnalysisMethod(method_str)
        except ValueError:
            method = AnalysisMethod.AERO_BUILDUP

        points = [PolarPoint.from_dict(p) for p in data.get("polar_points", []) if isinstance(p, dict)]
        ref = ReferenceValues.from_dict(data.get("reference") or {})
        cond = FlightCondition.from_dict(data.get("condition") or {})
        prop_pts = [
            PropulsionPoint.from_dict(p)
            for p in data.get("propulsion_points", [])
            if isinstance(p, dict)
        ]

        sweep_data = data.get("sweep_result")
        sweep = MultiDimensionalSweepResult.from_dict(sweep_data) if isinstance(sweep_data, dict) else None

        return cls(
            method=method,
            engine_name=str(data.get("engine_name", "")),
            polar_points=points,
            cl_max=float(data.get("cl_max", 0.0)),
            cl_max_alpha=float(data.get("cl_max_alpha", 0.0)),
            cd_min=float(data.get("cd_min", 0.0)),
            ld_max=float(data.get("ld_max", 0.0)),
            ld_max_alpha=float(data.get("ld_max_alpha", 0.0)),
            reference=ref,
            reynolds=float(data.get("reynolds", 0.0)),
            mach=float(data.get("mach", 0.0)),
            dynamic_pressure=float(data.get("dynamic_pressure", 0.0)),
            oswald_efficiency=data.get("oswald_efficiency"),
            stability_derivatives=dict(data.get("stability_derivatives") or {}),
            sweep_result=sweep,
            condition=cond,
            propulsion_points=prop_pts,
            raw=dict(data.get("raw") or {}),
        )


@dataclass(frozen=True)
class EngineCapabilities:
    """Capabilities supported by a particular engine."""
    methods: frozenset[AnalysisMethod] = field(default_factory=frozenset)
    analysis_types: frozenset[AnalysisType] = field(default_factory=frozenset)
    supports_fuselage: bool = False
    supports_control_surfaces: bool = False


class AeroEngine(ABC):
    """Abstract base class for aerodynamic analysis engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable engine name."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if engine runtime dependencies are installed and available."""
        ...

    @abstractmethod
    def capabilities(self) -> EngineCapabilities:
        """Report features and solver methods supported by this engine."""
        ...

    @abstractmethod
    def analyze(
        self,
        components: list[dict[str, Any]],
        condition: FlightCondition,
        method: AnalysisMethod = AnalysisMethod.AERO_BUILDUP,
        settings: dict[str, Any] | None = None,
        progress_callback: Any | None = None,
    ) -> AeroResult:
        """Run aerodynamic analysis.

        Args:
            components: Project component dictionaries (lifting-surfaces, fuselages, etc.)
            condition: Flight conditions and sweep parameters
            method: Selected solver method
            settings: Optional engine-specific configuration options
            progress_callback: Optional callback(completed, total, message)

        Returns:
            AeroResult containing polar curve data, 6-DoF coefficients, and key aerodynamic metrics
        """
        ...
