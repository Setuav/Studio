"""Data models for aircraft concept presets and airframe sizing configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlanformMetrics:
    """Derived aerodynamic and planform metrics calculated from geometric constants."""

    wing_area_m2: float
    aspect_ratio: float
    mean_aerodynamic_chord_mm: float
    taper_ratio: float
    semi_span_mm: float
    tail_projected_area_m2: float
    tail_area_ratio_percent: float


@dataclass
class ConceptPreset:
    """Definition and design constants for an aircraft archetype preset."""

    id: str
    title: str
    image_filename: str

    # Primary Wing Constants
    wingspan_mm: float
    wing_root_chord_mm: float
    wing_tip_chord_mm: float
    wing_sweep_deg: float = 0.0
    wing_dihedral_deg: float = 0.0
    wing_airfoil: str = "NACA 2412"
    wing_position: str = "High-Wing"  # "High-Wing", "Mid-Wing", "Low-Wing"

    # Primary Fuselage Constants
    fuselage_length_mm: float = 850.0
    fuselage_diameter_mm: float = 130.0
    nose_length_mm: float = 220.0
    tail_length_mm: float = 450.0
    fuselage_style: str = "Pod & Boom"

    # Primary Empennage / Tail Constants
    tail_type: str = "Conventional"  # "V-Tail", "Inverted V-Tail", "Conventional", "T-Tail", "Twin Boom", "Winglets Only"
    tail_span_mm: float = 380.0
    tail_root_chord_mm: float = 120.0
    tail_tip_chord_mm: float = 80.0
    tail_v_angle_deg: float = 0.0
    tail_height_mm: float = 160.0
    tail_arm_mm: float = 520.0
    tail_airfoil: str = "NACA 0012"

    # Propulsion Architecture
    propulsion_layout: str = "Tractor"  # "Tractor", "Pusher", "Twin"

    def compute_metrics(self) -> PlanformMetrics:
        """Derive standard aerodynamic planform metrics from wing and tail dimensions."""
        b_m = self.wingspan_mm / 1000.0
        cr_m = self.wing_root_chord_mm / 1000.0
        ct_m = self.wing_tip_chord_mm / 1000.0

        s_wing = b_m * (cr_m + ct_m) / 2.0
        ar = (b_m ** 2) / max(s_wing, 1e-4)
        taper = ct_m / max(cr_m, 1e-4)
        mac_m = (2.0 / 3.0) * cr_m * (1.0 + taper + taper ** 2) / max(1.0 + taper, 1e-4)

        tail_b_m = self.tail_span_mm / 1000.0
        tail_cr_m = self.tail_root_chord_mm / 1000.0
        tail_ct_m = self.tail_tip_chord_mm / 1000.0
        s_tail = tail_b_m * (tail_cr_m + tail_ct_m) / 2.0
        tail_ratio = (s_tail / max(s_wing, 1e-4)) * 100.0

        return PlanformMetrics(
            wing_area_m2=s_wing,
            aspect_ratio=ar,
            mean_aerodynamic_chord_mm=mac_m * 1000.0,
            taper_ratio=taper,
            semi_span_mm=self.wingspan_mm / 2.0,
            tail_projected_area_m2=s_tail,
            tail_area_ratio_percent=tail_ratio,
        )

    def to_dict(self) -> dict[str, Any]:
        """Export all configuration constants as a dictionary."""
        return {
            "concept_id": self.id,
            "concept_title": self.title,
            "image_filename": self.image_filename,
            "wingspan_mm": self.wingspan_mm,
            "wing_root_chord_mm": self.wing_root_chord_mm,
            "wing_tip_chord_mm": self.wing_tip_chord_mm,
            "wing_sweep_deg": self.wing_sweep_deg,
            "wing_dihedral_deg": self.wing_dihedral_deg,
            "wing_airfoil": self.wing_airfoil,
            "wing_position": self.wing_position,
            "fuselage_length_mm": self.fuselage_length_mm,
            "fuselage_diameter_mm": self.fuselage_diameter_mm,
            "nose_length_mm": self.nose_length_mm,
            "tail_length_mm": self.tail_length_mm,
            "fuselage_style": self.fuselage_style,
            "tail_type": self.tail_type,
            "tail_span_mm": self.tail_span_mm,
            "tail_root_chord_mm": self.tail_root_chord_mm,
            "tail_tip_chord_mm": self.tail_tip_chord_mm,
            "tail_v_angle_deg": self.tail_v_angle_deg,
            "tail_height_mm": self.tail_height_mm,
            "tail_arm_mm": self.tail_arm_mm,
            "tail_airfoil": self.tail_airfoil,
            "propulsion_layout": self.propulsion_layout,
        }


__all__ = ["ConceptPreset", "PlanformMetrics"]
