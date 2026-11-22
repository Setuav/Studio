from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

if TYPE_CHECKING:
    from setuav_studio.solver.base import SolverConfig
    from setuav_studio.solver.results import SolverResult

logger = logging.getLogger(__name__)


class ProjectOpenError(Exception):
    """Raised when a project cannot be opened."""


class ProjectSaveError(Exception):
    """Raised when a project cannot be saved."""


@dataclass
class ProjectDocument:
    """Represent the open Setuav project exposed to plugins.

    `data` contains the JSON-compatible project model. Plugins should mutate it
    through `StudioAPI.edit_project`, `StudioAPI.edit_component`, or their
    extension helpers so undo/redo and modified-state tracking remain correct.
    """

    path: Path
    kind: Literal["folder", "json", "archive"]
    data: dict[str, Any]
    modified: bool = field(default=False, compare=False)
    plugin_issues: list[str] = field(default_factory=list, compare=False)
    read_only: bool = field(default=False, compare=False)
    untitled: bool = field(default=False, compare=False)
    expression_diagnostics: list[dict[str, str]] = field(default_factory=list, compare=False)
    # Set when the file comes from a newer minor project format.
    format_warning: str | None = field(default=None, compare=False)
    # Deserialized solver results by id, kept in step with data["solver_results"].
    _solver_results_cache: dict[str, SolverResult] = field(
        default_factory=dict, init=False, compare=False, repr=False
    )

    @property
    def location(self) -> Path:
        if self.kind == "folder":
            return self.path.parent
        return self.path

    @property
    def name(self) -> str:
        """The project's name: its archive's file name, or the name of its folder."""
        if self.kind == "archive":
            return self.path.stem
        return self.path.parent.name

    @property
    def degraded(self) -> bool:
        return bool(self.plugin_issues)

    @property
    def solver_results(self) -> dict[str, SolverResult]:
        """Return the dictionary of SolverResult objects stored in the project data."""
        from setuav_studio.solver.results import SolverResult

        raw_results = self.data.get("solver_results")
        if not isinstance(raw_results, dict):
            self._solver_results_cache.clear()
            return {}

        # Remove deleted items from cache
        for k in list(self._solver_results_cache.keys()):
            if k not in raw_results:
                del self._solver_results_cache[k]

        # Deserialize new items into cache
        for res_id, res_data in raw_results.items():
            if str(res_id) not in self._solver_results_cache:
                self._solver_results_cache[str(res_id)] = SolverResult.from_dict(res_data)
        return self._solver_results_cache

    def add_solver_result(self, result: SolverResult) -> None:
        """Add or update a SolverResult in the project data."""
        self._solver_results_cache[result.id] = result
        if "solver_results" not in self.data or not isinstance(self.data["solver_results"], dict):
            self.data["solver_results"] = {}
        self.data["solver_results"][result.id] = result.to_dict()
        self.modified = True

    def results_of_config(self, config_id: str) -> list[SolverResult]:
        """The results of the analysis configuration ``config_id``, oldest first."""
        return [r for r in self.solver_results.values() if r.config.config_id == config_id]

    def get_solver_result(self, result_id: str) -> SolverResult | None:
        """Retrieve a specific SolverResult by ID."""
        return self.solver_results.get(result_id)

    def remove_solver_result(self, result_id: str) -> bool:
        """Remove a SolverResult by ID if present."""
        self._solver_results_cache.pop(result_id, None)
        raw_results = self.data.get("solver_results")
        if isinstance(raw_results, dict) and result_id in raw_results:
            del raw_results[result_id]
            self.modified = True
            return True
        return False

    def clear_solver_results(self) -> None:
        """Clear all solver results from the project data."""
        self._solver_results_cache.clear()
        if "solver_results" in self.data:
            self.data["solver_results"] = {}
            self.modified = True

    @property
    def solver_configs(self) -> dict[str, SolverConfig]:
        """Return the dictionary of SolverConfig objects stored in the project data."""
        from setuav_studio.solver.base import SolverConfig

        raw_configs = self.data.get("solver_configs")
        if not isinstance(raw_configs, dict):
            return {}

        return {
            str(cfg_id): SolverConfig.from_dict(cfg_data)
            for cfg_id, cfg_data in raw_configs.items()
        }

    def add_solver_config(self, config: SolverConfig) -> None:
        """Add or update a SolverConfig in the project data."""
        if "solver_configs" not in self.data or not isinstance(self.data["solver_configs"], dict):
            self.data["solver_configs"] = {}
        self.data["solver_configs"][config.config_id] = config.to_dict()
        self.modified = True

    def get_solver_config(self, config_id: str) -> SolverConfig | None:
        """Retrieve a specific SolverConfig by ID."""
        return self.solver_configs.get(config_id)

    def remove_solver_config(self, config_id: str) -> bool:
        """Remove a SolverConfig by ID if present."""
        raw_configs = self.data.get("solver_configs")
        if isinstance(raw_configs, dict) and config_id in raw_configs:
            del raw_configs[config_id]
            self.modified = True
            return True
        return False

    def clear_solver_configs(self) -> None:
        """Clear all solver configs from the project data."""
        if "solver_configs" in self.data:
            self.data["solver_configs"] = {}
            self.modified = True

    def get_component(self, comp_id: str) -> dict[str, Any] | None:
        """Find a component by its ID."""
        components = self.data.get("components")
        if not isinstance(components, list):
            return None
        return next((c for c in components if isinstance(c, dict) and c.get("id") == comp_id), None)

    @property
    def mass_properties(self) -> Any:
        """Aggregate total aircraft mass, center of gravity, and 3D inertia tensor."""
        from setuav_studio.utilities.mass_balance import resolve_aircraft_mass_properties

        return resolve_aircraft_mass_properties(self)

    def get_scope(self, api: Any | None = None) -> dict[str, Any]:
        """Return the complete runtime evaluation scope containing resolved parameters and live component models."""
        from setuav_studio.model.scope import build_universal_scope

        return build_universal_scope(self.data, api=api)


#: Version of the project file layout as (major, minor). Raise the minor when fields
#: are only added, so older Studios still open the file; raise the major when the
#: layout changes otherwise. Studio opens files of its own major only.
PROJECT_FORMAT_VERSION = (1, 0)


def _format_text(version: tuple[int, int]) -> str:
    return f"{version[0]}.{version[1]}"


def _studio_version() -> str:
    from importlib.metadata import version

    return version("setuav-studio")


def _check_format_version(data: dict[str, Any], path: Path) -> str | None:
    """Raise for a file this Studio cannot read; return a warning for a newer minor."""
    found = data.get("format_version")
    written_by = data.get("studio_version")
    by = f" by Setuav Studio {written_by}" if written_by else ""
    current = _format_text(PROJECT_FORMAT_VERSION)
    parts = found.split(".") if isinstance(found, str) else []
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ProjectOpenError(
            f"{path.name} has no valid project format version ({found!r}){by}; "
            f"this Studio reads format {current}."
        )
    major, minor = int(parts[0]), int(parts[1])
    if major > PROJECT_FORMAT_VERSION[0]:
        raise ProjectOpenError(
            f"{path.name} was saved{by} in project format {found}; this Studio "
            f"({_studio_version()}) reads format {current}. Update Setuav Studio."
        )
    if major < PROJECT_FORMAT_VERSION[0]:
        raise ProjectOpenError(
            f"{path.name} was saved{by} in project format {found}, which this Studio "
            f"({_studio_version()}, format {current}) no longer reads."
        )
    if minor > PROJECT_FORMAT_VERSION[1]:
        return (
            f"{path.name} was saved{by} in project format {found}, newer than this "
            f"Studio's {current}. Data this Studio does not know may be lost when you save."
        )
    return None


def create_project(path: str | Path) -> ProjectDocument:
    """Create a new, empty project document at ``path``.

    New projects start with empty collections. The document is marked modified
    until the caller saves it.
    """
    selected_path = Path(path).expanduser().resolve()
    if selected_path.suffix.lower() == ".suav":
        kind: Literal["json", "archive"] = "archive"
    elif selected_path.name == "project.json":
        kind = "json"
    else:
        raise ProjectSaveError("Expected a project.json or a .suav file")

    return ProjectDocument(
        path=selected_path,
        kind=kind,
        data={
            "format_version": _format_text(PROJECT_FORMAT_VERSION),
            "studio_version": _studio_version(),
            "plugins": [],
            "components": [],
            "parameters": {},
            "constraints": [],
            "solver_configs": {},
            "solver_results": {},
            "extensions": {},
        },
        modified=True,
    )


def open_project(path: str | Path) -> ProjectDocument:
    selected_path = Path(path).expanduser().resolve()
    logger.info("Opening project: %s", selected_path)

    if selected_path.is_dir():
        project_file = selected_path / "project.json"
        doc = ProjectDocument(project_file, "folder", _read_json_file(project_file))
    elif selected_path.name == "project.json":
        doc = ProjectDocument(selected_path, "json", _read_json_file(selected_path))
    elif selected_path.suffix.lower() == ".suav":
        doc = ProjectDocument(selected_path, "archive", _read_suav(selected_path))
    else:
        raise ProjectOpenError("Expected a project folder, project.json, or .suav file")
    doc.format_warning = _check_format_version(doc.data, selected_path)

    # Evaluate all parametric expressions to hydrate runtime numeric caches
    from setuav_studio.project.evaluator import recompute_project_expressions

    recompute_project_expressions(doc)
    doc.modified = False
    return doc


def _json_default(obj: Any) -> Any:
    """Handle non-standard JSON types such as NumPy scalars/arrays, Path, sets, and dates."""
    if hasattr(obj, "tolist") and callable(obj.tolist):
        return obj.tolist()
    if hasattr(obj, "item") and callable(obj.item):
        return obj.item()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if hasattr(obj, "isoformat") and callable(obj.isoformat):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def save_project(
    project: ProjectDocument,
    path: str | Path | None = None,
    *,
    api: Any | None = None,
) -> None:
    """Write the project; ``api`` gives formulas the plugins' component models."""
    if project.read_only:
        raise ProjectSaveError(
            f"Cannot save project: opened read-only due to validation issues ({project.path})"
        )
    target = project.path if path is None else Path(path).expanduser().resolve()
    logger.info("Saving project: %s", target)

    # 1. Recompute parametric expressions to ensure latest evaluated numbers
    from setuav_studio.project.evaluator import recompute_project_expressions

    recompute_project_expressions(project, api=api)

    # The file records its layout version and the Studio that wrote it.
    project.data["format_version"] = _format_text(PROJECT_FORMAT_VERSION)
    project.data["studio_version"] = _studio_version()
    save_data = project.data

    # 2. Pre-save validation: prevent writing corrupted project documents to disk
    from setuav_studio.project.validation import validate_project

    issues = validate_project(save_data)
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        error_msgs = "; ".join(e.message for e in errors[:5])
        raise ProjectSaveError(f"Cannot save invalid project: {error_msgs}")

    try:
        if target.suffix.lower() == ".suav":
            _write_suav(project, target, data=save_data)
            project.path = target
            project.kind = "archive"
        elif target.name == "project.json":
            _write_json_file(target, save_data)
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
            json.dump(data, temporary_file, ensure_ascii=False, indent=2, default=_json_default)
            temporary_file.write("\n")
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _write_suav(project: ProjectDocument, target: Path, data: dict[str, Any] | None = None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = data if data is not None else project.data
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
                json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n",
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
