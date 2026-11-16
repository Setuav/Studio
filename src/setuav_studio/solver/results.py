"""Immutable analysis result model."""

from __future__ import annotations

import csv
import datetime
import io
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import SolverConfig, SolverStatus


@dataclass
class SummaryItem:
    """A scalar summary metric produced by an engineering solver."""

    key: str
    value: float | int | str | bool
    label: str = ""
    unit: str = ""
    quantity_id: str | None = None

    def __post_init__(self) -> None:
        if not self.label:
            object.__setattr__(self, "label", self.key.replace("_", " ").title())
        if not self.quantity_id and self.unit:
            from setuav_studio.units import get_quantity_for_unit

            object.__setattr__(self, "quantity_id", get_quantity_for_unit(self.unit))

    def display_value_and_unit(self) -> tuple[float | int | str | bool, str]:
        """Return the value and unit converted according to user's display settings."""
        if self.quantity_id and isinstance(self.value, (int, float)):
            from setuav_studio.units import get_unit_manager

            um = get_unit_manager()
            disp_val = um.to_display(float(self.value), self.quantity_id)
            disp_unit = um.get_unit_symbol(self.quantity_id)
            return (disp_val, disp_unit)
        return (self.value, self.unit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "quantity_id": self.quantity_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SummaryItem:
        return cls(
            key=str(data["key"]),
            value=data["value"],
            label=str(data["label"]),
            unit=str(data["unit"]),
            quantity_id=data["quantity_id"],
        )


@dataclass
class TableColumn:
    """Definition of a table column including unit and quantity."""

    key: str
    label: str = ""
    unit: str = ""
    quantity_id: str | None = None

    def __post_init__(self) -> None:
        if not self.label:
            object.__setattr__(self, "label", self.key.replace("_", " ").title())
        if not self.quantity_id and self.unit:
            from setuav_studio.units import get_quantity_for_unit

            object.__setattr__(self, "quantity_id", get_quantity_for_unit(self.unit))

    def header_text(self, use_display_units: bool = False) -> str:
        """Return formatted column header, e.g. 'Angle of Attack [deg]' or 'CL [-]'."""
        unit_str = self.unit
        if use_display_units and self.quantity_id:
            from setuav_studio.units import get_unit_manager

            unit_str = get_unit_manager().get_unit_symbol(self.quantity_id)
        if unit_str:
            return f"{self.label} [{unit_str}]"
        return self.label

    def display_unit(self, use_display_units: bool = True) -> str:
        """Return the unit string according to display unit settings."""
        if use_display_units and self.quantity_id:
            from setuav_studio.units import get_unit_manager

            return get_unit_manager().get_unit_symbol(self.quantity_id)
        return self.unit

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "quantity_id": self.quantity_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TableColumn:
        return cls(
            key=str(data["key"]),
            label=str(data["label"]),
            unit=str(data["unit"]),
            quantity_id=data["quantity_id"],
        )


@dataclass
class TableDefinition:
    """Primary tabular dataset produced by an analysis.

    Stores numerical columns in a columnar format (dict[col_key, list[values]])
    for zero-copy plotting and high-speed data extraction.
    """

    id: str
    title: str = ""
    columns: list[TableColumn] = field(default_factory=list)
    data: dict[str, list[Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.title:
            object.__setattr__(self, "title", self.id.replace("_", " ").title())
        # Auto-infer columns from data keys if columns list was not provided
        if not self.columns and self.data:
            inferred = [TableColumn(key=k) for k in self.data]
            object.__setattr__(self, "columns", inferred)

    def get_column(self, key: str) -> list[Any]:
        """Return raw values for a column."""
        return list(self.data.get(key, []))

    def get_column_display_values(self, key: str) -> list[Any]:
        """Return values converted to the user's active display unit."""
        col = self.get_column_def(key)
        values = self.get_column(key)
        if col and col.quantity_id:
            from setuav_studio.units import convert_value, get_unit_manager

            um = get_unit_manager()
            target_unit = um.get_display_unit(col.quantity_id)
            from_unit = col.unit or target_unit
            return [
                convert_value(float(v), col.quantity_id, from_unit, target_unit)
                if isinstance(v, (int, float))
                else v
                for v in values
            ]
        return values

    def get_column_display_unit(self, key: str, use_display_units: bool = True) -> str:
        """Return the active display unit symbol for a column."""
        col = self.get_column_def(key)
        if not col:
            return ""
        return col.display_unit(use_display_units)

    def get_column_def(self, key: str) -> TableColumn | None:
        """Find the column definition for a key."""
        for col in self.columns:
            if col.key == key:
                return col
        return None

    def row_count(self) -> int:
        """Return the number of rows in the table."""
        if not self.data:
            return 0
        return max(len(v) for v in self.data.values())

    def to_rows(self) -> list[dict[str, Any]]:
        """Convert columnar data to a list of row dictionaries."""
        n = self.row_count()
        keys = [col.key for col in self.columns] or list(self.data.keys())
        rows: list[dict[str, Any]] = []
        for i in range(n):
            row = {k: self.data[k][i] if i < len(self.data.get(k, [])) else None for k in keys}
            rows.append(row)
        return rows

    def __getitem__(self, index: int) -> dict[str, Any]:
        """Support row-based indexing (e.g. table[0] -> {'alpha': 0.0, 'cl': 0.2})."""
        return self.to_rows()[index]

    def __iter__(self):
        """Support row iteration."""
        return iter(self.to_rows())

    def __len__(self) -> int:
        """Support len(table) -> row count."""
        return self.row_count()

    def to_csv(self, use_display_units: bool = False) -> str:
        """Export table to an RFC 4180 standard CSV string."""
        output = io.StringIO()
        writer = csv.writer(output)
        headers = [col.header_text(use_display_units) for col in self.columns]
        writer.writerow(headers)

        n = self.row_count()
        col_data = [
            (
                self.get_column_display_values(col.key)
                if use_display_units
                else self.get_column(col.key)
            )
            for col in self.columns
        ]
        for i in range(n):
            row = [col_data[c][i] if i < len(col_data[c]) else "" for c in range(len(self.columns))]
            writer.writerow(row)
        return output.getvalue()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "columns": [col.to_dict() for col in self.columns],
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TableDefinition:
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            columns=[TableColumn.from_dict(column) for column in data["columns"]],
            data={str(key): list(values) for key, values in data["data"].items()},
        )


PLOT_AXES = ("left", "right")


@dataclass
class PlotSeriesDef:
    """A series / curve definition pointing to a column in a table."""

    y_column: str
    label: str | None = None
    style: str = "solid"  # "solid", "dashed", "dotted"
    color: str | None = None
    axis: str = "left"
    """Y axis the series is drawn against: "left" or "right"."""

    def __post_init__(self) -> None:
        if self.axis not in PLOT_AXES:
            raise ValueError(f"Plot series axis must be 'left' or 'right', got {self.axis!r}.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "y_column": self.y_column,
            "label": self.label,
            "style": self.style,
            "color": self.color,
            "axis": self.axis,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlotSeriesDef:
        return cls(
            y_column=str(data["y_column"]),
            label=data["label"],
            style=str(data["style"]),
            color=data["color"],
            axis=str(data["axis"]),
        )


@dataclass
class PlotDefinition:
    """Plot view derived from an underlying table."""

    id: str
    title: str = ""
    table_id: str = ""
    x_column: str = ""
    series: list[PlotSeriesDef] = field(default_factory=list)
    x_label: str | None = None
    y_label: str | None = None
    y2_label: str | None = None
    """Title of the right axis, for series drawn against it."""
    valid_column: str | None = None
    """Boolean table column; the x ranges where it is false are shaded."""

    def __post_init__(self) -> None:
        if not self.title:
            object.__setattr__(self, "title", self.id.replace("_", " ").title())

    def get_x_label_and_unit(self, table: TableDefinition) -> tuple[str, str]:
        """Resolve x-axis label and unit from table column unless explicitly overridden."""
        col = table.get_column_def(self.x_column)
        label = self.x_label or (col.label if col else self.x_column)
        unit = col.unit if col else ""
        return (label, unit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "table_id": self.table_id,
            "x_column": self.x_column,
            "series": [s.to_dict() for s in self.series],
            "x_label": self.x_label,
            "y_label": self.y_label,
            "y2_label": self.y2_label,
            "valid_column": self.valid_column,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlotDefinition:
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            table_id=str(data["table_id"]),
            x_column=str(data["x_column"]),
            series=[PlotSeriesDef.from_dict(series) for series in data["series"]],
            x_label=data["x_label"],
            y_label=data["y_label"],
            y2_label=data["y2_label"],
            valid_column=data["valid_column"],
        )


def _plots_from_dict(raw: dict[str, Any]) -> dict[str, PlotDefinition]:
    return {str(key): PlotDefinition.from_dict(plot) for key, plot in raw.items()}


class SolverResult:
    """Standardized output result produced by a solver execution.

    Holds summary metrics, tabular data (single source of truth),
    and plot views derived from the tables.
    """

    def __init__(
        self,
        solver_id: str,
        config: SolverConfig,
        id: str | None = None,
        name: str = "Solver Result",
        timestamp: str | None = None,
        status: SolverStatus = SolverStatus.COMPLETED,
        execution_time_ms: float = 0.0,
        summary: dict[str, SummaryItem] | None = None,
        tables: dict[str, TableDefinition] | None = None,
        plots: dict[str, PlotDefinition] | None = None,
        artifacts: dict[str, str] | None = None,
    ) -> None:
        self.solver_id = solver_id
        self.config = config
        self.id = id or str(uuid.uuid4())
        self.name = name
        self.timestamp = timestamp or datetime.datetime.now(datetime.UTC).isoformat()
        self.status = status
        self.execution_time_ms = execution_time_ms

        # Summary
        self.summary: dict[str, SummaryItem] = dict(summary) if summary else {}

        # Tables (Single Source of Truth)
        self.tables: dict[str, TableDefinition] = dict(tables) if tables else {}

        # Plots
        self.plots: dict[str, PlotDefinition] = dict(plots) if plots else {}
        self._initial_plots: dict[str, PlotDefinition] = {
            k: PlotDefinition.from_dict(v.to_dict()) for k, v in self.plots.items()
        }

        # Artifacts & errors
        self.artifacts: dict[str, str] = dict(artifacts) if artifacts else {}

    def __repr__(self) -> str:
        return (
            f"SolverResult(id={self.id!r}, solver_id={self.solver_id!r}, "
            f"status={self.status}, tables={list(self.tables.keys())})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SolverResult):
            return False
        return (
            self.id == other.id
            and self.solver_id == other.solver_id
            and self.status == other.status
            and self.summary == other.summary
            and self.tables == other.tables
            and self.plots == other.plots
        )

    # ------------------------------------------------------------------
    # Convenience Builder Helpers
    # ------------------------------------------------------------------

    def add_summary(
        self,
        key: str,
        value: float | int | str | bool,
        label: str = "",
        unit: str = "",
        quantity_id: str | None = None,
    ) -> SummaryItem:
        """Add a summary metric to the result."""
        item = SummaryItem(
            key=key,
            value=value,
            label=label,
            unit=unit,
            quantity_id=quantity_id,
        )
        self.summary[key] = item
        return item

    def add_table(
        self,
        table_id: str,
        title: str = "",
        columns: list[TableColumn | tuple[str, str, str]] | None = None,
        data: dict[str, list[Any]] | list[dict[str, Any]] | None = None,
    ) -> TableDefinition:
        """Create, add, and return a TableDefinition."""
        parsed_cols: list[TableColumn] = []
        if columns:
            for c in columns:
                if isinstance(c, TableColumn):
                    parsed_cols.append(c)
                elif isinstance(c, (tuple, list)) and len(c) >= 2:
                    k, lbl = c[0], c[1]
                    u = c[2] if len(c) > 2 else ""
                    parsed_cols.append(TableColumn(key=k, label=lbl, unit=u))

        columnar_data: dict[str, list[Any]] = {}
        if isinstance(data, dict):
            columnar_data = dict(data)
        elif isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    for k, v in row.items():
                        columnar_data.setdefault(k, []).append(v)

        table = TableDefinition(
            id=table_id,
            title=title or table_id.replace("_", " ").title(),
            columns=parsed_cols,
            data=columnar_data,
        )
        self.tables[table_id] = table
        return table

    def add_plot(
        self,
        plot_id: str,
        table_id: str,
        x_column: str,
        y_columns: list[str] | None = None,
        title: str = "",
        series: list[PlotSeriesDef] | None = None,
        x_label: str | None = None,
        y_label: str | None = None,
    ) -> PlotDefinition:
        """Create, add, and return a PlotDefinition derived from a table."""
        parsed_series: list[PlotSeriesDef] = []
        if series:
            parsed_series.extend(series)
        elif y_columns:
            for y in y_columns:
                parsed_series.append(PlotSeriesDef(y_column=y))

        plot = PlotDefinition(
            id=plot_id,
            title=title or plot_id.replace("_", " ").title(),
            table_id=table_id,
            x_column=x_column,
            series=parsed_series,
            x_label=x_label,
            y_label=y_label,
        )
        self.plots[plot_id] = plot
        if plot_id not in self._initial_plots:
            self._initial_plots[plot_id] = PlotDefinition.from_dict(plot.to_dict())
        return plot

    def reset_plot(self, plot_id: str) -> PlotDefinition | None:
        """Reset a plot definition back to its original state as generated by the solver."""
        if plot_id in self._initial_plots:
            restored = PlotDefinition.from_dict(self._initial_plots[plot_id].to_dict())
            if plot_id in self.plots:
                target = self.plots[plot_id]
                target.title = restored.title
                target.table_id = restored.table_id
                target.x_column = restored.x_column
                target.series = [PlotSeriesDef.from_dict(s.to_dict()) for s in restored.series]
                target.x_label = restored.x_label
                target.y_label = restored.y_label
                target.y2_label = restored.y2_label
                target.valid_column = restored.valid_column
                return target
            self.plots[plot_id] = restored
            return restored
        return None

    # ------------------------------------------------------------------
    # Serialization & Exporting
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "solver_id": self.solver_id,
            "name": self.name,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "execution_time_ms": self.execution_time_ms,
            "config": self.config.to_dict(),
            "summary": {k: item.to_dict() for k, item in self.summary.items()},
            "tables": {k: table.to_dict() for k, table in self.tables.items()},
            "plots": {k: plot.to_dict() for k, plot in self.plots.items()},
            "initial_plots": {k: plot.to_dict() for k, plot in self._initial_plots.items()},
            "artifacts": self.artifacts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SolverResult:
        """Deserialize result from a dictionary."""
        res = cls(
            id=str(data["id"]),
            solver_id=str(data["solver_id"]),
            name=str(data["name"]),
            timestamp=str(data["timestamp"]),
            status=SolverStatus(data["status"]),
            execution_time_ms=float(data["execution_time_ms"]),
            config=SolverConfig.from_dict(data["config"]),
            summary={
                str(key): SummaryItem.from_dict(item) for key, item in data["summary"].items()
            },
            tables={
                str(key): TableDefinition.from_dict(table) for key, table in data["tables"].items()
            },
            plots=_plots_from_dict(data["plots"]),
            artifacts={str(k): str(v) for k, v in data["artifacts"].items()},
        )
        res._initial_plots = _plots_from_dict(data["initial_plots"])
        return res

    # ------------------------------------------------------------------
    # Core Export Utilities
    # ------------------------------------------------------------------

    def export_csv(self, target_dir: Path | str, use_display_units: bool = False) -> list[Path]:
        """Export all tables and summary to CSV files in target_dir."""
        target = Path(target_dir).resolve()
        target.mkdir(parents=True, exist_ok=True)
        exported: list[Path] = []

        if self.summary:
            summary_path = target / "summary.csv"
            self.export_summary_csv(summary_path, use_display_units=use_display_units)
            exported.append(summary_path)

        for table_id in self.tables:
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in table_id)
            table_path = target / f"{safe_name}.csv"
            self.export_table_csv(table_id, table_path, use_display_units=use_display_units)
            exported.append(table_path)

        return exported

    def export_table_csv(
        self, table_id: str, target_file: Path | str, use_display_units: bool = False
    ) -> Path:
        """Export a single table to a CSV file."""
        table = self.tables.get(table_id)
        if table is None:
            raise KeyError(f"Table '{table_id}' not found in result")
        target = Path(target_file).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(table.to_csv(use_display_units=use_display_units), encoding="utf-8")
        return target

    def export_summary_csv(self, target_file: Path | str, use_display_units: bool = False) -> Path:
        """Export summary metrics to a CSV file."""
        target = Path(target_file).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Key", "Label", "Value", "Unit"])
        for item in self.summary.values():
            val, unit = (
                item.display_value_and_unit() if use_display_units else (item.value, item.unit)
            )
            writer.writerow([item.key, item.label, val, unit])

        target.write_text(output.getvalue(), encoding="utf-8")
        return target

    def export_json(self, target_file: Path | str) -> Path:
        """Export entire analysis result as a standalone JSON file."""
        target = Path(target_file).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return target
