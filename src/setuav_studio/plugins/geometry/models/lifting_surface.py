"""Lifting surface (Wing, Tail, Fin) domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.component_model import BaseComponentModel
from setuav_studio.plugins.geometry.engine.wing_planform_engine import compute_planform_metrics


class LiftingSurfaceModel(BaseComponentModel):
    """Domain model for LiftingSurface (Wing / Tail / Fin) with live geometric properties."""

    @property
    def geometry(self) -> dict[str, Any]:
        return self.parameters.setdefault("geometry", {})

    @property
    def profiles(self) -> list[dict[str, Any]]:
        geom = self.geometry
        return geom.get("profiles") or geom.get("sections") or []

    @property
    def mirror(self) -> bool:
        return bool(self.geometry.get("mirror", self.geometry.get("symmetric", True)))

    @property
    def symmetric(self) -> bool:
        return self.mirror

    @property
    def planform_metrics(self) -> dict[str, float]:
        """Compute closed-loop planform metrics from station profile geometry."""
        profiles = self.profiles
        if not isinstance(profiles, list) or len(profiles) < 2:
            return {}
        try:
            return compute_planform_metrics(
                profiles,
                sweep_loc=0.25,
                symmetric=self.symmetric,
                y_offset=self.y,
            )
        except Exception:
            return {}

    @property
    def planform_area(self) -> float:
        return float(self.planform_metrics.get("area", 0.0))

    @property
    def area(self) -> float:
        return self.planform_area

    @property
    def wingspan(self) -> float:
        return float(self.planform_metrics.get("span", 0.0))

    @property
    def span(self) -> float:
        return self.wingspan

    @property
    def aspect_ratio(self) -> float:
        return float(self.planform_metrics.get("aspect_ratio", 0.0))

    @property
    def ar(self) -> float:
        return self.aspect_ratio

    @property
    def taper_ratio(self) -> float:
        return float(self.planform_metrics.get("taper_ratio", 0.0))

    @property
    def taper(self) -> float:
        return self.taper_ratio

    @property
    def root_chord(self) -> float:
        return float(self.planform_metrics.get("root_chord", 0.0))

    @property
    def tip_chord(self) -> float:
        return float(self.planform_metrics.get("tip_chord", 0.0))

    @property
    def average_chord(self) -> float:
        if "average_chord" in self.planform_metrics:
            return float(self.planform_metrics["average_chord"])
        span_val = max(self.wingspan, 1e-6)
        return self.planform_area / span_val

    @property
    def mac(self) -> float:
        return float(self.planform_metrics.get("mac", 0.0))

    @property
    def sweep_angle(self) -> float:
        return float(self.planform_metrics.get("sweep", 0.0))

    @property
    def dihedral_angle(self) -> float:
        return float(self.planform_metrics.get("dihedral", 0.0))

    @property
    def twist(self) -> float:
        return float(self.planform_metrics.get("washout", 0.0))

    @property
    def washout(self) -> float:
        return self.twist

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update({
            "planform_area": self.planform_area,
            "wingspan": self.wingspan,
            "aspect_ratio": self.aspect_ratio,
            "taper_ratio": self.taper_ratio,
            "root_chord": self.root_chord,
            "tip_chord": self.tip_chord,
            "average_chord": self.average_chord,
            "mac": self.mac,
            "sweep_angle": self.sweep_angle,
            "dihedral_angle": self.dihedral_angle,
            "twist": self.twist,
        })
        return props
