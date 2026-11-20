"""Load the GI index GeoJSON exports into a DuckDB file.

    python -m app.ingest            # build data/moravia.duckdb from the configured files
    python -m app.ingest --force    # rebuild even if it exists

Tables:
    hexes       one row per H3 hexagon: every property of the export, the four
                score dimensions (he, v, gd, feas) computed exactly as the
                frontend does (frontend/js/scoring/score.js), the centre
                (lon, lat) and the outline as GeoJSON text.
    microzones  the microzone outlines, their resident count and centre.
    metadata    the notebook's metadata.json, as one JSON document.

Geometry is kept as GeoJSON text, so no DuckDB extension is needed.
"""

import argparse
import json
import logging
import math
import os
from pathlib import Path
from typing import Any

import duckdb

from app.config import settings

logger = logging.getLogger(__name__)

FLOOR = 0.01  # the score's floor, as in score.js
DEFAULT_A = 0.5
DEFAULT_DAY_WEIGHT = 0.5
TEXT_COLUMNS = {"h3_index", "mz_id"}


def ingest(
    index_path: Path,
    db_path: Path,
    metadata_path: Path | None = None,
    microzones_path: Path | None = None,
) -> int:
    """Build db_path from the exports; returns the number of hexes loaded."""
    features = _features(index_path)
    metadata = _read_json(metadata_path) if metadata_path and metadata_path.exists() else {}
    a = _number(metadata.get("heat_hazard_share_a"), DEFAULT_A)
    day_weight = _number(metadata.get("day_weight"), DEFAULT_DAY_WEIGHT)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".building.duckdb")
    tmp.unlink(missing_ok=True)
    conn = duckdb.connect(str(tmp))
    try:
        _load_hexes(conn, features, a, day_weight)
        if microzones_path and microzones_path.exists():
            _load_microzones(conn, _features(microzones_path))
        else:
            conn.execute(
                "CREATE TABLE microzones (name VARCHAR, residents DOUBLE, "
                "lon DOUBLE, lat DOUBLE, geometry VARCHAR)"
            )
        conn.execute("CREATE TABLE metadata (doc JSON)")
        conn.execute("INSERT INTO metadata VALUES (?)", [json.dumps(metadata)])
        conn.execute("CHECKPOINT")
    finally:
        conn.close()
    os.replace(tmp, db_path)
    return len(features)


def _load_hexes(
    conn: duckdb.DuckDBPyConnection, features: list[dict[str, Any]], a: float, day_weight: float
) -> None:
    columns: list[str] = []
    for feature in features:
        for key in feature.get("properties") or {}:
            if key not in columns:
                columns.append(key)
    if "h3_index" not in columns:
        raise ValueError("the index GeoJSON has no h3_index property")
    for column in columns:
        if not column.replace("_", "").isalnum():
            raise ValueError(f"unexpected property name {column!r}")

    numeric = [c for c in columns if c not in TEXT_COLUMNS]
    ddl = [f'"{c}" VARCHAR' for c in columns if c in TEXT_COLUMNS]
    ddl += [f'"{c}" DOUBLE' for c in numeric]
    ddl += ["he DOUBLE", "v DOUBLE", "gd DOUBLE", "feas DOUBLE"]
    ddl += ["lon DOUBLE", "lat DOUBLE", "geometry VARCHAR"]
    conn.execute(f"CREATE TABLE hexes ({', '.join(ddl)}, PRIMARY KEY (h3_index))")

    ordered = [c for c in columns if c in TEXT_COLUMNS] + numeric
    rows = []
    for feature in features:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry")
        lon, lat = _centre(geometry)
        rows.append(
            [props.get(c) if c in TEXT_COLUMNS else _float(props.get(c)) for c in ordered]
            + list(_dimensions(props, a, day_weight))
            + [lon, lat, json.dumps(geometry, separators=(",", ":"))]
        )
    names = ", ".join(
        f'"{c}"' for c in [*ordered, "he", "v", "gd", "feas", "lon", "lat", "geometry"]
    )
    marks = ", ".join("?" for _ in range(len(ordered) + 7))
    conn.executemany(f"INSERT INTO hexes ({names}) VALUES ({marks})", rows)


def _load_microzones(conn: duckdb.DuckDBPyConnection, features: list[dict[str, Any]]) -> None:
    conn.execute(
        "CREATE TABLE microzones (name VARCHAR PRIMARY KEY, residents DOUBLE, "
        "lon DOUBLE, lat DOUBLE, geometry VARCHAR)"
    )
    rows = []
    for feature in features:
        props = feature.get("properties") or {}
        name = props.get("Name") or props.get("name")
        if not name:
            continue
        geometry = _drop_z(feature.get("geometry"))
        lon, lat = _centre(geometry)
        residents = _float(props.get("PopGrid_No"))
        rows.append([name, residents, lon, lat, json.dumps(geometry, separators=(",", ":"))])
    conn.executemany("INSERT INTO microzones VALUES (?, ?, ?, ?, ?)", rows)


def _dimensions(
    p: dict[str, Any], a: float, day_weight: float
) -> tuple[float, float, float | None, float]:
    """he, v, gd, feas: the parts of the score that don't depend on the weights.
    A copy of dimensions() in frontend/js/scoring/score.js; keep them identical."""
    exposure = _wmean(
        [(p.get("c_exposure_day"), day_weight), (p.get("c_exposure_night"), 1 - day_weight)]
    )
    he = _fl(p.get("c_heat")) ** a * _fl(exposure) ** (1 - a)
    v = _float(p.get("c_vulnerability"))
    gd = _wmean([(p.get("c_green_supply"), 0.5), (p.get("c_green_access"), 0.5)])
    feas = _float(p.get("d_feasibility"))
    return he, v if v is not None else 0.0, gd, feas if feas is not None else 0.0


def _wmean(pairs: list[tuple[Any, float]]) -> float | None:
    total = weights = 0.0
    for value, weight in pairs:
        value = _float(value)
        if value is None:
            continue
        total += value * weight
        weights += weight
    return total / weights if weights > 0 else None


def _fl(value: Any) -> float:
    value = _float(value)
    return max(value if value is not None else FLOOR, FLOOR)


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _number(value: Any, default: float) -> float:
    number = _float(value)
    return default if number is None else number


def _features(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path)
    if data.get("type") != "FeatureCollection":
        raise ValueError(f"{path} is not a GeoJSON FeatureCollection")
    return list(data.get("features") or [])


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _rings(geometry: dict[str, Any] | None) -> list[list[list[float]]]:
    """Outer rings of a Polygon or MultiPolygon."""
    if not geometry:
        return []
    if geometry.get("type") == "Polygon":
        return geometry["coordinates"][:1]
    if geometry.get("type") == "MultiPolygon":
        return [polygon[0] for polygon in geometry["coordinates"] if polygon]
    return []


def _centre(geometry: dict[str, Any] | None) -> tuple[float | None, float | None]:
    """Mean of the outer-ring vertices: good enough for hexagons and labels."""
    points = [pt for ring in _rings(geometry) for pt in ring[:-1]]
    if not points:
        return None, None
    return (
        sum(pt[0] for pt in points) / len(points),
        sum(pt[1] for pt in points) / len(points),
    )


def _drop_z(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    """The microzone export has a zero Z on every vertex; maps don't need it."""

    def strip(node: Any) -> Any:
        if isinstance(node, list) and node and isinstance(node[0], (int, float)):
            return node[:2]
        if isinstance(node, list):
            return [strip(item) for item in node]
        return node

    if not geometry:
        return geometry
    return {**geometry, "coordinates": strip(geometry.get("coordinates"))}


def ensure_database(force: bool = False) -> Path:
    """Build the DuckDB file when it is missing (or force); return its path."""
    db_path = settings.path(settings.DUCKDB_PATH)
    if db_path.exists() and not force:
        return db_path
    index = settings.path(settings.INDEX_GEOJSON)
    if not index.exists():
        raise FileNotFoundError(f"index GeoJSON not found: {index} (set INDEX_GEOJSON)")
    count = ingest(
        index,
        db_path,
        settings.path(settings.INDEX_METADATA),
        settings.path(settings.MICROZONES_GEOJSON),
    )
    logger.info("Loaded %d hexes into %s", count, db_path)
    return db_path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.ingest", description=__doc__.split("\n")[0]
    )
    parser.add_argument("--force", action="store_true", help="rebuild even if the file exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = ensure_database(force=args.force)
    with duckdb.connect(str(path), read_only=True) as conn:
        hexes = conn.execute("SELECT count(*) FROM hexes").fetchone()[0]
        zones = conn.execute("SELECT count(*) FROM microzones").fetchone()[0]
    print(f"{path}: {hexes} hexes, {zones} microzones")


if __name__ == "__main__":
    main()
