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
    WORKSPACE_CHANGED = "workspace.changed"

    # Aerodynamics
    AERODYNAMICS_ANALYSIS_COMPLETED = "aerodynamics.analysis_completed"
    AERODYNAMICS_RESULT_SELECTED = "aerodynamics.result_selected"

    # Flight Performance
    FLIGHT_PERFORMANCE_ANALYSIS_COMPLETED = "flight_performance.analysis_completed"

    # Electrical Propulsion
    PROPULSION_RESULTS_UPDATED = "propulsion.results_updated"
    PROPULSION_PLOT_SWEEP = "propulsion.plot_sweep"
    PROPULSION_CLEAR_CHARTS = "propulsion.clear_charts"

    # Weight & Balance
    WEIGHT_BALANCE_ANALYSIS_COMPLETED = "weight_balance.analysis_completed"

    # Geometry
    GEOMETRY_VIEWER_SETTINGS_CHANGED = "geometry.viewer.settings.changed"

    def __str__(self) -> str:
        return self.value


__all__ = ["StudioEvents"]
