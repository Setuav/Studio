"""Thread-safe in-memory cache for 2D airfoil polar data."""
from __future__ import annotations

import hashlib
import logging
import math
import threading
from collections import OrderedDict
from typing import Sequence

from .airfoil_models import AirfoilPolar

logger = logging.getLogger(__name__)


def _compute_cache_key(
    airfoil_identifier: str | Sequence[Sequence[float]],
    reynolds: float,
    mach: float,
    alphas: Sequence[float],
    n_crit: float = 9.0,
    model_size: str = "large",
) -> str:
    """Generate a deterministic hash key for an airfoil analysis condition."""
    if isinstance(airfoil_identifier, str):
        ident_str = airfoil_identifier.strip().lower()
    else:
        # Array of (x, y) coordinates
        coords_str = "_".join(f"{round(pt[0], 4):.4f},{round(pt[1], 4):.4f}" for pt in airfoil_identifier)
        ident_str = hashlib.sha256(coords_str.encode("utf-8")).hexdigest()[:16]

    # Quantize Reynolds to 4 significant digits
    if reynolds > 0:
        exp = math.floor(math.log10(reynolds))
        re_quant = round(reynolds, -int(exp) + 3)
    else:
        re_quant = 0.0

    mach_quant = round(mach, 3)
    n_crit_quant = round(n_crit, 2)
    model = model_size.strip().lower()
    alphas_quant = ",".join(f"{round(float(a), 2):.2f}" for a in sorted(alphas))

    raw_key = (
        f"{ident_str}|Re={float(re_quant):.12g}|M={float(mach_quant):.12g}"
        f"|Ncrit={float(n_crit_quant):.12g}"
        f"|model={model}|alphas=[{alphas_quant}]"
    )
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class AirfoilPolarCache:
    """Thread-safe LRU cache for 2D airfoil polars."""

    def __init__(self, max_entries: int = 512) -> None:
        self._max_entries = max_entries
        self._cache: OrderedDict[str, AirfoilPolar] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(
        self,
        airfoil_identifier: str | Sequence[Sequence[float]],
        reynolds: float,
        mach: float,
        alphas: Sequence[float],
        n_crit: float = 9.0,
        model_size: str = "large",
    ) -> AirfoilPolar | None:
        """Lookup cached airfoil polar. Returns None on cache miss."""
        key = _compute_cache_key(
            airfoil_identifier,
            reynolds,
            mach,
            alphas,
            n_crit,
            model_size,
        )
        with self._lock:
            if key in self._cache:
                self._hits += 1
                self._cache.move_to_end(key)
                return self._cache[key]
            self._misses += 1
            return None

    def put(
        self,
        polar: AirfoilPolar,
        alphas: Sequence[float],
        airfoil_identifier: str | Sequence[Sequence[float]] | None = None,
        model_size: str | None = None,
    ) -> None:
        """Store an airfoil polar in the cache."""
        ident = airfoil_identifier if airfoil_identifier is not None else polar.airfoil_name
        key = _compute_cache_key(
            ident,
            polar.reynolds,
            polar.mach,
            alphas,
            polar.n_crit,
            model_size or polar.model_size,
        )
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = polar
            if len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, int]:
        """Return cache performance statistics."""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_entries": self._max_entries,
                "hits": self._hits,
                "misses": self._misses,
            }


# Global singleton instance for app-wide airfoil caching
global_airfoil_cache = AirfoilPolarCache()
