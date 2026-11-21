"""GeoJSON layers for the map: what one agent step found, drawn as hexagons or
microzones, plus public building outlines on top when the step found buildings
(their features have `kind: "building"`). No model is involved; the body is the
step's `layer`."""

import json
from typing import Any

from pydantic import BaseModel

from agent import costs as green_roof
from agent.catalog import AgentContext
from agent.query import CLASS_BREAKS, LayerSpec, Level, Sql, _agg, _agg_sql, shown
from app.database import Database

MAX_IDS = 1000
MAX_BUILDINGS = 50


class Legend(BaseModel):
    label: str
    unit: str
    min: float | None
    max: float | None
    breaks: list[float]  # upper bounds of the first four of five classes


class MapLayer(BaseModel):
    title: str
    level: Level
    metric: str
    legend: Legend
    features: dict[str, Any]  # GeoJSON FeatureCollection
    bbox: list[float] | None  # [west, south, east, north]
    scoring: dict[str, Any] | None
    # Green roof cost rates and their sources, when the layer has buildings.
    costs: dict[str, Any] | None = None


async def build(db: Database, ctx: AgentContext, spec: LayerSpec) -> MapLayer:
    scoring = spec.resolved()
    metric = ctx.metric(spec.metric)
    q = Sql(ctx, scoring)
    value = q.metric(metric)
    where = q.where(spec.filters)
    ids = (spec.ids or [])[:MAX_IDS]

    if spec.level is Level.HEX:
        id_clause = f"AND h3_index IN ({', '.join(q.bind(i) for i in ids)})" if ids else ""
        result = await db.query(
            f"""
            SELECT h3_index AS id, mz_id AS name, {value} AS value, geometry
            FROM hexes WHERE {where} {id_clause}
            """,
            q.params,
        )
    else:
        agg = _agg(metric, spec.agg)
        names = [ctx.microzone(i) for i in ids]
        id_clause = f"AND z.name IN ({', '.join(q.bind(n) for n in names)})" if names else ""
        result = await db.query(
            f"""
            WITH v AS (
                SELECT mz_id, {_agg_sql(agg, value)} AS value, count(*) AS hexagons
                FROM hexes WHERE {where} AND mz_id IS NOT NULL GROUP BY mz_id
            )
            SELECT z.name AS id, z.name AS name, v.value, v.hexagons, z.geometry
            FROM microzones z JOIN v ON v.mz_id = z.name
            WHERE TRUE {id_clause}
            """,
            q.params,
        )

    # With buildings, the buildings carry the rank numbers, not their places.
    order = (
        {i: n for n, i in enumerate(names if spec.level is Level.MICROZONE else ids, 1)}
        if ids and not spec.buildings
        else {}
    )
    features = []
    values = []
    for row in result.rows:
        shown_value = shown(metric, row["value"])
        if isinstance(shown_value, (int, float)):
            values.append(float(shown_value))
        props: dict[str, Any] = {"id": row["id"], "name": row["name"], "value": shown_value}
        if order:
            props["rank"] = order.get(row["id"])
        if "hexagons" in row:
            props["hexagons"] = row["hexagons"]
        features.append(
            {
                "type": "Feature",
                "id": row["id"],
                "properties": props,
                "geometry": json.loads(row["geometry"]),
            }
        )
    features.sort(key=lambda f: f["properties"].get("rank") or 0)
    if spec.buildings:
        features += await _building_features(db, Sql(ctx, scoring), spec.buildings[:MAX_BUILDINGS])

    return MapLayer(
        title=spec.title or metric.label,
        level=spec.level,
        metric=metric.name,
        legend=Legend(
            label=metric.label,
            unit=metric.shown_unit,
            min=min(values) if values else None,
            max=max(values) if values else None,
            breaks=list(CLASS_BREAKS) if metric.is_score else _quantile_breaks(values),
        ),
        features={"type": "FeatureCollection", "features": features},
        bbox=_bbox(features),
        scoring=scoring.describe() if metric.derived else None,
        costs=_costs_info() if spec.buildings else None,
    )


def _costs_info() -> dict[str, Any] | None:
    costs = green_roof.load()
    return costs.describe() if costs else None


async def _building_features(db: Database, q: Sql, ids: list[str]) -> list[dict[str, Any]]:
    """Public building outlines, drawn on top of their places, numbered in order.
    q must be a fresh Sql: its parameters are this query's only."""
    result = await db.query(
        f"""
        SELECT building_id, name, kind, roof_m2, roof_shape, geometry
        FROM buildings WHERE building_id IN ({", ".join(q.bind(i) for i in ids)})
        """,
        q.params,
    )
    rank = {i: n for n, i in enumerate(ids, 1)}
    costs = green_roof.load()
    features = [
        {
            "type": "Feature",
            "id": row["building_id"],
            "properties": {
                "kind": "building",
                "id": row["building_id"],
                "name": row["name"],
                "type": row["kind"],
                "roof_m2": round(row["roof_m2"]) if row["roof_m2"] is not None else None,
                "roof_shape": row["roof_shape"],
                "rank": rank.get(row["building_id"]),
                # install_min/avg/max (one-off) and maint_min/avg/max (per
                # year), in costs.currency: roof area x rate per m².
                **(costs.for_roof(row["roof_m2"]) if costs else {}),
            },
            "geometry": json.loads(row["geometry"]),
        }
        for row in result.rows
    ]
    return sorted(features, key=lambda f: f["properties"]["rank"] or 0)


def _quantile_breaks(values: list[float]) -> list[float]:
    if not values:
        return []
    ordered = sorted(values)
    breaks = []
    for share in (0.2, 0.4, 0.6, 0.8):
        breaks.append(round(ordered[min(int(share * len(ordered)), len(ordered) - 1)], 3))
    return breaks


def _bbox(features: list[dict[str, Any]]) -> list[float] | None:
    xs: list[float] = []
    ys: list[float] = []

    def walk(node: Any) -> None:
        if isinstance(node, list) and node and isinstance(node[0], (int, float)):
            xs.append(node[0])
            ys.append(node[1])
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for feature in features:
        walk((feature.get("geometry") or {}).get("coordinates"))
    return [min(xs), min(ys), max(xs), max(ys)] if xs else None
