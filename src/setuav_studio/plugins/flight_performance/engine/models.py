"""Flight performance analysis data models."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        f = float(val)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class OptimalSpeeds:
    """Characteristic optimal speeds for flight envelope."""

    best_endurance: float = 0.0  # m/s (min power required / electrical draw)
    best_range: float = 0.0      # m/s (max L/D in cruise or max range)
    best_climb: float = 0.0      # m/s (max excess power / Vy)
    best_ld: float = 0.0         # m/s (speed at maximum L/D)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OptimalSpeeds:
        return cls(
            best_endurance=_safe_float(data.get("best_endurance")),
            best_range=_safe_float(data.get("best_range")),
            best_climb=_safe_float(data.get("best_climb")),
            best_ld=_safe_float(data.get("best_ld")),
        )


@dataclass(frozen=True)
class PerformanceMetrics:
    """Scalar performance envelope summary metrics."""

    stall_speed: float = 0.0          # m/s
    max_speed: float = 0.0            # m/s (max level flight speed)
    max_ld_ratio: float = 0.0         # (L/D)_max
    glide_ratio: float = 0.0          # Unpowered glide ratio
    best_climb_angle_deg: float = 0.0 # deg (gamma_max)
    min_power_required: float = 0.0   # W (aerodynamic power)
    max_range_km: float = 0.0         # km
    max_endurance_hours: float = 0.0  # hours
    max_rate_of_climb: float = 0.0    # m/s (ROC_max)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PerformanceMetrics:
        return cls(
            stall_speed=_safe_float(data.get("stall_speed")),
            max_speed=_safe_float(data.get("max_speed")),
            max_ld_ratio=_safe_float(data.get("max_ld_ratio")),
            glide_ratio=_safe_float(data.get("glide_ratio")),
            best_climb_angle_deg=_safe_float(data.get("best_climb_angle_deg")),
            min_power_required=_safe_float(data.get("min_power_required")),
            max_range_km=_safe_float(data.get("max_range_km")),
            max_endurance_hours=_safe_float(data.get("max_endurance_hours")),
            max_rate_of_climb=_safe_float(data.get("max_rate_of_climb")),
        )


@dataclass(frozen=True)
class CruisePerformance:
    """Operating state at cruise speed."""

    speed: float = 0.0      # m/s
    power: float = 0.0      # W (electrical power)
    current: float = 0.0    # A
    throttle: float = 0.0   # % (0-100)
    endurance: float = 0.0  # hours
    range: float = 0.0      # km
    feasible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CruisePerformance:
        return cls(
            speed=_safe_float(data.get("speed")),
            power=_safe_float(data.get("power")),
            current=_safe_float(data.get("current")),
            throttle=_safe_float(data.get("throttle")),
            endurance=_safe_float(data.get("endurance")),
            range=_safe_float(data.get("range")),
            feasible=bool(data.get("feasible", True)),
        )


@dataclass(frozen=True)
class FlightCurves:
    """Vector curves across velocity sweep."""

    velocities: list[float] = field(default_factory=list)
    power_required: list[float] = field(default_factory=list)     # W (aerodynamic)
    power_available: list[float] = field(default_factory=list)    # W (propulsive at current-safe max throttle)
    thrust_required: list[float] = field(default_factory=list)    # N (level flight drag)
    thrust_available: list[float] = field(default_factory=list)   # N (at current-safe max throttle)
    rate_of_climb: list[float] = field(default_factory=list)      # m/s
    climb_angle_deg: list[float] = field(default_factory=list)    # deg
    range_km: list[float] = field(default_factory=list)           # km
    endurance_hours: list[float] = field(default_factory=list)    # hours
    electrical_power: list[float] = field(default_factory=list)   # W (level flight battery draw)
    current_draw: list[float] = field(default_factory=list)       # A (level flight battery current)
    throttle_pct: list[float] = field(default_factory=list)       # %
    feasible: list[bool] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlightCurves:
        return cls(
            velocities=[_safe_float(v) for v in data.get("velocities", [])],
            power_required=[_safe_float(v) for v in data.get("power_required", [])],
            power_available=[_safe_float(v) for v in data.get("power_available", [])],
            thrust_required=[_safe_float(v) for v in data.get("thrust_required", [])],
            thrust_available=[_safe_float(v) for v in data.get("thrust_available", [])],
            rate_of_climb=[_safe_float(v) for v in data.get("rate_of_climb", [])],
            climb_angle_deg=[_safe_float(v) for v in data.get("climb_angle_deg", [])],
            range_km=[_safe_float(v) for v in data.get("range_km", [])],
            endurance_hours=[_safe_float(v) for v in data.get("endurance_hours", [])],
            electrical_power=[_safe_float(v) for v in data.get("electrical_power", [])],
            current_draw=[_safe_float(v) for v in data.get("current_draw", [])],
            throttle_pct=[_safe_float(v) for v in data.get("throttle_pct", [])],
            feasible=[bool(v) for v in data.get("feasible", [])],
        )


@dataclass(frozen=True)
class FlightEnvelopeResult:
    """Complete flight performance envelope result container."""

    mass_kg: float = 0.0
    area_m2: float = 0.0
    air_density: float = 1.225
    cl_max: float = 1.2
    cd0: float | None = None
    k_induced: float | None = None
    battery_capacity_ah: float | None = None
    battery_voltage: float | None = None
    optimal_speeds: OptimalSpeeds = field(default_factory=OptimalSpeeds)
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    cruise: CruisePerformance = field(default_factory=CruisePerformance)
    curves: FlightCurves = field(default_factory=FlightCurves)
    # ``feasible`` describes the completed analysis.  Propulsion feasibility
    # is kept separate so an aerodynamic-only result is not mistaken for a
    # coupled propulsion result.
    propulsion_available: bool = False
    propulsion_feasible: bool | None = None
    feasible: bool = True
    notes: list[str] = field(default_factory=list)
    aero_summary: dict[str, Any] = field(default_factory=dict)
    propulsion_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mass_kg": self.mass_kg,
            "area_m2": self.area_m2,
            "air_density": self.air_density,
            "cl_max": self.cl_max,
            "cd0": self.cd0,
            "k_induced": self.k_induced,
            "battery_capacity_ah": self.battery_capacity_ah,
            "battery_voltage": self.battery_voltage,
            "optimal_speeds": self.optimal_speeds.to_dict(),
            "metrics": self.metrics.to_dict(),
            "cruise": self.cruise.to_dict(),
            "curves": self.curves.to_dict(),
            "propulsion_available": self.propulsion_available,
            "propulsion_feasible": self.propulsion_feasible,
            "feasible": self.feasible,
            "notes": list(self.notes),
            "aero_summary": dict(self.aero_summary),
            "propulsion_summary": dict(self.propulsion_summary),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlightEnvelopeResult:
        curves = FlightCurves.from_dict(data.get("curves", {}))
        # Results written before the availability field was introduced had
        # populated propulsion curves. Preserve their display behaviour.
        propulsion_available = bool(
            data.get("propulsion_available", bool(curves.power_available))
        )
        return cls(
            mass_kg=_safe_float(data.get("mass_kg")),
            area_m2=_safe_float(data.get("area_m2")),
            air_density=_safe_float(data.get("air_density", 1.225)),
            cl_max=_safe_float(data.get("cl_max", 1.2)),
            cd0=_safe_float(data.get("cd0")) if data.get("cd0") is not None else None,
            k_induced=_safe_float(data.get("k_induced")) if data.get("k_induced") is not None else None,
            battery_capacity_ah=_safe_float(data.get("battery_capacity_ah")) if data.get("battery_capacity_ah") is not None else None,
            battery_voltage=_safe_float(data.get("battery_voltage")) if data.get("battery_voltage") is not None else None,
            optimal_speeds=OptimalSpeeds.from_dict(data.get("optimal_speeds", {})),
            metrics=PerformanceMetrics.from_dict(data.get("metrics", {})),
            cruise=CruisePerformance.from_dict(data.get("cruise", {})),
            curves=curves,
            propulsion_available=propulsion_available,
            propulsion_feasible=(
                bool(data["propulsion_feasible"])
                if data.get("propulsion_feasible") is not None
                else (True if propulsion_available else None)
            ),
            feasible=bool(data.get("feasible", True)),
            notes=list(data.get("notes", [])),
            aero_summary=dict(data.get("aero_summary", {})),
            propulsion_summary=dict(data.get("propulsion_summary", {})),
        )
