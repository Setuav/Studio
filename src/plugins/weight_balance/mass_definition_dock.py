"""Backward-compatibility shim for MassPropertiesEditor.

The editor implementation has moved to core (`setuav_studio.ui.editor.mass`).
"""

from __future__ import annotations

from setuav_studio.ui.editor.mass import (
    EXTENSION_ID,
    WB_EXTENSION_ID,
    MassPropertiesEditor,
)

__all__ = [
    "EXTENSION_ID",
    "WB_EXTENSION_ID",
    "MassPropertiesEditor",
]
