"""Lifting surface (Wing, Tail, Fin) domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.component_model import BaseComponentModel
from setuav_studio.plugins.geometry.engine.wing_planform_engine import compute_planform_metrics


class WingSectionModel:
    """Domain model for a single Wing station / profile section."""

    def __init__(self, data: dict[str, Any], index: int = 0) -> None:
        self._data = data
        self._index = index

    @property
    def chord(self) -> float:
        return float(self._data.get("chord", 0.0))

    @property
    def position(self) -> dict[str, float]:
        return self._data.setdefault("position", {})

    @property
    def x(self) -> float:
        return float(self.position.get("x", 0.0))

    @property
    def y(self) -> float:
        return float(self.position.get("y", 0.0))

    @property
    def z(self) -> float:
        return float(self.position.get("z", 0.0))

    @property
    def twist(self) -> float:
        rot = self._data.get("rotation", {})
        if isinstance(rot, dict):
            return float(rot.get("x", self._data.get("twist", 0.0)))
        return float(self._data.get("twist", 0.0))

    @property
    def airfoil(self) -> str:
        af = self._data.get("airfoil")
        if isinstance(af, dict):
            return str(af.get("code") or af.get("name") or "naca0012")
        return str(af or "naca0012")

    def get_exposed_properties(self) -> dict[str, Any]:
        return {
            "chord": self.chord,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "twist": self.twist,
            "airfoil": self.airfoil,
        }

    def __getattr__(self, name: str) -> Any:
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"'WingSectionModel' object has no attribute '{name}'")


class LiftingSurfaceModel(BaseComponentModel):
    """Domain model for LiftingSurface (Wing / Tail / Fin) with live geometric properties and station sections."""

    @property
    def geometry(self) -> dict[str, Any]:
        return self.parameters.setdefault("geometry", {})

    @property
    def profiles(self) -> list[dict[str, Any]]:
        geom = self.geometry
        return geom.get("profiles") or geom.get("sections") or []

    @property
    def sections(self) -> list[WingSectionModel]:
        """List of typed domain models for each station section."""
        return [WingSectionModel(p, i) for i, p in enumerate(self.profiles) if isinstance(p, dict)]

    @property
    def root_section(self) -> WingSectionModel | None:
        secs = self.sections
        return secs[0] if secs else None

    @property
    def tip_section(self) -> WingSectionModel | None:
        secs = self.sections
        return secs[-1] if secs else None

    @property
    def mirror(self) -> bool:
        return bool(self.geometry.get("mirror", self.geometry.get("symmetric", False)))

    @property
    def symmetric(self) -> bool:
        return self.mirror

    @property
    def sweep_location(self) -> float:
        return float(self.geometry.get("sweep_location", 0.25))

    @property
    def planform_metrics(self) -> dict[str, float]:
        """Compute closed-loop planform metrics from station profile geometry."""
        profiles = self.profiles
        if not isinstance(profiles, list) or len(profiles) < 2:
            return {}
        try:
            return compute_planform_metrics(
                profiles,
                sweep_loc=self.sweep_location,
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
        props.update(
            {
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
            }
        )
        for i, sec in enumerate(self.sections):
            for sp_k, sp_v in sec.get_exposed_properties().items():
                props[f"section_{i}_{sp_k}"] = sp_v
        return props

    def __getattr__(self, name: str) -> Any:
        # Dynamic section access: section_0, section_1, etc.
        if name.startswith("section_"):
            try:
                idx = int(name.split("_", 1)[1])
                secs = self.sections
                if 0 <= idx < len(secs):
                    return secs[idx]
            except ValueError:
                pass
        return super().__getattr__(name)
