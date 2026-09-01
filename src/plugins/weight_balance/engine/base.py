"""Weight-and-balance engine contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from setuav_studio.project import ProjectDocument

from ..models import WeightBalanceResult


class WeightBalanceEngine(ABC):
    @abstractmethod
    def evaluate(
        self,
        project: ProjectDocument,
    ) -> WeightBalanceResult: ...


class WeightBalanceError(ValueError):
    """Raised when a project has no usable mass model."""
