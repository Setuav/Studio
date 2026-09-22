from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


def add_parameter_action(
    api: StudioAPI,
    tree: QWidget | None = None,
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
    api.set_selection(
        {"kind": "parameter", "id": f"param_{param_name}", "key": param_name, "value": 0.0}
    )


def add_constraint_action(
    api: StudioAPI,
    tree: QWidget | None = None,
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
    api.set_selection({"kind": "constraint", "id": cid, "name": cname, **new_constraint})


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


def add_plot_action(
    api: StudioAPI,
    element: dict[str, Any] | None = None,
    parent: QWidget | None = None,
) -> Any | None:
    project = api.current_project
    if project is None:
        return None

    element = element or {}
    result_id = str(element.get("result_id") or "")
    config_id = str(element.get("config_id") or "")

    if not result_id and config_id:
        matching = [
            r
            for r in project.solver_results.values()
            if getattr(getattr(r, "config", None), "config_id", None) == config_id
        ]
        if matching:
            result_id = matching[-1].id

    if not result_id:
        if project.solver_results:
            result_id = next(reversed(project.solver_results.keys()))
        else:
            return None

    result = api.get_solver_result(result_id)
    if result is None or not result.tables:
        return None

    table_id = str(element.get("table_id") or "")
    if not table_id or table_id not in result.tables:
        table_id = next(iter(result.tables.keys()))

    table = result.tables[table_id]
    if not table.columns:
        return None

    # Determine X column and Y column
    x_col = table.columns[0].key
    x_label = table.columns[0].label
    y_col = table.columns[1].key if len(table.columns) > 1 else table.columns[0].key
    y_label = table.columns[1].label if len(table.columns) > 1 else table.columns[0].label

    existing_y_cols = {
        s.y_column for p in result.plots.values() if p.table_id == table_id for s in p.series
    }
    for col in table.columns[1:]:
        if col.key not in existing_y_cols:
            y_col = col.key
            y_label = col.label
            break

    base_id = f"{table_id}_plot"
    idx = len(result.plots) + 1
    while f"{base_id}_{idx}" in result.plots:
        idx += 1
    plot_id = f"{base_id}_{idx}"
    title = f"{y_label} vs {x_label}"

    from setuav_studio.solver.results import PlotDefinition, PlotSeriesDef

    new_plot: PlotDefinition | None = None

    def _apply() -> None:
        nonlocal new_plot
        new_plot = result.add_plot(
            plot_id=plot_id,
            table_id=table_id,
            x_column=x_col,
            series=[PlotSeriesDef(y_column=y_col, label=f"{y_label} Curve")],
            title=title,
        )
        project.add_solver_result(result)

    api.edit_project(f"Add plot '{title}'", _apply)

    plot_payload = {
        "kind": "analysis_plot",
        "id": f"{result.id}:plot:{plot_id}",
        "result_id": result.id,
        "plot_id": plot_id,
        "config_id": config_id or getattr(getattr(result, "config", None), "config_id", None),
        "name": title,
    }
    api.set_selection(plot_payload)
    api.show_panel("studio:result")

    return new_plot
