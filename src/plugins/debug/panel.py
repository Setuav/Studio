"""Debug inspector and status diagnostics panel for Setuav Studio."""

from __future__ import annotations

import datetime
import importlib
import platform
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from setuav_studio.api.events import StudioEvents
from setuav_studio.ui.style.icons import set_label_icon
from setuav_studio.ui.widget.table import PropertyTableMixin

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI
    from setuav_studio.project import ProjectDocument

_START_TIME = time.monotonic()


def _get_process_memory_mb() -> tuple[float, float]:
    """Return current process memory (RSS MB, VMS MB)."""
    try:
        psutil = importlib.import_module("psutil")
        proc = psutil.Process()
        mem = proc.memory_info()
        return mem.rss / 1048576.0, mem.vms / 1048576.0
    except Exception:
        pass
    try:
        rss_kb, vms_kb = 0.0, 0.0
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss_kb = float(line.split()[1])
                elif line.startswith("VmSize:"):
                    vms_kb = float(line.split()[1])
        return rss_kb / 1024.0, vms_kb / 1024.0
    except Exception:
        pass
    try:
        import resource

        rss_kb = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return rss_kb / 1024.0, rss_kb / 1024.0
    except Exception:
        return 0.0, 0.0


def _format_duration(seconds: float) -> str:
    """Format elapsed seconds into HH:MM:SS string."""
    secs = int(seconds)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    s = secs % 60
    return f"{hours:02d}:{minutes:02d}:{s:02d}"


class DebugPanel(PropertyTableMixin, QWidget):
    """Dock panel providing live Inspector and System Status using PropertyTables."""

    table_edit_triggers = QAbstractItemView.EditTrigger.NoEditTriggers
    table_value_placeholder = "-"
    table_value_editable_default = False

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("plugin.debug.panel")
        self._api = api
        self._unsubscribes: list[Callable[[], None]] = []
        self._events_history: list[tuple[str, str, str]] = []
        self._section_icons: list[tuple[QLabel, str]] = []

        self._setup_ui()
        self._connect_listeners()

        # Uptime and memory live refresh timer (1s interval)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_timer_tick)

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)

        # Tab 1: Inspector
        self._inspector_tab = self._create_inspector_tab()
        self._tabs.addTab(self._inspector_tab, "Inspector")

        # Tab 2: Status
        self._status_tab = self._create_status_tab()
        self._tabs.addTab(self._status_tab, "Status")

        root_layout.addWidget(self._tabs)

    def update_theme_style(self) -> None:
        for label, icon_name in self._section_icons:
            set_label_icon(label, icon_name)

    def _create_section(
        self,
        parent_layout: QVBoxLayout,
        title: str,
        icon_name: str | None = None,
        action_widget: QWidget | None = None,
    ) -> QVBoxLayout:
        section = QWidget()
        section.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        header = QWidget(section)
        header.setProperty("sectionHeader", True)
        header.setFixedHeight(20)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

        if icon_name:
            icon_label = QLabel(header)
            set_label_icon(icon_label, icon_name)
            icon_label.setFixedSize(14, 14)
            self._section_icons.append((icon_label, icon_name))
            header_layout.addWidget(icon_label)

        title_label = QLabel(title, header)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        if action_widget is not None:
            header_layout.addWidget(action_widget)

        layout.addWidget(header)
        parent_layout.addWidget(section)
        return layout

    # ------------------------------------------------------------------
    # Tab 1: Inspector UI
    # ------------------------------------------------------------------

    def _create_inspector_tab(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(6, 6, 6, 8)
        layout.setSpacing(10)

        # 1. Active Selection Section
        sel_layout = self._create_section(layout, "Active Selection", "search")
        self.selection_table = self._property_table(
            [
                ("kind", "Kind"),
                ("target", "Selection"),
                ("details", "Details"),
            ]
        )
        sel_layout.addWidget(self.selection_table)

        # 2. Component Information Section
        comp_layout = self._create_section(layout, "Component Information", "component")
        self.component_table = self._property_table(
            [
                ("name", "Name"),
                ("id", "ID"),
                ("type", "Type"),
                ("attach_to", "Attached to"),
                ("position", "Position"),
                ("rotation", "Rotation"),
            ]
        )
        comp_layout.addWidget(self.component_table)

        # 3. Component Parameters Section
        params_layout = self._create_section(layout, "Component Parameters", "fa6s.sliders")
        self.params_table = self._property_table([("empty", "Parameters")])
        params_layout.addWidget(self.params_table)

        # 4. Project Summary Section
        proj_layout = self._create_section(layout, "Project Summary", "project_folder")
        self.project_table = self._property_table(
            [
                ("name", "Project Name"),
                ("status", "Status"),
                ("path", "File Path"),
                ("components", "Components"),
                ("solvers", "Solvers"),
                ("units", "Active Units"),
            ]
        )
        proj_layout.addWidget(self.project_table)

        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    # ------------------------------------------------------------------
    # Tab 2: Status UI
    # ------------------------------------------------------------------

    def _create_status_tab(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(6, 6, 6, 8)
        layout.setSpacing(10)

        # 1. System & Runtime Section
        sys_layout = self._create_section(layout, "System & Runtime", "settings")
        self.system_table = self._property_table(
            [
                ("uptime", "Uptime"),
                ("ram_rss", "RAM (RSS)"),
                ("ram_vms", "RAM (VMS)"),
                ("python", "Python"),
                ("qt", "Qt / PySide6"),
                ("platform", "Platform"),
                ("undo_stack", "Undo Stack"),
                ("can_undo", "Can Undo"),
                ("can_redo", "Can Redo"),
                ("active_tasks", "Active Tasks"),
            ]
        )
        sys_layout.addWidget(self.system_table)

        # 2. Events Stream Section
        action_bar = QWidget()
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(4)

        self._lbl_events_count = QLabel("(0)", action_bar)
        action_layout.addWidget(self._lbl_events_count)

        btn_clear = QPushButton("Clear", action_bar)
        btn_clear.setFixedHeight(18)
        btn_clear.clicked.connect(self._clear_events)
        action_layout.addWidget(btn_clear)

        ev_layout = self._create_section(
            layout, "Studio Events Stream", "log", action_widget=action_bar
        )

        self.events_table = QTableWidget(0, 3, content)
        self.events_table.setHorizontalHeaderLabels(["Time", "Event", "Details"])
        self.events_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.events_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.events_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.events_table.verticalHeader().setVisible(False)
        self.events_table.verticalHeader().setDefaultSectionSize(22)
        self.events_table.horizontalHeader().setFixedHeight(23)
        self.events_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.events_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.events_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.events_table.setAlternatingRowColors(True)
        self.events_table.setMinimumHeight(180)
        ev_layout.addWidget(self.events_table)

        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    # ------------------------------------------------------------------
    # Data Refresh & Listeners
    # ------------------------------------------------------------------

    def _connect_listeners(self) -> None:
        """Register listeners with StudioAPI."""
        self._unsubscribes.append(self._api.on_selection_changed(self._on_selection_changed))
        self._unsubscribes.append(
            self._api.on_section_selection_changed(self._on_section_selection_changed)
        )
        self._unsubscribes.append(
            self._api.on_solver_config_selection_changed(self._on_solver_config_selection_changed)
        )
        self._unsubscribes.append(self._api.on_project_changed(self._on_project_changed))
        self._unsubscribes.append(
            self._api.on_project_content_changed(self._on_project_content_changed)
        )
        self._unsubscribes.append(self._api.on_modified_changed(self._on_modified_changed))

        # Event Bus Subscriptions
        events_to_track = (
            StudioEvents.PROJECT_OPENED,
            StudioEvents.PROJECT_CLOSED,
            StudioEvents.PROJECT_MODIFIED,
            StudioEvents.SELECTION_CHANGED,
            StudioEvents.SECTION_SELECTION_CHANGED,
            StudioEvents.UNITS_CHANGED,
            StudioEvents.TASK_STARTED,
            StudioEvents.TASK_FINISHED,
        )
        for ev in events_to_track:
            unsub = self._api.subscribe(ev, lambda payload, name=ev: self._log_event(name, payload))
            self._unsubscribes.append(unsub)

    def _log_event(self, event_name: str, payload: Any = None) -> None:
        """Record an event into the stream table."""
        now_str = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        payload_str = ""
        if payload is not None:
            if isinstance(payload, dict):
                p_id = payload.get("id") or payload.get("name")
                payload_str = f"id={p_id}" if p_id else str(payload)[:60]
            elif hasattr(payload, "name"):
                payload_str = f"name={payload.name}"
            else:
                payload_str = str(payload)[:60]

        self._events_history.insert(0, (now_str, event_name, payload_str))
        if len(self._events_history) > 100:
            self._events_history.pop()

        self.events_table.insertRow(0)
        t_item = QTableWidgetItem(now_str)
        e_item = QTableWidgetItem(event_name)
        p_item = QTableWidgetItem(payload_str)

        font_mono = QFont("monospace")
        font_mono.setPointSize(9)
        t_item.setFont(font_mono)

        self.events_table.setItem(0, 0, t_item)
        self.events_table.setItem(0, 1, e_item)
        self.events_table.setItem(0, 2, p_item)

        while self.events_table.rowCount() > 100:
            self.events_table.removeRow(self.events_table.rowCount() - 1)

        self._lbl_events_count.setText(f"({len(self._events_history)})")

    def _clear_events(self) -> None:
        self._events_history.clear()
        self.events_table.setRowCount(0)
        self._lbl_events_count.setText("(0)")

    def _on_selection_changed(self, selection: Any | None) -> None:
        self._refresh_inspector()

    def _on_section_selection_changed(self, _selection: Any | None) -> None:
        self._refresh_inspector()

    def _on_solver_config_selection_changed(self, _config: Any | None) -> None:
        self._refresh_inspector()

    def _on_project_changed(self, _project: ProjectDocument | None) -> None:
        self._refresh_inspector()

    def _on_project_content_changed(self, _project: ProjectDocument | None) -> None:
        self._refresh_inspector()

    def _on_modified_changed(self, _modified: bool) -> None:
        self._refresh_inspector()

    def _on_timer_tick(self) -> None:
        if self.isVisible():
            self._refresh_status()

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    def _refresh_inspector(self) -> None:
        """Update active selection, component details and project summary."""
        project = self._api.project
        sel = self._api.current_selection
        sec_sel = self._api.current_section_selection
        sol_id = self._api.current_solver_config_id

        # 1. Active Selection Table
        sel_kind = "-"
        sel_target = "-"
        sel_details = "-"
        comp_dict: dict[str, Any] | None = None

        if sel is not None:
            raw = getattr(sel, "raw_data", sel)
            if isinstance(raw, dict):
                comp_dict = raw
                sel_kind = "Component"
                sel_target = f"{raw.get('name', '(unnamed)')} ({raw.get('id', '-')})"
            else:
                sel_kind = type(sel).__name__
                sel_target = str(getattr(sel, "name", getattr(sel, "id", str(sel))))

        if sec_sel is not None:
            comp_id, sec_idx, side = sec_sel
            sel_kind = "Section" if sel_kind == "-" else f"{sel_kind} / Section"
            sel_details = f"{comp_id} [idx: {sec_idx}, side: {side}]"

        if sol_id is not None:
            if sel_kind == "-":
                sel_kind = "Solver Config"
                sel_target = sol_id
            else:
                sel_details = (
                    f"Solver: {sol_id}"
                    if sel_details == "-"
                    else f"{sel_details} | Solver: {sol_id}"
                )

        self._set_property_value(self.selection_table, "kind", sel_kind)
        self._set_property_value(self.selection_table, "target", sel_target)
        self._set_property_value(self.selection_table, "details", sel_details)

        # 2. Component Details Table
        if comp_dict is not None:
            c_name = str(comp_dict.get("name") or comp_dict.get("id") or "-")
            c_id = str(comp_dict.get("id", "-"))
            c_type = str(comp_dict.get("type", "-"))
            c_attach_to = str(comp_dict.get("attach_to") or "Vehicle")

            pos = comp_dict.get("position", [0.0, 0.0, 0.0])
            rot = comp_dict.get("rotation", [0.0, 0.0, 0.0])
            pos_str = f"[{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}]" if len(pos) >= 3 else str(pos)
            rot_str = (
                f"[{rot[0]:.2f}°, {rot[1]:.2f}°, {rot[2]:.2f}°]" if len(rot) >= 3 else str(rot)
            )

            self._set_property_value(self.component_table, "name", c_name)
            self._set_property_value(self.component_table, "id", c_id)
            self._set_property_value(self.component_table, "type", c_type)
            self._set_property_value(self.component_table, "attach_to", c_attach_to)
            self._set_property_value(self.component_table, "position", pos_str)
            self._set_property_value(self.component_table, "rotation", rot_str)

            # Parameters Table
            params = comp_dict.get("parameters", {})
            if isinstance(params, dict) and params:
                defs = [(k, k.replace("_", " ").title()) for k in params]
                self._configure_property_table(self.params_table, defs)
                for k, v in params.items():
                    self._set_property_value(self.params_table, k, str(v))
            else:
                self._configure_property_table(self.params_table, [("status", "Parameters")])
                self._set_property_value(self.params_table, "status", "(No parameters defined)")
        else:
            self._set_property_value(self.component_table, "name", "-")
            self._set_property_value(self.component_table, "id", "-")
            self._set_property_value(self.component_table, "type", "-")
            self._set_property_value(self.component_table, "attach_to", "-")
            self._set_property_value(self.component_table, "position", "-")
            self._set_property_value(self.component_table, "rotation", "-")

            self._configure_property_table(self.params_table, [("status", "Parameters")])
            self._set_property_value(self.params_table, "status", "(No component selected)")

        # 3. Project Summary Table
        if project is not None:
            p_data = project.data
            p_name = p_data.get("name", "Untitled Project")
            p_path = project.path
            p_file = str(p_path) if p_path else "(Unsaved)"
            status_text = "Modified (Unsaved)" if project.modified else "Clean / Saved"

            # Breakdown of components by type
            raw_comps = p_data.get("components", [])
            type_counts: dict[str, int] = {}
            for c in raw_comps:
                if isinstance(c, dict):
                    t = c.get("type", "unknown")
                    type_counts[t] = type_counts.get(t, 0) + 1

            type_summary = (
                ", ".join(f"{k.split(':')[-1]}: {v}" for k, v in type_counts.items()) or "0"
            )
            comp_summary = f"{len(raw_comps)} total ({type_summary})"

            n_solvers = len(project.solver_configs)
            n_results = len(project.solver_results)
            solver_summary = f"{n_solvers} configs, {n_results} results"

            # Units
            units = self._api.units
            u_len = units.get_display_unit("length")
            u_spd = units.get_display_unit("speed")
            u_mass = units.get_display_unit("mass")
            units_summary = f"length={u_len}, speed={u_spd}, mass={u_mass}"

            self._set_property_value(self.project_table, "name", p_name)
            self._set_property_value(self.project_table, "status", status_text)
            self._set_property_value(self.project_table, "path", p_file)
            self._set_property_value(self.project_table, "components", comp_summary)
            self._set_property_value(self.project_table, "solvers", solver_summary)
            self._set_property_value(self.project_table, "units", units_summary)
        else:
            self._set_property_value(self.project_table, "name", "-")
            self._set_property_value(self.project_table, "status", "-")
            self._set_property_value(self.project_table, "path", "(No project open)")
            self._set_property_value(self.project_table, "components", "-")
            self._set_property_value(self.project_table, "solvers", "-")
            self._set_property_value(self.project_table, "units", "-")

    def _refresh_status(self) -> None:
        """Update system metrics: RAM, uptime, runtime environment, tasks."""
        rss_mb, vms_mb = _get_process_memory_mb()
        uptime_str = _format_duration(time.monotonic() - _START_TIME)

        undo_count = self._api.undo_count
        can_undo = self._api.can_undo
        can_redo = self._api.can_redo
        undo_text = f"'{self._api.undo_text}'" if can_undo else "-"
        redo_text = f"'{self._api.redo_text}'" if can_redo else "-"

        active_tasks = len(self._api.tasks.active_tasks)

        py_ver = sys.version.split()[0]
        os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"

        self._set_property_value(self.system_table, "uptime", uptime_str)
        self._set_property_value(self.system_table, "ram_rss", f"{rss_mb:.1f} MB")
        self._set_property_value(self.system_table, "ram_vms", f"{vms_mb:.1f} MB")
        self._set_property_value(self.system_table, "python", py_ver)
        self._set_property_value(self.system_table, "qt", "PySide6")
        self._set_property_value(self.system_table, "platform", os_info)
        self._set_property_value(self.system_table, "undo_stack", f"{undo_count} commands")
        self._set_property_value(self.system_table, "can_undo", undo_text)
        self._set_property_value(self.system_table, "can_redo", redo_text)
        self._set_property_value(self.system_table, "active_tasks", f"{active_tasks} running")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_inspector()
        self._refresh_status()
        self._timer.start()

    def hideEvent(self, event: Any) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def closeEvent(self, event: Any) -> None:
        self._timer.stop()
        for unsub in self._unsubscribes:
            with suppress(Exception):
                unsub()
        self._unsubscribes.clear()
        super().closeEvent(event)
