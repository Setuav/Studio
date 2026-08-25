"""Data models for linear stability derivatives, control effectiveness, and elevator trim."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MARGINAL_STATIC_MARGIN_PERCENT = 2.0


@dataclass(frozen=True)
class ControlEffectiveness:
    """Aerodynamic control derivative response for a specific control surface."""

    control_tag: str
    c_l_delta: float = 0.0  # ∂Cl/∂δ per deg (roll control power)
    c_m_delta: float = 0.0  # ∂Cm/∂δ per deg (pitch control power)
    c_n_delta: float = 0.0  # ∂Cn/∂δ per deg (yaw control power)
    c_y_delta: float = 0.0  # ∂CY/∂δ per deg (sideforce)
    c_L_delta: float = 0.0  # ∂CL/∂δ per deg (lift response)
    c_D_delta: float = 0.0  # ∂CD/∂δ per deg (control drag penalty)
    # Metadata for derivatives estimated by perturbing the selected solver.
    derivative_method: str = "finite_difference"
    perturbation_deg: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_tag": self.control_tag,
            "c_l_delta": self.c_l_delta,
            "c_m_delta": self.c_m_delta,
            "c_n_delta": self.c_n_delta,
            "c_y_delta": self.c_y_delta,
            "c_L_delta": self.c_L_delta,
            "c_D_delta": self.c_D_delta,
            "derivative_method": self.derivative_method,
            "perturbation_deg": self.perturbation_deg,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ControlEffectiveness:
        return cls(
            control_tag=str(data.get("control_tag", "control")),
            c_l_delta=float(data.get("c_l_delta", 0.0)),
            c_m_delta=float(data.get("c_m_delta", 0.0)),
            c_n_delta=float(data.get("c_n_delta", 0.0)),
            c_y_delta=float(data.get("c_y_delta", 0.0)),
            c_L_delta=float(data.get("c_L_delta", 0.0)),
            c_D_delta=float(data.get("c_D_delta", 0.0)),
            derivative_method=str(data.get("derivative_method", "finite_difference")),
            perturbation_deg=float(data.get("perturbation_deg", 2.0)),
        )


@dataclass(frozen=True)
class ElevatorTrim:
    """Elevator trim equilibrium results for longitudinal flight."""

    alpha_ref: float = 0.0  # deg reference angle of attack
    cm_0: float = 0.0  # Cm at alpha=0, delta_e=0
    cm_alpha: float = 0.0  # dCm/dalpha per deg
    cm_delta_e: float = 0.0  # dCm/ddelta_e per deg
    delta_e_trim: float = 0.0  # deg required elevator deflection for Cm=0
    alpha_trim_neutral: float = 0.0  # deg trimmed AoA at delta_e=0
    cl_trim: float = 0.0  # Lift coefficient at trimmed condition

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha_ref": self.alpha_ref,
            "cm_0": self.cm_0,
            "cm_alpha": self.cm_alpha,
            "cm_delta_e": self.cm_delta_e,
            "delta_e_trim": self.delta_e_trim,
            "alpha_trim_neutral": self.alpha_trim_neutral,
            "cl_trim": self.cl_trim,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ElevatorTrim:
        return cls(
            alpha_ref=float(data.get("alpha_ref", 0.0)),
            cm_0=float(data.get("cm_0", 0.0)),
            cm_alpha=float(data.get("cm_alpha", 0.0)),
            cm_delta_e=float(data.get("cm_delta_e", 0.0)),
            delta_e_trim=float(data.get("delta_e_trim", 0.0)),
            alpha_trim_neutral=float(data.get("alpha_trim_neutral", 0.0)),
            cl_trim=float(data.get("cl_trim", 0.0)),
        )


@dataclass(frozen=True)
class StabilityDerivatives:
    """Complete 6-DoF linear stability derivatives, static margins, and trim states."""

    # Longitudinal derivatives
    c_L_alpha_rad: float = 0.0  # ∂CL/∂α per radian
    c_L_alpha_deg: float = 0.0  # ∂CL/∂α per degree
    c_D_alpha_rad: float = 0.0  # ∂CD/∂α per radian
    c_D_alpha_deg: float = 0.0  # ∂CD/∂α per degree
    c_m_alpha_rad: float = 0.0  # ∂Cm/∂α per radian (pitch stiffness)
    c_m_alpha_deg: float = 0.0  # ∂Cm/∂α per degree
    c_L_q: float = 0.0  # ∂CL/∂q̂ (pitch rate lift derivative)
    c_m_q: float = 0.0  # ∂Cm/∂q̂ (pitch damping derivative)

    # Lateral-Directional derivatives
    c_Y_beta_rad: float = 0.0  # ∂CY/∂β per radian
    c_Y_beta_deg: float = 0.0  # ∂CY/∂β per degree
    c_l_beta_rad: float = 0.0  # ∂Cl/∂β per radian (dihedral roll stability)
    c_l_beta_deg: float = 0.0  # ∂Cl/∂β per degree
    c_n_beta_rad: float = 0.0  # ∂Cn/∂β per radian (weathercock yaw stability)
    c_n_beta_deg: float = 0.0  # ∂Cn/∂β per degree
    c_l_p: float = 0.0  # ∂Cl/∂p̂ (roll damping)
    c_n_p: float = 0.0  # ∂Cn/∂p̂ (roll-yaw cross coupling)
    c_l_r: float = 0.0  # ∂Cl/∂r̂ (yaw-roll cross coupling)
    c_n_r: float = 0.0  # ∂Cn/∂r̂ (yaw damping)

    # Longitudinal balance and static stability
    x_cg: float = 0.0  # m center of gravity X position
    x_np: float = 0.0  # m aerodynamic neutral point X position
    static_margin: float = 0.0  # % MAC static margin ((x_np - x_cg)/c_ref * 100)
    is_pitch_stable: bool = True  # True if Cm_alpha < 0 and static margin > 0
    is_pitch_damped: bool = True  # True if Cm_q < 0 (pitch damping)

    # Lateral-directional balance
    is_roll_stable: bool = True  # True if Cl_beta < 0 (dihedral effect)
    is_roll_damped: bool = True  # True if Cl_p < 0 (roll damping)
    is_yaw_stable: bool = True  # True if Cn_beta > 0 (weathercock directional stability)
    is_yaw_damped: bool = True  # True if Cn_r < 0 (yaw damping)

    # Control effectiveness per control surface
    controls: dict[str, ControlEffectiveness] = field(default_factory=dict)

    # Longitudinal trim state
    elevator_trim: ElevatorTrim | None = None
    trim_valid: bool = False
    trim_invalid_reasons: tuple[str, ...] = field(default_factory=tuple)

    # Provenance/convention for native and finite-difference values.
    solver_method: str = "unknown"
    rate_derivative_convention: str = "normalized_body_rates"

    def to_dict(self) -> dict[str, Any]:
        return {
            "c_L_alpha_rad": self.c_L_alpha_rad,
            "c_L_alpha_deg": self.c_L_alpha_deg,
            "c_D_alpha_rad": self.c_D_alpha_rad,
            "c_D_alpha_deg": self.c_D_alpha_deg,
            "c_m_alpha_rad": self.c_m_alpha_rad,
            "c_m_alpha_deg": self.c_m_alpha_deg,
            "c_L_q": self.c_L_q,
            "c_m_q": self.c_m_q,
            "c_Y_beta_rad": self.c_Y_beta_rad,
            "c_Y_beta_deg": self.c_Y_beta_deg,
            "c_l_beta_rad": self.c_l_beta_rad,
            "c_l_beta_deg": self.c_l_beta_deg,
            "c_n_beta_rad": self.c_n_beta_rad,
            "c_n_beta_deg": self.c_n_beta_deg,
            "c_l_p": self.c_l_p,
            "c_n_p": self.c_n_p,
            "c_l_r": self.c_l_r,
            "c_n_r": self.c_n_r,
            "x_cg": self.x_cg,
            "x_np": self.x_np,
            "static_margin": self.static_margin,
            "is_pitch_stable": self.is_pitch_stable,
            "is_pitch_damped": self.is_pitch_damped,
            "is_roll_stable": self.is_roll_stable,
            "is_roll_damped": self.is_roll_damped,
            "is_yaw_stable": self.is_yaw_stable,
            "is_yaw_damped": self.is_yaw_damped,
            "controls": {k: v.to_dict() for k, v in self.controls.items()},
            "elevator_trim": self.elevator_trim.to_dict() if self.elevator_trim else None,
            "trim_valid": self.trim_valid,
            "trim_invalid_reasons": list(self.trim_invalid_reasons),
            "solver_method": self.solver_method,
            "rate_derivative_convention": self.rate_derivative_convention,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StabilityDerivatives:
        ctrls = {}
        raw_ctrls = data.get("controls") or {}
        if isinstance(raw_ctrls, dict):
            for k, v in raw_ctrls.items():
                if isinstance(v, dict):
                    ctrls[k] = ControlEffectiveness.from_dict(v)

        trim_data = data.get("elevator_trim")
        trim_obj = ElevatorTrim.from_dict(trim_data) if isinstance(trim_data, dict) else None

        return cls(
            c_L_alpha_rad=float(data.get("c_L_alpha_rad", 0.0)),
            c_L_alpha_deg=float(data.get("c_L_alpha_deg", 0.0)),
            c_D_alpha_rad=float(data.get("c_D_alpha_rad", 0.0)),
            c_D_alpha_deg=float(data.get("c_D_alpha_deg", 0.0)),
            c_m_alpha_rad=float(data.get("c_m_alpha_rad", 0.0)),
            c_m_alpha_deg=float(data.get("c_m_alpha_deg", 0.0)),
            c_L_q=float(data.get("c_L_q", 0.0)),
            c_m_q=float(data.get("c_m_q", 0.0)),
            c_Y_beta_rad=float(data.get("c_Y_beta_rad", 0.0)),
            c_Y_beta_deg=float(data.get("c_Y_beta_deg", 0.0)),
            c_l_beta_rad=float(data.get("c_l_beta_rad", 0.0)),
            c_l_beta_deg=float(data.get("c_l_beta_deg", 0.0)),
            c_n_beta_rad=float(data.get("c_n_beta_rad", 0.0)),
            c_n_beta_deg=float(data.get("c_n_beta_deg", 0.0)),
            c_l_p=float(data.get("c_l_p", 0.0)),
            c_n_p=float(data.get("c_n_p", 0.0)),
            c_l_r=float(data.get("c_l_r", 0.0)),
            c_n_r=float(data.get("c_n_r", 0.0)),
            x_cg=float(data.get("x_cg", 0.0)),
            x_np=float(data.get("x_np", 0.0)),
            static_margin=float(data.get("static_margin", 0.0)),
            is_pitch_stable=bool(data.get("is_pitch_stable", True)),
            is_pitch_damped=bool(data.get("is_pitch_damped", True)),
            is_roll_stable=bool(data.get("is_roll_stable", True)),
            is_roll_damped=bool(data.get("is_roll_damped", True)),
            is_yaw_stable=bool(data.get("is_yaw_stable", True)),
            is_yaw_damped=bool(data.get("is_yaw_damped", True)),
            controls=ctrls,
            elevator_trim=trim_obj,
            trim_valid=bool(data.get("trim_valid", trim_obj is not None)),
            trim_invalid_reasons=tuple(
                str(reason) for reason in (data.get("trim_invalid_reasons") or [])
            ),
            solver_method=str(data.get("solver_method", "unknown")),
            rate_derivative_convention=str(
                data.get("rate_derivative_convention", "normalized_body_rates")
            ),
        )
