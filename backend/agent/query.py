"""Compiles the agent's typed tool arguments into read-only DuckDB SQL.

This is the security core:
- the model never writes SQL: it picks metrics, filters and options;
- metric names must exist in the catalog (the allow-list of columns), and
  every value is a bound parameter;
- the database file is opened read-only.

Scores (0-1 in the data) come out as 0-100 and shares as percentages, the way
the app shows them, so the model never has to rescale a number. Filter values
are read on the same scale.
"""

import itertools
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent import places as places_api
from agent.catalog import AgentContext, Agg, Metric
from app.database import Database

FLOOR = 0.01
MAX_ROWS = 50
MAX_EXTRA = 5
MAX_LOCATE = 20
NEAREST_MAX_M = 400  # a point further than this from every hexagon is outside the index
CLASS_BREAKS = (20, 40, 60, 80)  # the map's five score classes, 0-100

# Columns any detail view shows, when the export has them.
KEY_METRICS = (
    "score",
    "need",
    "priority",
    "he",
    "v",
    "gd",
    "feas",
    "raw_residents",
    "raw_day_people",
    "raw_heatwave_tmax",
    "raw_heatwave_tmin",
    "raw_lst_microzone",
    "raw_share_65plus",
    "raw_share_75plus",
    "raw_share_0_4",
    "raw_sensitive_facilities",
    "raw_vegetation_share",
    "raw_ndvi_mean",
    "raw_green_share",
    "raw_tree_cover",
    "raw_sealing",
    "raw_green_per_capita",
    "raw_dist_green",
    "raw_brownfield_share",
    "raw_vacant_share",
    "raw_public_building_share",
    "raw_public_roof_m2",
    "raw_parking",
    "val_perceived_heat",
)
# Plain names for a few values in a single place's summary:
# summary key -> metric.
SUMMARY_ALIASES = {
    "green_vegetation": "raw_vegetation_share",
    "public_roof_m2": "raw_public_roof_m2",
    "surface_temp_c": "raw_lst_microzone",
    "residents_uncomfortable_share": "val_perceived_heat",
}
RANKED = ("score", "he", "v", "gd", "feas")


class ToolError(Exception):
    """A problem with the arguments that the model can fix; the message goes back to it."""


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------


class Preset(StrEnum):
    """The app's preset tiles (frontend/js/ui/presets.js)."""

    BALANCE = "balance"
    COOL_STREET = "cool-street"
    PROTECT_VULNERABLE = "protect-vulnerable"
    POCKET_PARKS = "pocket-parks"
    QUICK_WINS = "quick-wins"


THIRD = 1 / 3
PRESETS: dict[Preset, tuple[tuple[float, float, float], bool]] = {
    Preset.BALANCE: ((THIRD, THIRD, THIRD), False),
    Preset.COOL_STREET: ((0.5, 0.2, 0.3), False),
    Preset.PROTECT_VULNERABLE: ((0.3, 0.5, 0.2), False),
    Preset.POCKET_PARKS: ((0.2, 0.4, 0.4), False),
    Preset.QUICK_WINS: ((THIRD, THIRD, THIRD), True),
}


class Weights(BaseModel):
    he: float = Field(ge=0, le=1, description="Heat & people exposed")
    v: float = Field(ge=0, le=1, description="Vulnerable groups")
    gd: float = Field(ge=0, le=1, description="Lack of green")


class Op(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    BETWEEN = "between"
    IN = "in"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"


class Filter(BaseModel):
    model_config = ConfigDict(extra="ignore")

    metric: str = Field(description="A metric name, or 'microzone' to filter by microzone name")
    op: Op
    value: float | str | list[float | str] | None = Field(
        None,
        description="On the scale results show: scores 0-100, shares in %. "
        "between takes [low, high]; in takes a list",
    )


class Level(StrEnum):
    HEX = "hex"
    MICROZONE = "microzone"


class Language(StrEnum):
    CS = "cs"
    EN = "en"


class Order(StrEnum):
    DESC = "desc"
    ASC = "asc"


class ScoreArgs(BaseModel):
    """How 'score' is weighted. Default: the Balance preset, as the app opens."""

    model_config = ConfigDict(extra="ignore")

    preset: Preset | None = Field(None, description="One of the app's presets")
    weights: Weights | None = Field(
        None, description="Custom weights instead of a preset; they are rescaled to sum to 1"
    )
    only_buildable: bool | None = Field(
        None, description="Multiply by space to build, as the app's 'only places we can build'"
    )

    def resolved(self) -> "Scoring":
        base, buildable = PRESETS[self.preset or Preset.BALANCE]
        he, v, gd = base
        if self.weights is not None:
            total = self.weights.he + self.weights.v + self.weights.gd
            if total <= 0:
                raise ToolError("weights must not all be 0")
            he, v, gd = (self.weights.he / total, self.weights.v / total, self.weights.gd / total)
        if self.only_buildable is not None:
            buildable = self.only_buildable
        return Scoring(
            he,
            v,
            gd,
            buildable,
            self.preset.value
            if self.preset and not self.weights
            else "custom"
            if self.weights
            else "balance",
        )


class OverviewSpec(ScoreArgs):
    pass


class RankSpec(ScoreArgs):
    metric: str = Field("score", description="What to rank by")
    level: Level = Field(Level.HEX, description="hex: 200 m hexagons; microzone: city districts")
    order: Order = Field(Order.DESC, description="desc: highest first")
    limit: int = Field(10, ge=1, le=MAX_ROWS)
    agg: Agg | None = Field(
        None, description="For microzones: how hexagons add up (default: sum for counts, else avg)"
    )
    filters: list[Filter] = Field(default_factory=list)
    show: list[str] = Field(
        default_factory=list, description=f"Up to {MAX_EXTRA} more metrics to show per row"
    )


class SummarizeSpec(ScoreArgs):
    filters: list[Filter] = Field(default_factory=list)
    metrics: list[str] = Field(
        default_factory=lambda: ["score"], description="Metrics to total or average (up to 6)"
    )
    by_microzone: bool = Field(False, description="One row per microzone instead of one total")


class DescribeSpec(ScoreArgs):
    metric: str
    filters: list[Filter] = Field(default_factory=list)


class DetailSpec(ScoreArgs):
    h3_index: str | None = Field(None, description="One hexagon")
    microzone: str | None = Field(None, description="One microzone, by name")
    lon: float | None = Field(None, ge=-180, le=180, description="A point: its hexagon")
    lat: float | None = Field(None, ge=-90, le=90)

    @field_validator("h3_index", "microzone")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value


class LocateSpec(ScoreArgs):
    h3_indexes: list[str] = Field(
        min_length=1,
        max_length=MAX_LOCATE,
        description=f"Up to {MAX_LOCATE} hexagons (h3_index), e.g. from a ranking",
    )
    lang: Language = Field(Language.CS, description="Language of the place names")

    @field_validator("h3_indexes")
    @classmethod
    def clean_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(v.strip().lower() for v in values if v and v.strip()))


class LayerSpec(ScoreArgs):
    """What to draw: the body of POST /api/agent/map, and the `layer` of a tool step."""

    level: Level = Level.HEX
    metric: str = "score"
    ids: list[str] | None = Field(
        None, description="Only these hexagons (h3_index) or microzones (name), in rank order"
    )
    filters: list[Filter] = Field(default_factory=list)
    agg: Agg | None = None
    title: str | None = None
    buildings: list[str] | None = Field(
        None, description="Public buildings (building_id) to outline on top, in rank order"
    )


class BuildingsSpec(ScoreArgs):
    metric: str = Field(
        "he", description="Rank by this metric of the place each building stands in"
    )
    filters: list[Filter] = Field(
        default_factory=list, description="Filters on the place's metrics, as in rank_areas"
    )
    microzone: str | None = Field(None, description="Only buildings in this microzone")
    min_roof_m2: float = Field(
        300, ge=0, description="Smallest roof (footprint) area worth listing, in m²"
    )
    flat_roofs_only: bool = Field(
        False, description="Only buildings mapped with a flat roof (few have a roof shape)"
    )
    limit: int = Field(10, ge=1, le=MAX_LOCATE)
    lang: Language = Field(Language.CS, description="Language of the street names")

    @field_validator("microzone")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scoring:
    he: float
    v: float
    gd: float
    only_buildable: bool
    name: str

    def describe(self) -> dict[str, Any]:
        return {
            "weights": self.name,
            "heat_exposed_pct": round(self.he * 100),
            "vulnerable_pct": round(self.v * 100),
            "lack_of_green_pct": round(self.gd * 100),
            "only_buildable": self.only_buildable,
        }


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    summary: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False
    layer: LayerSpec | None = None


class Sql:
    """Collects bound parameters while a query is assembled."""

    def __init__(self, ctx: AgentContext, scoring: Scoring):
        self.ctx = ctx
        self.scoring = scoring
        self.params: dict[str, Any] = {}

    def bind(self, value: Any) -> str:
        name = f"p{len(self.params)}"
        self.params[name] = value
        return f"${name}"

    def metric(self, metric: Metric) -> str:
        """The SQL expression of a metric, on the stored (0-1) scale."""
        if not metric.derived:
            return f'"{metric.name}"'
        s = self.scoring
        need = (
            f"(pow(greatest(coalesce(he, {FLOOR}), {FLOOR}), {self.bind(s.he)})"
            f" * pow(greatest(coalesce(v, {FLOOR}), {FLOOR}), {self.bind(s.v)})"
            f" * pow(greatest(coalesce(gd, {FLOOR}), {FLOOR}), {self.bind(s.gd)}))"
        )
        if metric.name == "need" or (metric.name == "score" and not s.only_buildable):
            return need
        return f"({need} * coalesce(feas, 0))"

    def where(self, filters: list[Filter]) -> str:
        clauses = [self._filter(f) for f in filters]
        return " AND ".join(clauses) if clauses else "TRUE"

    def _filter(self, f: Filter) -> str:
        if f.metric.lower() in {"microzone", "mz_id"}:
            return self._microzone_filter(f)
        metric = self.ctx.metric(f.metric)
        column = self.metric(metric)
        if f.op is Op.IS_NULL:
            return f"{column} IS NULL"
        if f.op is Op.NOT_NULL:
            return f"{column} IS NOT NULL"

        def num(value: Any) -> float:
            try:
                return float(value) / metric.scale
            except (TypeError, ValueError):
                raise ToolError(f"filter on {metric.name} needs a number, not {value!r}") from None

        if f.op is Op.BETWEEN:
            if not isinstance(f.value, list) or len(f.value) != 2:
                raise ToolError("between needs [low, high]")
            return f"{column} BETWEEN {self.bind(num(f.value[0]))} AND {self.bind(num(f.value[1]))}"
        if f.op is Op.IN:
            values = f.value if isinstance(f.value, list) else [f.value]
            return f"{column} IN ({', '.join(self.bind(num(v)) for v in values)})"
        if isinstance(f.value, list):
            raise ToolError(f"{f.op.value} takes one value, not a list")
        sign = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[f.op.value]
        return f"{column} {sign} {self.bind(num(f.value))}"

    def _microzone_filter(self, f: Filter) -> str:
        if f.op in (Op.IS_NULL, Op.NOT_NULL):
            return f"mz_id {'IS NULL' if f.op is Op.IS_NULL else 'IS NOT NULL'}"
        values = f.value if isinstance(f.value, list) else [f.value]
        names = [self.ctx.microzone(str(v)) for v in values if v is not None]
        if not names:
            raise ToolError("the microzone filter needs a name")
        if f.op in (Op.EQ, Op.IN):
            return f"mz_id IN ({', '.join(self.bind(n) for n in names)})"
        if f.op is Op.NE:
            return f"mz_id NOT IN ({', '.join(self.bind(n) for n in names)})"
        raise ToolError("microzones can only be filtered with eq, ne, in, is_null or not_null")


def shown(metric: Metric, value: Any) -> Any:
    """A stored value as people see it: scores 0-100, shares in %, sensibly rounded."""
    if value is None or not isinstance(value, (int, float)):
        return value
    value = float(value) * metric.scale
    if abs(value) >= 100:
        return round(value)
    if abs(value) >= 1:
        return round(value, 1)
    return round(value, 3)


def _agg(metric: Metric, agg: Agg | None) -> Agg:
    return agg or metric.agg


def _agg_sql(agg: Agg, expr: str) -> str:
    return f"{agg.value}({expr})"


def _label(metric: Metric) -> dict[str, Any]:
    return {"metric": metric.name, "label": metric.label, "unit": metric.shown_unit}


def _extras(ctx: AgentContext, names: list[str], limit: int = MAX_EXTRA) -> list[Metric]:
    seen: list[Metric] = []
    for name in names[:limit]:
        metric = ctx.metric(name)
        if metric not in seen:
            seen.append(metric)
    return seen


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def overview(db: Database, ctx: AgentContext, spec: OverviewSpec) -> QueryResult:
    scoring = spec.resolved()
    q = Sql(ctx, scoring)
    score = ctx.metric("score")
    expr = q.metric(score)
    classes = ", ".join(
        f"count(*) FILTER (WHERE s >= {lo / 100} AND s < {hi / 100}) AS c{i}"
        for i, (lo, hi) in enumerate(zip((0, *CLASS_BREAKS), (*CLASS_BREAKS, 101), strict=True))
    )
    totals = (
        await db.query(
            f"""
        WITH t AS (SELECT *, {expr} AS s FROM hexes)
        SELECT count(*) AS hexes, count(DISTINCT mz_id) AS microzones,
               sum(raw_residents) AS residents, sum(raw_day_people) AS day_people,
               sum(area_ha) AS area_ha, avg(s) AS mean, median(s) AS median, max(s) AS max,
               {classes}
        FROM t
        """,
            q.params,
        )
    ).rows[0]

    q = Sql(ctx, scoring)
    expr = q.metric(score)
    top = await db.query(
        f"""
        SELECT mz_id AS microzone, avg({expr}) AS value, count(*) AS hexes,
               sum(raw_residents) AS residents
        FROM hexes WHERE mz_id IS NOT NULL
        GROUP BY mz_id ORDER BY value DESC LIMIT 5
        """,
        q.params,
    )
    bands = ["0-20", "20-40", "40-60", "60-80", "80-100"]
    summary = {
        "hexagons": totals["hexes"],
        "microzones": totals["microzones"],
        "residents": shown(ctx.metric("raw_residents"), totals["residents"])
        if "raw_residents" in ctx.metrics
        else None,
        "people_during_day": shown(ctx.metric("raw_day_people"), totals["day_people"])
        if "raw_day_people" in ctx.metrics
        else None,
        "area_ha": round(totals["area_ha"] or 0),
        "score_mean": shown(score, totals["mean"]),
        "score_median": shown(score, totals["median"]),
        "score_max": shown(score, totals["max"]),
        "hexagons_per_score_band": {b: totals[f"c{i}"] for i, b in enumerate(bands)},
        "scoring": scoring.describe(),
        "top_microzones_by_mean_score": "rows",
    }
    rows = [
        {
            "microzone": r["microzone"],
            "mean_score": shown(score, r["value"]),
            "hexagons": r["hexes"],
            "residents": shown(ctx.metric("raw_residents"), r["residents"])
            if "raw_residents" in ctx.metrics
            else None,
        }
        for r in top.rows
    ]
    return QueryResult(
        columns=["microzone", "mean_score", "hexagons", "residents"],
        rows=rows,
        summary=summary,
        layer=_layer(spec, Level.HEX, "score", title="Green infrastructure need"),
    )


async def rank(db: Database, ctx: AgentContext, spec: RankSpec) -> QueryResult:
    scoring = spec.resolved()
    metric = ctx.metric(spec.metric)
    extras = [m for m in _extras(ctx, spec.show) if m != metric]
    q = Sql(ctx, scoring)
    value = q.metric(metric)
    direction = "DESC" if spec.order is Order.DESC else "ASC"
    where = q.where(spec.filters)
    residents = "raw_residents" in ctx.metrics

    if spec.level is Level.HEX:
        cols = [f'{q.metric(m)} AS "{m.name}"' for m in extras]
        sql = f"""
            SELECT h3_index, mz_id AS microzone, {value} AS value
                   {", raw_residents AS residents" if residents else ""}
                   {"".join(", " + c for c in cols)},
                   count(*) OVER () AS matching
            FROM hexes
            WHERE {where} AND {value} IS NOT NULL
            ORDER BY value {direction} NULLS LAST, h3_index
            LIMIT {spec.limit}
        """
        id_key = "h3_index"
        agg = None
    else:
        agg = _agg(metric, spec.agg)
        cols = [f'{_agg_sql(m.agg, q.metric(m))} AS "{m.name}"' for m in extras]
        sql = f"""
            SELECT mz_id AS microzone, {_agg_sql(agg, value)} AS value, count(*) AS hexagons
                   {", sum(raw_residents) AS residents" if residents else ""}
                   {"".join(", " + c for c in cols)},
                   count(*) OVER () AS matching
            FROM hexes
            WHERE {where} AND mz_id IS NOT NULL
            GROUP BY mz_id
            HAVING {_agg_sql(agg, value)} IS NOT NULL
            ORDER BY value {direction} NULLS LAST, microzone
            LIMIT {spec.limit}
        """
        id_key = "microzone"

    result = await db.query(sql, q.params)
    matching = result.rows[0]["matching"] if result.rows else 0
    rows = []
    for i, r in enumerate(result.rows, 1):
        row: dict[str, Any] = {"rank": i}
        if spec.level is Level.HEX:
            row |= {"h3_index": r["h3_index"], "microzone": r["microzone"]}
        else:
            row |= {"microzone": r["microzone"], "hexagons": r["hexagons"]}
        row[metric.name] = shown(metric, r["value"])
        if residents:
            row["residents"] = shown(ctx.metric("raw_residents"), r["residents"])
        for m in extras:
            row[m.name] = shown(m, r[m.name])
        rows.append(row)

    unit_name = "hexagons" if spec.level is Level.HEX else "microzones"
    summary = {
        **_label(metric),
        "order": "highest first" if spec.order is Order.DESC else "lowest first",
        f"matching_{unit_name}": matching,
    }
    if agg:
        summary["per_microzone"] = f"{agg.value} of its hexagons"
    if metric.derived:
        summary["scoring"] = scoring.describe()
    return QueryResult(
        columns=list(rows[0]) if rows else [],
        rows=rows,
        summary=summary,
        truncated=matching > len(rows),
        layer=_layer(
            spec,
            spec.level,
            metric.name,
            ids=[r[id_key] for r in rows],
            agg=agg,
            title=f"{'Top' if spec.order is Order.DESC else 'Bottom'} {len(rows)} "
            f"{'places' if spec.level is Level.HEX else 'microzones'}: {metric.label}",
        ),
    )


async def summarize(db: Database, ctx: AgentContext, spec: SummarizeSpec) -> QueryResult:
    scoring = spec.resolved()
    metrics = _extras(ctx, spec.metrics or ["score"], limit=6)
    q = Sql(ctx, scoring)
    where = q.where(spec.filters)
    cols = [f'{_agg_sql(m.agg, q.metric(m))} AS "{m.name}"' for m in metrics]
    residents = "raw_residents" in ctx.metrics
    base = [
        "count(*) AS hexagons",
        "sum(raw_residents) AS residents" if residents else "NULL AS residents",
        "sum(area_ha) AS area_ha",
    ]
    select = ", ".join(base + cols)
    city = (
        await db.query(
            "SELECT count(*) AS hexagons"
            + (", sum(raw_residents) AS residents" if residents else ", NULL AS residents")
            + " FROM hexes"
        )
    ).rows[0]

    def out(r: dict[str, Any]) -> dict[str, Any]:
        row = {
            "hexagons": r["hexagons"],
            "residents": shown(ctx.metric("raw_residents"), r["residents"]) if residents else None,
            "area_ha": round(r["area_ha"] or 0, 1),
        }
        for m in metrics:
            row[f"{m.agg.value}_{m.name}"] = shown(m, r[m.name])
        return row

    first = metrics[0].name if metrics else "score"
    layer = _layer(spec, Level.HEX, first, filters=spec.filters, title="Matching places")
    labels = {
        m.name: f"{m.label} ({m.agg.value}, {m.shown_unit})".replace(", )", ")") for m in metrics
    }
    if not spec.by_microzone:
        r = (await db.query(f"SELECT {select} FROM hexes WHERE {where}", q.params)).rows[0]
        total = out(r)
        total["share_of_city_hexagons_pct"] = (
            round(100 * r["hexagons"] / city["hexagons"], 1) if city["hexagons"] else None
        )
        if residents and city["residents"]:
            total["share_of_city_residents_pct"] = round(
                100 * (r["residents"] or 0) / city["residents"], 1
            )
        summary = {**total, "metrics": labels}
        if any(m.derived for m in metrics):
            summary["scoring"] = scoring.describe()
        return QueryResult(columns=[], rows=[], summary=summary, layer=layer)

    result = await db.query(
        f"""
        SELECT mz_id AS microzone, {select}, count(*) OVER () AS groups
        FROM hexes WHERE {where} AND mz_id IS NOT NULL
        GROUP BY mz_id ORDER BY hexagons DESC, microzone LIMIT {MAX_ROWS}
        """,
        q.params,
    )
    rows = [{"microzone": r["microzone"], **out(r)} for r in result.rows]
    groups = result.rows[0]["groups"] if result.rows else 0
    summary: dict[str, Any] = {"microzones": groups, "metrics": labels}
    if any(m.derived for m in metrics):
        summary["scoring"] = scoring.describe()
    return QueryResult(
        columns=list(rows[0]) if rows else [],
        rows=rows,
        summary=summary,
        truncated=groups > len(rows),
        layer=layer,
    )


async def describe(db: Database, ctx: AgentContext, spec: DescribeSpec) -> QueryResult:
    scoring = spec.resolved()
    metric = ctx.metric(spec.metric)
    q = Sql(ctx, scoring)
    value = q.metric(metric)
    where = q.where(spec.filters)
    r = (
        await db.query(
            f"""
        WITH t AS (SELECT {value} AS x FROM hexes WHERE {where})
        SELECT count(*) AS hexagons, count(x) AS with_value, min(x) AS min,
               quantile_cont(x, 0.25) AS p25, median(x) AS median, quantile_cont(x, 0.75) AS p75,
               max(x) AS max, avg(x) AS mean
        FROM t
        """,
            q.params,
        )
    ).rows[0]
    summary: dict[str, Any] = {
        **_label(metric),
        "description": metric.description,
        "hexagons": r["hexagons"],
        "without_value": r["hexagons"] - r["with_value"],
        **{k: shown(metric, r[k]) for k in ("min", "p25", "median", "p75", "max", "mean")},
    }
    if metric.is_score:
        bounds = (0, *CLASS_BREAKS, 101)
        q = Sql(ctx, scoring)
        value = q.metric(metric)
        where = q.where(spec.filters)
        counts = ", ".join(
            f"count(*) FILTER (WHERE x >= {lo / 100} AND x < {hi / 100}) AS c{i}"
            for i, (lo, hi) in enumerate(itertools.pairwise(bounds))
        )
        bands = (
            await db.query(
                f"WITH t AS (SELECT {value} AS x FROM hexes WHERE {where}) SELECT {counts} FROM t",
                q.params,
            )
        ).rows[0]
        summary["hexagons_per_band"] = {
            f"{lo}-{min(hi, 100)}": bands[f"c{i}"]
            for i, (lo, hi) in enumerate(itertools.pairwise(bounds))
        }
    if metric.derived:
        summary["scoring"] = scoring.describe()
    return QueryResult(
        columns=[],
        rows=[],
        summary=summary,
        layer=_layer(spec, Level.HEX, metric.name, filters=spec.filters, title=metric.label),
    )


async def detail(db: Database, ctx: AgentContext, spec: DetailSpec) -> QueryResult:
    given = [
        spec.h3_index is not None,
        spec.microzone is not None,
        spec.lon is not None or spec.lat is not None,
    ]
    if sum(given) != 1:
        raise ToolError("give exactly one of h3_index, microzone, or lon and lat")
    scoring = spec.resolved()
    metrics = [ctx.metrics[n] for n in KEY_METRICS if n in ctx.metrics]

    if spec.microzone is not None:
        return await _microzone_detail(db, ctx, spec, scoring, metrics)

    h3_index = spec.h3_index
    distance = None
    if h3_index is None:
        if spec.lon is None or spec.lat is None:
            raise ToolError("a point needs both lon and lat")
        h3_index, distance = await _nearest(db, spec.lon, spec.lat)

    q = Sql(ctx, scoring)
    ranked = ", ".join(
        f'rank() OVER (ORDER BY {q.metric(ctx.metrics[n])} DESC NULLS LAST) AS "rank_{n}"'
        for n in RANKED
        if n in ctx.metrics
    )
    values = ", ".join(f'{q.metric(m)} AS "{m.name}"' for m in metrics)
    rows = (
        await db.query(
            f"""
        WITH t AS (SELECT h3_index, mz_id, area_ha, {values}, {ranked}, count(*) OVER () AS total FROM hexes)
        SELECT * FROM t WHERE h3_index = {q.bind(h3_index)}
        """,
            q.params,
        )
    ).rows
    if not rows:
        raise ToolError(f"no hexagon {h3_index!r} in the index")
    r = rows[0]
    summary: dict[str, Any] = {
        "h3_index": r["h3_index"],
        "microzone": r["mz_id"],
        "area_ha": round(r["area_ha"] or 0, 2),
        "scoring": scoring.describe(),
    }
    if distance is not None:
        summary["point_distance_to_hexagon_centre_m"] = round(distance)
    for key, name in SUMMARY_ALIASES.items():
        if name in r:
            summary[key] = shown(ctx.metrics[name], r[name])
    rows_out = [
        {
            "metric": m.name,
            "label": m.label,
            "value": shown(m, r[m.name]),
            "unit": m.shown_unit,
            "rank_in_city": f"{r['rank_' + m.name]} of {r['total']}"
            if f"rank_{m.name}" in r
            else None,
        }
        for m in metrics
    ]
    return QueryResult(
        columns=["metric", "label", "value", "unit", "rank_in_city"],
        rows=rows_out,
        summary=summary,
        layer=_layer(
            spec, Level.HEX, "score", ids=[r["h3_index"]], title=str(r["mz_id"] or "Selected place")
        ),
    )


async def _microzone_detail(
    db: Database, ctx: AgentContext, spec: DetailSpec, scoring: Scoring, metrics: list[Metric]
) -> QueryResult:
    name = ctx.microzone(spec.microzone or "")
    q = Sql(ctx, scoring)
    values = ", ".join(f'{_agg_sql(m.agg, q.metric(m))} AS "{m.name}"' for m in metrics)
    ranked = ", ".join(
        f'rank() OVER (ORDER BY "{n}" DESC NULLS LAST) AS "rank_{n}"'
        for n in RANKED
        if n in ctx.metrics
    )
    rows = (
        await db.query(
            f"""
        WITH z AS (
            SELECT mz_id, count(*) AS hexagons, sum(area_ha) AS area_ha, {values}
            FROM hexes WHERE mz_id IS NOT NULL GROUP BY mz_id
        ), t AS (SELECT *, {ranked}, count(*) OVER () AS total FROM z)
        SELECT * FROM t WHERE mz_id = {q.bind(name)}
        """,
            q.params,
        )
    ).rows
    if not rows:
        raise ToolError(f"no hexagons in microzone {name!r}")
    r = rows[0]
    rows_out = [
        {
            "metric": m.name,
            "label": m.label,
            "value": shown(m, r[m.name]),
            "unit": m.shown_unit,
            "per_microzone": f"{m.agg.value} of its hexagons",
            "rank_among_microzones": f"{r['rank_' + m.name]} of {r['total']}"
            if f"rank_{m.name}" in r
            else None,
        }
        for m in metrics
    ]
    return QueryResult(
        columns=["metric", "label", "value", "unit", "per_microzone", "rank_among_microzones"],
        rows=rows_out,
        summary={
            "microzone": name,
            "hexagons": r["hexagons"],
            "area_ha": round(r["area_ha"] or 0, 1),
            "scoring": scoring.describe(),
        },
        layer=_layer(
            spec,
            Level.HEX,
            "score",
            filters=[Filter(metric="microzone", op=Op.EQ, value=name)],
            title=name,
        ),
    )


async def locate(db: Database, ctx: AgentContext, spec: LocateSpec) -> QueryResult:
    """Where hexagons are: microzone, centre and, when a geocoder key is set,
    the street and district at the centre."""
    ids = spec.h3_indexes
    if not ids:
        raise ToolError("give at least one h3_index")
    scoring = spec.resolved()
    score = ctx.metric("score")
    q = Sql(ctx, scoring)
    residents = "raw_residents" in ctx.metrics
    found = {
        r["h3_index"]: r
        for r in (
            await db.query(
                f"""
            SELECT h3_index, mz_id, lon, lat, {q.metric(score)} AS score
                   {", raw_residents AS residents" if residents else ""}
            FROM hexes WHERE h3_index IN ({", ".join(q.bind(i) for i in ids)})
            """,
                q.params,
            )
        ).rows
    }
    missing = [i for i in ids if i not in found]
    if not found:
        raise ToolError(
            f"none of {', '.join(ids)} is in the index; h3_index values come from "
            "rank_areas or area_detail (resolution 9 hexagons in Olomouc)"
        )
    hits = [found[i] for i in ids if i in found]
    places = await places_api.reverse_many([(r["lon"], r["lat"]) for r in hits], spec.lang.value)

    rows = []
    for r, place in zip(hits, places, strict=True):
        row: dict[str, Any] = {
            "h3_index": r["h3_index"],
            "microzone": r["mz_id"],
            "street": (place or {}).get("street"),
            "district": (place or {}).get("district"),
            "near": (place or {}).get("name"),
            "score": shown(score, r["score"]),
        }
        if residents:
            row["residents"] = shown(ctx.metric("raw_residents"), r["residents"])
        row |= {"lon": round(r["lon"], 5), "lat": round(r["lat"], 5)}
        rows.append(row)

    summary: dict[str, Any] = {"hexagons_found": len(rows), "scoring": scoring.describe()}
    if missing:
        summary["not_in_index"] = missing
    if not places_api.enabled():
        summary["place_names"] = "unavailable (no geocoder key); name places by microzone"
    elif not any(places):
        summary["place_names"] = "the geocoder did not answer; name places by microzone"
    return QueryResult(
        columns=list(rows[0]),
        rows=rows,
        summary=summary,
        layer=_layer(
            spec,
            Level.HEX,
            "score",
            ids=[r["h3_index"] for r in rows],
            title=_place_title(rows),
        ),
    )


async def public_buildings(db: Database, ctx: AgentContext, spec: BuildingsSpec) -> QueryResult:
    """Public buildings (schools, offices, hospitals, ...) in the places that rank
    highest on a metric: candidates for green roofs and greened courtyards."""
    scoring = spec.resolved()
    metric = ctx.metric(spec.metric)
    q = Sql(ctx, scoring)
    filters = list(spec.filters)
    if spec.microzone:
        filters.append(Filter(metric="microzone", op=Op.EQ, value=spec.microzone))
    flat = "AND b.roof_shape = 'flat'" if spec.flat_roofs_only else ""
    # The place's values first (unambiguous column names), then its buildings.
    result = await db.query(
        f"""
        WITH h AS (
            SELECT h3_index AS hex_id, mz_id, {q.metric(metric)} AS value
            FROM hexes WHERE {q.where(filters)}
        )
        SELECT b.building_id, b.name, b.kind, b.roof_m2, b.roof_shape, b.levels,
               b.lon, b.lat, h.hex_id, h.mz_id, h.value,
               count(*) OVER () AS matching
        FROM buildings b JOIN h ON h.hex_id = b.h3_index
        WHERE b.roof_m2 >= {q.bind(spec.min_roof_m2)} AND h.value IS NOT NULL {flat}
        ORDER BY h.value DESC, b.roof_m2 DESC, b.building_id
        LIMIT {spec.limit}
        """,
        q.params,
    )
    if not result.rows:
        return QueryResult(
            columns=[],
            rows=[],
            summary={"buildings_found": 0, "hint": "lower min_roof_m2 or loosen the filters"},
        )
    matching = result.rows[0]["matching"]
    places = await places_api.reverse_many(
        [(r["lon"], r["lat"]) for r in result.rows], spec.lang.value
    )
    rows = []
    for i, (r, place) in enumerate(zip(result.rows, places, strict=True), 1):
        rows.append(
            {
                "rank": i,
                "building": r["name"],
                "type": r["kind"],
                "roof_m2": round(r["roof_m2"]),
                "roof_shape": r["roof_shape"],
                "levels": int(r["levels"]) if r["levels"] is not None else None,
                "street": (place or {}).get("street"),
                "district": (place or {}).get("district"),
                "microzone": r["mz_id"],
                metric.name: shown(metric, r["value"]),
                "h3_index": r["hex_id"],
            }
        )
    summary: dict[str, Any] = {
        "ranked_by": _label(metric) | {"of": "the place the building stands in"},
        "matching_buildings": matching,
        "min_roof_m2": spec.min_roof_m2,
    }
    if not places_api.enabled():
        summary["street_names"] = "unavailable (no geocoder key); name buildings by microzone"
    if metric.derived:
        summary["scoring"] = scoring.describe()
    hexes = list(dict.fromkeys(r["hex_id"] for r in result.rows))
    return QueryResult(
        columns=list(rows[0]),
        rows=rows,
        summary=summary,
        truncated=matching > len(rows),
        layer=_layer(
            spec,
            Level.HEX,
            metric.name,
            ids=hexes,
            title=f"{len(rows)} public buildings: {metric.label}",
            buildings=[r["building_id"] for r in result.rows],
        ),
    )


def _place_title(rows: list[dict[str, Any]]) -> str:
    if len(rows) > 1:
        return f"{len(rows)} places"
    r = rows[0]
    return ", ".join(p for p in (r.get("street"), r.get("microzone")) if p) or "Selected place"


async def _nearest(db: Database, lon: float, lat: float) -> tuple[str, float]:
    """The hexagon whose centre is nearest the point, and how far it is (m)."""
    rows = (
        await db.query(
            """
        SELECT h3_index,
               sqrt(pow((lon - $lon) * 111320 * cos(radians($lat)), 2)
                    + pow((lat - $lat) * 110540, 2)) AS metres
        FROM hexes WHERE lon IS NOT NULL ORDER BY metres LIMIT 1
        """,
            {"lon": lon, "lat": lat},
        )
    ).rows
    if not rows or rows[0]["metres"] > NEAREST_MAX_M:
        raise ToolError("that point is outside the area the index covers (Olomouc)")
    return rows[0]["h3_index"], rows[0]["metres"]


def _layer(
    spec: ScoreArgs,
    level: Level,
    metric: str,
    *,
    ids: list[str] | None = None,
    filters: list[Filter] | None = None,
    agg: Agg | None = None,
    title: str | None = None,
    buildings: list[str] | None = None,
) -> LayerSpec:
    return LayerSpec(
        preset=spec.preset,
        weights=spec.weights,
        only_buildable=spec.only_buildable,
        level=level,
        metric=metric,
        ids=ids,
        filters=filters or [],
        agg=agg,
        title=title,
        buildings=buildings,
    )
