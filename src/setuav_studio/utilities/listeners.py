"""Calling listeners that may belong to destroyed Qt objects."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def is_deleted_qobject_error(exc: RuntimeError) -> bool:
    """Whether ``exc`` is shiboken refusing a call on a destroyed Qt object."""
    return "already deleted" in str(exc)


def dispatch_listeners(listeners: list[Callable[..., Any]], *args: Any) -> None:
    """Call every listener with ``args``.

    A listener whose Qt object was destroyed (a lambda capturing a deleted
    widget) is dropped; any other error propagates to the caller.
    """
    for listener in list(listeners):
        try:
            listener(*args)
        except RuntimeError as exc:
            if not is_deleted_qobject_error(exc):
                raise
            if listener in listeners:
                listeners.remove(listener)
