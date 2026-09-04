"""Preliminary sizing computational engine package."""

from .aerodynamics import (
    AeroParameters,
    calculate_induced_drag_factor,
    calculate_oswald_raymer,
)
from .battery import (
    BatteryParameters,
    BatterySizingResult,
    size_battery_pack,
)
from .constraints import (
    ConstraintCurve,
    climb_thrust_to_weight,
    cruise_thrust_to_weight,
    max_wing_loading_landing,
    max_wing_loading_stall,
    service_ceiling_thrust_to_weight,
    takeoff_thrust_to_weight,
    turn_thrust_to_weight,
)
from .converters import (
    WATTS_PER_HORSEPOWER,
    hp_to_watts,
    required_shaft_power_watts,
    tw_to_power_loading_w_kg,
    tw_to_pw,
    watts_to_hp,
)
from .recommender import (
    MotorRecommendation,
    PropellerRecommendation,
    recommend_motors,
    recommend_propellers,
)
from .solver import (
    MatchingChartAnalysis,
    compute_matching_chart,
    solve_sizing_for_mission,
)
from .weight import (
    MissionProfile,
    SizingResult,
    WeightBreakdown,
    converge_sizing,
    estimate_airframe_mass_noth,
    estimate_propulsion_mass,
)

__all__ = [
    "WATTS_PER_HORSEPOWER",
    "AeroParameters",
    "BatteryParameters",
    "BatterySizingResult",
    "ConstraintCurve",
    "MatchingChartAnalysis",
    "MissionProfile",
    "MotorRecommendation",
    "PropellerRecommendation",
    "SizingResult",
    "WeightBreakdown",
    "calculate_induced_drag_factor",
    "calculate_oswald_raymer",
    "climb_thrust_to_weight",
    "compute_matching_chart",
    "converge_sizing",
    "cruise_thrust_to_weight",
    "estimate_airframe_mass_noth",
    "estimate_propulsion_mass",
    "hp_to_watts",
    "max_wing_loading_landing",
    "max_wing_loading_stall",
    "recommend_motors",
    "recommend_propellers",
    "required_shaft_power_watts",
    "service_ceiling_thrust_to_weight",
    "size_battery_pack",
    "solve_sizing_for_mission",
    "takeoff_thrust_to_weight",
    "turn_thrust_to_weight",
    "tw_to_power_loading_w_kg",
    "tw_to_pw",
    "watts_to_hp",
]
