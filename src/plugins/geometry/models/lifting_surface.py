"""Lifting surface (Wing, Tail, Fin) domain entity model."""

from __future__ import annotations

from typing import Any

from setuav_studio.model import Component

from ..engine.airfoil import airfoil_label
from ..engine.lifting_surface_layout import layout_planform


class LiftingSurfaceProfileModel:
    """Domain model for one profile station of a lifting surface."""

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
        rotation = self._data.get("rotation")
        return float(rotation.get("y", 0.0)) if isinstance(rotation, dict) else 0.0

    @property
    def airfoil(self) -> str:
        return airfoil_label(self._data.get("airfoil"))

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
        raise AttributeError(f"'LiftingSurfaceProfileModel' object has no attribute '{name}'")


class LiftingSurfaceSectionModel:
    """Domain model for one section of a lifting surface, between its root and tip profile."""

    def __init__(self, data: dict[str, Any], root: dict[str, Any], index: int = 0) -> None:
        self._data = data
        self._root = root
        self._index = index

    @property
    def span(self) -> float:
        return float(self._data["span"])

    @property
    def sweep(self) -> float:
        return float(self._data["sweep"])

    @property
    def dihedral(self) -> float:
        return float(self._data["dihedral"])

    @property
    def twist(self) -> float:
        return float(self._data["twist"])

    @property
    def root_chord(self) -> float:
        return float(self._root["chord"])

    @property
    def tip_chord(self) -> float:
        return float(self._data["tip"]["chord"])

    @property
    def root_airfoil(self) -> str:
        return airfoil_label(self._root["airfoil"])

    @property
    def tip_airfoil(self) -> str:
        return airfoil_label(self._data["tip"]["airfoil"])

    def get_exposed_properties(self) -> dict[str, Any]:
        return {
            "span": self.span,
            "sweep": self.sweep,
            "dihedral": self.dihedral,
            "twist": self.twist,
            "root_chord": self.root_chord,
            "tip_chord": self.tip_chord,
            "root_airfoil": self.root_airfoil,
            "tip_airfoil": self.tip_airfoil,
        }


class LiftingSurfaceModel(Component):
    """Domain model for LiftingSurface (Wing / Tail / Fin) with live geometric properties and station sections."""

    @property
    def geometry(self) -> dict[str, Any]:
        return self.parameters.setdefault("geometry", {})

    @property
    def profiles(self) -> list[dict[str, Any]]:
        geom = self.geometry
        return geom.get("profiles") or []

    @property
    def profile_models(self) -> list[LiftingSurfaceProfileModel]:
        """Typed domain models of the profile stations, from root to tip."""
        return [
            LiftingSurfaceProfileModel(p, i)
            for i, p in enumerate(self.profiles)
            if isinstance(p, dict)
        ]

    @property
    def sections(self) -> list[LiftingSurfaceSectionModel]:
        """Typed domain models of the sections, from root to tip."""
        root = self.geometry["root"]
        sections = self.geometry["sections"]
        return [
            LiftingSurfaceSectionModel(section, root if i == 0 else sections[i - 1]["tip"], i)
            for i, section in enumerate(sections)
        ]

    @property
    def root_profile(self) -> LiftingSurfaceProfileModel | None:
        profiles = self.profile_models
        return profiles[0] if profiles else None

    @property
    def tip_profile(self) -> LiftingSurfaceProfileModel | None:
        profiles = self.profile_models
        return profiles[-1] if profiles else None

    @property
    def mirror(self) -> bool:
        return bool(self.geometry.get("mirror", False))

    @property
    def sweep_location(self) -> float:
        return float(self.geometry.get("sweep_location", 0.25))

    @property
    def planform_metrics(self) -> dict[str, float]:
        """The planform values the editor's Planform table shows, area in dm²."""
        geometry = self.geometry
        if not isinstance(geometry.get("root"), dict) or not geometry.get("sections"):
            return {}
        return layout_planform(geometry, symmetric=self.mirror, y_offset=self.y)

    @property
    def planform_area(self) -> float:
        return float(self.planform_metrics.get("area", 0.0))

    @property
    def area(self) -> float:
        return self.planform_area

    @property
    def span(self) -> float:
        return float(self.planform_metrics.get("span", 0.0))

    @property
    def wingspan(self) -> float:
        return self.span

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
        return float(self.planform_metrics.get("ave_chord", 0.0))

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
        return float(self.planform_metrics.get("twist", 0.0))

    @property
    def washout(self) -> float:
        return self.twist

    def get_exposed_properties(self) -> dict[str, Any]:
        props = super().get_exposed_properties()
        props.update(
            {
                "planform_area": self.planform_area,
                "span": self.span,
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
        for prefix, models in (("profile", self.profile_models), ("section", self.sections)):
            for i, model in enumerate(models):
                for sp_k, sp_v in model.get_exposed_properties().items():
                    props[f"{prefix}_{i}_{sp_k}"] = sp_v
        return props

    def __getattr__(self, name: str) -> Any:
        # Indexed access: profile_0, profile_1, ... and section_0, section_1, ...
        prefix, _, index = name.partition("_")
        if prefix in ("profile", "section") and index.isdigit():
            models = self.profile_models if prefix == "profile" else self.sections
            if int(index) < len(models):
                return models[int(index)]
        return super().__getattr__(name)
