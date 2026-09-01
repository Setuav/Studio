"""AeroSandbox lifting-surface and control-surface conversion."""

from __future__ import annotations

import math
from copy import deepcopy
from itertools import pairwise
from typing import TYPE_CHECKING, Any

from .base import ControlSurfaceType, FlightCondition

if TYPE_CHECKING:
    asb: Any = None
    np: Any = None
else:
    try:
        import aerosandbox as asb
        import aerosandbox.numpy as np
    except ImportError:
        asb = None
        np = None


class AeroSandboxGeometryMixin:
    """Translate Setuav lifting surfaces into AeroSandbox geometry."""

    if TYPE_CHECKING:

        def _resolve_world_transform(
            self,
            comp: dict[str, Any],
            comp_by_id: dict[str, dict[str, Any]],
        ) -> tuple[Any, Any]: ...

        def _local_transform(self, comp: dict[str, Any]) -> tuple[Any, Any]: ...

        def _resolve_airfoil(self, airfoil_spec: Any, shaping: Any = None) -> Any: ...

    def _resolve_parent_transform(
        self,
        comp: dict[str, Any],
        comp_by_id: dict[str, dict[str, Any]],
    ) -> tuple[Any, Any]:
        """Return the world frame of a component's parent (or the aircraft frame)."""
        transform = comp.get("transform")
        transform = transform if isinstance(transform, dict) else {}
        parent_id = comp.get("parent") or comp.get("attach_to") or transform.get("parent")
        if parent_id and str(parent_id) in comp_by_id:
            return self._resolve_world_transform(comp_by_id[str(parent_id)], comp_by_id)
        return np.zeros(3), np.eye(3)

    @staticmethod
    def _lifting_surface_geometry(
        comp: dict[str, Any],
    ) -> tuple[dict[str, Any], list[Any] | None]:
        parameters = comp.get("parameters")
        params = parameters if isinstance(parameters, dict) else {}
        geometry_value = params.get("geometry")
        geometry = geometry_value if isinstance(geometry_value, dict) else {}
        profiles = geometry.get("profiles")
        if not isinstance(profiles, list) or len(profiles) < 2:
            return geometry, None
        return geometry, profiles

    def _lifting_surface_frames(
        self,
        comp: dict[str, Any],
        comp_by_id: dict[str, dict[str, Any]] | None,
    ) -> dict[str, Any]:
        if comp_by_id:
            parent_pos, parent_rot = self._resolve_parent_transform(comp, comp_by_id)
        else:
            parent_pos, parent_rot = np.zeros(3), np.eye(3)
        local_pos, local_rot = self._local_transform(comp)
        mirror = np.diag([1.0, -1.0, 1.0])
        return {
            "right_pos": parent_pos + parent_rot @ local_pos,
            "right_rot": parent_rot @ local_rot,
            "left_pos": parent_pos + parent_rot @ (mirror @ local_pos),
            "left_rot": parent_rot @ mirror @ local_rot,
        }

    def _lifting_surface_stations(
        self,
        profiles: list[Any],
        geometry: dict[str, Any],
        frames: dict[str, Any],
    ) -> list[dict[str, Any]]:
        stations: list[dict[str, Any]] = []
        for profile in profiles:
            if isinstance(profile, dict):
                stations.append(self._lifting_surface_station(profile, geometry, frames))
        return stations

    def _lifting_surface_station(
        self,
        profile: dict[str, Any],
        geometry: dict[str, Any],
        frames: dict[str, Any],
    ) -> dict[str, Any]:
        position = profile.get("position")
        profile_position = position if isinstance(position, dict) else {}
        rotation = profile.get("rotation")
        profile_rotation = rotation if isinstance(rotation, dict) else {}
        raw_xyz = np.array(
            [
                float(profile_position.get("x", 0.0)) / 1000.0,
                float(profile_position.get("y", 0.0)) / 1000.0,
                float(profile_position.get("z", 0.0)) / 1000.0,
            ]
        )
        profile_pitch = self._profile_pitch(profile, profile_rotation)
        attach_pitch = np.degrees(np.arcsin(-np.clip(frames["right_rot"][2, 0], -1.0, 1.0)))
        return {
            "local_y": float(profile_position.get("y", 0.0)),
            "xyz_le": frames["right_rot"] @ raw_xyz + frames["right_pos"],
            "xyz_le_left": frames["left_rot"] @ raw_xyz + frames["left_pos"],
            "chord": max(float(profile.get("chord", 100.0)) / 1000.0, 1e-4),
            "twist": profile_pitch + attach_pitch,
            "airfoil": self._resolve_airfoil(
                profile.get("airfoil"), shaping=geometry.get("airfoil_shaping")
            ),
        }

    @staticmethod
    def _profile_pitch(profile: dict[str, Any], rotation: dict[str, Any]) -> float:
        if "twist" in profile:
            return float(profile.get("twist") or 0.0)
        if "pitch" in rotation:
            return float(rotation.get("pitch") or 0.0)
        return float(rotation.get("y") or 0.0)

    @staticmethod
    def _assign_span_coordinates(stations: list[dict[str, Any]]) -> float:
        y_start = stations[0]["local_y"]
        y_delta = stations[-1]["local_y"] - y_start
        if abs(y_delta) > 1e-9:
            total_span = max(abs(y_delta) / 1000.0, 1e-4)
            for station in stations:
                station["eta"] = float(np.clip((station["local_y"] - y_start) / y_delta, 0.0, 1.0))
            return total_span
        total_span = max(
            float(np.linalg.norm(stations[-1]["xyz_le"] - stations[0]["xyz_le"])),
            1e-4,
        )
        for index, station in enumerate(stations):
            station["eta"] = float(index / max(len(stations) - 1, 1))
        return total_span

    def _collect_control_surfaces(
        self,
        comp: dict[str, Any],
        geometry: dict[str, Any],
        comp_by_id: dict[str, dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        controls = self._inline_control_surfaces(geometry)
        if comp_by_id:
            controls.extend(self._child_control_surfaces(str(comp.get("id") or ""), comp_by_id))
        if not controls:
            controls.extend(self._tag_control_surfaces(comp))
        return controls

    @staticmethod
    def _inline_control_surfaces(geometry: dict[str, Any]) -> list[dict[str, Any]]:
        values = geometry.get("control_surfaces")
        if not isinstance(values, list):
            return []
        return [value for value in values if isinstance(value, dict)]

    @staticmethod
    def _child_control_surfaces(
        component_id: str, comp_by_id: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        controls: list[dict[str, Any]] = []
        for other in comp_by_id.values():
            if (
                not isinstance(other, dict)
                or other.get("type") != "org.setuav.core:control-surface"
            ):
                continue
            if str(AeroSandboxGeometryMixin._component_parent_id(other)) != component_id:
                continue
            parameters = other.get("parameters")
            geometry = parameters.get("geometry", {}) if isinstance(parameters, dict) else {}
            control = deepcopy(geometry)
            control.setdefault("tag", other.get("name") or other.get("id"))
            control.setdefault("id", other.get("id"))
            control["_child_component"] = True
            controls.append(control)
        return controls

    @staticmethod
    def _component_parent_id(component: dict[str, Any]) -> Any:
        transform = component.get("transform")
        transform_parent = transform.get("parent") if isinstance(transform, dict) else None
        return component.get("parent") or component.get("attach_to") or transform_parent

    @staticmethod
    def _tag_control_surfaces(comp: dict[str, Any]) -> list[dict[str, Any]]:
        parameters = comp.get("parameters")
        tags = parameters.get("tags", []) if isinstance(parameters, dict) else []
        normalized_tags = {str(tag).lower() for tag in tags}
        candidates = (
            "elevator",
            "rudder",
            "aileron",
            "flap",
            "elevon",
            "ruddervator",
            "vtail",
            "v-tail",
        )
        return [
            AeroSandboxGeometryMixin._tag_control_surface(candidate)
            for candidate in candidates
            if candidate in normalized_tags
        ]

    @staticmethod
    def _tag_control_surface(tag: str) -> dict[str, Any]:
        is_ruddervator = tag in ("ruddervator", "vtail", "v-tail")
        control_type = "ruddervator" if is_ruddervator else tag
        return {
            "tag": control_type,
            "type": control_type,
            "eta_start": 0.0,
            "eta_end": 1.0,
            "chord_fraction": 0.35,
            "symmetry_mode": "antisymmetric" if tag in ("aileron", "elevon") else "symmetric",
        }

    def _parse_control_surfaces(
        self,
        controls: list[dict[str, Any]],
        condition: FlightCondition | None,
        total_span: float,
        stations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            self._parse_control_surface(control, condition, total_span, stations)
            for control in controls
        ]

    def _parse_control_surface(
        self,
        control: dict[str, Any],
        condition: FlightCondition | None,
        total_span: float,
        stations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        control_type = ControlSurfaceType.from_str(control.get("type")) or ControlSurfaceType.FLAP
        tag = str(
            control.get("tag") or control.get("name") or control.get("id") or control_type.value
        )
        control_id = str(control.get("id") or tag)
        inputs = self._control_inputs(condition, tag, control_id, control_type)
        symmetry_mode = str(control.get("symmetry_mode") or "auto").lower()
        delta_right, delta_left = self._surface_deflections(
            control_type,
            float(control.get("deflection", 0.0)),
            inputs,
            symmetry_mode,
        )
        eta_start, eta_end = self._control_span_range(control, total_span)
        chord_fraction = self._control_chord_fraction(control, eta_start, eta_end, stations)
        return {
            "tag": tag,
            "type": control_type.value,
            "symmetry_mode": symmetry_mode,
            "eta_start": eta_start,
            "eta_end": eta_end,
            "chord_fraction": chord_fraction,
            "delta_r": delta_right,
            "delta_l": delta_left,
            "include_left": symmetry_mode != "none",
        }

    @staticmethod
    def _control_inputs(
        condition: FlightCondition | None,
        tag: str,
        control_id: str,
        control_type: ControlSurfaceType,
    ) -> dict[str, float]:
        inputs = {"elevator": 0.0, "rudder": 0.0, "aileron": 0.0, "direct": 0.0}
        if not condition or not condition.control_deflections:
            return inputs
        direct_names = (tag.lower(), control_type.value, control_id.lower())
        for key, value in condition.control_deflections.items():
            normalized = key.strip().lower()
            if normalized in ("elevator", "rudder", "aileron"):
                inputs[normalized] = float(value)
            elif normalized in direct_names:
                inputs["direct"] = float(value)
        return inputs

    @classmethod
    def _surface_deflections(
        cls,
        control_type: ControlSurfaceType,
        base_deflection: float,
        inputs: dict[str, float],
        symmetry_mode: str,
    ) -> tuple[float, float]:
        direct = base_deflection + inputs["direct"]
        differential = control_type in (ControlSurfaceType.AILERON, ControlSurfaceType.ELEVON)
        right = direct
        left = cls._mirrored_control_command(direct, differential, symmetry_mode)
        if control_type == ControlSurfaceType.ELEVATOR:
            right += inputs["elevator"]
            left += cls._mirrored_control_command(inputs["elevator"], False, symmetry_mode)
        elif control_type == ControlSurfaceType.RUDDER:
            right += inputs["rudder"]
            left += cls._mirrored_control_command(inputs["rudder"], True, symmetry_mode)
        elif control_type == ControlSurfaceType.AILERON:
            right += inputs["aileron"]
            left += cls._mirrored_control_command(inputs["aileron"], True, symmetry_mode)
        elif control_type == ControlSurfaceType.ELEVON:
            right += inputs["elevator"] + inputs["aileron"]
            left += cls._mirrored_control_command(inputs["elevator"], False, symmetry_mode)
            left += cls._mirrored_control_command(inputs["aileron"], True, symmetry_mode)
        elif control_type == ControlSurfaceType.RUDDERVATOR:
            right += inputs["elevator"] + inputs["rudder"]
            left += cls._mirrored_control_command(inputs["elevator"], False, symmetry_mode)
            left += cls._mirrored_control_command(inputs["rudder"], True, symmetry_mode)
        return right, left

    @staticmethod
    def _mirrored_control_command(
        value: float, auto_antisymmetric: bool, symmetry_mode: str
    ) -> float:
        if symmetry_mode == "symmetric":
            return value
        if symmetry_mode in ("antisymmetric", "anti-symmetric"):
            return -value
        if symmetry_mode == "none":
            return 0.0
        return -value if auto_antisymmetric else value

    @staticmethod
    def _control_span_range(control: dict[str, Any], total_span: float) -> tuple[float, float]:
        if "eta_start" in control and "eta_end" in control:
            eta_start = float(np.clip(float(control["eta_start"]), 0.0, 1.0))
            eta_end = float(np.clip(float(control["eta_end"]), 0.0, 1.0))
        elif "span_start" in control and "span_end" in control:
            span_start = float(control["span_start"])
            span_end = float(control["span_end"])
            ratio_mode = str(control.get("span_mode") or "dimension").lower() == "ratio"
            if ratio_mode and abs(span_start) <= 1.0 and abs(span_end) <= 1.0:
                eta_start = float(np.clip(span_start, 0.0, 1.0))
                eta_end = float(np.clip(span_end, 0.0, 1.0))
            else:
                if abs(span_start) > 5.0 or abs(span_end) > 5.0:
                    span_start /= 1000.0
                    span_end /= 1000.0
                eta_start = float(np.clip(span_start / total_span, 0.0, 1.0))
                eta_end = float(np.clip(span_end / total_span, 0.0, 1.0))
        else:
            eta_start, eta_end = 0.0, 1.0
        return (eta_end, eta_start) if eta_start > eta_end else (eta_start, eta_end)

    def _control_chord_fraction(
        self,
        control: dict[str, Any],
        eta_start: float,
        eta_end: float,
        stations: list[dict[str, Any]],
    ) -> float:
        fraction = float(control.get("chord_fraction", 0.25))
        if control.get("chord_mode") != "dimension" or "chord" not in control:
            return float(np.clip(fraction, 0.05, 0.95))
        chord = float(control["chord"])
        if chord > 5.0:
            chord /= 1000.0
        mid_chord = self._chord_at_eta(stations, 0.5 * (eta_start + eta_end))
        return float(np.clip(chord / max(mid_chord, 0.01), 0.05, 0.95))

    @staticmethod
    def _chord_at_eta(stations: list[dict[str, Any]], eta: float) -> float:
        for start, end in pairwise(stations):
            if start["eta"] <= eta <= end["eta"]:
                fraction = float(
                    np.clip(
                        (eta - start["eta"]) / max(end["eta"] - start["eta"], 1e-9),
                        0.0,
                        1.0,
                    )
                )
                return (1.0 - fraction) * start["chord"] + fraction * end["chord"]
        return float(stations[0]["chord"])

    @staticmethod
    def _station_breakpoints(
        stations: list[dict[str, Any]], controls: list[dict[str, Any]]
    ) -> list[float]:
        values = {round(station["eta"], 4) for station in stations}
        for control in controls:
            values.add(round(control["eta_start"], 4))
            values.add(round(control["eta_end"], 4))
        return sorted(values)

    @staticmethod
    def _interpolate_station(
        stations: list[dict[str, Any]], eta: float, side: str
    ) -> dict[str, Any]:
        xyz_key = "xyz_le_left" if side == "left" else "xyz_le"
        for start, end in pairwise(stations):
            in_interval = start["eta"] <= eta <= end["eta"]
            near_boundary = math.isclose(eta, start["eta"], abs_tol=1e-4) or math.isclose(
                eta, end["eta"], abs_tol=1e-4
            )
            if in_interval or near_boundary:
                fraction = float(
                    np.clip(
                        (eta - start["eta"]) / max(end["eta"] - start["eta"], 1e-6),
                        0.0,
                        1.0,
                    )
                )
                return {
                    "xyz_le": (1.0 - fraction) * start[xyz_key] + fraction * end[xyz_key],
                    "chord": (1.0 - fraction) * start["chord"] + fraction * end["chord"],
                    "twist": (1.0 - fraction) * start["twist"] + fraction * end["twist"],
                    "airfoil": start["airfoil"] if fraction < 0.5 else end["airfoil"],
                    "eta": eta,
                }
        last = stations[-1]
        return {
            "xyz_le": last[xyz_key],
            "chord": last["chord"],
            "twist": last["twist"],
            "airfoil": last["airfoil"],
            "eta": eta,
        }

    @staticmethod
    def _control_applies(control: dict[str, Any], eta: float, side: str) -> bool:
        in_span = control["eta_start"] <= eta <= control["eta_end"]
        return in_span and (side != "left" or control["include_left"])

    @staticmethod
    def _control_is_symmetric(control: dict[str, Any]) -> bool:
        mode = control["symmetry_mode"]
        if mode == "symmetric":
            return True
        if mode in ("antisymmetric", "anti-symmetric"):
            return False
        return control["type"] not in ("aileron", "elevon")

    def _controls_for_interval(
        self,
        controls: list[dict[str, Any]],
        eta_start: float,
        eta_end: float,
        side: str,
        control_encoding: str,
    ) -> list[Any]:
        eta_mid = 0.5 * (eta_start + eta_end)
        return [
            asb.ControlSurface(
                name=control["tag"],
                symmetric=self._control_is_symmetric(control),
                deflection=(
                    0.0
                    if control_encoding == "airfoil"
                    else float(control["delta_l"] if side == "left" else control["delta_r"])
                ),
                hinge_point=1.0 - float(control["chord_fraction"]),
            )
            for control in controls
            if self._control_applies(control, eta_mid, side)
        ]

    def _airfoil_for_station(
        self,
        station: dict[str, Any],
        controls: list[dict[str, Any]],
        side: str,
        control_encoding: str,
    ) -> Any:
        airfoil = station["airfoil"]
        if control_encoding != "airfoil":
            return airfoil
        for control in controls:
            if not self._control_applies(control, float(station["eta"]), side):
                continue
            deflection = float(control["delta_l"] if side == "left" else control["delta_r"])
            if abs(deflection) > 1e-4:
                airfoil = airfoil.add_control_surface(
                    deflection=deflection,
                    hinge_point_x=1.0 - float(control["chord_fraction"]),
                )
        return airfoil

    def _build_wing_xsecs(
        self,
        stations: list[dict[str, Any]],
        controls: list[dict[str, Any]],
        side: str,
        control_encoding: str,
        *,
        reverse: bool = False,
    ) -> list[Any]:
        ordered = list(reversed(stations)) if reverse else list(stations)
        sections: list[Any] = []
        for index, station in enumerate(ordered):
            interval_controls = []
            if index + 1 < len(ordered):
                interval_controls = self._controls_for_interval(
                    controls,
                    float(station["eta"]),
                    float(ordered[index + 1]["eta"]),
                    side,
                    control_encoding,
                )
            xyz = station["xyz_le"]
            sections.append(
                asb.WingXSec(
                    xyz_le=[float(xyz[0]), float(xyz[1]), float(xyz[2])],
                    chord=float(station["chord"]),
                    twist=float(station["twist"]),
                    airfoil=self._airfoil_for_station(station, controls, side, control_encoding),
                    control_surfaces=interval_controls,
                )
            )
        return sections

    def _convert_lifting_surface(
        self,
        comp: dict[str, Any],
        comp_by_id: dict[str, dict[str, Any]] | None = None,
        condition: FlightCondition | None = None,
        control_encoding: str = "native",
    ) -> Any:
        """Convert a single lifting surface and its control surfaces into AeroSandbox Wing(s)."""
        geometry, profiles = self._lifting_surface_geometry(comp)
        if profiles is None:
            return None
        mirror = bool(geometry.get("mirror", False) or comp.get("mirror", False))
        frames = self._lifting_surface_frames(comp, comp_by_id)
        station_raw = self._lifting_surface_stations(profiles, geometry, frames)
        if len(station_raw) < 2:
            return None

        total_span = self._assign_span_coordinates(station_raw)

        cs_list = self._collect_control_surfaces(comp, geometry, comp_by_id)

        parsed_cs = self._parse_control_surfaces(cs_list, condition, total_span, station_raw)

        breakpoints = self._station_breakpoints(station_raw, parsed_cs)
        right_stations = [
            self._interpolate_station(station_raw, eta, "right") for eta in breakpoints
        ]
        left_stations = [self._interpolate_station(station_raw, eta, "left") for eta in breakpoints]
        xsecs_right = self._build_wing_xsecs(right_stations, parsed_cs, "right", control_encoding)
        xsecs_left = self._build_wing_xsecs(
            left_stations, parsed_cs, "left", control_encoding, reverse=True
        )
        has_asymmetric_controls = any(
            not cs["include_left"] or abs(float(cs["delta_r"]) - float(cs["delta_l"])) > 1e-4
            for cs in parsed_cs
        )

        name = str(comp.get("name") or comp.get("id") or "Wing")

        if mirror:
            # Wing.symmetric mirrors in the *global* XZ plane.  It is only
            # equivalent to Setuav's parent-frame mirror when the transformed
            # left stations are exactly that global reflection (e.g. a normal
            # horizontal wing).  A rolled/rotated V-tail must remain two real
            # asymmetric AeroSandbox wings.
            global_reflection_matches = all(
                np.allclose(
                    left.xyz_le,
                    [right.xyz_le[0], -right.xyz_le[1], right.xyz_le[2]],
                    atol=1e-9,
                )
                for right, left in zip(xsecs_right, reversed(xsecs_left), strict=True)
            )
            if not has_asymmetric_controls and global_reflection_matches:
                return asb.Wing(name=name, xsecs=xsecs_right, symmetric=True)

            return [
                asb.Wing(name=f"{name}_Right", xsecs=xsecs_right, symmetric=False),
                asb.Wing(name=f"{name}_Left", xsecs=xsecs_left, symmetric=False),
            ]

        return asb.Wing(name=name, xsecs=xsecs_right, symmetric=False)
