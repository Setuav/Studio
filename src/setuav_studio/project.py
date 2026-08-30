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

    @property
    def location(self) -> Path:
        if self.kind == "folder":
            return self.path.parent
        return self.path

    @property
    def degraded(self) -> bool:
        return bool(self.plugin_issues)

    def get_extension(self, namespace: str, default: Any = None) -> Any:
        """Retrieve root-level extension data for a given namespace."""
        extensions = self.data.get("extensions")
        if not isinstance(extensions, dict):
            return default
        return extensions.get(namespace, default)

    def set_extension(self, namespace: str, value: Any) -> None:
        """Set root-level extension data for a given namespace."""
        if "extensions" not in self.data or not isinstance(self.data["extensions"], dict):
            self.data["extensions"] = {}
        self.data["extensions"][namespace] = value
        self.modified = True

    def remove_extension(self, namespace: str) -> None:
        """Remove root-level extension data for a given namespace."""
        extensions = self.data.get("extensions")
        if isinstance(extensions, dict) and namespace in extensions:
            del extensions[namespace]
            self.modified = True

    def get_component(self, comp_id: str) -> dict[str, Any] | None:
        """Find a component by its ID."""
        components = self.data.get("components")
        if not isinstance(components, list):
            return None
        return next((c for c in components if isinstance(c, dict) and c.get("id") == comp_id), None)

    def get_component_extension(self, comp_id: str, namespace: str, default: Any = None) -> Any:
        """Retrieve component-level extension data for a given namespace."""
        comp = self.get_component(comp_id)
        if comp is None:
            return default
        extensions = comp.get("extensions")
        if not isinstance(extensions, dict):
            return default
        return extensions.get(namespace, default)

    def set_component_extension(self, comp_id: str, namespace: str, value: Any) -> None:
        """Set component-level extension data for a given namespace."""
        comp = self.get_component(comp_id)
        if comp is None:
            raise KeyError(f"Component '{comp_id}' not found in project")
        if "extensions" not in comp or not isinstance(comp["extensions"], dict):
            comp["extensions"] = {}
        comp["extensions"][namespace] = value
        self.modified = True

    def get_configuration_manager(self) -> Any:
        """Return the shared ConfigurationManager instance for this project."""
        if (
            not hasattr(self, "_config_manager")
            or getattr(self, "_config_manager_data", None) is not self.data
        ):
            from setuav_studio.plugins.core.configurations import ConfigurationManager

            self._config_manager = ConfigurationManager(self.data)
            self._config_manager_data = self.data
        return self._config_manager

    def get_component_models(self, api: Any | None = None, config_id: str | None = None) -> list[Any]:
        """Return the list of typed domain model instances for all project components."""
        from setuav_studio.component_model import GenericComponentModel

        cfg_mgr = self.get_configuration_manager()
        components = self.data.get("components", [])
        models: list[Any] = []
        if not isinstance(components, list):
            return models

        for comp in components:
            if not isinstance(comp, dict):
                continue
            resolved_comp = cfg_mgr.get_resolved_component(comp, config_id)
            if api is not None and hasattr(api, "create_component_model"):
                model = api.create_component_model(resolved_comp)
            else:
                model = GenericComponentModel(resolved_comp)
            models.append(model)
        return models

    def get_scope(self, api: Any | None = None, config_id: str | None = None) -> dict[str, Any]:
        """Return the complete runtime evaluation scope containing resolved parameters and live component models."""
        cfg_mgr = self.get_configuration_manager()
        scope: dict[str, Any] = {}

        # 1. Project Parameters & Constants
        resolved_params = cfg_mgr.get_effective_project_parameters(config_id)
        for k, v in resolved_params.items():
            scope[k] = v

        # 2. Live Component Models
        models = self.get_component_models(api, config_id)
        total_mass = 0.0

        for model in models:
            raw_cid = model.id
            if not raw_cid:
                continue
            clean_cid = raw_cid.replace("-", "_")
            scope[clean_cid] = model
            if raw_cid != clean_cid:
                scope[raw_cid] = model

            # Flat aliases for compatibility (e.g. main_wing_planform_area)
            if hasattr(model, "get_exposed_properties"):
                for prop_name, prop_val in model.get_exposed_properties().items():
                    if isinstance(prop_val, (int, float, bool, str)):
                        scope[f"{clean_cid}_{prop_name}"] = prop_val

            total_mass += model.mass

        scope["total_mass"] = total_mass
        scope["mtow"] = resolved_params.get("mtow", total_mass)
        return scope


def create_project(path: str | Path) -> ProjectDocument:
    """Create a new, empty project document at ``path``.

    New projects always start with the core plugin requirement and empty
    collections. The document is marked modified until the caller saves it.
    """
    selected_path = Path(path).expanduser().resolve()
    if selected_path.suffix.lower() == ".suav":
        kind: Literal["json", "archive"] = "archive"
    elif selected_path.name == "project.json":
        kind = "json"
    else:
        raise ProjectSaveError("Expected a project.json or a .suav file")

    project_name = selected_path.stem
    if selected_path.name == "project.json":
        project_name = selected_path.parent.name or "Untitled Project"
    if not project_name:
        project_name = "Untitled Project"

    return ProjectDocument(
        path=selected_path,
        kind=kind,
        data={
            "$schema": "https://schemas.setuav.org/core/project.schema.json",
            "name": project_name,
            "plugins": [{"id": "org.setuav.core", "version": "^1.0.0"}],
            "components": [],
            "assemblies": [],
            "parameters": {},
            "extensions": {},
        },
        modified=True,
    )


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
    if project.read_only:
        raise ProjectSaveError(
            f"Cannot save project: opened read-only due to validation issues ({project.path})"
        )
    target = project.path if path is None else Path(path).expanduser().resolve()
    logger.info("Saving project: %s", target)

    save_data = project.data
    if hasattr(project, "get_configuration_manager"):
        import copy

        cfg_mgr = project.get_configuration_manager()
        cfg_mgr.sync_current_state_to_active()
        if cfg_mgr.get_active_id() is not None:
            save_data = copy.deepcopy(project.data)
            save_data["components"] = copy.deepcopy(cfg_mgr._base_state["components"])
            save_data["parameters"] = copy.deepcopy(cfg_mgr._base_state["parameters"])
            save_data["assemblies"] = copy.deepcopy(cfg_mgr._base_state["assemblies"])

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
            json.dump(data, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _write_suav(
    project: ProjectDocument, target: Path, data: dict[str, Any] | None = None
) -> None:
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
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
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
