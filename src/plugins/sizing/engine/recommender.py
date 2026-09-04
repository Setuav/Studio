"""Propulsion matching and recommendation engine using PyThrust catalog databases."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MotorRecommendation:
    """A recommended motor from catalog matching sizing power requirements."""

    id: str
    manufacturer: str
    name: str
    kv: float
    max_power_w: float
    weight_g: float
    max_current_a: float
    internal_resistance_ohm: float
    power_match_score: float  # Difference percentage from target power


@dataclass(frozen=True)
class PropellerRecommendation:
    """A recommended propeller from catalog matching sizing requirements."""

    id: str
    manufacturer: str
    model: str
    diameter_in: float
    pitch_in: float
    blade_count: int
    pitch_to_diameter: float


def recommend_motors(
    target_power_w: float,
    tolerance_pct: float = 35.0,
    limit: int = 8,
) -> list[MotorRecommendation]:
    """Query PyThrust motor database and recommend motors matching target power."""
    p_target = max(float(target_power_w), 10.0)
    p_min = p_target * (1.0 - tolerance_pct / 100.0)
    p_max = p_target * (1.0 + tolerance_pct / 100.0)

    recommendations: list[MotorRecommendation] = []

    try:
        from plugins.electrical_propulsion.database import get_motor_database

        db = get_motor_database()
        motors: list[Any] = list(getattr(db, "motors", {}).values()) if db else []

        for m in motors:
            p_motor = getattr(m, "max_power", None)
            if p_motor is None or p_motor <= 0:
                continue

            if p_min <= p_motor <= p_max:
                diff = abs(p_motor - p_target) / p_target
                recommendations.append(
                    MotorRecommendation(
                        id=str(getattr(m, "id", m.name)),
                        manufacturer=str(getattr(m, "manufacturer", "")),
                        name=str(getattr(m, "name", "Unnamed Motor")),
                        kv=float(getattr(m, "kv", 0.0) or 0.0),
                        max_power_w=float(p_motor),
                        weight_g=float(getattr(m, "weight_g", 0.0) or 0.0),
                        max_current_a=float(getattr(m, "max_current", 0.0) or 0.0),
                        internal_resistance_ohm=float(getattr(m, "resistance", 0.0) or 0.0),
                        power_match_score=diff,
                    )
                )
    except Exception as exc:
        logger.debug("Could not query PyThrust motor database: %s", exc)

    # Sort by closeness to target power
    recommendations.sort(key=lambda r: r.power_match_score)

    # If database had no matches or was unavailable, provide realistic representative models
    if not recommendations:
        for factor in (0.9, 1.0, 1.15):
            p = round(p_target * factor)
            # Standard Kv rule: Kv approx 5000 / sqrt(P)
            kv = round(max(300.0, 5000.0 / math.sqrt(max(p, 10.0))))
            weight = round(p / 2.5)  # ~2.5 W/g
            recommendations.append(
                MotorRecommendation(
                    id=f"generic_brushless_{p}w",
                    manufacturer="Generic UAV",
                    name=f"Brushless {p}W (Kv {kv})",
                    kv=float(kv),
                    max_power_w=float(p),
                    weight_g=float(weight),
                    max_current_a=float(round(p / 14.8, 1)),
                    internal_resistance_ohm=0.045,
                    power_match_score=abs(p - p_target) / p_target,
                )
            )

    return recommendations[:limit]


def recommend_propellers(
    target_power_w: float,
    v_cruise_mps: float,
    limit: int = 8,
) -> list[PropellerRecommendation]:
    """Query PyThrust propeller database and recommend propellers matching cruise airspeed and power."""
    # Approximate rule of thumb for diameter D (inches) from shaft power P (W):
    # D_in approx 0.5 * P^(0.45)
    p_w = max(float(target_power_w), 10.0)
    target_diameter_in = max(5.0, min(32.0, 0.52 * (p_w**0.44)))
    recommendations: list[PropellerRecommendation] = []

    try:
        from plugins.electrical_propulsion.database import get_propeller_database

        db = get_propeller_database()
        propellers: list[Any] = list(getattr(db, "propellers", {}).values()) if db else []

        for prop in propellers:
            meta = getattr(prop, "metadata", None)
            if not meta:
                continue
            d_in = getattr(meta, "diameter_in", None)
            p_in = getattr(meta, "pitch_in", None)
            if d_in is None or p_in is None or d_in <= 0 or p_in <= 0:
                continue

            pd = p_in / d_in
            if abs(d_in - target_diameter_in) <= 2.5 and 0.4 <= pd <= 0.85:
                recommendations.append(
                    PropellerRecommendation(
                        id=str(getattr(prop, "id", f"prop_{d_in}x{p_in}")),
                        manufacturer=str(getattr(meta, "manufacturer", "APC")),
                        model=str(getattr(meta, "model", f"{d_in}x{p_in}")),
                        diameter_in=float(d_in),
                        pitch_in=float(p_in),
                        blade_count=int(getattr(meta, "blade_count", 2) or 2),
                        pitch_to_diameter=pd,
                    )
                )
    except Exception as exc:
        logger.debug("Could not query PyThrust propeller database: %s", exc)

    # Sort by closeness to target diameter
    recommendations.sort(key=lambda p: abs(p.diameter_in - target_diameter_in))

    # Synthetic fallback if catalog empty
    if not recommendations:
        base_d = round(target_diameter_in)
        for d in (base_d - 1, base_d, base_d + 1):
            if d < 4:
                continue
            for p in (round(d * 0.5), round(d * 0.65)):
                recommendations.append(
                    PropellerRecommendation(
                        id=f"apc_thin_electric_{d}x{p}",
                        manufacturer="APC Style",
                        model=f"{d}x{p} Thin Electric",
                        diameter_in=float(d),
                        pitch_in=float(p),
                        blade_count=2,
                        pitch_to_diameter=float(p) / float(d),
                    )
                )

    return recommendations[:limit]


__all__ = [
    "MotorRecommendation",
    "PropellerRecommendation",
    "recommend_motors",
    "recommend_propellers",
]
