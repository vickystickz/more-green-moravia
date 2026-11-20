"""Place names for points, from the Mapy.com reverse geocoder.

Optional: without MAPY_API_KEY every lookup returns None and the agent names
places by microzone only. Hexagons don't move, so answers are cached for the
life of the process.
"""

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

URL = "https://api.mapy.com/v1/rgeocode"
TIMEOUT_SECONDS = 5.0
MAX_PARALLEL = 5

_cache: dict[tuple[float, float, str], dict[str, Any] | None] = {}


def enabled() -> bool:
    return bool(settings.MAPY_API_KEY)


async def reverse_many(
    points: list[tuple[float, float]], lang: str = "cs"
) -> list[dict[str, Any] | None]:
    """The place at each (lon, lat), or None where it is unknown or the lookup failed."""
    if not enabled():
        return [None] * len(points)
    limit = asyncio.Semaphore(MAX_PARALLEL)
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:

        async def one(lon: float, lat: float) -> dict[str, Any] | None:
            async with limit:
                return await _reverse(client, lon, lat, lang)

        return list(await asyncio.gather(*(one(lon, lat) for lon, lat in points)))


async def _reverse(
    client: httpx.AsyncClient, lon: float, lat: float, lang: str
) -> dict[str, Any] | None:
    key = (round(lon, 6), round(lat, 6), lang)
    if key in _cache:
        return _cache[key]
    try:
        response = await client.get(
            URL,
            params={"lon": lon, "lat": lat, "lang": lang, "apikey": settings.MAPY_API_KEY},
        )
        response.raise_for_status()
        place = _place(response.json())
    except (httpx.HTTPError, ValueError):
        logger.warning("Reverse geocoding failed for %s, %s", lon, lat, exc_info=True)
        return None  # not cached: it may work next time
    _cache[key] = place
    return place


def _place(data: dict[str, Any]) -> dict[str, Any] | None:
    items = data.get("items") or []
    if not items:
        return None
    item = items[0]
    parts = {
        str(part.get("type", "")).removeprefix("regional."): part.get("name")
        for part in item.get("regionalStructure") or []
        if part.get("name")
    }
    place = {
        "name": item.get("name"),
        "street": parts.get("street"),
        "district": parts.get("municipality_part"),
        "location": item.get("location"),
    }
    return {k: v for k, v in place.items() if v} or None
