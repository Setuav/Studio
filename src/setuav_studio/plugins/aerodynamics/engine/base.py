"""Abstract aerodynamic engine interface and shared data models."""

from __future__ import annotations

import enum
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence


class _Unserializable:
    pass


_UNSERIALIZABLE = _Unserializable()


def _json_safe(value: Any) -> Any:
    """Convert native solver values into JSON-compatible Python values."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        # Strict JSON has no NaN/Infinity literals.  Native solvers can emit
        # either for an ill-conditioned point, so preserve the unavailability
        # rather than writing a non-standard JSON number.
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            safe = _json_safe(item)
            if safe is not _UNSERIALIZABLE:
                result[str(key)] = safe
        return result
    if isinstance(value, (list, tuple)):
        result_list: list[Any] = []
        for item in value:
            safe = _json_safe(item)
            if safe is _UNSERIALIZABLE:
                return _UNSERIALIZABLE
            result_list.append(safe)
        return result_list
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return _json_safe(tolist())
        except Exception:
            return _UNSERIALIZABLE
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except Exception:
            return _UNSERIALIZABLE
    return _UNSERIALIZABLE


class AnalysisMethod(enum.Enum):
    """Available solver methods."""

    VLM = "vlm"
    AERO_BUILDUP = "aero_buildup"
    LIFTING_LINE = "lifting_line"

    @classmethod
    def from_value(cls, value: Any) -> "AnalysisMethod":
        """Parse a supported solver method without silently changing it."""
        if isinstance(value, cls):
            return value
        return cls(str(value or "").strip().lower())


class AeroAnalysisError(RuntimeError):
    """Raised when an aerodynamic solver cannot produce a usable result."""


class AnalysisType(enum.Enum):
    """Types of analysis an engine can perform."""

    SINGLE_POINT = "single_point"
    ALPHA_SWEEP = "alpha_sweep"
    BETA_SWEEP = "beta_sweep"
    MULTI_SWEEP = "multi_sweep"
    STABILITY_DERIVATIVES = "stability_derivatives"
    CONTROL_CHANNEL = "control_channel"


class SweepType(enum.Enum):
    """Types of parametric sweeps available."""

    ALPHA = "alpha"  # Angle of attack sweep (AoA α)
    BETA = "beta"  # Sideslip angle sweep (Sideslip β)
    DUAL_ALPHA_BETA = "dual_alpha_beta"  # Simultaneous 1D Alpha + 1D Beta sweep (both populated)
    MULTI_GRID = "multi_grid"  # 2D Parametric grid sweep (α × β flight envelope)
    CONTROL_DEFLECTION = "control_deflection"  # Persisted name for a control-channel analysis (δ)


class ControlSurfaceType(enum.Enum):
    """Types of aerodynamic control surfaces supported across Setuav Studio."""

    AILERON = "aileron"
    FLAP = "flap"
    ELEVATOR = "elevator"
    RUDDER = "rudder"
    ELEVON = "elevon"
    RUDDERVATOR = "ruddervator"

    @classmethod
    def from_str(cls, value: str | None) -> ControlSurfaceType | None:
        if not value:
            return None
        val_clean = str(value).strip().lower()
        for member in cls:
            if member.value == val_clean:
                return member
        return None


CONTROL_CHANNELS: tuple[str, ...] = ("elevator", "aileron", "rudder", "flap")
_CONTROL_TYPE_CHANNELS: dict[str, tuple[str, ...]] = {
    "elevator": ("elevator",),
    "aileron": ("aileron",),
    "rudder": ("rudder",),
    "flap": ("flap",),
    "elevon": ("elevator", "aileron"),
    "ruddervator": ("elevator", "rudder"),
    "vtail": ("elevator", "rudder"),
    "v-tail": ("elevator", "rudder"),
}


def control_channels_for_components(
    components: Sequence[dict[str, Any]],
) -> tuple[str, ...]:
    """Return canonical pilot-control channels provided by the component geometry."""
    discovered: set[str] = set()

    def add_surface(value: object) -> None:
        normalized = str(value or "").strip().lower()
        discovered.update(_CONTROL_TYPE_CHANNELS.get(normalized, ()))

    for component in components:
        if not isinstance(component, dict):
            continue
        parameters = component.get("parameters")
        parameters = parameters if isinstance(parameters, dict) else {}
        geometry = parameters.get("geometry")
        geometry = geometry if isinstance(geometry, dict) else {}

        control_surfaces = geometry.get("control_surfaces")
        if isinstance(control_surfaces, list):
            for surface in control_surfaces:
                if not isinstance(surface, dict):
                    continue
                add_surface(surface.get("type") or surface.get("tag"))

        if component.get("type") == "org.setuav.core:control-surface":
            add_surface(geometry.get("type") or geometry.get("tag"))

        tags = parameters.get("tags")
        if isinstance(tags, list):
            for tag in tags:
                add_surface(tag)

    return tuple(channel for channel in CONTROL_CHANNELS if channel in discovered)


@dataclass(frozen=True)
class FlightCondition:
    """Operating conditions and sweep parameters for aerodynamic analysis."""

    velocity: float = 25.0  # m/s (true airspeed)
    alpha: float = 2.0  # deg (single point or reference AoA)
    beta: float = 0.0  # deg (sideslip angle)
    altitude: float = 0.0  # m MSL
    p: float = 0.0  # rad/s (body roll rate)
    q: float = 0.0  # rad/s (body pitch rate)
    r: float = 0.0  # rad/s (body yaw rate)
    control_deflections: dict[str, float] = field(default_factory=dict)  # deg per control surface
    # Sweep configuration
    sweep_type: SweepType = SweepType.ALPHA
    sweep_variable: str = "alpha"  # Primary variable name ('alpha', 'beta', or a control channel)
    sweep_min: float = -10.0  # Range start
    sweep_max: float = 18.0  # Range end
    sweep_steps: int = 29  # Number of evaluation points
    # Secondary sweep configuration (for 2D grid sweeps)
    secondary_variable: str | None = None
    secondary_min: float = 0.0
    secondary_max: float = 0.0
    secondary_steps: int = 1
    # Backward compatibility fields
    alpha_min: float = -10.0  # deg
    alpha_max: float = 18.0  # deg
    alpha_steps: int = 29
    beta_min: float = 0.0
    beta_max: float = 0.0
    beta_steps: int = 1

    def get_primary_sweep_values(self) -> list[float]:
        """Compute the array of evaluated values for the primary sweep parameter."""
        import numpy as _np

        if self.sweep_type == SweepType.ALPHA:
            if self.alpha_steps != 29:
                steps = self.alpha_steps
                s_min = self.alpha_min
                s_max = self.alpha_max
            elif self.sweep_steps != 29:
                steps = self.sweep_steps
                s_min = self.sweep_min
                s_max = self.sweep_max
            else:
                steps = self.alpha_steps
                s_min = self.alpha_min
                s_max = self.alpha_max

            if steps <= 1:
                return [float(self.alpha)]
            return [float(v) for v in _np.linspace(s_min, s_max, max(steps, 2))]
        else:
            steps = max(int(self.sweep_steps), 1)
            if steps <= 1:
                if self.sweep_type == SweepType.BETA:
                    return [float(self.beta)]
                return [float(self.sweep_min)]
            return [float(v) for v in _np.linspace(self.sweep_min, self.sweep_max, steps)]

    def get_secondary_sweep_values(self) -> list[float]:
        """Compute the array of evaluated values for the secondary sweep parameter."""
        steps = max(int(self.secondary_steps), 1)
        if steps <= 1 or not self.secondary_variable:
            return [float(self.secondary_min)]
        import numpy as _np

        return [float(v) for v in _np.linspace(self.secondary_min, self.secondary_max, steps)]

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
            "sweep_type": self.sweep_type.value,
            "sweep_variable": self.sweep_variable,
            "sweep_min": self.sweep_min,
            "sweep_max": self.sweep_max,
            "sweep_steps": self.sweep_steps,
            "secondary_variable": self.secondary_variable,
            "secondary_min": self.secondary_min,
            "secondary_max": self.secondary_max,
            "secondary_steps": self.secondary_steps,
            "alpha_min": self.alpha_min,
            "alpha_max": self.alpha_max,
            "alpha_steps": self.alpha_steps,
            "beta_min": self.beta_min,
            "beta_max": self.beta_max,
            "beta_steps": self.beta_steps,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlightCondition:
        st_val = data.get("sweep_type", "alpha")
        try:
            st = SweepType(st_val)
        except ValueError:
            st = SweepType.ALPHA

        # Handle backward compatibility with alpha_min / alpha_max
        s_min = float(data.get("sweep_min", data.get("alpha_min", -4.0)))
        s_max = float(data.get("sweep_max", data.get("alpha_max", 16.0)))
        s_steps = int(data.get("sweep_steps", data.get("alpha_steps", 21)))

        return cls(
            velocity=float(data.get("velocity", 25.0)),
            alpha=float(data.get("alpha", 2.0)),
            beta=float(data.get("beta", 0.0)),
            altitude=float(data.get("altitude", 0.0)),
            p=float(data.get("p", 0.0)),
            q=float(data.get("q", 0.0)),
            r=float(data.get("r", 0.0)),
            control_deflections=dict(data.get("control_deflections") or {}),
            sweep_type=st,
            sweep_variable=str(data.get("sweep_variable", "alpha")),
            sweep_min=s_min,
            sweep_max=s_max,
            sweep_steps=s_steps,
            secondary_variable=data.get("secondary_variable"),
            secondary_min=float(data.get("secondary_min", 0.0)),
            secondary_max=float(data.get("secondary_max", 0.0)),
            secondary_steps=int(data.get("secondary_steps", 1)),
            alpha_min=float(data.get("alpha_min", s_min)),
            alpha_max=float(data.get("alpha_max", s_max)),
            alpha_steps=int(data.get("alpha_steps", s_steps)),
            beta_min=float(data.get("beta_min", 0.0)),
            beta_max=float(data.get("beta_max", 0.0)),
            beta_steps=int(data.get("beta_steps", 1)),
        )


@dataclass(frozen=True)
class ReferenceValues:
    """Aerodynamic reference geometry."""

    s_ref: float = 0.0  # m² reference area (S)
    b_ref: float = 0.0  # m reference span (b)
    c_ref: float = 0.0  # m mean aerodynamic chord (MAC, c)
    x_cg: float = 0.0  # m moment reference X
    y_cg: float = 0.0  # m moment reference Y
    z_cg: float = 0.0  # m moment reference Z

    @property
    def xyz_ref(self) -> tuple[float, float, float]:
        return (self.x_cg, self.y_cg, self.z_cg)

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
    # Wind-frame force vector (N): [-Drag, Sideforce, -Lift]
    fx_w: float = 0.0
    fy_w: float = 0.0
    fz_w: float = 0.0
    # Conventional aerodynamic force magnitudes (N)
    lift: float = 0.0  # perpendicular to freestream (positive up)
    drag: float = 0.0  # parallel to freestream (positive aft)
    sideforce: float = 0.0  # perpendicular to lift & drag (positive right)
    # Geometry-frame forces (N)
    fx_g: float = 0.0
    fy_g: float = 0.0
    fz_g: float = 0.0
    # Body-frame moments (N·m) about CG/reference point
    mx_b: float = 0.0  # Roll moment (L_b) about body X
    my_b: float = 0.0  # Pitch moment (M_b) about body Y
    mz_b: float = 0.0  # Yaw moment (N_b) about body Z
    # Wind-frame moments (N·m)
    mx_w: float = 0.0
    my_w: float = 0.0
    mz_w: float = 0.0
    # Geometry-frame moments (N·m)
    mx_g: float = 0.0
    my_g: float = 0.0
    mz_g: float = 0.0
    # Native solver output dictionary
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def m_roll(self) -> float:
        """Roll moment (Mx) in Newton-meters."""
        return self.mx_b

    @property
    def m_pitch(self) -> float:
        """Pitch moment (My) in Newton-meters."""
        return self.my_b

    @property
    def m_yaw(self) -> float:
        """Yaw moment (Mz) in Newton-meters."""
        return self.mz_b

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
        """Native wind-axis force vector (Fx, Fy, Fz) in Newtons."""
        return (self.fx_w, self.fy_w, self.fz_w)

    @property
    def moment_wind(self) -> tuple[float, float, float]:
        """Wind moment vector in Newton-meters."""
        return (self.mx_w, self.my_w, self.mz_w)

    @property
    def force_geometry(self) -> tuple[float, float, float]:
        """Geometry force vector in Newtons."""
        return (self.fx_g, self.fy_g, self.fz_g)

    @property
    def moment_geometry(self) -> tuple[float, float, float]:
        """Geometry moment vector in Newton-meters."""
        return (self.mx_g, self.my_g, self.mz_g)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fx_b": self.fx_b,
            "fy_b": self.fy_b,
            "fz_b": self.fz_b,
            "fx_w": self.fx_w,
            "fy_w": self.fy_w,
            "fz_w": self.fz_w,
            "lift": self.lift,
            "drag": self.drag,
            "sideforce": self.sideforce,
            "fx_g": self.fx_g,
            "fy_g": self.fy_g,
            "fz_g": self.fz_g,
            "mx_b": self.mx_b,
            "my_b": self.my_b,
            "mz_b": self.mz_b,
            "mx_w": self.mx_w,
            "my_w": self.my_w,
            "mz_w": self.mz_w,
            "mx_g": self.mx_g,
            "my_g": self.my_g,
            "mz_g": self.mz_g,
            "raw": _json_safe(self.raw),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AeroForcesMoments:
        return cls(
            fx_b=float(data.get("fx_b", 0.0)),
            fy_b=float(data.get("fy_b", 0.0)),
            fz_b=float(data.get("fz_b", 0.0)),
            fx_w=float(data.get("fx_w", -float(data.get("drag", 0.0)))),
            fy_w=float(data.get("fy_w", data.get("sideforce", 0.0))),
            fz_w=float(data.get("fz_w", -float(data.get("lift", 0.0)))),
            lift=float(data.get("lift", 0.0)),
            drag=float(data.get("drag", 0.0)),
            sideforce=float(data.get("sideforce", 0.0)),
            fx_g=float(data.get("fx_g", 0.0)),
            fy_g=float(data.get("fy_g", 0.0)),
            fz_g=float(data.get("fz_g", 0.0)),
            mx_b=float(data.get("mx_b", 0.0)),
            my_b=float(data.get("my_b", 0.0)),
            mz_b=float(data.get("mz_b", 0.0)),
            mx_w=float(data.get("mx_w", 0.0)),
            my_w=float(data.get("my_w", 0.0)),
            mz_w=float(data.get("mz_w", 0.0)),
            mx_g=float(data.get("mx_g", 0.0)),
            my_g=float(data.get("my_g", 0.0)),
            mz_g=float(data.get("mz_g", 0.0)),
            raw=dict(data.get("raw")) if isinstance(data.get("raw"), dict) else {},
        )


@dataclass(frozen=True)
class AeroState:
    """Operating flight and flow state at an evaluation point."""

    alpha: float = 0.0  # deg (angle of attack)
    beta: float = 0.0  # deg (sideslip angle)
    p: float = 0.0  # rad/s (roll rate)
    q: float = 0.0  # rad/s (pitch rate)
    r: float = 0.0  # rad/s (yaw rate)
    velocity: float = 0.0  # m/s (true airspeed)
    altitude: float = 0.0  # m MSL
    mach: float = 0.0
    reynolds: float = 0.0
    dynamic_pressure: float = 0.0  # Pa (q_inf = 0.5 * rho * V^2)
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
    cm: float = 0.0  # Pitching moment coefficient (C_m about Y body)
    cd_induced: float | None = None  # Native induced drag coefficient, when available
    cd_profile: float | None = None  # Native profile drag coefficient, when available
    cl_over_cd: float = 0.0  # Lift-to-drag ratio (L/D)
    # 6-DoF Non-dimensional body/wind coefficients
    cx: float = 0.0  # Body X force coefficient (C_X)
    cy: float = 0.0  # Side force coefficient (C_Y)
    cz: float = 0.0  # Body Z force coefficient (C_Z)
    cl_roll: float = 0.0  # Rolling moment coefficient (C_l about X body)
    cn: float = 0.0  # Yawing moment coefficient (C_n about Z body)
    cd_wave: float | None = None  # Native wave drag coefficient, when available
    # Operating state
    beta: float = 0.0  # deg (sideslip angle)
    p: float = 0.0  # rad/s (roll rate)
    q: float = 0.0  # rad/s (pitch rate)
    r: float = 0.0  # rad/s (yaw rate)
    # Full forces, moments and state containers
    forces_moments: AeroForcesMoments | None = None
    state: AeroState | None = None
    # Quick flow parameters
    velocity: float = 0.0  # m/s
    altitude: float = 0.0  # m
    mach: float = 0.0
    reynolds: float = 0.0
    dynamic_pressure: float = 0.0  # Pa
    control_deflections: dict[str, float] = field(default_factory=dict)
    # Execution & solver status
    converged: bool = True
    notes: str = ""
    # Native solver raw dictionary for this evaluation point
    raw: dict[str, Any] = field(default_factory=dict)

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
            "forces_moments": self.forces_moments.to_dict()
            if self.forces_moments is not None
            else None,
            "state": self.state.to_dict() if self.state is not None else None,
            "velocity": self.velocity,
            "altitude": self.altitude,
            "mach": self.mach,
            "reynolds": self.reynolds,
            "dynamic_pressure": self.dynamic_pressure,
            "control_deflections": dict(self.control_deflections),
            "converged": self.converged,
            "notes": self.notes,
            "raw": _json_safe(self.raw),
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
            cd_induced=(float(data["cd_induced"]) if data.get("cd_induced") is not None else None),
            cd_profile=(float(data["cd_profile"]) if data.get("cd_profile") is not None else None),
            cl_over_cd=float(data.get("cl_over_cd", 0.0)),
            cx=float(data.get("cx", 0.0)),
            cy=float(data.get("cy", 0.0)),
            cz=float(data.get("cz", 0.0)),
            cl_roll=float(data.get("cl_roll", 0.0)),
            cn=float(data.get("cn", 0.0)),
            cd_wave=(float(data["cd_wave"]) if data.get("cd_wave") is not None else None),
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
            raw=dict(data.get("raw")) if isinstance(data.get("raw"), dict) else {},
        )


# Alias for generalized point results
AeroPointResult = PolarPoint


@dataclass(frozen=True)
class SweepVariable:
    """A parameter varied during multi-dimensional aerodynamic sweeps."""

    name: str  # Parameter name: 'alpha', 'beta', or control channel name
    values: list[float]  # Evaluated grid values
    unit: str = ""  # Unit for display (normally 'deg')

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
    """Structured sweep data in row-major, last-variable-fastest order."""

    variables: list[SweepVariable] = field(default_factory=list)
    points: list[PolarPoint] = field(default_factory=list)
    grid_shape: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.variables and not self.grid_shape and not self.points:
            return
        if len(self.variables) != len(self.grid_shape):
            raise ValueError("Sweep variables and grid_shape dimensions must match")
        expected_shape = tuple(len(variable.values) for variable in self.variables)
        if self.grid_shape != expected_shape:
            raise ValueError(
                f"grid_shape {self.grid_shape!r} does not match variable sizes {expected_shape!r}"
            )
        expected_points = math.prod(self.grid_shape)
        if len(self.points) != expected_points:
            raise ValueError(
                f"Sweep contains {len(self.points)} point(s), expected {expected_points}"
            )

    @property
    def variable_names(self) -> list[str]:
        return [v.name for v in self.variables]

    def point_at_indices(self, *indices: int) -> PolarPoint:
        """Return a grid point; the last variable is the fastest-changing axis."""
        if len(indices) != len(self.grid_shape):
            raise IndexError("One index is required for each sweep variable")
        flat_index = 0
        for index, size in zip(indices, self.grid_shape, strict=True):
            if index < 0 or index >= size:
                raise IndexError("Sweep grid index out of range")
            flat_index = flat_index * size + index
        return self.points[flat_index]

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

    def find_point(
        self,
        conditions_dict: dict[str, float] | None = None,
        tolerance: float = 1e-4,
        **conditions: float,
    ) -> PolarPoint | None:
        """Find a specific point in the sweep dataset matching condition values.

        Can be called with keyword arguments or a condition dictionary:
            pt = sweep.find_point(alpha=2.0, beta=0.0)
            pt = sweep.find_point({"alpha": 2.0, "beta": 0.0})
        """
        conds = dict(conditions_dict or {})
        conds.update(conditions)
        matches = self.get_slice(conds, tolerance=tolerance)
        return matches[0] if matches else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "variables": [v.to_dict() for v in self.variables],
            "points": [p.to_dict() for p in self.points],
            "grid_shape": list(self.grid_shape),
            "point_order": "last_variable_fastest",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MultiDimensionalSweepResult:
        point_order = data.get("point_order", "last_variable_fastest")
        if point_order != "last_variable_fastest":
            raise ValueError(f"Unsupported sweep point order: {point_order}")
        vars_data = data.get("variables", [])
        pts_data = data.get("points", [])
        return cls(
            variables=[SweepVariable.from_dict(v) for v in vars_data if isinstance(v, dict)],
            points=[PolarPoint.from_dict(p) for p in pts_data if isinstance(p, dict)],
            grid_shape=tuple(data.get("grid_shape", ())),
        )


@dataclass(frozen=True)
class ControlChannelAnalysis:
    """Control-channel effectiveness fitted from a deflection response sweep."""

    channel: str
    sample_count: int
    deflection_min_deg: float
    deflection_max_deg: float
    derivatives_per_deg: dict[str, float] = field(default_factory=dict)
    linearity_r2: dict[str, float] = field(default_factory=dict)
    method: str = "least_squares"

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "sample_count": self.sample_count,
            "deflection_min_deg": self.deflection_min_deg,
            "deflection_max_deg": self.deflection_max_deg,
            "derivatives_per_deg": dict(self.derivatives_per_deg),
            "linearity_r2": dict(self.linearity_r2),
            "method": self.method,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ControlChannelAnalysis:
        return cls(
            channel=str(data.get("channel", "")),
            sample_count=int(data.get("sample_count", 0)),
            deflection_min_deg=float(data.get("deflection_min_deg", 0.0)),
            deflection_max_deg=float(data.get("deflection_max_deg", 0.0)),
            derivatives_per_deg={
                str(key): float(value)
                for key, value in (data.get("derivatives_per_deg") or {}).items()
            },
            linearity_r2={
                str(key): float(value) for key, value in (data.get("linearity_r2") or {}).items()
            },
            method=str(data.get("method", "least_squares")),
        )


@dataclass(frozen=True)
class PropulsionPoint:
    """Propulsion installation / attachment point and thrust line definition."""

    id: str
    name: str
    component_type: str
    position: tuple[float, float, float]  # (x, y, z) in meters in geometry/body frame
    thrust_vector: tuple[float, float, float] = (
        1.0,
        0.0,
        0.0,
    )  # Normalized thrust direction vector
    diameter: float = 0.0  # Propeller/rotor diameter in meters
    pitch: float = 0.0  # Propeller pitch in meters or inches
    rotation_direction: str = "CW"  # "CW" or "CCW"
    max_thrust: float = 0.0  # Max static thrust in Newtons (if known)
    motor_kv: float = 0.0  # Motor KV (RPM/V)
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
    stability_derivatives: Any | None = None
    # Multi-dimensional sweep dataset (if sweep performed)
    sweep_result: MultiDimensionalSweepResult | None = None
    # Control-channel effectiveness fitted from a control response analysis.
    control_analysis: ControlChannelAnalysis | None = None
    # Flight condition specified for this analysis
    condition: FlightCondition = field(default_factory=FlightCondition)
    # Propulsion attachment points and thrust lines identified in project
    propulsion_points: list[PropulsionPoint] = field(default_factory=list)
    # Raw engine specific payload (for custom downstream rendering or debugging)
    raw: dict[str, Any] = field(default_factory=dict)

    def get_point(
        self, alpha: float, beta: float = 0.0, tolerance: float = 1e-4
    ) -> PolarPoint | None:
        """Find a polar point by alpha and beta."""
        for pt in self.polar_points:
            if math.isclose(pt.alpha, alpha, abs_tol=tolerance) and math.isclose(
                pt.beta, beta, abs_tol=tolerance
            ):
                return pt
        return None

    @property
    def converged_point_count(self) -> int:
        return sum(point.converged for point in self.polar_points)

    @property
    def failed_point_count(self) -> int:
        return len(self.polar_points) - self.converged_point_count

    @property
    def is_complete(self) -> bool:
        return bool(self.polar_points) and self.failed_point_count == 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to a dictionary for persistent storage or JSON output."""
        stab_dict = None
        if hasattr(self.stability_derivatives, "to_dict"):
            stab_dict = self.stability_derivatives.to_dict()
        elif isinstance(self.stability_derivatives, dict):
            stab_dict = dict(self.stability_derivatives)

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
            "stability_derivatives": stab_dict,
            "sweep_result": self.sweep_result.to_dict() if self.sweep_result is not None else None,
            "control_analysis": self.control_analysis.to_dict()
            if self.control_analysis is not None
            else None,
            "propulsion_points": [p.to_dict() for p in self.propulsion_points],
            "condition": self.condition.to_dict(),
            # Don't serialize non-JSON raw object instances in to_dict
            "raw": _json_safe(self.raw),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AeroResult:
        """Construct an AeroResult instance from a serialized dictionary."""
        method = AnalysisMethod.from_value(data.get("method", "aero_buildup"))

        points = [
            PolarPoint.from_dict(p) for p in data.get("polar_points", []) if isinstance(p, dict)
        ]

        ref = ReferenceValues.from_dict(data.get("reference") or {})
        cond = FlightCondition.from_dict(data.get("condition") or {})
        prop_pts = [
            PropulsionPoint.from_dict(p)
            for p in data.get("propulsion_points", [])
            if isinstance(p, dict)
        ]

        sweep_data = data.get("sweep_result")
        sweep = (
            MultiDimensionalSweepResult.from_dict(sweep_data)
            if isinstance(sweep_data, dict)
            else None
        )
        control_data = data.get("control_analysis")
        control_analysis = (
            ControlChannelAnalysis.from_dict(control_data)
            if isinstance(control_data, dict)
            else None
        )

        stab_raw = data.get("stability_derivatives")
        stab_res = None
        if isinstance(stab_raw, dict):
            try:
                from .stability_models import StabilityDerivatives

                stab_res = StabilityDerivatives.from_dict(stab_raw)
            except Exception:
                stab_res = stab_raw

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
            stability_derivatives=stab_res,
            sweep_result=sweep,
            control_analysis=control_analysis,
            condition=cond,
            propulsion_points=prop_pts,
            raw=dict(data.get("raw")) if isinstance(data.get("raw"), dict) else {},
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
