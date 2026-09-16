"""Dialog windows for Setuav Studio."""

from __future__ import annotations

from setuav_studio.ui.dialog.about import AboutDialog
from setuav_studio.ui.dialog.expression_dialog import AdvancedExpressionDialog
from setuav_studio.ui.dialog.log import (
    LogBridge,
    LogEntry,
    LogWindow,
    clear_log_buffer,
    install_log_buffer,
    log_buffer_entries,
    log_signal,
)
from setuav_studio.ui.dialog.plugin_manager import PluginManagerDialog
from setuav_studio.ui.dialog.problems import Problem, ProblemsDialog
from setuav_studio.ui.dialog.task_monitor import TaskMonitorDialog

__all__ = [
    "AboutDialog",
    "AdvancedExpressionDialog",
    "LogBridge",
    "LogEntry",
    "LogWindow",
    "PluginManagerDialog",
    "Problem",
    "ProblemsDialog",
    "TaskMonitorDialog",
    "clear_log_buffer",
    "install_log_buffer",
    "log_buffer_entries",
    "log_signal",
]
