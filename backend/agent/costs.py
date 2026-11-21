"""Green roof cost estimates for public buildings, from data/green_roof_costs.json.

The file holds per-m² rates with their sources: one record for installation
(CZK/m²) and one for annual maintenance (CZK/m²/yr). A building's estimate is
its roof area times the rate (min, average, max). Edit the file to change the
rates or sources; it is reread when it changes.
"""

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Rate:
    min: float
    avg: float
    max: float
    unit: str
    type: str
    source: str
    url: str | None

    def total(self, area_m2: float) -> dict[str, float]:
        return {k: _round(getattr(self, k) * area_m2) for k in ("min", "avg", "max")}

    def describe(self) -> dict[str, Any]:
        return {
            "per_m2": {"min": self.min, "avg": self.avg, "max": self.max},
            "unit": self.unit,
            "type": self.type,
            "source": self.source,
            "url": self.url,
        }


@dataclass(frozen=True)
class GreenRoofCosts:
    currency: str
    install: Rate
    maintenance: Rate
    accessed: str | None

    def for_roof(self, area_m2: float | None) -> dict[str, float]:
        """Flat feature properties (GeoJSON properties can't nest in MapLibre)."""
        if not area_m2:
            return {}
        out: dict[str, float] = {}
        for prefix, rate in (("install", self.install), ("maint", self.maintenance)):
            for k, v in rate.total(area_m2).items():
                out[f"{prefix}_{k}"] = v
        return out

    def describe(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "accessed": self.accessed,
            "install": self.install.describe(),
            "maintenance": self.maintenance.describe(),
            "basis": "roof area x rate per m2 (extensive green roof)",
        }


def _round(value: float) -> float:
    """Three significant figures: an estimate, not an invoice."""
    if value <= 0:
        return 0
    digits = 2 - math.floor(math.log10(value))
    return round(value, digits) if digits > 0 else float(round(value, digits))


def _rate(record: dict[str, Any]) -> Rate:
    low, high = float(record["cost_min"]), float(record["cost_max"])
    return Rate(
        min=low,
        avg=float(record.get("cost_average") or (low + high) / 2),
        max=high,
        unit=record.get("unit", ""),
        type=record.get("type", ""),
        source=record.get("source", ""),
        url=record.get("url"),
    )


def parse(doc: dict[str, Any]) -> GreenRoofCosts:
    """Pick the installation and the maintenance record (by their unit or type)."""
    install = maintenance = None
    for record in doc.get("records", []):
        text = f"{record.get('unit', '')} {record.get('type', '')}".lower()
        if "maintenance" in text and maintenance is None:
            maintenance = record
        elif ("installation" in text or "investment" in text) and install is None:
            install = record
    if install is None or maintenance is None:
        raise ValueError("needs one installation and one maintenance record")
    currencies = {install.get("currency"), maintenance.get("currency")}
    if len(currencies) != 1:
        raise ValueError(f"records use different currencies: {currencies}")
    return GreenRoofCosts(
        currency=currencies.pop() or "CZK",
        install=_rate(install),
        maintenance=_rate(maintenance),
        accessed=doc.get("accessed"),
    )


_cache: tuple[Path, int, GreenRoofCosts | None] | None = None


def load(path: Path | None = None) -> GreenRoofCosts | None:
    """The costs, or None when the file is missing or unusable (logged once)."""
    global _cache
    path = path or settings.path(settings.GREEN_ROOF_COSTS)
    mtime = path.stat().st_mtime_ns if path.exists() else -1
    if _cache and _cache[0] == path and _cache[1] == mtime:
        return _cache[2]
    costs = None
    if mtime >= 0:
        try:
            costs = parse(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Green roof costs not used (%s): %s", path.name, exc)
    _cache = (path, mtime, costs)
    return costs
