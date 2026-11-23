"""Starting an analysis from the user interface."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from setuav_studio.api import StudioAPI


def run_analysis(api: StudioAPI, config_id: str | None = None) -> None:
    """Run the analysis ``config_id``, or the current one (the first when none is).

    Progress and the outcome are reported in the status bar.
    """
    if config_id is not None:
        config = api.get_solver_config(config_id)
        if config is None:
            raise KeyError(f"No analysis configuration {config_id!r}")
        api.set_current_solver_config(config_id)
    else:
        config = api.get_current_solver_config()
        if config is None:
            all_configs = api.get_solver_configs()
            if not all_configs:
                api.show_status("No analysis configuration available to run.", "warning", 3000)
                return
            config = next(iter(all_configs.values()))
            api.set_current_solver_config(config.config_id)

    solver_cls = api.get_solver_class(config.solver_id)
    if solver_cls is None:
        api.show_status(f"No registered solver found for '{config.solver_id}'.", "error", 3000)
        return

    name = config.name
    api.show_status(f"Starting analysis '{name}'...", "info", 3000)
    api.run_solver(
        solver_cls(config),
        on_complete=lambda res: api.show_status(
            f"Analysis '{name}' completed ({res.execution_time_ms:.1f} ms).", "success", 4000
        ),
        on_error=lambda err: api.show_status(f"Analysis '{name}' failed: {err}", "error", 5000),
        on_cancelled=lambda: api.show_status(f"Analysis '{name}' cancelled.", "warning", 3000),
    )
