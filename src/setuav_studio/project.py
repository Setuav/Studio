import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

logger = logging.getLogger(__name__)


class ProjectOpenError(Exception):
    """Raised when a project cannot be opened."""


class ProjectSaveError(Exception):
    """Raised when a project cannot be saved."""


@dataclass
class ProjectDocument:
    path: Path
    kind: Literal["folder", "json", "archive"]
    data: dict[str, Any]
    modified: bool = field(default=False, compare=False)
    plugin_issues: list[str] = field(default_factory=list, compare=False)

    @property
    def location(self) -> Path:
        if self.kind == "folder":
            return self.path.parent
        return self.path

    @property
    def degraded(self) -> bool:
        return bool(self.plugin_issues)


def open_project(path: str | Path) -> ProjectDocument:
    selected_path = Path(path).expanduser().resolve()
    logger.info("Opening project: %s", selected_path)

    if selected_path.is_dir():
        project_file = selected_path / "project.json"
        return ProjectDocument(project_file, "folder", _read_json_file(project_file))

    if selected_path.name == "project.json":
        return ProjectDocument(selected_path, "json", _read_json_file(selected_path))

    if selected_path.suffix.lower() == ".suav":
        return ProjectDocument(selected_path, "archive", _read_suav(selected_path))

    raise ProjectOpenError("Expected a project folder, project.json, or .suav file")


def save_project(
    project: ProjectDocument,
    path: str | Path | None = None,
) -> None:
    target = project.path if path is None else Path(path).expanduser().resolve()
    logger.info("Saving project: %s", target)

    try:
        if target.suffix.lower() == ".suav":
            _write_suav(project, target)
            project.path = target
            project.kind = "archive"
        elif target.name == "project.json":
            _write_json_file(target, project.data)
            project.path = target
            if path is not None or project.kind != "folder":
                project.kind = "json"
        else:
            raise ProjectSaveError("Expected project.json or a .suav file")
    except ProjectSaveError:
        raise
    except OSError as exc:
        raise ProjectSaveError(f"Cannot save project: {target}") from exc

    project.modified = False


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


def _write_json_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(data, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _write_suav(project: ProjectDocument, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        with ZipFile(temporary_path, "w", compression=ZIP_DEFLATED) as destination:
            _copy_project_files_to_archive(project, destination)
            destination.writestr(
                "project.json",
                json.dumps(project.data, ensure_ascii=False, indent=2) + "\n",
            )
        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _copy_project_files_to_archive(
    project: ProjectDocument,
    destination: ZipFile,
) -> None:
    if project.kind == "archive" and project.path.exists():
        with ZipFile(project.path) as source:
            for info in source.infolist():
                if info.filename != "project.json":
                    destination.writestr(info, source.read(info.filename))
        return

    if project.kind != "folder":
        return

    root = project.path.parent
    for source_path in root.rglob("*"):
        if source_path.is_file() and source_path != project.path:
            destination.write(source_path, source_path.relative_to(root).as_posix())


def _require_object(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ProjectOpenError("project.json must contain a JSON object")
    return data
