from typing import Any

from PySide6.QtWidgets import QMessageBox, QWidget

from setuav_studio.project import ProjectDocument


def _items_by_id(data: dict[str, Any], key: str) -> dict[object, dict[str, Any]]:
    return {item.get("id"): item for item in data.get(key, []) if isinstance(item, dict)}


def _append_entity_changes(
    changes: list[str],
    disk_items: dict[object, dict[str, Any]],
    current_items: dict[object, dict[str, Any]],
    entity_name: str,
    *,
    include_deleted: bool = False,
) -> None:
    for item_id, item in current_items.items():
        name = item.get("name") or item_id
        if item_id not in disk_items:
            changes.append(f"New {entity_name}: {name}")
        elif disk_items[item_id] != item:
            changes.append(f"Modified {entity_name}: {name}")
    if include_deleted:
        for item_id, item in disk_items.items():
            if item_id not in current_items:
                changes.append(f"Deleted {entity_name}: {item.get('name') or item_id}")


def apply_runtime_validation(
    project: ProjectDocument,
    issues: object,
    strictness: str,
    parent: QWidget | None = None,
    *,
    interactive: bool = True,
) -> str:
    """Apply runtime schema validation decisions to a freshly opened project.

    Returns ``"open"``, ``"read_only"``, or ``"cancel"``. When
    ``interactive`` is ``False`` the strict-mode blocking dialog is skipped
    and the project is forced read-only (used by tests).
    """
    if not issues or strictness == "off":
        return "open"
    if strictness == "warn":
        project.read_only = True
        return "read_only"
    if strictness != "strict":
        return "open"

    if not interactive:
        project.read_only = True
        return "read_only"

    issue_list = list(issues) if isinstance(issues, (list, tuple)) else []
    message = "\n".join(f"• {issue.path}: {issue.message}" for issue in issue_list[:10])
    if len(issue_list) > 10:
        message += f"\n…and {len(issue_list) - 10} more."

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("Project validation failed")
    box.setText(f"Found {len(issue_list)} schema issue(s).")
    box.setInformativeText(message)
    btn_ro = box.addButton("Open read-only", QMessageBox.ButtonRole.AcceptRole)
    btn_cancel = box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(btn_ro)
    box.exec()
    if box.clickedButton() is btn_cancel:
        return "cancel"
    project.read_only = True
    return "read_only"


__all__ = [
    "_append_entity_changes",
    "_items_by_id",
    "apply_runtime_validation",
]
