"""Standard application and domain event topics."""

from enum import StrEnum


class StudioEvents(StrEnum):
    """Canonical event topics for cross-plugin and shell communication."""

    # Project lifecycle
    PROJECT_OPENED = "project.opened"
    PROJECT_CLOSED = "project.closed"
    PROJECT_MODIFIED = "project.modified"

    # Selection
    SELECTION_CHANGED = "selection.changed"
    SECTION_SELECTION_CHANGED = "section_selection.changed"

    # Units
    UNITS_CHANGED = "units.changed"

    # Geometry
    GEOMETRY_VIEWER_SETTINGS_CHANGED = "geometry.viewer.settings.changed"

    # Analysis & Results
    ANALYSIS_PLOT_ACTION = "analysis.plot_action"
    ANALYSIS_ADD_TO_VIEW = "analysis.add_to_view"

    # Tasks / Background Jobs
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_FINISHED = "task.finished"
    TASK_CANCELLED = "task.cancelled"
    TASK_ERROR = "task.error"

    def __str__(self) -> str:
        return self.value


__all__ = ["StudioEvents"]
