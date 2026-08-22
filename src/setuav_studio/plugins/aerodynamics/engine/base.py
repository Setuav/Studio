"""Abstract aerodynamic engine interface and shared data models."""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class AnalysisMethod(enum.Enum):
    """Available solver methods."""
    VLM = "vlm"
    AERO_BUILDUP = "aero_buildup"
    PANEL = "panel"
    LIFTING_LINE = "lifting_line"


class AnalysisType(enum.Enum):
    """Types of analysis an engine can perform."""
    SINGLE_POINT = "single_point"
    ALPHA_SWEEP = "alpha_sweep"
    STABILITY_DERIVATIVES = "stability_derivatives"


@dataclass(frozen=True)
class FlightCondition:
    """Operating conditions for aerodynamic analysis."""
    velocity: float = 25.0            # m/s
    alpha: float = 2.0                # deg (single point or reference AoA)
    beta: float = 0.0                 # deg
    altitude: float = 0.0             # m MSL
    alpha_min: float = -10.0          # deg (polar sweep start)
    alpha_max: float = 18.0           # deg (polar sweep end)
    alpha_steps: int = 29             # number of sweep evaluation points


@dataclass(frozen=True)
class ReferenceValues:
    """Aerodynamic reference geometry."""
    s_ref: float = 0.0    # m² reference area
    b_ref: float = 0.0    # m reference span
    c_ref: float = 0.0    # m mean aerodynamic chord
    x_cg: float = 0.0     # m moment reference X
    y_cg: float = 0.0     # m moment reference Y
    z_cg: float = 0.0     # m moment reference Z


@dataclass(frozen=True)
class PolarPoint:
    """Aerodynamic coefficients at a specific angle of attack."""
    alpha: float
    cl: float
    cd: float
    cm: float = 0.0
    cd_induced: float = 0.0
    cd_profile: float = 0.0
    cl_over_cd: float = 0.0


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
    oswald_efficiency: float | None = None
    # Stability derivatives (longitudinal & lateral-directional)
    stability_derivatives: dict[str, float] = field(default_factory=dict)
    # Raw engine specific payload (for custom downstream rendering or debugging)
    raw: dict[str, Any] = field(default_factory=dict)


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
    ) -> AeroResult:
        """Run aerodynamic analysis.

        Args:
            components: Project component dictionaries (lifting-surfaces, fuselages, etc.)
            condition: Flight conditions and sweep parameters
            method: Selected solver method
            settings: Optional engine-specific configuration options

        Returns:
            AeroResult containing polar curve data and key aerodynamic metrics
        """
        ...
