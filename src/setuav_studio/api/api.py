from __future__ import annotations

import dataclasses
import weakref
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias, cast

import shiboken6
from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon, QUndoStack
from PySide6.QtWidgets import QWidget

from setuav_studio.project import ProjectDocument
from setuav_studio.ui.style.icons import get_icon
from setuav_studio.utilities.listeners import dispatch_listeners

from .contributions import (
    ActionContribution,
    ComponentDeriver,
    ComponentMenuItemContribution,
    ComponentMenuProvider,
    ComponentTreeNodeContribution,
    ComponentTreeProvider,
    ComponentTypeContribution,
    PanelContribution,
    ProjectTreeNodeContribution,
    ProjectTreeProvider,
    SettingsPageContribution,
    ToolbarContribution,
    ToolContribution,
)
from .events import StudioEvents

if TYPE_CHECKING:
    from setuav_studio.solver.base import AbstractSolver, SolverConfig
    from setuav_studio.solver.results import SolverResult
    from setuav_studio.task.manager import TaskManager
    from setuav_studio.ui.viewport import StudioViewport
    from setuav_studio.units import UnitManager

from .host import _StudioHost
from .undo import (
    _ComponentEditCommand,
    _ProjectEditCommand,
    apply_diff,
    compute_dict_diff,
)

UnsubscribeCallable: TypeAlias = Callable[[], None]


def _qobject_callback_key(channel: str, callback: Any) -> tuple[str, int, int] | None:
    """Return a hashable non-retaining key for a bound method owned by a QObject."""
    owner = getattr(callback, "__self__", None)
    func = getattr(callback, "__func__", None)
    if isinstance(owner, QObject) and func is not None:
        return (channel, id(owner), id(func))
    return None


def _remove_callback_by_ids(listeners: list[Any], owner_id: int, func_id: int) -> None:
    listeners[:] = [
        cb
        for cb in listeners
        if not (
            id(getattr(cb, "__self__", None)) == owner_id
            and id(getattr(cb, "__func__", None)) == func_id
        )
    ]


class StudioAPI:
    """Public service surface passed to a plugin during activation.

    Plugins use this object to contribute UI elements, observe application
    state, edit project data with undo/redo support, publish events, and
    register schemas or domain providers. UI contributions and callbacks run on
    the Qt UI thread; long-running work must be delegated to a worker thread.

    Registration identifiers must be globally unique and should use the
    plugin's reverse-domain namespace. QObject-bound event subscribers are
    removed automatically when their owner is destroyed; other listeners and
    contributions should still be removed during plugin deactivation.
    """

    def __init__(self) -> None:
        self._project: ProjectDocument | None = None
        self.current_selection: Any | None = None
        self.current_section_selection: tuple[str, int, int] | None = None
        self.current_solver_config_id: str | None = None
        self._register_panel: Callable[[PanelContribution], None] | None = None
        self._unregister_panel: Callable[[str], None] | None = None
        self._show_panel: Callable[[str], None] | None = None
        self._pending_panels: list[PanelContribution] = []
        self._register_toolbar_item: Callable[[ToolbarContribution], None] | None = None
        self._unregister_toolbar_item: Callable[[str], None] | None = None
        self._refresh_toolbar_handler: Callable[[], None] | None = None
        self._pending_toolbar_items: list[ToolbarContribution] = []
        self._register_action: Callable[[ActionContribution], None] | None = None
        self._unregister_action: Callable[[str, str], None] | None = None
        self._pending_actions: list[ActionContribution] = []
        self._settings_pages: dict[str, SettingsPageContribution] = {}
        self._status_handler: Callable[[str, str, int], None] | None = None
        self._pending_status: list[tuple[str, str, int]] = []
        self._progress_handler: Callable[[int, int, str], None] | None = None
        self._project_listeners: list[Callable[[ProjectDocument], None]] = []
        self._solver_icons: dict[str, str] = {}
        self._project_content_listeners: list[Callable[[ProjectDocument], None]] = []
        self._modified_listeners: list[Callable[[bool], None]] = []
        self._selection_listeners: list[Callable[[Any | None], None]] = []
        self._section_selection_listeners: list[Callable[[tuple[str, int, int] | None], None]] = []
        self._solver_config_selection_listeners: list[Callable[[SolverConfig | None], None]] = []
        self._is_recomputing_expressions: bool = False
        self._dirty_outside_undo: bool = False
        self._last_notified_modified: bool | None = None
        self._component_editors: dict[
            str,
            Callable[[dict[str, Any]], QWidget],
        ] = {}
        self._kind_editors: dict[
            str,
            Callable[[dict[str, Any]], QWidget],
        ] = {}
        self._component_types: dict[str, ComponentTypeContribution] = {}
        self._component_icons: dict[str, str | Path | QIcon] = {}
        self._kind_icons: dict[str, str | Path | QIcon] = {}
        self._component_models: dict[str, Any] = {}
        self._component_tree_providers: dict[str, ComponentTreeProvider] = {}
        self._component_menu_providers: dict[str, ComponentMenuProvider] = {}
        self._component_derivers: dict[str, ComponentDeriver] = {}
        self._project_tree_providers: dict[str, ProjectTreeProvider] = {}
        self._project_requirement_checker: Callable[[dict[str, Any]], list[str]] | None = None
        self._event_subscribers: dict[str, list[Callable[[Any], None]]] = {}
        self._destroyed_hooks: dict[tuple[str, int, int], Callable[[], None]] = {}
        from setuav_studio.task.manager import TaskManager

        self._tasks = TaskManager(self)
        from setuav_studio.solver import SolverRunner

        self._solver_runner = SolverRunner(self)
        api_ref = weakref.ref(self)
        self._undo_stack = QUndoStack()

        def _on_clean(clean: bool) -> None:
            if (api := api_ref()) is not None:
                api._on_clean_changed(clean)

        def _notify_content() -> None:
            if (api := api_ref()) is not None:
                api._notify_project_content_changed()

        # Keep Qt-owned undo commands and signals off a strong reference cycle to self
        # so PySide6's cyclic GC never tears down QUndoStack/QUndoCommand out of order.
        self._weak_notify_content: Callable[[], None] = _notify_content
        self._undo_stack.cleanChanged.connect(_on_clean)
        self._host = _StudioHost(self)
        self._viewport: Any | None = None
        from setuav_studio.units import get_unit_manager

        unit_manager = get_unit_manager()

        def _on_units_changed() -> None:
            api = api_ref()
            if api is None:
                unit_manager.units_changed.disconnect(_on_units_changed)
                return
            api.publish(StudioEvents.UNITS_CHANGED)

        unit_manager.units_changed.connect(_on_units_changed)

    def __del__(self, _is_valid: Callable[[object], bool] = shiboken6.isValid) -> None:
        # Clear QUndoStack before cyclic GC tears down Python-subclassed QUndoCommands
        # out of order relative to their owning C++ QUndoStack.
        undo_stack = getattr(self, "_undo_stack", None)
        if undo_stack is not None and _is_valid(undo_stack):
            undo_stack.clear()

    @property
    def units(self) -> UnitManager:
        """Access application-wide unit manager and conversions."""
        from setuav_studio.units import get_unit_manager

        return get_unit_manager()

    @property
    def viewport(self) -> StudioViewport | None:
        """Return the central :class:`StudioViewport` instance, or *None*."""
        return self._viewport

    @property
    def tasks(self) -> TaskManager:
        """Central background task manager for asynchronous jobs."""
        return self._tasks

    @property
    def project(self) -> ProjectDocument | None:
        """Return the currently open project, or `None` when no project is open."""
        return self._project

    def register_panel(self, contribution: PanelContribution) -> None:
        """Register a dockable panel contribution.

        @param contribution Panel descriptor with a globally unique ID.
        """
        if self._register_panel is not None:
            self._register_panel(contribution)
        else:
            self._pending_panels.append(contribution)

    def unregister_panel(self, panel_id: str) -> None:
        """Unregister a previously contributed panel by ID."""
        self._pending_panels = [p for p in self._pending_panels if p.id != panel_id]
        if self._unregister_panel is not None:
            self._unregister_panel(panel_id)

    def show_panel(self, panel_id: str) -> None:
        """Show and bring a dock panel to the front by ID."""
        if self._show_panel is not None:
            self._show_panel(panel_id)

    def show_status(
        self,
        message: str,
        level: str = "info",
        timeout_ms: int = 5000,
    ) -> None:
        """Show a message in the shell status bar.

        Levels: "info", "success", "warning", "error". A timeout_ms of 0
        keeps the message until replaced or cleared.
        """
        if self._status_handler is not None:
            self._status_handler(message, level, timeout_ms)
        else:
            self._pending_status.append((message, level, timeout_ms))

    def clear_status(self) -> None:
        """Clear the current status-bar message."""
        if self._status_handler is not None:
            self._status_handler("", "info", 0)

    def report_progress(self, completed: int, total: int, label: str = "") -> None:
        """Report task progress to the shell status bar.

        A total of 0 (or completed >= total) hides the progress bar.
        """
        if self._progress_handler is not None:
            self._progress_handler(completed, total, label)

    def clear_progress(self) -> None:
        """Hide the status-bar progress indicator."""
        self.report_progress(1, 1, "")

    def _bind_destroyed(
        self,
        channel: str,
        callback: Any,
        get_list: Callable[[StudioAPI], list[Any] | None],
    ) -> None:
        key = _qobject_callback_key(channel, callback)
        if key is None or key in self._destroyed_hooks:
            return
        owner = callback.__self__
        _, owner_id, func_id = key
        api_ref = weakref.ref(self)
        owner_ref = weakref.ref(owner)

        def _on_destroyed(*_: Any) -> None:
            api = api_ref()
            if api is None:
                return
            api._destroyed_hooks.pop(key, None)
            listeners = get_list(api)
            if listeners is not None:
                _remove_callback_by_ids(listeners, owner_id, func_id)

        owner.destroyed.connect(_on_destroyed)

        def _disconnect() -> None:
            o = owner_ref()
            if o is not None:
                import contextlib

                import shiboken6

                if shiboken6.isValid(o):
                    with contextlib.suppress(RuntimeError, TypeError):
                        o.destroyed.disconnect(_on_destroyed)

        self._destroyed_hooks[key] = _disconnect

    def _unbind_destroyed(self, channel: str, callback: Any) -> None:
        key = _qobject_callback_key(channel, callback)
        if key is None:
            return
        disconnect = self._destroyed_hooks.pop(key, None)
        if disconnect is not None:
            disconnect()

    def subscribe(self, event_name: str, handler: Callable[[Any], None]) -> UnsubscribeCallable:
        """Subscribe a callback handler to a named studio event (Event Bus).

        Bound methods owned by a QObject are removed automatically when that
        QObject is destroyed. Returns an unsubscribe callable.
        """
        subscribers = self._event_subscribers.setdefault(event_name, [])
        if handler not in subscribers:
            subscribers.append(handler)
            self._bind_destroyed(
                f"event:{event_name}",
                handler,
                lambda api, ev=event_name: api._event_subscribers.get(ev),
            )
        return lambda: self.unsubscribe(event_name, handler)

    def unsubscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Unsubscribe a callback handler from a named studio event."""
        subscribers = self._event_subscribers.get(event_name, [])
        if handler in subscribers:
            subscribers.remove(handler)
        self._unbind_destroyed(f"event:{event_name}", handler)

    def publish(self, event_name: str, payload: Any = None) -> None:
        """Publish an event to all subscribed listeners; a subscriber's error propagates."""
        dispatch_listeners(self._event_subscribers.get(event_name, []), payload)

    def register_toolbar_item(self, contribution: ToolbarContribution) -> None:
        """Register an action to the main toolbar."""
        if self._register_toolbar_item is not None:
            self._register_toolbar_item(contribution)
        else:
            self._pending_toolbar_items.append(contribution)

    def unregister_toolbar_item(self, contribution_id: str) -> None:
        """Unregister a previously contributed toolbar action by ID."""
        self._pending_toolbar_items = [
            item for item in self._pending_toolbar_items if item.id != contribution_id
        ]
        if self._unregister_toolbar_item is not None:
            self._unregister_toolbar_item(contribution_id)

    def refresh_toolbar_states(self) -> None:
        """Request the shell to re-evaluate and refresh all toolbar item states."""
        if self._refresh_toolbar_handler is not None:
            self._refresh_toolbar_handler()

    def register_action(self, contribution: ActionContribution) -> None:
        """Register an action to the menu path declared by the contribution."""
        if self._register_action is not None:
            self._register_action(contribution)
        else:
            self._pending_actions.append(contribution)

    def unregister_action(self, menu: str, title: str) -> None:
        """Unregister a contributed menu action by menu path and title."""
        self._pending_actions = [
            a for a in self._pending_actions if not (a.menu == menu and a.title == title)
        ]
        if self._unregister_action is not None:
            self._unregister_action(menu, title)

    def register_settings_page(self, contribution: SettingsPageContribution) -> None:
        """Register a category to the application Settings dialog.

        Plugins may register pages during ``activate`` and remove them during
        ``deactivate``. Pages are created lazily when the dialog is opened.
        """
        if contribution.id in self._settings_pages:
            raise ValueError(f"A settings page is already registered for: {contribution.id}")
        self._settings_pages[contribution.id] = contribution

    def unregister_settings_page(self, page_id: str) -> None:
        """Unregister a plugin settings page by ID."""
        self._settings_pages.pop(page_id, None)

    def register_tool(self, contribution: ToolContribution) -> None:
        """Register a Tools-menu command from a compact tool descriptor."""
        menu_path = f"Tools/{contribution.group}" if contribution.group else "Tools"
        self.register_action(
            ActionContribution(
                menu=menu_path,
                title=contribution.title,
                callback=contribution.callback,
                icon=contribution.icon,
                shortcut=contribution.shortcut,
            )
        )

    def unregister_tool(self, contribution: ToolContribution) -> None:
        """Unregister a Tools-menu command previously registered with register_tool."""
        menu_path = f"Tools/{contribution.group}" if contribution.group else "Tools"
        self.unregister_action(menu_path, contribution.title)

    def on_project_changed(
        self, listener: Callable[[ProjectDocument], None]
    ) -> UnsubscribeCallable:
        """Subscribe to project replacement and receive the current project immediately.

        Returns an unsubscribe callable.
        """
        if listener not in self._project_listeners:
            self._project_listeners.append(listener)
            self._bind_destroyed("project", listener, lambda api: api._project_listeners)
        if self._project is not None:
            listener(self._project)
        return lambda: self.remove_project_listener(listener)

    def on_project_content_changed(
        self,
        listener: Callable[[ProjectDocument], None],
    ) -> UnsubscribeCallable:
        """Subscribe to edits made within the current project.

        Returns an unsubscribe callable.
        """
        if listener not in self._project_content_listeners:
            self._project_content_listeners.append(listener)
            self._bind_destroyed(
                "project_content", listener, lambda api: api._project_content_listeners
            )
        return lambda: self.remove_project_content_listener(listener)

    def remove_project_content_listener(
        self,
        listener: Callable[[ProjectDocument], None],
    ) -> None:
        """Unsubscribe a project-content listener."""
        if listener in self._project_content_listeners:
            self._project_content_listeners.remove(listener)
        self._unbind_destroyed("project_content", listener)

    def on_modified_changed(self, listener: Callable[[bool], None]) -> UnsubscribeCallable:
        """Subscribe to project modified-state changes and receive current state.

        Returns an unsubscribe callable.
        """
        if listener not in self._modified_listeners:
            self._modified_listeners.append(listener)
            self._bind_destroyed("modified", listener, lambda api: api._modified_listeners)
        listener(bool(self._project and self._project.modified))
        return lambda: self.remove_modified_listener(listener)

    def remove_modified_listener(self, listener: Callable[[bool], None]) -> None:
        """Unsubscribe a project modified-state listener."""
        if listener in self._modified_listeners:
            self._modified_listeners.remove(listener)
        self._unbind_destroyed("modified", listener)

    def component_color(self, component_id: str) -> str:
        """The ``#RRGGBB`` color component ``component_id`` is drawn in.

        A component without a color of its own is drawn in the default gray, and an
        instance in its source's color.
        """
        from setuav_studio.model.appearance import component_color

        if self._project is None:
            raise LookupError("No project is open.")
        components = {
            str(c["id"]): c for c in self._project.data["components"] if isinstance(c, dict)
        }
        if component_id not in components:
            raise LookupError(f"Component {component_id!r} is not in the project.")
        return component_color(components[component_id], components)

    def set_component_color(self, component_id: str, color: str | None) -> None:
        """Set a component's ``#RRGGBB`` color as one undoable edit; None restores the default."""
        from setuav_studio.model.appearance import is_hex_color

        if color is not None and not is_hex_color(color):
            raise ValueError(f"Expected a #RRGGBB color, got {color!r}")
        component = self._project.get_component(component_id) if self._project else None
        if component is None:
            raise LookupError(f"Component {component_id!r} is not in the project.")

        def change() -> None:
            if color is None:
                component.pop("color", None)
            else:
                component["color"] = color.upper()

        name = component.get("name") or component_id
        self.edit_component(component, f"Set color of {name}", change)

    def edit_component(
        self,
        component: dict[str, Any],
        description: str,
        change: Callable[[], None],
    ) -> None:
        """Apply one undoable edit to a component.

        @param component Mutable component object owned by the current project.
        @param description Human-readable undo command text.
        @param change Callback that performs the mutation.
        """
        comp_id = str(component.get("id") or "")
        live_component = (
            self._project.get_component(comp_id) if self._project is not None and comp_id else None
        )
        target = live_component if live_component is not None else component

        before = deepcopy(target)
        change()
        if target is not component:
            comp_diffs = compute_dict_diff(target, component)
            for path, _, val in comp_diffs:
                apply_diff(target, path, val)

        diffs = compute_dict_diff(before, target)
        if not diffs:
            return

        self._undo_stack.push(
            _ComponentEditCommand(
                target,
                diffs,
                description,
                self._weak_notify_content,
                source=component if target is not component else None,
            )
        )

    def attach_component(
        self,
        component: dict[str, Any],
        target_id: str | None,
        *,
        preserve_world_transform: bool,
        description: str | None = None,
    ) -> None:
        """Attach a component to another component, or to the vehicle, with undo support.

        @param component The component to attach.
        @param target_id The component to attach to, or None for the vehicle.
        @param preserve_world_transform When True, recomputes the component's position
            and rotation relative to the new target so it stays where it is; when False,
            keeps them, so the component moves with the target's frame.
        @param description Custom undo description, or None for automatic description.
        """
        from setuav_studio.utilities.transform import attach_component

        if self._project is None:
            raise RuntimeError("No project is open.")

        comp_name = str(component.get("name") or component.get("id") or "component")
        cmd_desc = description or f"Attach {comp_name} to {target_id or 'Vehicle'}"

        def change() -> None:
            attach_component(
                component,
                target_id,
                self._project,
                preserve_world_transform=preserve_world_transform,
            )

        self.edit_component(component, cmd_desc, change)

    @property
    def subpart_types(self) -> frozenset[str]:
        """Component types registered as parts of the component they attach to."""
        return frozenset(
            type_id for type_id, contrib in self._component_types.items() if contrib.subpart
        )

    def edit_project(
        self,
        description: str,
        change: Callable[[], None],
    ) -> None:
        """Apply one undoable edit to the current project data."""
        if self._project is None:
            change()
            return
        before = deepcopy(self._project.data)
        change()
        diffs = compute_dict_diff(before, self._project.data)
        if not diffs:
            return
        self._undo_stack.push(
            _ProjectEditCommand(
                self._project,
                diffs,
                description,
                self._weak_notify_content,
            )
        )

    def edit_project_extension(
        self,
        namespace: str,
        description: str,
        change: Callable[[dict[str, Any]], None],
    ) -> None:
        """Edit root-level extension data for a given namespace with full Undo/Redo tracking."""
        if self._project is None:
            return

        def wrapper() -> None:
            assert self._project is not None
            if "extensions" not in self._project.data or not isinstance(
                self._project.data["extensions"], dict
            ):
                self._project.data["extensions"] = {}
            ext = self._project.data["extensions"].setdefault(namespace, {})
            change(ext)

        self.edit_project(description, wrapper)

    def edit_component_extension(
        self,
        component_id: str,
        namespace: str,
        description: str,
        change: Callable[[dict[str, Any]], None],
    ) -> None:
        """Edit component-level extension data for a given namespace with full Undo/Redo tracking.

        Raises ValueError when the project has no component ``component_id``.
        """
        if self._project is None:
            return
        comp = self._project.get_component(component_id)
        if comp is None:
            raise ValueError(f"No component {component_id!r} in the project")

        def wrapper() -> None:
            if "extensions" not in comp or not isinstance(comp["extensions"], dict):
                comp["extensions"] = {}
            ext = comp["extensions"].setdefault(namespace, {})
            change(ext)

        self.edit_component(comp, description, wrapper)

    @contextmanager
    def transaction(self, description: str) -> Generator[None, None, None]:
        """Context manager to group multiple edits into a single atomic Undo/Redo command."""
        self.begin_macro(description)
        try:
            yield
        finally:
            self.end_macro()

    def begin_macro(self, description: str) -> None:
        """Begin a compound Undo macro."""
        self._undo_stack.beginMacro(description)

    def end_macro(self) -> None:
        """End the current compound Undo macro."""
        self._undo_stack.endMacro()

    def _resolve_live_selection(self, selection: Any | None) -> Any | None:
        """Return the live project object for ``selection``, or None if it was deleted."""
        if selection is None or self._project is None or not isinstance(selection, dict):
            return selection
        kind = str(selection.get("kind") or "")
        if kind in ("", "component"):
            comp_id = str(selection.get("id") or "")
            if comp_id:
                return self._project.get_component(comp_id)
            return selection
        if kind == "parameter":
            key = selection.get("key")
            params = self._project.data.get("parameters")
            if isinstance(key, str) and (not isinstance(params, dict) or key not in params):
                return None
            return selection
        if kind == "constraint":
            cid = str(selection.get("id") or "")
            constraints = self._project.data.get("constraints")
            if cid and not (
                isinstance(constraints, list)
                and any(isinstance(c, dict) and c.get("id") == cid for c in constraints)
            ):
                return None
            return selection
        if kind == "analysis_config":
            cid = str(selection.get("id") or "")
            if cid and self._project.get_solver_config(cid) is None:
                return None
            return selection
        return selection

    def undo(self) -> None:
        """Undo the most recent project or component edit when available."""
        if self._undo_stack.canUndo():
            self._undo_stack.undo()
            self.set_selection(self._resolve_live_selection(self.current_selection))

    def redo(self) -> None:
        """Redo the most recently undone edit when available."""
        if self._undo_stack.canRedo():
            self._undo_stack.redo()
            self.set_selection(self._resolve_live_selection(self.current_selection))

    @property
    def can_undo(self) -> bool:
        """Return whether an undo step is currently available."""
        return self._undo_stack.canUndo()

    @property
    def can_redo(self) -> bool:
        """Return whether a redo step is currently available."""
        return self._undo_stack.canRedo()

    @property
    def undo_count(self) -> int:
        """Return the number of commands currently on the undo stack."""
        return self._undo_stack.count()

    @property
    def undo_text(self) -> str:
        """Return the description of the next command to undo, if any."""
        return self._undo_stack.undoText()

    @property
    def redo_text(self) -> str:
        """Return the description of the next command to redo, if any."""
        return self._undo_stack.redoText()

    def notify_project_content_changed(self) -> None:
        """Explicitly notify listeners that project content was updated or needs refresh."""
        self._notify_project_content_changed()

    @property
    def expression_diagnostics(self) -> list[dict[str, str]]:
        """Diagnostics collected from the most recent project expression evaluation."""
        return list(self._project.expression_diagnostics) if self._project is not None else []

    def _show_expression_diagnostics(self) -> None:
        diagnostics = self.expression_diagnostics
        if not diagnostics:
            return
        first = diagnostics[0]
        loc = (
            f"{first['component_id']}.{first['path']}"
            if first.get("component_id")
            else first.get("path", "")
        )
        extra = f" (+{len(diagnostics) - 1} more)" if len(diagnostics) > 1 else ""
        self.show_status(
            f"Expression error at {loc}: {first['message']}{extra}",
            "error",
            6000,
        )

    def recompute_project_expressions(self) -> list[dict[str, str]]:
        """Evaluate all parametric formulas across the project and return any diagnostics."""
        if self._project is None:
            return []
        from setuav_studio.project.evaluator import recompute_project_expressions

        diagnostics = recompute_project_expressions(self._project, api=self)
        self._show_expression_diagnostics()
        return diagnostics

    def register_solver(self, solver_id: str, solver_cls: Any, icon: str | None = None) -> None:
        """Register a solver class by solver ID.

        @param icon Optional icon name shown for the solver's analyses in the project tree.
        """
        self._solver_runner.register_solver(solver_id, solver_cls)
        if icon is not None:
            self._solver_icons[solver_id] = icon

    def unregister_solver(self, solver_id: str) -> None:
        """Unregister a solver class by solver ID."""
        self._solver_runner.unregister_solver(solver_id)
        self._solver_icons.pop(solver_id, None)

    def get_solver_class(self, solver_id: str) -> type[AbstractSolver] | None:
        """Return the registered solver class for ``solver_id``, or ``None``."""
        return self._solver_runner.get_solver_class(solver_id)

    def solver_icon(self, solver_id: str) -> str:
        """The icon name of the solver's analyses; a generic chart unless one was registered."""
        return self._solver_icons.get(solver_id, "fa6s.chart-line")

    def run_solver(
        self,
        solver: Any,
        on_complete: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
        priority: Any = None,
    ) -> Any:
        """Run a solver asynchronously in the background via TaskManager."""
        from setuav_studio.task import TaskPriority

        task_priority = priority if priority is not None else TaskPriority.NORMAL
        return self._solver_runner.run_solver(
            solver,
            on_complete=on_complete,
            on_error=on_error,
            on_cancelled=on_cancelled,
            priority=task_priority,
        )

    def get_solver_results(self) -> dict[str, SolverResult]:
        """Return the dictionary of solver results in the current project."""
        if self._project is None:
            return {}
        return self._project.solver_results

    def get_solver_result(self, result_id: str) -> SolverResult | None:
        """Retrieve a solver result by ID from the current project."""
        if self._project is None:
            return None
        return self._project.get_solver_result(result_id)

    def add_solver_result(self, result: SolverResult) -> None:
        """Add or update a solver result in the current project."""
        if self._project is None:
            return
        self._project.add_solver_result(result)
        self._dirty_outside_undo = True
        self._sync_modified_state()
        self._notify_project_content_changed()

    def remove_solver_result(self, result_id: str) -> bool:
        """Remove a solver result by ID from the current project."""
        if self._project is None:
            return False
        removed = self._project.remove_solver_result(result_id)
        if removed:
            self._dirty_outside_undo = True
            self._sync_modified_state()
            self._notify_project_content_changed()
        return removed

    def on_solver_config_selection_changed(
        self, listener: Callable[[SolverConfig | None], None]
    ) -> UnsubscribeCallable:
        """Subscribe to active solver configuration selection changes.

        Returns an unsubscribe callable.
        """
        if listener not in self._solver_config_selection_listeners:
            self._solver_config_selection_listeners.append(listener)
            self._bind_destroyed(
                "solver_config_selection",
                listener,
                lambda api: api._solver_config_selection_listeners,
            )
        return lambda: self.remove_solver_config_selection_listener(listener)

    def remove_solver_config_selection_listener(
        self,
        listener: Callable[[SolverConfig | None], None],
    ) -> None:
        """Unsubscribe a solver configuration selection listener."""
        if listener in self._solver_config_selection_listeners:
            self._solver_config_selection_listeners.remove(listener)
        self._unbind_destroyed("solver_config_selection", listener)

    def set_current_solver_config(self, config_id: str | None) -> None:
        """Set the active solver config selection by ID and notify listeners."""
        self.current_solver_config_id = config_id
        active_config = self.get_current_solver_config()
        dispatch_listeners(self._solver_config_selection_listeners, active_config)

    def get_current_solver_config(self) -> SolverConfig | None:
        """Return the currently selected SolverConfig, or None."""
        if self._project is None or self.current_solver_config_id is None:
            return None
        return self._project.get_solver_config(self.current_solver_config_id)

    def get_solver_configs(self) -> dict[str, SolverConfig]:
        """Return all SolverConfig objects stored in the current project."""
        if self._project is None:
            return {}
        return self._project.solver_configs

    def get_solver_config(self, config_id: str) -> SolverConfig | None:
        """Retrieve a SolverConfig by ID from the current project."""
        if self._project is None:
            return None
        return self._project.get_solver_config(config_id)

    def add_solver_config(self, config: SolverConfig) -> None:
        """Add or update a SolverConfig in the current project, as one undoable
        edit, and make it the active one.

        A new config whose name another analysis already has is numbered, like
        components: "Alpha Sweep Analysis 2"; an update keeps its name.
        """
        project = self._project
        if project is None:
            return
        existing = project.solver_configs
        if config.config_id not in existing:
            taken = {other.name for other in existing.values()}
            base, suffix, name = config.name, 2, config.name
            while name in taken:
                name = f"{base} {suffix}"
                suffix += 1
            config = dataclasses.replace(config, name=name)
        self.edit_project(
            f"Set analysis '{config.name}'", lambda: project.add_solver_config(config)
        )
        self.set_current_solver_config(config.config_id)

    def remove_solver_config(self, config_id: str) -> bool:
        """Remove a SolverConfig by ID from the current project as one undoable edit."""
        project = self._project
        if project is None or project.get_solver_config(config_id) is None:
            return False

        def change() -> None:
            project.remove_solver_config(config_id)

        self.edit_project("Remove analysis", change)
        if self.current_solver_config_id == config_id:
            self.set_current_solver_config(None)
        return True

    def get_aircraft_mass_properties(self) -> Any:
        """Calculate and return aggregate aircraft mass, center of gravity, and inertia tensor."""
        if self._project is None:
            from setuav_studio.model.mass import InertiaTensor, MassProperties

            return MassProperties(
                mass_kg=0.0,
                cg_body_m=(0.0, 0.0, 0.0),
                inertia_cg_kg_m2=InertiaTensor(),
            )
        return self._project.mass_properties

    def _notify_project_content_changed(self) -> None:
        if self._project is None:
            return

        if not self._is_recomputing_expressions:
            self._is_recomputing_expressions = True
            try:
                from setuav_studio.project.evaluator import recompute_project_expressions

                recompute_project_expressions(self._project, api=self)
                self._show_expression_diagnostics()
            finally:
                self._is_recomputing_expressions = False

        dispatch_listeners(self._project_content_listeners, self._project)
        self.publish(StudioEvents.PROJECT_CONTENT_CHANGED, self._project)
        if (
            self.current_selection is not None
            and self._resolve_live_selection(self.current_selection) is None
        ):
            self.set_selection(None)

    def _sync_modified_state(
        self,
        *,
        clean: bool | None = None,
        force_notify: bool = False,
    ) -> None:
        if clean is None:
            import shiboken6

            clean = self._undo_stack.isClean() if shiboken6.isValid(self._undo_stack) else True
        modified = (not clean) or self._dirty_outside_undo
        if self._project is not None:
            self._project.modified = modified
        if force_notify or self._last_notified_modified != modified:
            self._last_notified_modified = modified
            dispatch_listeners(self._modified_listeners, modified)
            self.publish(StudioEvents.PROJECT_MODIFIED, modified)

    def _on_clean_changed(self, clean: bool) -> None:
        self._sync_modified_state(clean=clean)

    def on_selection_changed(self, listener: Callable[[Any | None], None]) -> UnsubscribeCallable:
        """Subscribe to selection changes and receive the current selection.

        Returns an unsubscribe callable.
        """
        if listener not in self._selection_listeners:
            self._selection_listeners.append(listener)
            self._bind_destroyed("selection", listener, lambda api: api._selection_listeners)
        listener(self.current_selection)
        return lambda: self.remove_selection_listener(listener)

    def set_selection(self, selection: Any | None) -> None:
        """Set the application selection and notify listeners."""
        self.current_selection = selection
        dispatch_listeners(self._selection_listeners, selection)
        self.publish(StudioEvents.SELECTION_CHANGED, selection)

    def on_section_selection_changed(
        self,
        listener: Callable[[tuple[str, int, int] | None], None],
    ) -> UnsubscribeCallable:
        """Subscribe to geometry-section selection changes.

        Returns an unsubscribe callable.
        """
        if listener not in self._section_selection_listeners:
            self._section_selection_listeners.append(listener)
            self._bind_destroyed(
                "section_selection", listener, lambda api: api._section_selection_listeners
            )
        listener(self.current_section_selection)
        return lambda: self.remove_section_selection_listener(listener)

    def remove_section_selection_listener(
        self,
        listener: Callable[[tuple[str, int, int] | None], None],
    ) -> None:
        """Unsubscribe a geometry-section selection listener."""
        if listener in self._section_selection_listeners:
            self._section_selection_listeners.remove(listener)
        self._unbind_destroyed("section_selection", listener)

    def set_section_selection(
        self,
        selection: tuple[str, int, int] | None,
    ) -> None:
        """Set the selected component, section, and side tuple."""
        self.current_section_selection = selection
        dispatch_listeners(self._section_selection_listeners, selection)
        self.publish(StudioEvents.SECTION_SELECTION_CHANGED, selection)

    def register_component_type(
        self,
        contribution: ComponentTypeContribution,
        *,
        override: bool = True,
    ) -> None:
        """Register a component type descriptor defining name, icon, model, or editor.

        @param contribution Component type descriptor.
        @param override Whether to override or enrich an existing component type registration.
                        Defaults to True to allow plugins to register implementations for native types.
        """
        if contribution.id in self._component_types and not override:
            raise ValueError(f"A component type is already registered for: {contribution.id}")
        self._component_types[contribution.id] = contribution
        if contribution.icon is not None:
            self._component_icons[contribution.id] = contribution.icon
        if contribution.model is not None:
            self._component_models[contribution.id] = contribution.model
        if contribution.editor is not None:
            self._component_editors[contribution.id] = contribution.editor

    def unregister_component_type(self, type_id: str) -> None:
        """Unregister a component type descriptor and its associated resources."""
        contrib = self._component_types.pop(type_id, None)
        if contrib is not None:
            if contrib.icon is not None and self._component_icons.get(type_id) == contrib.icon:
                self.unregister_component_icon(type_id)
            if contrib.model is not None and self._component_models.get(type_id) == contrib.model:
                self.unregister_component_model(type_id)
            if (
                contrib.editor is not None
                and self._component_editors.get(type_id) == contrib.editor
            ):
                self.unregister_component_editor(type_id)

    def get_component_type(self, type_id: str) -> ComponentTypeContribution | None:
        """Retrieve a registered component type contribution by ID."""
        return self._component_types.get(type_id)

    def get_component_type_label(self, type_id: str) -> str:
        """Return the user-friendly label for a component type ID."""
        contrib = self._component_types.get(type_id)
        if contrib is not None and contrib.name:
            return contrib.name
        clean = type_id.split(":")[-1] if ":" in type_id else type_id
        return clean.replace("-", " ").replace("_", " ").title()

    def register_component_editor(
        self,
        component_type: str,
        factory: Callable[[dict[str, Any]], QWidget],
        *,
        override: bool = True,
    ) -> None:
        """Register an editor factory for one fully qualified component type."""
        if component_type in self._component_editors and not override:
            raise ValueError(f"A component editor is already registered for: {component_type}")
        self._component_editors[component_type] = factory

    def unregister_component_editor(self, component_type: str) -> None:
        """Unregister the editor factory registered for a component type."""
        self._component_editors.pop(component_type, None)

    def register_kind_editor(
        self,
        component_kind: str,
        factory: Callable[[dict[str, Any]], QWidget],
        *,
        override: bool = True,
    ) -> None:
        """Register a fallback editor factory for a component kind."""
        if component_kind in self._kind_editors and not override:
            raise ValueError(
                f"An editor is already registered for component kind: {component_kind}"
            )
        self._kind_editors[component_kind] = factory

    def unregister_kind_editor(self, component_kind: str) -> None:
        """Unregister the fallback editor registered for a component kind."""
        self._kind_editors.pop(component_kind, None)

    def has_kind_editor(self, component_kind: str) -> bool:
        """Return whether a fallback editor is registered for ``component_kind``."""
        return component_kind in self._kind_editors

    def create_component_editor(
        self,
        component: dict[str, Any],
    ) -> QWidget | None:
        component_type = component.get("type")
        factory = (
            self._component_editors.get(component_type) if isinstance(component_type, str) else None
        )
        if factory is None:
            component_kind = component.get("kind")
            if isinstance(component_kind, str):
                factory = self._kind_editors.get(component_kind)
        if factory is not None:
            return factory(component)

        # Without an editor, a component model's parameter fields give one.
        model_cls = (
            self._component_models.get(component_type) if isinstance(component_type, str) else None
        )
        from setuav_studio.model.component import Component

        if isinstance(model_cls, type) and issubclass(model_cls, Component):
            fields = model_cls.get_fields()
            if fields:
                from setuav_studio.ui.editor.component import BaseComponentEditor

                return BaseComponentEditor(cast(Any, self), component, fields)
        return None

    def register_component_icon(
        self,
        component_type: str,
        icon: str | Path | QIcon,
        *,
        override: bool = True,
    ) -> None:
        """Register an icon for one fully qualified component type."""
        if component_type in self._component_icons and not override:
            raise ValueError(f"An icon is already registered for component type: {component_type}")
        self._component_icons[component_type] = icon

    def unregister_component_icon(self, component_type: str) -> None:
        """Unregister the icon registered for a component type."""
        self._component_icons.pop(component_type, None)

    def register_kind_icon(
        self,
        component_kind: str,
        icon: str | Path | QIcon,
        *,
        override: bool = True,
    ) -> None:
        """Register a fallback icon for a component kind."""
        if component_kind in self._kind_icons and not override:
            raise ValueError(f"An icon is already registered for component kind: {component_kind}")
        self._kind_icons[component_kind] = icon

    def unregister_kind_icon(self, component_kind: str) -> None:
        """Unregister the fallback icon registered for a component kind."""
        self._kind_icons.pop(component_kind, None)

    def get_component_icon(self, component: dict[str, Any]) -> QIcon:
        component_type = component.get("type")
        if isinstance(component_type, str):
            if component_type in self._component_icons:
                return get_icon(self._component_icons[component_type])
            contrib = self._component_types.get(component_type)
            if contrib is not None and contrib.icon is not None:
                return get_icon(contrib.icon)

        component_kind = component.get("kind")
        if isinstance(component_kind, str) and component_kind in self._kind_icons:
            return get_icon(self._kind_icons[component_kind])

        return get_icon("component")

    def register_component_model(
        self,
        component_type: str,
        model_factory: Any,
    ) -> None:
        """Register a domain model class or factory for a component type."""
        self._component_models[component_type] = model_factory

    def unregister_component_model(self, component_type: str) -> None:
        """Unregister a registered component model by component type."""
        self._component_models.pop(component_type, None)

    def create_component_model(
        self,
        component: dict[str, Any],
    ) -> Any:
        """Instantiate the domain model object for a given component dictionary."""
        from setuav_studio.model import GenericComponent

        component_type = component.get("type")
        factory = (
            self._component_models.get(component_type) if isinstance(component_type, str) else None
        )
        if factory is not None:
            return factory(component)
        return GenericComponent(component)

    def register_component_deriver(self, type_id: str, deriver: ComponentDeriver) -> None:
        """Register how components of ``type_id`` derive data from their parameters.

        Studio runs the deriver on every such component when a project opens and after
        every change, undo and redo once formulas are evaluated, so derived data such as
        envelopes follows parameters however they change. A component is derived after
        the component it attaches to, so its deriver sees that component's derived data.
        A deriver raises ``ValueError`` for parameters it cannot derive from; Studio shows
        it in the status bar and the component keeps its previous derived data.
        """
        if type_id in self._component_derivers:
            raise ValueError(f"A component deriver is already registered for: {type_id}")
        self._component_derivers[type_id] = deriver

    def unregister_component_deriver(self, type_id: str) -> None:
        """Unregister the deriver of a component type."""
        self._component_derivers.pop(type_id, None)

    def derive_components(
        self,
        project: ProjectDocument | None = None,
        *,
        report_errors: bool = True,
    ) -> list[str]:
        """Run the registered derivers on the components of ``project`` (or the open project)."""
        target_project = project if project is not None else self._project
        if target_project is None or not self._component_derivers:
            return []
        components = [c for c in target_project.data["components"] if isinstance(c, dict)]
        by_id = {str(c["id"]): c for c in components}
        ordered: list[dict[str, Any]] = []
        placed: set[str] = set()

        def place(component: dict[str, Any]) -> None:
            component_id = str(component["id"])
            if component_id in placed:
                return
            placed.add(component_id)
            target = by_id.get(str(component.get("attach_to")))
            if target is not None:
                place(target)
            ordered.append(component)

        for component in components:
            place(component)
        failures: list[str] = []
        for component in ordered:
            deriver = self._component_derivers.get(str(component.get("type")))
            if deriver is None:
                continue
            try:
                deriver(component, by_id)
            except ValueError as exc:
                failures.append(f"{component.get('name') or component['id']}: {exc}")
        if failures and report_errors:
            self.show_status("Cannot update " + "; ".join(failures), "error", 8000)
        return failures

    def register_component_tree_provider(
        self,
        provider_id: str,
        provider: ComponentTreeProvider,
    ) -> None:
        """Register a provider of virtual nodes beneath project components."""
        if provider_id in self._component_tree_providers:
            raise ValueError(f"A component tree provider is already registered for: {provider_id}")
        self._component_tree_providers[provider_id] = provider

    def unregister_component_tree_provider(self, provider_id: str) -> None:
        """Unregister a component-tree provider by ID."""
        self._component_tree_providers.pop(provider_id, None)

    def component_tree_nodes(
        self,
        component: dict[str, Any],
    ) -> tuple[ComponentTreeNodeContribution, ...]:
        nodes: list[ComponentTreeNodeContribution] = []
        for provider in self._component_tree_providers.values():
            nodes.extend(provider(component))
        return tuple(nodes)

    def register_component_menu_provider(
        self,
        provider_id: str,
        provider: ComponentMenuProvider,
    ) -> None:
        """Register a provider of commands for the context menu of a component."""
        if provider_id in self._component_menu_providers:
            raise ValueError(f"A component menu provider is already registered for: {provider_id}")
        self._component_menu_providers[provider_id] = provider

    def unregister_component_menu_provider(self, provider_id: str) -> None:
        """Unregister a component menu provider by ID."""
        self._component_menu_providers.pop(provider_id, None)

    def component_menu_items(
        self,
        component: dict[str, Any],
    ) -> tuple[ComponentMenuItemContribution, ...]:
        """Context-menu commands the registered providers offer for ``component``."""
        items: list[ComponentMenuItemContribution] = []
        for provider in self._component_menu_providers.values():
            items.extend(provider(component))
        return tuple(items)

    def component_deletion_scope(self, component_ids: Iterable[str]) -> frozenset[str]:
        """``component_ids`` with the subparts deleted along with them."""
        deleted = {str(component_id) for component_id in component_ids}
        if self._project is None:
            return frozenset(deleted)
        components = [c for c in self._project.data.get("components", []) if isinstance(c, dict)]
        subpart_types = self.subpart_types
        changed = True
        while changed:
            changed = False
            for component in components:
                component_id = str(component.get("id") or "")
                if not component_id or component_id in deleted:
                    continue
                owner = str(component.get("attach_to") or "")
                if component.get("type") in subpart_types and owner in deleted:
                    deleted.add(component_id)
                    changed = True
        return frozenset(deleted)

    def delete_components(self, component_ids: Iterable[str], description: str) -> None:
        """Delete components in one undoable edit.

        The edit deletes the components of :meth:`component_deletion_scope` and
        attaches the components mounted on them to the vehicle where they are.

        @param component_ids Ids of the components to delete.
        @param description Human-readable undo command text.
        """
        from setuav_studio.utilities.transform import attach_component

        project = self._project
        if project is None:
            raise RuntimeError("No project is open.")
        deleted = self.component_deletion_scope(component_ids)

        def change() -> None:
            components = project.data["components"]
            for component in components:
                if str(component.get("id")) in deleted:
                    continue
                if str(component.get("attach_to") or "") in deleted:
                    attach_component(component, None, components, preserve_world_transform=True)
            components[:] = [c for c in components if str(c.get("id")) not in deleted]

        self.edit_project(description, change)

    def register_project_tree_provider(
        self,
        provider_id: str,
        provider: ProjectTreeProvider,
    ) -> None:
        """Register a provider of plugin-owned project-root nodes."""
        if provider_id in self._project_tree_providers:
            raise ValueError(f"A project tree provider is already registered for: {provider_id}")
        self._project_tree_providers[provider_id] = provider
        if self._project is not None:
            self.notify_project_content_changed()

    def unregister_project_tree_provider(self, provider_id: str) -> None:
        """Unregister a project-tree provider and refresh the project tree."""
        removed = self._project_tree_providers.pop(provider_id, None)
        if removed is not None and self._project is not None:
            self.notify_project_content_changed()

    def project_tree_nodes(
        self,
        project: ProjectDocument,
    ) -> tuple[ProjectTreeNodeContribution, ...]:
        nodes: list[ProjectTreeNodeContribution] = []
        for provider in self._project_tree_providers.values():
            nodes.extend(provider(project))
        return tuple(nodes)

    def remove_project_listener(
        self,
        listener: Callable[[ProjectDocument], None],
    ) -> None:
        """Unsubscribe a project replacement listener."""
        if listener in self._project_listeners:
            self._project_listeners.remove(listener)
        self._unbind_destroyed("project", listener)

    def remove_selection_listener(
        self,
        listener: Callable[[Any | None], None],
    ) -> None:
        """Unsubscribe a selection listener."""
        if listener in self._selection_listeners:
            self._selection_listeners.remove(listener)
        self._unbind_destroyed("selection", listener)


__all__ = ["StudioAPI"]
