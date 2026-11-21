"""Public buildings: loaded from buildings_with_class.geojson, found by the
public_buildings tool, and drawn on the map on top of their places."""

import pytest
from fastapi.testclient import TestClient

from agent import maps, places
from agent.query import BuildingsSpec, Filter, LayerSpec, Op, ToolError, public_buildings
from app.database import get_db
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def ctx(client):
    return app.state.agent_context


@pytest.fixture(scope="module")
def db(client):
    return get_db()


@pytest.fixture(autouse=True)
def no_geocoder(monkeypatch):
    monkeypatch.setattr(places, "enabled", lambda: False)


def test_public_buildings_are_loaded_in_wgs84(db):
    rows = db.query_sync(
        "SELECT count(*) AS n, count(h3_index) AS placed, min(lon) AS w, max(lon) AS e, "
        "min(lat) AS s, max(lat) AS n2 FROM buildings"
    ).rows[0]
    if rows["n"] == 0:
        pytest.skip("no buildings file in data/")
    assert rows["placed"] >= 0.95 * rows["n"]
    # Inside Olomouc (MAP_CONFIG.maxBounds in the frontend), not in EPSG:5514 metres.
    assert 17.13 < rows["w"] < rows["e"] < 17.41
    assert 49.51 < rows["s"] < rows["n2"] < 49.69


async def test_buildings_rank_by_their_place(db, ctx):
    result = await public_buildings(db, ctx, BuildingsSpec(limit=5))
    if not result.rows:
        pytest.skip("no buildings file in data/")
    heat = [r["he"] for r in result.rows]
    assert heat == sorted(heat, reverse=True)
    assert all(r["roof_m2"] >= 300 for r in result.rows)
    assert "street_names" in result.summary  # no geocoder in tests
    layer = result.layer
    assert layer.metric == "he" and len(layer.buildings) == len(result.rows)
    assert set(layer.ids) == {r["h3_index"] for r in result.rows}


async def test_buildings_filters_and_flat_roofs(db, ctx):
    hot = await public_buildings(
        db,
        ctx,
        BuildingsSpec(
            filters=[Filter(metric="he", op=Op.GTE, value=60)],
            microzone="Hodolany",
            flat_roofs_only=True,
            min_roof_m2=0,
            limit=20,
        ),
    )
    for row in hot.rows:
        assert row["he"] >= 60 and row["roof_shape"] == "flat"
        assert row["microzone"] == "Mikrozóna Hodolany"
    with pytest.raises(ToolError):
        await public_buildings(db, ctx, BuildingsSpec(metric="nope"))


async def test_map_draws_buildings_on_top(client, db, ctx):
    result = await public_buildings(db, ctx, BuildingsSpec(limit=3))
    if not result.rows:
        pytest.skip("no buildings file in data/")
    body = client.post("/api/agent/map", json=result.layer.model_dump(mode="json")).json()
    features = body["features"]["features"]
    buildings = [f for f in features if f["properties"].get("kind") == "building"]
    places_ = [f for f in features if f["properties"].get("kind") != "building"]
    assert [f["properties"]["rank"] for f in buildings] == [1, 2, 3]
    assert places_ and all("rank" not in f["properties"] for f in places_)
    assert buildings[0]["geometry"]["type"] in ("Polygon", "MultiPolygon")


async def test_building_layer_has_green_roof_costs(db, ctx):
    from agent import costs as green_roof

    costs = green_roof.load()
    assert costs is not None and costs.currency == "CZK"
    row = db.query_sync(
        "SELECT building_id, roof_m2 FROM buildings WHERE roof_m2 > 500 AND h3_index IS NOT NULL "
        "LIMIT 1"
    ).rows[0]
    hex_id = db.query_sync(
        "SELECT h3_index FROM buildings WHERE building_id = ?", [row["building_id"]]
    ).rows[0]["h3_index"]
    layer = await maps.build(
        db, ctx, LayerSpec(level="hex", metric="he", ids=[hex_id], buildings=[row["building_id"]])
    )
    building = next(
        f["properties"]
        for f in layer.features["features"]
        if f["properties"].get("kind") == "building"
    )
    assert building["install_min"] <= building["install_avg"] <= building["install_max"]
    assert building["maint_min"] <= building["maint_avg"] <= building["maint_max"]
    expected = costs.install.avg * row["roof_m2"]
    assert abs(building["install_avg"] - expected) / expected < 0.01  # 3 significant figures
    assert layer.costs["install"]["url"].startswith("https://")
    assert layer.costs["maintenance"]["url"].startswith("https://")


def test_costs_parse_rejects_missing_record():

    from agent import costs as green_roof

    with pytest.raises(ValueError):
        green_roof.parse(
            {"records": [{"unit": "CZK/m² (installation)", "cost_min": 1, "cost_max": 2}]}
        )
