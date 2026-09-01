"""Project document lifecycle, persistence, archive packaging, and schema validation."""

from __future__ import annotations

from setuav_studio.project.document import (
    ProjectDocument,
    ProjectOpenError,
    ProjectSaveError,
    _write_json_file,
    _write_suav,
    create_project,
    open_project,
    save_project,
)
from setuav_studio.project.validation import (
    Issue,
    PluginInfo,
    SchemaCatalog,
    get_catalog,
    validate_project,
)

__all__ = [
    "Issue",
    "PluginInfo",
    "ProjectDocument",
    "ProjectOpenError",
    "ProjectSaveError",
    "SchemaCatalog",
    "_write_json_file",
    "_write_suav",
    "create_project",
    "get_catalog",
    "open_project",
    "save_project",
    "validate_project",
]
