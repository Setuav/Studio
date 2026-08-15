import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from zipfile import BadZipFile, ZipFile


class ProjectOpenError(Exception):
    """Raised when a project cannot be opened."""


@dataclass(frozen=True)
class ProjectDocument:
    path: Path
    kind: Literal["folder", "json", "archive"]
    data: dict[str, Any]


def open_project(path: str | Path) -> ProjectDocument:
    selected_path = Path(path).expanduser().resolve()

    if selected_path.is_dir():
        project_file = selected_path / "project.json"
        return ProjectDocument(project_file, "folder", _read_json_file(project_file))

    if selected_path.name == "project.json":
        return ProjectDocument(selected_path, "json", _read_json_file(selected_path))

    if selected_path.suffix.lower() == ".suav":
        return ProjectDocument(selected_path, "archive", _read_suav(selected_path))

    raise ProjectOpenError("Expected a project folder, project.json, or .suav file")


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProjectOpenError(f"Project file not found: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectOpenError(f"Cannot read project file: {path}") from exc
    return _require_object(data)


def _read_suav(path: Path) -> dict[str, Any]:
    try:
        with ZipFile(path) as archive:
            data = json.loads(archive.read("project.json").decode("utf-8"))
    except FileNotFoundError as exc:
        raise ProjectOpenError(f"Project archive not found: {path}") from exc
    except KeyError as exc:
        raise ProjectOpenError("Project archive has no project.json at its root") from exc
    except (BadZipFile, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectOpenError(f"Cannot read project archive: {path}") from exc
    return _require_object(data)


def _require_object(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ProjectOpenError("project.json must contain a JSON object")
    return data
