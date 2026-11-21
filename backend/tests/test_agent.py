"""End-to-end checks against the real index, with a scripted model instead of an LLM."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent.llm import LLMReply, ToolCall, Usage, get_llm
from agent.query import (
    DescribeSpec,
    DetailSpec,
    Filter,
    LocateSpec,
    Op,
    OverviewSpec,
    RankSpec,
    SummarizeSpec,
    ToolError,
    describe,
    detail,
    locate,
    overview,
    rank,
    summarize,
)
from agent.tools import tool_schemas
from app.config import settings
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
    from app.database import get_db

    return get_db()


def test_score_matches_notebook(db, ctx):
    """With Balance weights 'need' must equal the notebook's gi_need_provisional,
    as the frontend's INFORM self-test checks."""
    from agent.query import Sql

    q = Sql(ctx, OverviewSpec().resolved())
    rows = db.query_sync(
        f"SELECT max(abs({q.metric(ctx.metric('need'))} - gi_need_provisional)) AS diff FROM hexes",
        q.params,
    ).rows
    assert rows[0]["diff"] < 0.005


async def test_overview(db, ctx):
    result = await overview(db, ctx, OverviewSpec())
    assert result.summary["hexagons"] == ctx.hex_count
    assert sum(result.summary["hexagons_per_score_band"].values()) == ctx.hex_count
    assert len(result.rows) == 5


async def test_rank_microzones_with_preset(db, ctx):
    spec = RankSpec(metric="score", level="microzone", limit=3, preset="cool-street")
    result = await rank(db, ctx, spec)
    assert [r["rank"] for r in result.rows] == [1, 2, 3]
    scores = [r["score"] for r in result.rows]
    assert scores == sorted(scores, reverse=True)
    assert result.layer.ids == [r["microzone"] for r in result.rows]


async def test_rank_hexes_filtered_and_scaled(db, ctx):
    spec = RankSpec(
        metric="raw_sealing",
        limit=5,
        filters=[Filter(metric="raw_residents", op=Op.GT, value=0)],
        show=["raw_tree_cover"],
    )
    result = await rank(db, ctx, spec)
    assert all(0 <= r["raw_sealing"] <= 100 for r in result.rows)  # shares come out in %
    assert all(r["residents"] > 0 for r in result.rows)


async def test_rank_hexes_capped_and_grouped_by_microzone(db, ctx):
    result = await rank(db, ctx, RankSpec(metric="score", limit=50))
    assert len(result.rows) <= 10
    groups = result.summary["by_microzone"]
    assert sum(g["hexagons"] for g in groups) == len(result.rows)
    assert len({g["microzone"] for g in groups}) == len(groups)
    assert groups[0]["best"] == result.rows[0]["score"]


async def test_summarize_by_filter(db, ctx):
    spec = SummarizeSpec(filters=[Filter(metric="score", op=Op.GTE, value=0)])
    result = await summarize(db, ctx, spec)
    assert result.summary["hexagons"] == ctx.hex_count
    assert result.summary["share_of_city_hexagons_pct"] == 100.0


async def test_microzone_names_are_forgiving(db, ctx):
    result = await detail(db, ctx, DetailSpec(microzone="losov"))
    assert result.summary["microzone"] == "Mikrozóna Lošov"
    with pytest.raises(ToolError):
        ctx.microzone("Prague")


async def test_detail_by_point_and_describe(db, ctx):
    result = await detail(db, ctx, DetailSpec(lon=17.2509, lat=49.5938))
    assert result.summary["h3_index"]
    with pytest.raises(ToolError):
        await detail(db, ctx, DetailSpec(lon=14.42, lat=50.08))  # Prague
    described = await describe(db, ctx, DescribeSpec(metric="raw_heatwave_tmax"))
    assert described.summary["unit"] == "°C"


async def test_locate_hexagons(db, ctx, monkeypatch):
    from agent import places

    top = await rank(db, ctx, RankSpec(limit=3))
    ids = [r["h3_index"] for r in top.rows]

    monkeypatch.setattr(places, "enabled", lambda: False)
    plain = await locate(db, ctx, LocateSpec(h3_indexes=[*ids, "89000000000ffff"]))
    assert [r["h3_index"] for r in plain.rows] == ids
    assert [r["microzone"] for r in plain.rows] == [r["microzone"] for r in top.rows]
    assert plain.rows[0]["street"] is None
    assert plain.summary["not_in_index"] == ["89000000000ffff"]
    assert "place_names" in plain.summary
    assert plain.layer.ids == ids

    async def fake(points, lang="cs"):
        return [{"street": "Třída Svobody", "district": "Olomouc", "name": "X"} for _ in points]

    monkeypatch.setattr(places, "enabled", lambda: True)
    monkeypatch.setattr(places, "reverse_many", fake)
    named = await locate(db, ctx, LocateSpec(h3_indexes=[ids[0].upper()]))
    assert named.rows[0]["h3_index"] == ids[0]
    assert named.rows[0]["street"] == "Třída Svobody"
    assert "place_names" not in named.summary

    with pytest.raises(ToolError):
        await locate(db, ctx, LocateSpec(h3_indexes=["nope"]))


def test_place_from_mapy_response():
    from agent.places import _place

    data = {
        "items": [
            {
                "name": "Třída Svobody 12",
                "location": "Olomouc, Česko",
                "regionalStructure": [
                    {"name": "Třída Svobody 12", "type": "regional.address"},
                    {"name": "Třída Svobody", "type": "regional.street"},
                    {"name": "Olomouc", "type": "regional.municipality_part"},
                ],
            }
        ]
    }
    assert _place(data) == {
        "name": "Třída Svobody 12",
        "street": "Třída Svobody",
        "district": "Olomouc",
        "location": "Olomouc, Česko",
    }
    assert _place({"items": []}) is None


def test_tool_schemas_are_flat():
    text = json.dumps(tool_schemas())
    assert "$ref" not in text
    assert {t["function"]["name"] for t in tool_schemas()} >= {
        "rank_areas",
        "area_detail",
        "locate_hexagons",
    }


def test_map_endpoint(client):
    response = client.post(
        "/api/agent/map",
        json={"level": "microzone", "metric": "score", "ids": ["Lošov", "Centrum"]},
    )
    assert response.status_code == 200, response.text
    layer = response.json()
    assert layer["features"]["type"] == "FeatureCollection"
    assert len(layer["features"]["features"]) == 2
    assert layer["legend"]["breaks"] == [20, 40, 60, 80]
    assert client.post("/api/agent/map", json={"metric": "nope"}).status_code == 400


class ScriptedLLM:
    """Ranks microzones, then answers with the top one."""

    model = "scripted"

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        self.calls += 1
        if self.calls == 1:
            return LLMReply(
                "",
                [ToolCall("c1", "rank_areas", {"level": "microzone", "limit": 3})],
                Usage(10, 5, 1),
            )
        result = json.loads(messages[-1]["content"])
        top = result["rows"][0]["microzone"]
        return LLMReply(f"The highest need is in **{top}**.", [], Usage(20, 8, 1))


def test_chat_json_and_stream(client, monkeypatch):
    monkeypatch.setattr(settings, "AI_BASE_URL", "http://fake")
    monkeypatch.setattr(settings, "AI_MODEL", "scripted")
    app.dependency_overrides[get_llm] = ScriptedLLM
    try:
        response = client.post(
            "/api/agent/chat", json={"message": "Where is need highest?", "stream": False}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["answer"].startswith("The highest need is in **Mikrozóna")
        assert body["steps"][0]["ok"] and body["steps"][0]["layer"]["level"] == "microzone"

        with client.stream(
            "POST", "/api/agent/chat", json={"message": "Where is need highest?"}
        ) as stream:
            text = "".join(stream.iter_text())
        assert [line for line in text.splitlines() if line.startswith("event:")] == [
            "event: step",
            "event: answer",
            "event: done",
        ]
    finally:
        app.dependency_overrides.clear()


def test_chat_off_without_model(client, monkeypatch):
    monkeypatch.setattr(settings, "AI_BASE_URL", None)
    assert client.post("/api/agent/chat", json={"message": "hi"}).status_code == 503
    assert client.get("/api/agent/status").json()["enabled"] is False
