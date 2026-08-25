"""Persistent flight performance analysis results stored in the project document."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from setuav_studio.project import ProjectDocument

from .engine.models import FlightEnvelopeResult

EXTENSION_ID = "org.setuav.studio.flight_performance"
RESULT_SELECTION_KIND = "flight-performance-result"
RESULTS_GROUP_ID = "flight_performance.analysis-results"
RESULTS_VERSION = 1


def performance_selection(analysis_id: str) -> dict[str, Any]:
    return {
        "kind": RESULT_SELECTION_KIND,
        "id": analysis_id,
    }


def make_analysis_entry(
    result: FlightEnvelopeResult,
    name: str = "Flight Envelope",
) -> dict[str, Any]:
    return {
        "id": uuid4().hex,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result": result.to_dict(),
    }


def append_analysis_entry(extension: dict[str, Any], entry: dict[str, Any]) -> None:
    results = extension.setdefault("results", [])
    if not isinstance(results, list):
        results = []
        extension["results"] = results
    results.append(entry)
    extension["results_version"] = RESULTS_VERSION


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


def get_stored_performance_result(project: ProjectDocument | None) -> FlightEnvelopeResult | None:
    """Retrieve the most recent flight performance result from project extension."""
    entries = analysis_entries(project)
    if not entries:
        return None
    latest = entries[-1]
    payload = latest.get("result")
    if isinstance(payload, dict):
        try:
            return FlightEnvelopeResult.from_dict(payload)
        except Exception:
            return None
    return None


def store_performance_result(
    project: ProjectDocument,
    result: FlightEnvelopeResult,
    label: str = "Flight Performance Envelope",
) -> dict[str, Any]:
    """Store a flight performance envelope result in the project document extension."""
    ext = project.get_extension(EXTENSION_ID)
    if not isinstance(ext, dict):
        ext = {"results_version": RESULTS_VERSION, "results": []}
        project.set_extension(EXTENSION_ID, ext)

    entry = make_analysis_entry(result, label)
    append_analysis_entry(ext, entry)
    return entry


def delete_analysis_entry(extension: dict[str, Any], analysis_id: str) -> None:
    results = extension.get("results")
    if isinstance(results, list):
        extension["results"] = [
            e for e in results if isinstance(e, dict) and str(e.get("id")) != analysis_id
        ]


def rename_analysis_entry(extension: dict[str, Any], analysis_id: str, new_name: str) -> None:
    results = extension.get("results")
    if isinstance(results, list):
        for entry in results:
            if isinstance(entry, dict) and str(entry.get("id")) == analysis_id:
                entry["name"] = new_name
                return
