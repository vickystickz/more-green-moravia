# more-green-moravia
More Green, Moravia is an interactive map dashboard that shows cities, planners and businesses where green improvements would help the most people in Olomouc. It scores a 200 m H3 hexagon grid by heat & people exposed, vulnerable groups and lack of green (INFORM-style), using the priorities you set. This version focuses on heat stress.

## Data

Put the files exported by the GI index notebook in `data/`, with exactly these names:

| File | Required | What it is |
|---|---|---|
| `data/olomouc_gi_h3_r9.geojson` | yes | H3 hexagons (res. 9, WGS84) with the `c_*`, `d_*`, `raw_*` and `gi_*_provisional` columns |
| `data/olomouc_gi_h3_r9_metadata.json` | no | notebook parameters (`heat_hazard_share_a`, `day_weight`); defaults 0.5 / 0.7 |
| `data/olomouc_microzones.geojson` | no | microzone outlines; adds a "Microzone boundaries" layer when present |

Paths are set in `DATA_PATHS` in `js/config.js`. On load, the browser console logs `INFORM check passed` when the in-browser score matches the notebook's `gi_need_provisional` (Balance weights).

## Run locally

The site is plain HTML/JS (no build step), but ES modules need a local server:

```sh
python3 -m http.server 8000   # then open http://localhost:8000
```
