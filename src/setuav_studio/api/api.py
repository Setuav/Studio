from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon, QUndoStack
from PySide6.QtWidgets import QWidget

from setuav_studio.api.hooks import HookRegistry
from setuav_studio.project import ProjectDocument
from setuav_studio.ui.style.icons import get_icon

from .contributions import (
    ActionContribution,
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
    from setuav_studio.solver.base import SolverConfig
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

logger = logging.getLogger(__name__)

UnsubscribeCallable: TypeAlias = Callable[[], None]


def _bind_qobject_destroyed(callback: Any, cleanup: Callable[[], None]) -> None:
    """If callback is a bound method on a QObject, automatically invoke cleanup on destruction."""
    owner = getattr(callback, "__self__", None)
    if isinstance(owner, QObject):
        with suppress(RuntimeError):
            owner.destroyed.connect(lambda *_: cleanup())


def _dispatch_listeners(listeners: list[Any], arg: Any) -> None:
    """Safely invoke listeners and clean up dead Qt object references."""
    dead: list[Any] = []
    for listener in list(listeners):
        try:
            listener(arg)
        except RuntimeError:
            dead.append(listener)
    for d in dead:
        if d in listeners:
            listeners.remove(d)


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
        self._project_content_listeners: list[Callable[[ProjectDocument], None]] = []
        self._modified_listeners: list[Callable[[bool], None]] = []
        self._selection_listeners: list[Callable[[Any | None], None]] = []
        self._section_selection_listeners: list[Callable[[tuple[str, int, int] | None], None]] = []
        self._solver_config_selection_listeners: list[Callable[[SolverConfig | None], None]] = []
        self._is_recomputing_expressions: bool = False
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
        self._project_tree_providers: dict[str, ProjectTreeProvider] = {}
        self._project_requirement_checker: Callable[[dict[str, Any]], list[str]] | None = None
        self._event_subscribers: dict[str, list[Callable[[Any], None]]] = {}
        self._hooks = HookRegistry()
        from setuav_studio.task.manager import TaskManager

        self._tasks = TaskManager(self)
        from setuav_studio.solver import SolverRunner

        self._solver_runner = SolverRunner(self)
        self._undo_stack = QUndoStack()
        self._undo_stack.cleanChanged.connect(self._on_clean_changed)
        self._host = _StudioHost(self)
        self._viewport: Any | None = None
        from setuav_studio.units import get_unit_manager

        get_unit_manager().units_changed.connect(lambda: self.publish(StudioEvents.UNITS_CHANGED))

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
    def hooks(self) -> HookRegistry:
        """Central extensible lifecycle hooks registry."""
        return self._hooks

    @property
    def tasks(self) -> TaskManager:
        """Central background task manager for asynchronous jobs."""
        return self._tasks

    @property
    def solvers(self) -> Any:
        """Central solver runner and registry."""
        return self._solver_runner

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

    def subscribe(self, event_name: str, handler: Callable[[Any], None]) -> UnsubscribeCallable:
        """Subscribe a callback handler to a named studio event (Event Bus).

        Bound methods owned by a QObject are removed automatically when that
        QObject is destroyed. Returns an unsubscribe callable.
        """
        subscribers = self._event_subscribers.setdefault(event_name, [])
        if handler not in subscribers:
            subscribers.append(handler)
            _bind_qobject_destroyed(handler, lambda: self.unsubscribe(event_name, handler))
        return lambda: self.unsubscribe(event_name, handler)

    def unsubscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Unsubscribe a callback handler from a named studio event."""
        if event_name in self._event_subscribers:
            with suppress(ValueError):
                self._event_subscribers[event_name].remove(handler)

    def publish(self, event_name: str, payload: Any = None) -> None:
        """Publish an event to all subscribed listeners."""
        handlers = list(self._event_subscribers.get(event_name, []))
        for handler in handlers:
            try:
                handler(payload)
            except RuntimeError as exc:
                if "already deleted" in str(exc):
                    # QObject destruction can race with queued events. Drop
                    # the stale callback and keep the event bus healthy.
                    self.unsubscribe(event_name, handler)
                    logger.debug(
                        "Removed stale subscriber for event '%s': %s",
                        event_name,
                        exc,
                    )
                    continue
                logger.error(
                    "Error executing subscriber for event '%s': %s", event_name, exc, exc_info=True
                )
            except Exception as exc:
                logger.error(
                    "Error executing subscriber for event '%s': %s", event_name, exc, exc_info=True
                )

    emit = publish

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
            _bind_qobject_destroyed(listener, lambda: self.remove_project_listener(listener))
        if self._project is not None:
            with suppress(RuntimeError):
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
            _bind_qobject_destroyed(
                listener, lambda: self.remove_project_content_listener(listener)
            )
        return lambda: self.remove_project_content_listener(listener)

    def remove_project_content_listener(
        self,
        listener: Callable[[ProjectDocument], None],
    ) -> None:
        """Unsubscribe a project-content listener."""
        if listener in self._project_content_listeners:
            self._project_content_listeners.remove(listener)

    def on_modified_changed(self, listener: Callable[[bool], None]) -> UnsubscribeCallable:
        """Subscribe to project modified-state changes and receive current state.

        Returns an unsubscribe callable.
        """
        if listener not in self._modified_listeners:
            self._modified_listeners.append(listener)
            _bind_qobject_destroyed(listener, lambda: self.remove_modified_listener(listener))
        with suppress(RuntimeError):
            listener(bool(self._project and self._project.modified))
        return lambda: self.remove_modified_listener(listener)

    def remove_modified_listener(self, listener: Callable[[bool], None]) -> None:
        """Unsubscribe a project modified-state listener."""
        if listener in self._modified_listeners:
            self._modified_listeners.remove(listener)

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
                self._notify_project_content_changed,
                source=component if target is not component else None,
            )
        )

    def attach_component(
        self,
        component: dict[str, Any] | Any,
        target_id: str | None,
        *,
        preserve_world_transform: bool,
        description: str | None = None,
    ) -> None:
        """Attach a component to another component, or to the vehicle, with undo support.

        @param component The component to attach (dict or Component object).
        @param target_id The component to attach to, or None for the vehicle.
        @param preserve_world_transform When True, recomputes the component's position
            and rotation relative to the new target so it stays where it is; when False,
            keeps them, so the component moves with the target's frame.
        @param description Custom undo description, or None for automatic description.
        """
        from setuav_studio.utilities.transform import attach_component

        raw_data = getattr(component, "raw_data", None)
        raw = raw_data if isinstance(raw_data, dict) else component
        if not isinstance(raw, dict):
            raise TypeError(f"{type(component).__name__} is not a component.")
        if self._project is None:
            raise RuntimeError("No project is open.")

        comp_name = str(raw.get("name") or raw.get("id") or "component")
        cmd_desc = description or f"Attach {comp_name} to {target_id or 'Vehicle'}"

        def change() -> None:
            attach_component(
                raw,
                target_id,
                self._project,
                preserve_world_transform=preserve_world_transform,
            )

        self.edit_component(raw, cmd_desc, change)

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
                self._notify_project_content_changed,
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
        """Edit component-level extension data for a given namespace with full Undo/Redo tracking."""
        if self._project is None:
            return
        comp = self._project.get_component(component_id)
        if comp is None:
            return

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

    def undo(self) -> None:
        """Undo the most recent project or component edit when available."""
        if self._undo_stack.canUndo():
            self._undo_stack.undo()
            self.set_selection(self.current_selection)

    def redo(self) -> None:
        """Redo the most recently undone edit when available."""
        if self._undo_stack.canRedo():
            self._undo_stack.redo()
            self.set_selection(self.current_selection)

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

    def register_solver(self, solver_id: str, solver_cls: Any) -> None:
        """Register a solver class by solver ID."""
        self._solver_runner.register_solver(solver_id, solver_cls)

    def unregister_solver(self, solver_id: str) -> None:
        """Unregister a solver class by solver ID."""
        self._solver_runner.unregister_solver(solver_id)

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
        self._notify_project_content_changed()

    def remove_solver_result(self, result_id: str) -> bool:
        """Remove a solver result by ID from the current project."""
        if self._project is None:
            return False
        removed = self._project.remove_solver_result(result_id)
        if removed:
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
            _bind_qobject_destroyed(
                listener, lambda: self.remove_solver_config_selection_listener(listener)
            )
        return lambda: self.remove_solver_config_selection_listener(listener)

    def remove_solver_config_selection_listener(
        self,
        listener: Callable[[SolverConfig | None], None],
    ) -> None:
        """Unsubscribe a solver configuration selection listener."""
        if listener in self._solver_config_selection_listeners:
            self._solver_config_selection_listeners.remove(listener)

    def set_current_solver_config(self, config_id: str | None) -> None:
        """Set the active solver config selection by ID and notify listeners."""
        self.current_solver_config_id = config_id
        active_config = self.get_current_solver_config()
        _dispatch_listeners(self._solver_config_selection_listeners, active_config)

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
        """Add a SolverConfig to the current project and set it as active."""
        if self._project is None:
            return
        self._project.add_solver_config(config)
        self.set_current_solver_config(config.config_id)
        self._notify_project_content_changed()

    def remove_solver_config(self, config_id: str) -> bool:
        """Remove a SolverConfig by ID from the current project."""
        if self._project is None:
            return False
        removed = self._project.remove_solver_config(config_id)
        if removed:
            if self.current_solver_config_id == config_id:
                self.set_current_solver_config(None)
            self._notify_project_content_changed()
        return removed

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

        _dispatch_listeners(self._project_content_listeners, self._project)

    def _on_clean_changed(self, clean: bool) -> None:
        modified = not clean
        if self._project is not None:
            self._project.modified = modified
        _dispatch_listeners(self._modified_listeners, modified)
        self.publish(StudioEvents.PROJECT_MODIFIED, modified)

    def on_selection_changed(self, listener: Callable[[Any | None], None]) -> UnsubscribeCallable:
        """Subscribe to selection changes and receive the current selection.

        Returns an unsubscribe callable.
        """
        if listener not in self._selection_listeners:
            self._selection_listeners.append(listener)
            _bind_qobject_destroyed(listener, lambda: self.remove_selection_listener(listener))
        with suppress(RuntimeError):
            listener(self.current_selection)
        return lambda: self.remove_selection_listener(listener)

    def set_selection(self, selection: Any | None) -> None:
        """Set the application selection and notify listeners."""
        self.current_selection = selection
        _dispatch_listeners(self._selection_listeners, selection)
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
            _bind_qobject_destroyed(
                listener, lambda: self.remove_section_selection_listener(listener)
            )
        with suppress(RuntimeError):
            listener(self.current_section_selection)
        return lambda: self.remove_section_selection_listener(listener)

    def remove_section_selection_listener(
        self,
        listener: Callable[[tuple[str, int, int] | None], None],
    ) -> None:
        """Unsubscribe a geometry-section selection listener."""
        if listener in self._section_selection_listeners:
            self._section_selection_listeners.remove(listener)

    def set_section_selection(
        self,
        selection: tuple[str, int, int] | None,
    ) -> None:
        """Set the selected component, section, and side tuple."""
        self.current_section_selection = selection
        _dispatch_listeners(self._section_selection_listeners, selection)
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

        # Fallback: auto-generate editor if component model defines parameter field descriptors
        if isinstance(component_type, str) and component_type in self._component_models:
            model_cls = self._component_models[component_type]
            if hasattr(model_cls, "get_fields"):
                fields = model_cls.get_fields()
                if fields:
                    from setuav_studio.ui.editor.component import BaseComponentEditor

                    raw_comp = getattr(component, "raw_data", component)
                    return BaseComponentEditor(cast(Any, self), raw_comp, fields)

        get_fields_fn = getattr(component, "get_fields", None)
        if callable(get_fields_fn):
            fields = get_fields_fn()
            if fields:
                from setuav_studio.ui.editor.component import BaseComponentEditor

                raw_comp = getattr(component, "raw_data", component)
                return BaseComponentEditor(cast(Any, self), raw_comp, cast(Any, fields))

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

        if component_kind == "instance":
            source_id = component.get("source")
            if source_id and self._project is not None:
                source = self._project.get_component(str(source_id))
                if source is not None and source.get("id") != component.get("id"):
                    return self.get_component_icon(source)
            return get_icon("instance")

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

    def remove_selection_listener(
        self,
        listener: Callable[[Any | None], None],
    ) -> None:
        """Unsubscribe a selection listener."""
        if listener in self._selection_listeners:
            self._selection_listeners.remove(listener)


__all__ = ["StudioAPI"]
