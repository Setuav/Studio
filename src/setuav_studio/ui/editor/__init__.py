"""Component property and instance editors."""

from __future__ import annotations

from setuav_studio.ui.editor.analysis_plot import AnalysisPlotPropertyEditor
from setuav_studio.ui.editor.analysis_table import AnalysisTablePropertyEditor
from setuav_studio.ui.editor.component import BaseComponentEditor
from setuav_studio.ui.editor.constraint import ConstraintPropertyEditor
from setuav_studio.ui.editor.envelope import EnvelopeEditor
from setuav_studio.ui.editor.mass import MassPropertiesEditor
from setuav_studio.ui.editor.parameter import ParameterPropertyEditor
from setuav_studio.ui.editor.solver_config import SolverConfigPropertyEditor
from setuav_studio.ui.editor.transform import TransformEditor
from setuav_studio.ui.editor.vehicle import VehicleSummaryEditor

__all__ = [
    "AnalysisPlotPropertyEditor",
    "AnalysisTablePropertyEditor",
    "BaseComponentEditor",
    "ConstraintPropertyEditor",
    "EnvelopeEditor",
    "MassPropertiesEditor",
    "ParameterPropertyEditor",
    "SolverConfigPropertyEditor",
    "TransformEditor",
    "VehicleSummaryEditor",
]
