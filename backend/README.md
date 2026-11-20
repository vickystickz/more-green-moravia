# More Green, Moravia: backend

A FastAPI service with one job for now: an AI agent that answers questions about
the Olomouc green infrastructure (GI) index and returns map layers for its
answers. The agent design is adapted from the xyField agent (`backend/agent`).

## Run

```sh
cd backend
uv sync                                  # install (Python 3.12+)
cp .env.example .env                     # then set AI_BASE_URL, AI_API_KEY, AI_MODEL
uv run uvicorn app.main:app --reload     # http://localhost:8000/docs
```

On start the server builds `data/moravia.duckdb` from the GeoJSON exports in
`data/` if the file is missing. They are copies of the frontend's files in
`../frontend/data/`: after a new notebook export, copy the three files
(`olomouc_gi_h3_r9.geojson`, `olomouc_gi_h3_r9_metadata.json`,
`olomouc_microzones.geojson`) to `backend/data/` too, then rebuild:

```sh
uv run python -m app.ingest --force
```

Without `AI_BASE_URL` and `AI_MODEL` the server still starts; `/chat` answers 503
and `/status` reports `enabled: false`. `/map` works either way.

Tests: `uv run pytest`. Lint: `uv run ruff check . && uv run ruff format .`

## Deploy (Docker, Render)

The image is built from `backend/` (it builds the DuckDB file from `data/`
at build time):

```sh
cd backend
docker build -t moravia-api .
docker run --rm -p 8000:8000 --env-file .env moravia-api
```

On Render: **New → Blueprint**, pick this repo; `render.yaml` sets up the
service. Fill in `AI_API_KEY` and `AI_MODEL` when asked, and check that
`CORS_ORIGINS` is the site's origin. Then set the GitHub repository variable
`AGENT_API_URL` to the service URL (`https://<name>.onrender.com`) and re-run
the Pages deploy so the site points at it.

## The model

Any OpenAI-compatible chat-completions API that supports **tool calling**:

| Provider | `AI_BASE_URL` | `AI_MODEL` (example) |
|---|---|---|
| OpenRouter | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4.5`, `openai/gpt-4.1-mini` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| Ollama (local, no key) | `http://localhost:11434/v1` | `qwen2.5:14b` |

`AI_API_KEY` is the provider's key. It stays on the server: never put it in the
frontend.

## Endpoints (`/api/agent`)

| Method | Path | What |
|---|---|---|
| GET | `/status` | Agent on/off, model, hexagon and microzone counts |
| GET | `/suggestions` | Starter questions for an empty chat |
| GET | `/metrics` | Every metric the agent and `/map` can use |
| POST | `/chat` | Ask a question: `{message, history?, stream?}`. Server-sent events (`step`, `answer`, `done`, or `error`) or one JSON response |
| POST | `/map` | A GeoJSON layer: send a step's `layer`, or any `{level, metric, ids?, filters?, preset?, weights?, only_buildable?}` |

Conversations are not stored. For follow-up questions the client sends the
earlier turns in `history`.

## How it works

```
question ─► model ─► tool call (typed JSON) ─► SQL on DuckDB ─► result ─► model ─► … ─► answer
                                                    │
                                                    └─► step event with rows + map layer
```

- `app/ingest.py` loads the hexagon GeoJSON (every property, plus the score
  dimensions `he, v, gd, feas` computed as in `frontend/js/scoring/score.js`,
  a centre and the outline), the microzone outlines and `metadata.json` into DuckDB.
- `agent/catalog.py` lists the metrics (from the table columns and the metadata).
  It is the allow-list: no other column reaches a query.
- `agent/query.py` turns tool arguments into parameterized SQL. The model never
  writes SQL. Scores come out 0–100 and shares in %, as the app shows them.
  `score` is weighted like the sliders: a preset (`balance`, `cool-street`,
  `protect-vulnerable`, `pocket-parks`, `quick-wins`) or custom weights.
- `agent/tools.py` has the five tools: `index_overview`, `rank_areas`,
  `summarize_areas`, `describe_metric`, `area_detail`.
- `agent/loop.py` runs the model until it answers (at most `AGENT_MAX_STEPS`
  tool rounds) and strips links, images and HTML from the answer.

## Adding data or tools

- **A new tool** (e.g. geocoding place names in Olomouc, or an administrative
  area lookup): write `async def run(db, ctx, spec) -> QueryResult` with a
  Pydantic `spec`, and add a `Tool` to `TOOLS` in `agent/tools.py`. A geocoder
  can hand its coordinates to `area_detail`, which already takes `lon`/`lat`.
- **A new layer** (e.g. administrative boundaries): load it into its own table
  in `app/ingest.py`, keeping the geometry as GeoJSON text like `microzones`.
