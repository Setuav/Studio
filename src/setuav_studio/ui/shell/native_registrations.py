from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

from setuav_studio.api import (
    ComponentTypeContribution,
    PanelContribution,
)
from setuav_studio.solver.launch import run_analysis
from setuav_studio.ui.editor.component import BaseComponentEditor
from setuav_studio.ui.panels.project_explorer import ProjectExplorerPanel
from setuav_studio.ui.panels.properties import PropertiesPanel

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


def _can_edit_project(api: StudioAPI) -> bool:
    project = api.project
    return project is not None and not project.read_only


def _on_add_constant_triggered(api: StudioAPI) -> None:
    from setuav_studio.ui.panels.project_explorer.dialog_actions import (
        add_parameter_action,
    )

    add_parameter_action(api, is_constant=True)


def _on_add_constraint_triggered(api: StudioAPI) -> None:
    from setuav_studio.ui.panels.project_explorer.dialog_actions import (
        add_constraint_action,
    )

    add_constraint_action(api)


def _can_open_expression_assistant(api: StudioAPI) -> bool:
    if not _can_edit_project(api):
        return False
    from setuav_studio.ui.widget.table import ExpressionFocusTracker

    return ExpressionFocusTracker.has_active_editor()


def _on_open_expression_assistant(api: StudioAPI) -> None:
    from setuav_studio.ui.widget.table import ExpressionFocusTracker

    editor = ExpressionFocusTracker.get_active_editor()
    if editor is not None:
        editor.open_assistant()
    else:
        from PySide6.QtWidgets import QApplication

        from setuav_studio.ui.dialog.expression_dialog import AdvancedExpressionDialog

        dlg = AdvancedExpressionDialog(
            api=api,
            initial_expression="",
            title="Formula Assistant",
            is_boolean_constraint=False,
            parent=QApplication.activeWindow(),
        )
        dlg.exec()


POINT_MASS_TYPE = "org.setuav.core:point-mass"


def _on_add_point_mass_triggered(api: StudioAPI) -> None:
    """Add a point mass at the vehicle origin and select it."""
    project = api.project
    if project is None or project.read_only:
        return
    components = project.data["components"]
    ids = {str(c.get("id") or "") for c in components if isinstance(c, dict)}
    names = {str(c.get("name") or "") for c in components if isinstance(c, dict)}
    component_id, name = "point-mass", "Point Mass"
    suffix = 2
    while component_id in ids or name in names:
        component_id, name = f"point-mass-{suffix}", f"Point Mass {suffix}"
        suffix += 1
    component = {
        "kind": "component",
        "id": component_id,
        "name": name,
        "type": POINT_MASS_TYPE,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "mass": 50.0,
    }
    api.edit_project(f"Add {name}", lambda: project.data["components"].append(component))
    api.set_selection(component)


def register_native_contributions(api: StudioAPI) -> None:
    """Register built-in native panels, tree providers, and kind editors into the StudioAPI."""
    from setuav_studio.api import ToolbarContribution
    from setuav_studio.ui.viewport import StudioViewport

    # 1. Native Panels
    api.register_panel(
        PanelContribution(
            id="studio:project-explorer",
            title="Project Explorer",
            factory=lambda: ProjectExplorerPanel(api),
            area=Qt.DockWidgetArea.LeftDockWidgetArea,
            icon="fa6s.folder-tree",
        )
    )
    api.register_panel(
        PanelContribution(
            id="studio:viewer-3d",
            title="3D Viewer",
            factory=lambda: StudioViewport(api=api),
            area=Qt.DockWidgetArea.RightDockWidgetArea,
            icon="viewer_3d",
        )
    )
    api.register_panel(
        PanelContribution(
            id="studio:properties",
            title="Properties",
            factory=lambda: PropertiesPanel(api),
            area=Qt.DockWidgetArea.RightDockWidgetArea,
            icon="fa6s.sliders",
        )
    )
    from setuav_studio.ui.panels.results import ResultPanel

    api.register_panel(
        PanelContribution(
            id="studio:result",
            title="Result",
            factory=lambda: ResultPanel(api),
            area=Qt.DockWidgetArea.RightDockWidgetArea,
            icon="fa6s.square-poll-vertical",
        )
    )

    # 2. Native Toolbar Contributions
    api.register_toolbar_item(
        ToolbarContribution(
            id="org.setuav.studio.toolbar.add_constant",
            title="Add Constant",
            callback=lambda: _on_add_constant_triggered(api),
            icon="constant",
            enabled_when=lambda: _can_edit_project(api),
            group="parameters",
            order=10,
        )
    )
    api.register_toolbar_item(
        ToolbarContribution(
            id="org.setuav.studio.toolbar.expression_assistant",
            title="Formula Assistant",
            callback=lambda: _on_open_expression_assistant(api),
            icon="formula",
            enabled_when=lambda: _can_open_expression_assistant(api),
            group="parameters",
            order=15,
        )
    )
    api.register_toolbar_item(
        ToolbarContribution(
            id="org.setuav.studio.toolbar.add_constraint",
            title="Add Constraint",
            callback=lambda: _on_add_constraint_triggered(api),
            icon="constraint",
            enabled_when=lambda: _can_edit_project(api),
            group="parameters",
            order=20,
        )
    )
    api.register_toolbar_item(
        ToolbarContribution(
            id="org.setuav.studio.toolbar.add_point_mass",
            title="Add Point Mass",
            callback=lambda: _on_add_point_mass_triggered(api),
            icon="point_mass",
            enabled_when=lambda: _can_edit_project(api),
            group="model",
            order=150,
        )
    )
    api.register_toolbar_item(
        ToolbarContribution(
            id="org.setuav.studio.toolbar.run_analysis",
            title="Run Analysis",
            callback=lambda: run_analysis(api),
            icon="run_analysis",
            group="analysis",
            order=290,
        )
    )
    # 3. Native Kind Editors
    register_native_kind_editors(api)

    # 5. Native Component Types
    register_native_component_types(api)


def register_native_component_types(api: StudioAPI) -> None:
    """Register the component types the core itself defines."""
    api.register_component_type(
        ComponentTypeContribution(
            id=POINT_MASS_TYPE,
            name="Point Mass",
            icon="point_mass",
            editor=lambda component: BaseComponentEditor(api, component),
            category="Structure",
        )
    )


def register_native_kind_editors(api: StudioAPI) -> None:
    """Register built-in fallback editors for standard component and document kinds."""
    from setuav_studio.ui.editor import (
        AnalysisPlotPropertyEditor,
        AnalysisTablePropertyEditor,
        ConstraintPropertyEditor,
        ParameterPropertyEditor,
        SolverConfigPropertyEditor,
        VehicleSummaryEditor,
    )

    defaults = {
        "vehicle": lambda _selection: VehicleSummaryEditor(api),
        "parameter": lambda selection: ParameterPropertyEditor(api, selection),
        "constraint": lambda selection: ConstraintPropertyEditor(api, selection),
        "analysis_config": lambda selection: SolverConfigPropertyEditor(api, selection),
        "analysis_plot": lambda selection: AnalysisPlotPropertyEditor(api, selection),
        "analysis_table": lambda selection: AnalysisTablePropertyEditor(api, selection),
    }
    for kind, factory in defaults.items():
        if kind not in api._kind_editors:
            api.register_kind_editor(kind, factory)
