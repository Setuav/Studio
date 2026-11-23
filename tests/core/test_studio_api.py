"""Unit tests for StudioAPI public contracts, registries, event system, and undo/redo."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from PySide6.QtWidgets import QWidget

from setuav_studio import api
from setuav_studio.api import (
    ActionContribution,
    ComponentMenuItemContribution,
    ComponentTypeContribution,
    PanelContribution,
    SettingsPageContribution,
    StudioAPI,
    StudioEvents,
    ToolbarContribution,
    ToolbarMenuItemContribution,
    ToolContribution,
)
from setuav_studio.project import ProjectDocument
from tests._common import get_qapp


def _component(project: ProjectDocument, component_id: str) -> dict[str, Any]:
    component = project.get_component(component_id)
    assert component is not None, f"component {component_id!r} is missing"
    return component


@pytest.fixture(autouse=True)
def qapp() -> Any:
    return get_qapp()


# ==============================================================================
# 1. API Contract & Export Tests
# ==============================================================================


def test_public_api_exports_essential_contracts() -> None:
    expected_symbols = [
        "StudioAPI",
        "StudioPlugin",
        "PanelContribution",
        "ActionContribution",
        "ToolContribution",
        "ToolbarContribution",
        "ComponentTypeContribution",
        "ComponentMenuItemContribution",
        "SettingsPageContribution",
        "StudioEvents",
        "ParameterField",
        "Component",
        "UnsubscribeCallable",
    ]
    for symbol in expected_symbols:
        assert hasattr(api, symbol), f"setuav_studio.api missing export: {symbol}"


def test_host_services_are_not_exposed_on_public_api() -> None:
    studio_api = StudioAPI()
    internal_host_names = [
        "check_project_requirements",
        "mark_project_saved",
        "set_action_handler",
        "set_panel_handler",
        "set_progress_handler",
        "set_project",
        "set_project_requirement_checker",
        "set_status_handler",
        "set_toolbar_handler",
        "settings_pages",
        "undo_stack",
    ]
    for name in internal_host_names:
        assert not hasattr(studio_api, name), f"{name} should not be exposed on public StudioAPI"


def test_studio_events_enum_contract() -> None:
    events = StudioEvents
    assert events.PROJECT_OPENED == "project.opened"
    assert events.PROJECT_CLOSED == "project.closed"
    assert events.PROJECT_MODIFIED == "project.modified"
    assert events.UNITS_CHANGED == "units.changed"
    assert events.TASK_STARTED == "task.started"
    assert events.TASK_FINISHED == "task.finished"

    # Must be compatible with str
    assert isinstance(events.PROJECT_OPENED, str)
    assert not any(
        name.startswith(("AERODYNAMICS_", "FLIGHT_PERFORMANCE_")) for name in events.__members__
    )


def test_studio_api_exposes_units_service() -> None:
    studio_api = StudioAPI()
    assert studio_api.units is not None
    assert hasattr(studio_api.units, "to_display")
    assert hasattr(studio_api.units, "to_base")
    assert hasattr(studio_api.units, "get_unit_symbol")


# ==============================================================================
# 2. Component Type & Editor Registrations
# ==============================================================================


def test_component_type_registration_and_lookups() -> None:
    studio_api = StudioAPI()
    contrib = ComponentTypeContribution(
        id="org.test:sensor",
        name="Optical Sensor",
        category="Sensors",
    )
    studio_api.register_component_type(contrib)
    assert studio_api.get_component_type("org.test:sensor") == contrib
    assert studio_api.get_component_type_label("org.test:sensor") == "Optical Sensor"

    # Fallback for unregistered types converts id suffix to title
    assert studio_api.get_component_type_label("org.test:camera-mount") == "Camera Mount"

    # Re-registration with override=False raises ValueError
    with pytest.raises(ValueError):
        studio_api.register_component_type(contrib, override=False)

    # Re-registration with override=True updates
    updated = ComponentTypeContribution(
        id="org.test:sensor",
        name="Updated Sensor",
        category="Sensors",
    )
    studio_api.register_component_type(updated, override=True)
    assert studio_api.get_component_type("org.test:sensor") == updated
    assert studio_api.get_component_type_label("org.test:sensor") == "Updated Sensor"

    # Unregistration
    studio_api.unregister_component_type("org.test:sensor")
    assert studio_api.get_component_type("org.test:sensor") is None
    assert studio_api.get_component_type_label("org.test:sensor") == "Sensor"


def test_component_editor_and_kind_registration() -> None:
    studio_api = StudioAPI()
    wing_editor_dummy = QWidget()
    instance_editor_dummy = QWidget()

    studio_api.register_component_editor("org.test:wing", lambda _comp: wing_editor_dummy)
    studio_api.register_kind_editor("instance", lambda _comp: instance_editor_dummy)

    assert (
        studio_api.create_component_editor({"type": "org.test:wing", "kind": "component"})
        is wing_editor_dummy
    )
    assert studio_api.create_component_editor({"kind": "instance"}) is instance_editor_dummy

    # Duplicate registration with override=False rejects
    with pytest.raises(ValueError):
        studio_api.register_component_editor(
            "org.test:wing", lambda _comp: QWidget(), override=False
        )

    with pytest.raises(ValueError):
        studio_api.register_kind_editor("instance", lambda _comp: QWidget(), override=False)


def test_component_icon_registration() -> None:
    studio_api = StudioAPI()
    studio_api.register_component_icon("org.test:sensor", "fa6s.camera")

    icon = studio_api.get_component_icon({"type": "org.test:sensor", "kind": "component"})
    assert not icon.isNull()

    # Fallback to default component icon
    default_icon = studio_api.get_component_icon({"type": "unknown:item", "kind": "component"})
    assert not default_icon.isNull()

    # Reject duplicate icon registration when override=False
    with pytest.raises(ValueError):
        studio_api.register_component_icon("org.test:sensor", "fa6s.camera", override=False)


# ==============================================================================
# 3. Event Pub/Sub & Selection
# ==============================================================================


def test_event_publish_subscribe_and_unsubscribe() -> None:
    studio_api = StudioAPI()
    received_payloads: list[dict[str, Any]] = []

    unsubscribe = studio_api.subscribe("test.custom_event", received_payloads.append)
    studio_api.publish("test.custom_event", {"value": 42})
    studio_api.publish("test.custom_event", {"value": 84})

    assert received_payloads == [{"value": 42}, {"value": 84}]

    # Unsubscribe
    unsubscribe()
    studio_api.publish("test.custom_event", {"value": 999})
    assert len(received_payloads) == 2


def test_listener_errors_propagate_and_deleted_objects_are_dropped() -> None:
    studio_api = StudioAPI()

    def failing(_payload: Any) -> None:
        raise RuntimeError("listener bug")

    def deleted(_payload: Any) -> None:
        raise RuntimeError("Internal C++ object (QLabel) already deleted.")

    studio_api.subscribe("test.failing", failing)
    with pytest.raises(RuntimeError, match="listener bug"):
        studio_api.publish("test.failing")
    with pytest.raises(RuntimeError, match="listener bug"):
        studio_api.publish("test.failing")

    studio_api.subscribe("test.deleted", deleted)
    studio_api.publish("test.deleted")
    assert studio_api._event_subscribers["test.deleted"] == []

    # A selection listener receives the current selection when it subscribes.
    with pytest.raises(RuntimeError, match="listener bug"):
        studio_api.on_selection_changed(failing)
    with pytest.raises(RuntimeError, match="listener bug"):
        studio_api.set_selection({"id": "wing"})


def test_selection_changed_dispatch() -> None:
    studio_api = StudioAPI()
    selections: list[Any] = []
    studio_api.on_selection_changed(selections.append)

    comp = {"id": "wing", "name": "Main Wing"}
    studio_api.set_selection(comp)

    assert studio_api.current_selection == comp
    # Listener was called initially with None, then with comp
    assert selections == [None, comp]

    # Section selection
    studio_api.set_section_selection(("wing", 0, 1))
    assert studio_api.current_section_selection == ("wing", 0, 1)


# ==============================================================================
# 4. Project Manipulation & Undo / Redo
# ==============================================================================


def test_studio_api_project_edits_undo_redo() -> None:
    studio_api = StudioAPI()
    project = ProjectDocument(
        Path("test.json"),
        "json",
        {
            "components": [
                {
                    "id": "c1",
                    "name": "Main Wing",
                    "parameters": {"span": 2.0},
                    "extensions": {},
                }
            ],
            "extensions": {},
        },
    )
    studio_api._host.set_project(project)

    # 1. Edit project units
    def _change_units() -> None:
        project.data["units"] = {"length": "in"}

    studio_api.edit_project("Change project units", _change_units)
    assert project.data["units"] == {"length": "in"}
    assert studio_api.can_undo
    assert studio_api.undo_count == 1
    assert studio_api.undo_text == "Change project units"

    # Undo project edit
    studio_api.undo()
    assert "units" not in project.data
    assert studio_api.can_redo
    assert studio_api.redo_text == "Change project units"

    # Redo project edit
    studio_api.redo()
    assert project.data["units"] == {"length": "in"}

    # 2. Edit component parameter
    comp_c1 = project.get_component("c1")
    assert comp_c1 is not None

    def _change_span() -> None:
        comp_c1.setdefault("parameters", {})["span"] = 3.5

    studio_api.edit_component(comp_c1, "Update wing span", _change_span)
    assert _component(project, "c1")["parameters"]["span"] == 3.5

    # Undo component edit
    studio_api.undo()
    assert _component(project, "c1")["parameters"]["span"] == 2.0

    # Redo component edit
    studio_api.redo()
    assert _component(project, "c1")["parameters"]["span"] == 3.5


def test_studio_api_extension_edits_undo_redo() -> None:
    studio_api = StudioAPI()
    project = ProjectDocument(
        Path("test.json"),
        "json",
        {
            "components": [{"id": "c1", "name": "Part", "extensions": {}}],
            "extensions": {},
        },
    )
    studio_api._host.set_project(project)

    # Edit root extension
    studio_api.edit_project_extension(
        "org.test.battery",
        "Set battery config",
        lambda ext: ext.update({"cells": 6, "voltage": 22.2}),
    )
    assert project.data["extensions"]["org.test.battery"] == {"cells": 6, "voltage": 22.2}

    studio_api.undo()
    assert "org.test.battery" not in project.data["extensions"]

    studio_api.redo()
    assert project.data["extensions"]["org.test.battery"] == {"cells": 6, "voltage": 22.2}

    # Edit component extension
    studio_api.edit_component_extension(
        "c1",
        "org.test.aero",
        "Set airfoil polar",
        lambda ext: ext.update({"cl_max": 1.6}),
    )
    assert project.data["components"][0]["extensions"]["org.test.aero"] == {"cl_max": 1.6}

    studio_api.undo()
    assert "org.test.aero" not in project.data["components"][0]["extensions"]

    with pytest.raises(ValueError, match="No component 'missing'"):
        studio_api.edit_component_extension("missing", "org.test.aero", "Set", lambda ext: None)


def test_studio_api_attach_component_undo_redo() -> None:
    studio_api = StudioAPI()
    project = ProjectDocument(
        Path("test.json"),
        "json",
        {
            "components": [
                {
                    "id": "fuselage",
                    "transform": {"position": {"x": 0.0, "y": 0.0, "z": 0.0}},
                },
                {
                    "id": "wing",
                    "transform": {"position": {"x": 500.0, "y": 0.0, "z": 50.0}},
                },
            ]
        },
    )
    studio_api._host.set_project(project)

    wing_comp = project.get_component("wing")
    assert wing_comp is not None
    studio_api.attach_component(
        wing_comp, "fuselage", preserve_world_transform=True, description="Attach wing"
    )
    assert _component(project, "wing")["attach_to"] == "fuselage"

    studio_api.undo()
    assert "attach_to" not in _component(project, "wing")

    studio_api.redo()
    assert _component(project, "wing")["attach_to"] == "fuselage"


def _deletion_project(studio_api: StudioAPI) -> ProjectDocument:
    studio_api.register_component_type(
        ComponentTypeContribution(id="org.test:flap", name="Flap", subpart=True)
    )
    project = ProjectDocument(
        Path("test.json"),
        "json",
        {
            "components": [
                {"id": "wing", "transform": {"position": {"x": 500.0, "y": 0.0, "z": 50.0}}},
                {"id": "flap", "type": "org.test:flap", "attach_to": "wing"},
                {
                    "id": "pod",
                    "attach_to": "wing",
                    "transform": {"position": {"x": 100.0, "y": 0.0, "z": 0.0}},
                },
                {"id": "tail"},
            ],
            "extensions": {},
        },
    )
    studio_api._host.set_project(project)
    return project


def test_component_deletion_scope_includes_subparts() -> None:
    studio_api = StudioAPI()
    _deletion_project(studio_api)
    assert studio_api.component_deletion_scope(["wing"]) == {"wing", "flap"}
    assert studio_api.component_deletion_scope(["tail"]) == {"tail"}


def test_delete_components_is_one_undoable_edit() -> None:
    studio_api = StudioAPI()
    project = _deletion_project(studio_api)

    studio_api.delete_components(["wing"], "Delete wing")

    assert [c["id"] for c in project.data["components"]] == ["pod", "tail"]
    pod = _component(project, "pod")
    assert "attach_to" not in pod, "a component mounted on a deleted one moves to the vehicle"
    assert pod["transform"]["position"]["x"] == pytest.approx(600.0)
    assert studio_api.undo_count == 1
    assert studio_api.undo_text == "Delete wing"

    studio_api.undo()
    assert [c["id"] for c in project.data["components"]] == [
        "wing",
        "flap",
        "pod",
        "tail",
    ]
    assert _component(project, "pod")["attach_to"] == "wing"

    studio_api.redo()
    assert [c["id"] for c in project.data["components"]] == ["pod", "tail"]


def test_delete_components_needs_a_project() -> None:
    with pytest.raises(RuntimeError):
        StudioAPI().delete_components(["wing"], "Delete wing")


def test_component_menu_providers() -> None:
    studio_api = StudioAPI()
    chosen: list[str] = []
    add = ComponentMenuItemContribution(
        title="Add",
        children=(
            ComponentMenuItemContribution(title="Spar", callback=lambda: chosen.append("spar")),
            ComponentMenuItemContribution(title="Joint", callback=lambda: None, enabled=False),
        ),
    )

    def provider(component: dict[str, Any]) -> tuple[ComponentMenuItemContribution, ...]:
        return (add,) if component.get("type") == "org.test:wing" else ()

    studio_api.register_component_menu_provider("org.test.menu", provider)
    with pytest.raises(ValueError):
        studio_api.register_component_menu_provider("org.test.menu", provider)

    assert studio_api.component_menu_items({"id": "w", "type": "org.test:wing"}) == (add,)
    assert studio_api.component_menu_items({"id": "b", "type": "org.test:battery"}) == ()
    studio_api.unregister_component_menu_provider("org.test.menu")
    assert studio_api.component_menu_items({"id": "w", "type": "org.test:wing"}) == ()


def test_component_menu_items_take_a_callback_or_children() -> None:
    with pytest.raises(ValueError):
        ComponentMenuItemContribution(title="Nothing")
    with pytest.raises(ValueError):
        ComponentMenuItemContribution(
            title="Both",
            callback=lambda: None,
            children=(ComponentMenuItemContribution(title="Child", callback=lambda: None),),
        )
    nested = ComponentMenuItemContribution(
        title="Submenu",
        children=(ComponentMenuItemContribution(title="Child", callback=lambda: None),),
    )
    with pytest.raises(ValueError):
        ComponentMenuItemContribution(title="Too deep", children=(nested,))


# ==============================================================================
# 5. UI Contributions Lifecycle
# ==============================================================================


def test_panel_and_toolbar_contributions_registration() -> None:
    studio_api = StudioAPI()

    # Panel registration and host dispatch
    panel = PanelContribution(id="test.panel", title="Test Panel", factory=QWidget)
    studio_api.register_panel(panel)

    registered_panels: list[PanelContribution] = []
    removed_panels: list[str] = []
    studio_api._host.bind_panel_handlers(registered_panels.append, removed_panels.append)

    # Late binding flushes previously registered panel
    assert len(registered_panels) == 1
    assert registered_panels[0].id == "test.panel"

    studio_api.unregister_panel("test.panel")
    assert removed_panels == ["test.panel"]

    # Toolbar registration
    item = ToolbarContribution(id="test.action", title="Test Action", command="test:run")
    studio_api.register_toolbar_item(item)
    studio_api.unregister_toolbar_item("test.action")

    # Toolbar validation rejects conflicting actions
    with pytest.raises(ValueError):
        ToolbarContribution("invalid", "Invalid")  # Neither callback, command, nor menu_items

    with pytest.raises(ValueError):
        ToolbarContribution(
            "invalid",
            "Invalid",
            command="run",
            menu_items=(ToolbarMenuItemContribution("Menu", lambda: None),),
        )


def test_action_tool_and_settings_page_contributions() -> None:
    studio_api = StudioAPI()

    action = ActionContribution(menu="Tools/Analysis", title="Do Action", callback=lambda: None)
    studio_api.register_action(action)
    studio_api.unregister_action(action.menu, action.title)

    tool = ToolContribution(title="Sample Tool", callback=lambda: None)
    studio_api.register_tool(tool)
    studio_api.unregister_tool(tool)

    settings = SettingsPageContribution(
        id="org.test:settings", title="Plugin Settings", factory=QWidget
    )
    studio_api.register_settings_page(settings)
    assert studio_api._host.settings_pages() == (settings,)
    studio_api.unregister_settings_page("org.test:settings")
    assert studio_api._host.settings_pages() == ()


def test_project_property_is_canonical_and_readonly() -> None:
    studio_api = StudioAPI()
    assert studio_api.project is None

    project = ProjectDocument(Path("test.json"), "json", {"components": []})
    studio_api._host.set_project(project)
    assert studio_api.project is project
    with pytest.raises(AttributeError):
        cast(Any, studio_api).project = project


def test_components_derive_after_the_component_they_attach_to() -> None:
    studio = StudioAPI()
    components = [
        {"id": "flap", "type": "test:part", "attach_to": "wing"},
        {"id": "wing", "type": "test:part", "attach_to": "body"},
        {"id": "body", "type": "test:part"},
    ]
    studio._host.set_project(ProjectDocument(Path("test.json"), "json", {"components": components}))
    derived: list[str] = []
    studio.register_component_deriver("test:part", lambda c, _all: derived.append(str(c["id"])))

    studio.derive_components()

    assert derived == ["body", "wing", "flap"]


def test_a_component_that_cannot_be_derived_is_reported_and_the_rest_still_derive() -> None:
    studio = StudioAPI()
    components = [
        {"id": "a", "name": "Wing", "type": "test:part"},
        {"id": "b", "type": "test:part"},
    ]
    studio._host.set_project(ProjectDocument(Path("test.json"), "json", {"components": components}))
    messages: list[tuple[str, str]] = []
    studio._host.bind_status_handler(
        lambda message, level, _timeout: messages.append((message, level))
    )
    derived: list[str] = []

    def derive(component: dict[str, Any], _all: Any) -> None:
        if component["id"] == "a":
            raise ValueError("span must be positive")
        derived.append(str(component["id"]))

    studio.register_component_deriver("test:part", derive)
    studio.derive_components()

    assert derived == ["b"]
    assert messages == [("Cannot update Wing: span must be positive", "error")]


def test_new_analyses_with_a_taken_name_are_numbered() -> None:
    from setuav_studio.solver import SolverConfig

    studio_api = StudioAPI()
    project = ProjectDocument(Path("analyses.json"), "json", {"components": []})
    studio_api._host.set_project(project)

    for _ in range(3):
        studio_api.add_solver_config(SolverConfig(solver_id="demo", name="Alpha Sweep"))
    names = [config.name for config in project.solver_configs.values()]
    assert names == ["Alpha Sweep", "Alpha Sweep 2", "Alpha Sweep 3"]

    # Updating an analysis keeps the name it already has.
    first = next(iter(project.solver_configs.values()))
    studio_api.add_solver_config(first)
    assert [config.name for config in project.solver_configs.values()] == names


def test_solver_icons_follow_their_registration() -> None:
    studio_api = StudioAPI()
    assert not hasattr(studio_api, "solvers")
    studio_api.register_solver("demo", object, icon="demo_icon")
    assert studio_api.get_solver_class("demo") is object
    assert studio_api.solver_icon("demo") == "demo_icon"
    studio_api.unregister_solver("demo")
    assert studio_api.get_solver_class("demo") is None
    assert studio_api.solver_icon("demo") == "fa6s.chart-line"


def test_studio_api_not_retained_by_unit_manager_after_deletion() -> None:
    import gc
    import weakref

    received: list[object] = []
    studio_api = StudioAPI()
    studio_api.subscribe(StudioEvents.UNITS_CHANGED, received.append)
    studio_api.units.units_changed.emit()
    assert len(received) == 1

    ref = weakref.ref(studio_api)
    units = studio_api.units
    del studio_api
    gc.collect()
    assert ref() is None
    units.units_changed.emit()
    assert len(received) == 1


def test_modified_state_stays_dirty_across_undo_when_solver_results_change() -> None:
    from setuav_studio.solver import SolverConfig, SolverResult, SolverStatus

    studio_api = StudioAPI()
    project = ProjectDocument(
        Path("mod.json"), "json", {"parameters": {"k": 1.0}, "components": []}
    )
    studio_api._host.set_project(project)

    events: list[bool] = []
    studio_api.subscribe(StudioEvents.PROJECT_MODIFIED, events.append)

    # Adding a solver result on a clean project marks modified and emits PROJECT_MODIFIED.
    result = SolverResult(
        solver_id="demo",
        config=SolverConfig(solver_id="demo", name="Run 1"),
        status=SolverStatus.COMPLETED,
    )
    studio_api.add_solver_result(result)
    assert project.modified is True
    assert events == [True]

    # An undoable edit followed by undo must NOT clear modified while unsaved results exist.
    studio_api.edit_project("Change k", lambda: project.data["parameters"].update({"k": 2.0}))
    studio_api.undo()
    assert project.modified is True
    assert events == [True]

    # Saving clears both undo stack and outside-undo dirty state.
    studio_api._host.mark_project_saved()
    assert project.modified is False
    assert events[-1] is False

    # Removing a solver result also marks modified and notifies listeners.
    assert studio_api.remove_solver_result(result.id) is True
    assert project.modified is True
    assert events[-1] is True


def test_undo_clears_deleted_selection_and_properties_panel_editor() -> None:
    from PySide6.QtWidgets import QLabel

    from setuav_studio.ui.panels.properties import PropertiesPanel

    studio_api = StudioAPI()
    project = ProjectDocument(
        Path("sel.json"),
        "json",
        {"parameters": {}, "constraints": [], "components": []},
    )
    studio_api._host.set_project(project)
    panel = PropertiesPanel(studio_api)

    # 1. Add component, select it, then undo -> selection and editor clear cleanly.
    comp = {"id": "wing-1", "name": "Wing", "type": "org.setuav.core:generic", "mass": 100.0}
    studio_api.edit_project("Add wing", lambda: project.data["components"].append(comp))
    studio_api.set_selection(comp)
    assert studio_api.current_selection is not None
    assert panel._active_component_id == "wing-1"

    studio_api.undo()
    assert studio_api.current_selection is None
    assert panel._active_component_id is None
    assert isinstance(panel._current_widget, QLabel)

    # 2. Add parameter, select it, then undo -> selection clears cleanly.
    studio_api.edit_project("Add param", lambda: project.data["parameters"].update({"k": 5.0}))
    studio_api.set_selection({"kind": "parameter", "id": "param_k", "key": "k", "value": 5.0})
    assert studio_api.current_selection is not None
    studio_api.undo()
    assert studio_api.current_selection is None

    # 3. Add constraint, select it, then undo -> selection clears cleanly.
    constraint = {"id": "c1", "name": "Rule", "expression": "1 > 0", "enabled": True}
    studio_api.edit_project(
        "Add constraint", lambda: project.data["constraints"].append(constraint)
    )
    studio_api.set_selection({"kind": "constraint", **constraint})
    assert studio_api.current_selection is not None
    studio_api.undo()
    assert studio_api.current_selection is None

    panel.deleteLater()


def test_project_content_changed_event_and_destroyed_hook_cleanup() -> None:
    import gc
    import weakref

    from PySide6.QtCore import QCoreApplication, QEvent, QObject

    class _Receiver(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.seen: list[Any] = []

        def on_event(self, payload: Any) -> None:
            self.seen.append(payload)

    studio_api = StudioAPI()
    project = ProjectDocument(Path("ev.json"), "json", {"parameters": {"k": 1.0}, "components": []})
    studio_api._host.set_project(project)

    receiver = _Receiver()
    unsub = studio_api.subscribe(StudioEvents.PROJECT_CONTENT_CHANGED, receiver.on_event)
    assert len(studio_api._destroyed_hooks) == 1

    studio_api.edit_project("Change k", lambda: project.data["parameters"].update({"k": 2.0}))
    assert receiver.seen == [project]

    # Explicit unsubscribe removes both subscriber and destroyed hook cleanly.
    unsub()
    del unsub
    assert studio_api._destroyed_hooks == {}

    # Re-subscribe and delete receiver via Qt -> auto-cleaned on destroyed.
    studio_api.subscribe(StudioEvents.PROJECT_CONTENT_CHANGED, receiver.on_event)
    assert len(studio_api._destroyed_hooks) == 1
    receiver.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert studio_api._destroyed_hooks == {}
    assert studio_api._event_subscribers.get(StudioEvents.PROJECT_CONTENT_CHANGED) == []

    # Subscribing a live QObject does not pin StudioAPI alive after release.
    survivor = _Receiver()
    studio_api.subscribe(StudioEvents.PROJECT_CONTENT_CHANGED, survivor.on_event)
    api_ref = weakref.ref(studio_api)
    del studio_api
    gc.collect()
    assert api_ref() is None
    survivor.deleteLater()
