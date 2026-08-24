"""Persistent aerodynamic analysis results stored in the project document."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from setuav_studio.project import ProjectDocument

from .engine.base import AeroResult, SweepType


EXTENSION_ID = "org.setuav.studio.aerodynamics"
RESULT_SELECTION_KIND = "aerodynamics-analysis-result"
RESULTS_GROUP_ID = "aerodynamics.analysis-results"


def result_name(result: AeroResult) -> str:
    custom_name = result.raw.get("analysis_name") if isinstance(result.raw, dict) else None
    if custom_name and str(custom_name).strip():
        return str(custom_name).strip()
    sweep_type = result.condition.sweep_type
    if sweep_type == SweepType.DUAL_ALPHA_BETA:
        return "α–β Sweep"
    if sweep_type == SweepType.BETA:
        return "β Sweep"
    if sweep_type == SweepType.CONTROL_DEFLECTION:
        channel = result.condition.sweep_variable.replace("_", " ").title()
        return f"{channel} Channel"
    if len(result.polar_points) <= 1:
        return "Single Point"
    return "α Sweep"


def short_result_name(name: str) -> str:
    """Shorten default names written by earlier plugin versions."""
    aliases = {
        "Alpha + Beta Sweep": "α–β Sweep",
        "Alpha Sweep": "α Sweep",
        "Beta Sweep": "β Sweep",
    }
    if name.endswith(" Channel Analysis"):
        return name.removesuffix(" Analysis")
    return aliases.get(name, name)


def make_analysis_entry(result: AeroResult) -> dict[str, Any]:
    return {
        "id": uuid4().hex,
        "name": result_name(result),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result": result.to_dict(),
    }


def append_analysis_entry(extension: dict[str, Any], entry: dict[str, Any]) -> None:
    extension["results_version"] = 1
    results = extension.setdefault("results", [])
    if not isinstance(results, list):
        results = []
        extension["results"] = results
    results.append(entry)


def analysis_entries(project: ProjectDocument | None) -> tuple[dict[str, Any], ...]:
    if project is None:
        return ()
    extension = project.get_extension(EXTENSION_ID, {})
    if not isinstance(extension, dict):
        return ()
    results = extension.get("results")
    if not isinstance(results, list):
        return ()
    return tuple(entry for entry in results if isinstance(entry, dict))


def load_analysis_result(
    project: ProjectDocument | None,
    analysis_id: str,
) -> AeroResult | None:
    for entry in analysis_entries(project):
        if str(entry.get("id") or "") != analysis_id:
            continue
        payload = entry.get("result")
        if not isinstance(payload, dict):
            return None
        try:
            return AeroResult.from_dict(payload)
        except (TypeError, ValueError):
            return None
    return None


def delete_analysis_entry(extension: dict[str, Any], analysis_id: str) -> bool:
    results = extension.get("results")
    if not isinstance(results, list):
        return False
    old_size = len(results)
    results[:] = [
        entry
        for entry in results
        if not (
            isinstance(entry, dict)
            and str(entry.get("id") or "") == analysis_id
        )
    ]
    return len(results) != old_size


def rename_analysis_entry(
    extension: dict[str, Any],
    analysis_id: str,
    name: str,
) -> bool:
    clean_name = name.strip()
    if not clean_name:
        return False
    results = extension.get("results")
    if not isinstance(results, list):
        return False
    for entry in results:
        if (
            isinstance(entry, dict)
            and str(entry.get("id") or "") == analysis_id
        ):
            entry["name"] = clean_name
            return True
    return False


def analysis_selection(analysis_id: str) -> dict[str, Any]:
    return {
        "id": f"aerodynamics.analysis-result.{analysis_id}",
        "kind": RESULT_SELECTION_KIND,
        "analysis_id": analysis_id,
    }
