"""Central Unit Manager with QSettings persistence and Qt change signals."""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal

from setuav_studio.units.presets import PRESETS
from setuav_studio.units.quantities import (
    QUANTITIES,
    get_quantity_for_unit,
)


def convert_value(
    value: float,
    quantity_id: str,
    from_unit_id: str,
    to_unit_id: str,
) -> float:
    """Convert a numeric value between two units of the same physical quantity."""
    if from_unit_id == to_unit_id:
        return float(value)

    qty = QUANTITIES.get(quantity_id)
    if qty is None:
        return float(value)

    return qty.convert(value, from_unit_id, to_unit_id)


class UnitManager(QObject):
    """Central singleton managing application-wide display units and conversions."""

    units_changed = Signal()

    _SETTINGS_PREFIX = "units/"
    _PRESET_KEY = "units/active_preset"

    def __init__(self) -> None:
        super().__init__()
        self._display_units: dict[str, str] = {}
        self._active_preset: str = "si"
        self._load_from_settings()

    def _load_from_settings(self) -> None:
        settings = QSettings()
        self._active_preset = str(settings.value(self._PRESET_KEY, "si")).lower()

        preset_defaults = PRESETS.get(self._active_preset, PRESETS["si"])
        for q_id, q_def in QUANTITIES.items():
            fallback = preset_defaults.get(q_id, q_def.base_unit_id)
            saved_unit = str(settings.value(f"{self._SETTINGS_PREFIX}{q_id}", fallback)).lower()
            if saved_unit in q_def.units:
                self._display_units[q_id] = saved_unit
            else:
                self._display_units[q_id] = fallback

    def save_to_settings(self) -> None:
        settings = QSettings()
        settings.setValue(self._PRESET_KEY, self._active_preset)
        for q_id, unit_id in self._display_units.items():
            settings.setValue(f"{self._SETTINGS_PREFIX}{q_id}", unit_id)
        settings.sync()
        self.units_changed.emit()

    def get_active_preset(self) -> str:
        return self._active_preset

    def set_active_preset(self, preset_id: str) -> None:
        preset_id = preset_id.lower()
        if preset_id in PRESETS:
            self._active_preset = preset_id
            preset_map = PRESETS[preset_id]
            for q_id in QUANTITIES:
                if q_id in preset_map:
                    self._display_units[q_id] = preset_map[q_id]
        else:
            self._active_preset = "custom"

    def get_display_unit(self, quantity_id: str) -> str:
        """Get the active display unit ID for a physical quantity (e.g. 'mm', 'in')."""
        if quantity_id in self._display_units:
            return self._display_units[quantity_id]
        qty = QUANTITIES.get(quantity_id)
        return qty.base_unit_id if qty else ""

    def set_display_unit(self, quantity_id: str, unit_id: str) -> None:
        """Set display unit for a quantity and switch preset to 'custom' if needed."""
        qty = QUANTITIES.get(quantity_id)
        if qty and unit_id in qty.units:
            self._display_units[quantity_id] = unit_id
            self._check_and_update_active_preset()

    def _check_and_update_active_preset(self) -> None:
        for preset_id, preset_map in PRESETS.items():
            matches = True
            for q_id, u_id in self._display_units.items():
                if q_id in preset_map and preset_map[q_id] != u_id:
                    matches = False
                    break
            if matches:
                self._active_preset = preset_id
                return
        self._active_preset = "custom"

    def get_unit_symbol(self, quantity_or_unit: str, unit_id: str | None = None) -> str:
        """Get the human-readable display symbol (e.g. 'dm²', 'in', '°', 'kg·m²')."""
        if not quantity_or_unit:
            return unit_id or ""
        q_id = get_quantity_for_unit(quantity_or_unit) or quantity_or_unit
        qty = QUANTITIES.get(q_id)
        if not qty:
            return unit_id or quantity_or_unit
        u_id = unit_id or self.get_display_unit(q_id)
        u_def = qty.units.get(u_id)
        return u_def.symbol if u_def else u_id

    def to_display(self, base_value: float, quantity_or_schema_unit: str) -> float:
        """Convert a base storage value to the user's active display unit."""
        q_id = get_quantity_for_unit(quantity_or_schema_unit) or quantity_or_schema_unit
        qty = QUANTITIES.get(q_id)
        if qty is None:
            return float(base_value)

        target_unit = self.get_display_unit(q_id)
        return convert_value(base_value, q_id, qty.base_unit_id, target_unit)

    def to_base(self, display_value: float, quantity_or_schema_unit: str) -> float:
        """Convert a display unit value back to standard base storage unit."""
        q_id = get_quantity_for_unit(quantity_or_schema_unit) or quantity_or_schema_unit
        qty = QUANTITIES.get(q_id)
        if qty is None:
            return float(display_value)

        current_unit = self.get_display_unit(q_id)
        return convert_value(display_value, q_id, current_unit, qty.base_unit_id)

    from_display = to_base

    def get_inertia_display(self, base_val_kg_m2: float) -> tuple[float, str]:
        """Convert standard kg*m^2 inertia tensor value based on active inertia unit."""
        disp_val = self.to_display(base_val_kg_m2, "inertia")
        symbol = self.get_unit_symbol("inertia")
        return disp_val, symbol

    def get_wing_loading_display(self, base_val_g_dm2: float) -> tuple[float, str]:
        """Convert standard g/dm^2 wing loading based on active mass & area units."""
        mass_u_id = self.get_display_unit("mass")
        area_u_id = self.get_display_unit("area")

        mass_u = QUANTITIES["mass"].units.get(mass_u_id)
        area_u = QUANTITIES["area"].units.get(area_u_id)

        if not mass_u or not area_u:
            return base_val_g_dm2, "g/dm²"

        mass_scale = mass_u.from_base if not callable(mass_u.from_base) else 1.0
        area_scale = area_u.from_base if not callable(area_u.from_base) else 1.0

        scale = mass_scale / area_scale if area_scale != 0 else 1.0
        disp_val = base_val_g_dm2 * scale
        symbol = f"{mass_u.symbol}/{area_u.symbol}"
        return disp_val, symbol


_unit_manager_instance: UnitManager | None = None


def get_unit_manager() -> UnitManager:
    """Get the global UnitManager instance."""
    global _unit_manager_instance
    if _unit_manager_instance is None:
        _unit_manager_instance = UnitManager()
    return _unit_manager_instance


__all__ = [
    "UnitManager",
    "convert_value",
    "get_unit_manager",
]
