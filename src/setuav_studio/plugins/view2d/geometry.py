"""Shared, transient project-geometry source for 2D canvases."""

from __future__ import annotations

from typing import Any


class View2DGeometrySource:
    """Cache one geometry snapshot for all projections in a view group."""

    def __init__(self, api: Any) -> None:
        self._api = api
        self._project: Any | None = None
        self._data: Any | None = None
        api.on_project_changed(self._invalidate)
        api.on_project_content_changed(self._invalidate)

    def current(self) -> Any:
        project = self._api.current_project
        if project is not self._project or self._data is None:
            self._project = project
            try:
                self._data = self._api.build_geometry_data(project)
            except Exception:
                self._data = None
        return self._data

    def refresh(self) -> Any:
        self._project = self._api.current_project
        try:
            self._data = self._api.build_geometry_data(self._project)
        except Exception:
            self._data = None
        return self._data

    def _invalidate(self, _project: Any) -> None:
        self._data = None
