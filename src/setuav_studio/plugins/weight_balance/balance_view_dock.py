"""Weight-Balance CG projections backed by the shared 2D view engine."""

from __future__ import annotations

from math import sqrt

from PySide6.QtCore import QEvent, QSettings, QTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDockWidget, QHBoxLayout, QLabel, QMainWindow, QStatusBar, QWidget

from setuav_studio.plugin_system import StudioAPI
from setuav_studio.plugins.view2d import View2DCanvas, View2DGeometrySource, View2DScene
from setuav_studio.ui.theme import chart_color, tokens

from .models import WeightBalanceResult

CG_COLOR = "#ff3b30"
GEOMETRY_COMPONENT_COLOR = "#2e8cff"
ELECTRONICS_COMPONENT_COLOR = "#ff8a00"


class _BalanceProjectionCanvas(View2DCanvas):
    """Adapt Weight-Balance markers to the generic projection scene."""

    def __init__(
        self,
        api: StudioAPI,
        *,
        axes: tuple[int, int],
        title: str,
        x_label: str,
        y_label: str,
        invert_vertical: bool = False,
        geometry_source: View2DGeometrySource,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            api=api,
            axes=axes,
            title=title,
            x_label=x_label,
            y_label=y_label,
            units="mm",
            invert_vertical=invert_vertical,
            geometry_source=geometry_source,
            parent=parent,
        )
        self.set_show_legend(False)
        self.result: WeightBalanceResult | None = None

    def set_result(self, result: WeightBalanceResult) -> None:
        self.result = result
        scene = View2DScene(
            # The enclosing QDockWidget already supplies the view title.
            title="",
            x_label=self._x_label,
            y_label=self._y_label,
            units="mm",
        )
        total_color = CG_COLOR
        max_mass = max((item.mass_kg for item in result.components), default=1.0)
        for item in result.components:
            point = (
                item.cg_body_m[self._axes[0]] * 1000.0,
                item.cg_body_m[self._axes[1]] * 1000.0,
            )
            # Keep markers readable while still communicating relative mass.
            radius = 3.5 + 4.0 * sqrt(max(item.mass_kg, 0.0) / max_mass)
            scene.add_marker(
                item.component_id,
                point,
                label=item.component_name,
                tooltip=self._component_tooltip(item),
                color=self._component_color(item.component_type),
                radius=radius,
                symbol="ring",
                layer="component",
            )

        total = result.total.cg_body_m
        total_point = (
            total[self._axes[0]] * 1000.0,
            total[self._axes[1]] * 1000.0,
        )
        scene.add_marker(
            "aircraft-cg",
            total_point,
            label="Aircraft CG",
            tooltip=self._total_tooltip(result),
            color=total_color,
            radius=7.0,
            symbol="crosshair",
            layer="cg",
        )
        self.set_scene(scene)

    def _geometry_color(self) -> str:
        # Keep the aircraft outline neutral so it never competes with the
        # plugin-family component colours or the red CG guides.
        return tokens()["viewer_fuselage"]

    def _geometry_style(self) -> tuple[float, int]:
        # Keep the aircraft silhouette as context behind the stronger
        # component outlines and CG guides.
        return 0.8, 150

    @staticmethod
    def _component_color(component_type: str) -> str:
        """Return the colour assigned to the component's plugin family."""
        type_name = component_type.rsplit(":", 1)[-1].lower()
        if type_name in {"fuselage", "lifting-surface", "control-surface"}:
            return GEOMETRY_COMPONENT_COLOR
        if type_name in {"motor", "propeller", "esc", "battery"}:
            return ELECTRONICS_COMPONENT_COLOR
        return chart_color("cyan")

    def _component_tooltip(self, item) -> str:
        x, y, z = (value * 1000.0 for value in item.cg_body_m)
        return (
            f"<b>{item.component_name}</b><br>"
            f"Mass: {item.mass_kg * 1000.0:.1f} g<br>"
            f"Body CG: X {x:+.2f} · Y {y:+.2f} · Z {z:+.2f} mm"
        )

    def _total_tooltip(self, result: WeightBalanceResult) -> str:
        x, y, z = (value * 1000.0 for value in result.total.cg_body_m)
        return (
            "<b>Aircraft CG</b><br>"
            f"Mass: {result.total.mass_kg * 1000.0:.1f} g<br>"
            f"Body CG: X {x:+.2f} · Y {y:+.2f} · Z {z:+.2f} mm"
        )


class WeightBalanceViewDock(QMainWindow):
    """Container with two persistent, rearrangeable CG projection docks."""

    _LAYOUT_VERSION = 1
    _LAYOUT_KEY = "weight_balance/cg_view_dock_state"

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("weight_balance.view_widget")
        self._restoring_layout = True
        self._layout_save_scheduled = False
        self._layout_persistence_enabled = False
        self.setDockNestingEnabled(True)
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
        )
        geometry_source = View2DGeometrySource(api)

        self.top_canvas = _BalanceProjectionCanvas(
            api,
            # Put longitudinal X on the vertical screen axis.  This project
            # uses -X toward the nose, so invert the vertical direction to
            # draw the nose upward.
            axes=(1, 0),
            x_label="Y",
            y_label="X",
            invert_vertical=True,
            title="",
            geometry_source=geometry_source,
            parent=self,
        )
        self.side_canvas = _BalanceProjectionCanvas(
            api,
            axes=(0, 2),
            x_label="X",
            y_label="Z",
            title="",
            geometry_source=geometry_source,
            parent=self,
        )
        # Compatibility alias for integrations that used the original canvas.
        self.canvas = self.top_canvas

        self.top_dock = self._projection_dock(
            "Top View · X / Y",
            "weight_balance.cg_top_dock",
            self.top_canvas,
        )
        self.side_dock = self._projection_dock(
            "Side View · X / Z",
            "weight_balance.cg_side_dock",
            self.side_canvas,
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.top_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.side_dock)
        self.resizeDocks(
            [self.top_dock, self.side_dock],
            [1, 1],
            Qt.Orientation.Horizontal,
        )

        self._legend_bar = self._create_legend_bar()
        self.setStatusBar(self._legend_bar)

        for dock in (self.top_dock, self.side_dock):
            dock.dockLocationChanged.connect(self._schedule_layout_save)
            dock.topLevelChanged.connect(self._schedule_layout_save)
            dock.visibilityChanged.connect(self._schedule_layout_save)
            dock.installEventFilter(self)
        self._restore_internal_layout()
        self._restoring_layout = False

        api.subscribe("weight_balance.analysis_completed", self._set_result)

    def _restore_internal_layout(self) -> None:
        state = QSettings().value(self._LAYOUT_KEY)
        if state is None:
            return
        try:
            self.restoreState(state, self._LAYOUT_VERSION)
        except (TypeError, ValueError):
            # Ignore an old/corrupt preference and retain the deterministic
            # two-column default layout.
            return

    def _schedule_layout_save(self, *_args) -> None:
        if (
            not self._layout_persistence_enabled
            or self._restoring_layout
            or self._layout_save_scheduled
        ):
            return
        self._layout_save_scheduled = True
        QTimer.singleShot(0, self.save_layout)

    def save_layout(self) -> None:
        self._layout_save_scheduled = False
        if self._restoring_layout:
            return
        QSettings().setValue(
            self._LAYOUT_KEY,
            self.saveState(self._LAYOUT_VERSION),
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._schedule_layout_save()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._layout_persistence_enabled:
            QTimer.singleShot(0, self._enable_layout_persistence)

    def _enable_layout_persistence(self) -> None:
        self._layout_persistence_enabled = True

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if isinstance(watched, QDockWidget) and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
        ):
            self._schedule_layout_save()
        return super().eventFilter(watched, event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        self.save_layout()
        super().closeEvent(event)

    def _create_legend_bar(self) -> QStatusBar:
        bar = QStatusBar(self)
        bar.setObjectName("weight_balance.cg_legend_bar")
        bar.setSizeGripEnabled(False)
        bar.setFixedHeight(24)
        content = QWidget(bar)
        layout = QHBoxLayout(content)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(12)
        self._legend_labels: list[tuple[QLabel, str, str]] = []
        for text, role in (
            ("Geometry", "geometry"),
            ("Electronics", "electronics"),
            ("Aircraft CG", "red"),
        ):
            label = QLabel(content)
            self._legend_labels.append((label, role, text))
            layout.addWidget(label)
        layout.addStretch(1)
        bar.addWidget(content)
        self._refresh_legend_bar()
        return bar

    def _refresh_legend_bar(self) -> None:
        for label, role, text in getattr(self, "_legend_labels", ()):
            color = (
                CG_COLOR
                if role == "red"
                else GEOMETRY_COMPONENT_COLOR
                if role == "geometry"
                else ELECTRONICS_COMPONENT_COLOR
            )
            label.setText(f'<span style="color:{color}">●</span> {text}')

    def update_theme_style(self) -> None:
        self._refresh_legend_bar()
        self.top_canvas.refresh_geometry()
        self.side_canvas.refresh_geometry()

    @staticmethod
    def _projection_dock(title: str, object_name: str, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title)
        dock.setObjectName(object_name)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        dock.setMinimumSize(300, 210)
        dock.setWidget(widget)
        return dock

    def _set_result(self, result: WeightBalanceResult) -> None:
        self.top_canvas.set_result(result)
        self.side_canvas.set_result(result)
