"""Project document lifecycle, persistence, archive packaging, and validation."""

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
    clear_component_validators,
    register_component_validator,
    unregister_component_validator,
    validate_project,
)

__all__ = [
    "Issue",
    "ProjectDocument",
    "ProjectOpenError",
    "ProjectSaveError",
    "_write_json_file",
    "_write_suav",
    "clear_component_validators",
    "create_project",
    "open_project",
    "register_component_validator",
    "save_project",
    "unregister_component_validator",
    "validate_project",
]
