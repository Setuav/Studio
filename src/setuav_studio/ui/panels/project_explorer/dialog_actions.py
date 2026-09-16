from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


def add_parameter_action(
    api: StudioAPI,
    tree: QWidget,
    is_constant: bool = False,
    parent: QWidget | None = None,
) -> None:
    data = api.current_project.data if api.current_project else {}
    raw = data.get("parameters", {}) if isinstance(data, dict) else {}
    prefix = "const_" if is_constant else "param_"
    idx = 1
    while f"{prefix}{idx}" in raw:
        idx += 1
    param_name = f"{prefix}{idx}"

    def _apply() -> None:
        pdata = api.current_project.data if api.current_project else {}
        pdata.setdefault("parameters", {})[param_name] = 0.0

    action_name = "constant" if is_constant else "parameter"
    api.edit_project(f"Add {action_name} '{param_name}'", _apply)
    api.set_selection({"kind": "parameter", "key": param_name, "value": 0.0})


def add_constraint_action(
    api: StudioAPI,
    tree: QWidget,
    parent: QWidget | None = None,
) -> None:
    data = api.current_project.data if api.current_project else {}
    raw = data.get("constraints", []) if isinstance(data, dict) else []
    idx = 1
    existing_ids = {str(c.get("id")) for c in raw if isinstance(c, dict)}
    while f"c_{idx}" in existing_ids:
        idx += 1
    cid = f"c_{idx}"
    cname = f"Constraint {idx}"
    new_constraint = {
        "id": cid,
        "name": cname,
        "expression": "span > 0",
        "severity": "warning",
        "enabled": True,
        "description": "",
    }

    def _apply() -> None:
        pdata = api.current_project.data if api.current_project else {}
        pdata.setdefault("constraints", []).append(new_constraint)

    api.edit_project(f"Add constraint '{cname}'", _apply)
    api.set_selection({"kind": "constraint", "id": cid, "name": cname})


def toggle_constraint(
    api: StudioAPI,
    _tree: QWidget,
    element: dict[str, Any],
) -> None:
    cid = str(element.get("id") or "")

    def _apply() -> None:
        pdata = api.current_project.data if api.current_project else {}
        for c in pdata.get("constraints", []):
            if c.get("id") == cid:
                c["enabled"] = not c.get("enabled", True)
                break

    api.edit_project("Toggle constraint", _apply)
