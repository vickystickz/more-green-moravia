"""Make the map's building layer from buildings_with_class.geojson.

The source is in the Czech S-JTSK grid (EPSG:5514), which MapLibre can't draw.
This writes a slim WGS84 copy for the website: outlines rounded to ~10 cm,
plus name, type and public / private class (for the building popup).

    uv run python scripts/buildings_for_web.py
    uv run python scripts/buildings_for_web.py SOURCE OUTPUT

Rerun it after every new buildings export.
"""

import json
import sys
from pathlib import Path

from pyproj import Transformer

from app.ingest import _crs, _drop_z, _reproject

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "backend/data/buildings_with_class.geojson"
OUTPUT = ROOT / "frontend/data/olomouc_buildings.geojson"


def main(source: Path = SOURCE, output: Path = OUTPUT) -> None:
    crs = _crs(source)
    transform = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform if crs else None
    features = json.loads(source.read_text(encoding="utf-8"))["features"]
    out = []
    for feature in features:
        p = feature.get("properties") or {}
        geometry = _reproject(_drop_z(feature.get("geometry")), transform)
        if not geometry:
            continue
        props = {
            "category": p.get("building_category"),  # public / private
            "name": p.get("name"),
            "type": p.get("amenity") or p.get("office") or p.get("building"),
            "area_m2": round(p["area_m2"]) if p.get("area_m2") is not None else None,
        }
        out.append(
            {
                "type": "Feature",
                "properties": {k: v for k, v in props.items() if v is not None},
                "geometry": geometry,
            }
        )
    output.write_text(
        json.dumps({"type": "FeatureCollection", "features": out}, separators=(",", ":")),
        encoding="utf-8",
    )
    size = output.stat().st_size / 1e6
    print(f"{output}: {len(out)} buildings, {size:.1f} MB (from {crs or 'WGS84'})")


if __name__ == "__main__":
    main(*(Path(a) for a in sys.argv[1:3]))
