from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QDialog, QWidget

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


def add_parameter_action(
    api: StudioAPI,
    tree: QWidget,
    is_constant: bool = False,
    parent: QWidget | None = None,
) -> None:
    from setuav_studio.plugins.core.ui.parameters_dialog import AddParameterDialog

    data = api.current_project.data if api.current_project else {}
    raw = data.setdefault("parameters", {})
    dlg = AddParameterDialog(
        api=api,
        existing_names=set(raw.keys()),
        is_constant=is_constant,
        parent=parent or tree,
    )
    if dlg.exec() == QDialog.DialogCode.Accepted:
        param_name, param_val = dlg.get_data()

        def _apply() -> None:
            pdata = api.current_project.data if api.current_project else {}
            pdata.setdefault("parameters", {})[param_name] = param_val

        action_name = "constant" if is_constant else "parameter"
        api.edit_project(f"Add {action_name} '{param_name}'", _apply)


def add_constraint_action(
    api: StudioAPI,
    tree: QWidget,
    parent: QWidget | None = None,
) -> None:
    from setuav_studio.plugins.core.ui.constraints_dialog import ConstraintEditDialog

    dlg = ConstraintEditDialog(
        parent or tree,
        api=api,
        project_data=api.current_project.data if api.current_project else {},
    )
    if dlg.exec() == QDialog.DialogCode.Accepted:
        data = dlg.get_data()

        def _apply() -> None:
            pdata = api.current_project.data if api.current_project else {}
            pdata.setdefault("constraints", []).append(data)

        api.edit_project(f"Add constraint '{data['name']}'", _apply)


def edit_parameter_fx(
    api: StudioAPI,
    tree: QWidget,
    element: dict[str, Any],
    parent: QWidget | None = None,
) -> None:
    from setuav_studio.plugins.core.ui.expression_dialog import AdvancedExpressionDialog

    param_key = str(element.get("key") or "")
    val = str(element.get("value") or "")
    dlg = AdvancedExpressionDialog(
        api,
        initial_expression=val,
        title=f"Equation Assistant — {param_key}",
        is_boolean_constraint=False,
        parent=parent or tree,
    )
    if dlg.exec() == QDialog.DialogCode.Accepted:
        new_expr = dlg.get_expression()

        def _apply() -> None:
            pdata = api.current_project.data if api.current_project else {}
            pdata.setdefault("parameters", {})[param_key] = new_expr

        api.edit_project(f"Edit parameter '{param_key}'", _apply)


def edit_constraint_fx(
    api: StudioAPI,
    tree: QWidget,
    element: dict[str, Any],
    parent: QWidget | None = None,
) -> None:
    from setuav_studio.plugins.core.ui.constraints_dialog import ConstraintEditDialog

    cid = str(element.get("id") or "")
    dlg = ConstraintEditDialog(
        parent or tree,
        initial_data=element,
        api=api,
        project_data=api.current_project.data if api.current_project else {},
    )
    if dlg.exec() == QDialog.DialogCode.Accepted:
        updated = dlg.get_data()

        def _apply() -> None:
            pdata = api.current_project.data if api.current_project else {}
            constraints = pdata.get("constraints", [])
            for i, c in enumerate(constraints):
                if c.get("id") == cid:
                    constraints[i] = updated
                    break

        api.edit_project(f"Edit constraint '{updated['name']}'", _apply)


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
