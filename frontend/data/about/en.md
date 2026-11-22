<!--
  About this tool: shown when the (i) button next to
  "Your city, your plan, your priorities" is clicked.
  Edit this file to change the text; no code change is needed.
  Czech version: cs.md (same structure).

  Supported: # ## ### headings, paragraphs, - lists, 1. lists,
  | tables |, **bold**, *italic*, `code`, [links](https://…),
  images ![alt](assets/img/file.png) on their own line,
  > a highlighted note, and --- for a divider. Image paths are relative to the site root.
-->

# More Green, Moravia

**Where would green improvements in Olomouc reduce heat stress for the people most affected?**

More Green, Moravia is an interactive map for residents, planners and the city. It scores every part of Olomouc (H3 hexagons of about 75 m) on three things: how hot it gets and how many people are there, how many vulnerable people live there, and how little green there is. You choose how much each factor matters, and the map, the ranking and the detail card update straight away.

Submitted to the [UPOL Hackathon 2026](https://hackathon.upol.cz/en/) for the topic **Smart City in Data: Assessing Quality of Life in Olomouc's Micro-zones Using Sensor Data**.

> **Provisional results.** Scores combine satellite surface temperature (Landsat, summer 2026), heatwave temperatures (night and day), population, vulnerable groups, green vegetation (Sentinel-2, summer 2026), tree cover, sealed ground, walking distance to parks and available land on a 75 m hexagon grid (H3); people and vulnerable groups per ~200 m neighbourhood. Checked against 2,091 places residents marked as comfortable or uncomfortable on hot days. This version focuses on heat stress. Use as a guide, not a final decision.

---

## How it works

![How the product works: data, then the INFORM index, then the portal](assets/img/how-it-works.png)

1. **Data.** Heat, population, green space and land-use data are collected for Olomouc (see *Data sources* below).
2. **GI index notebook.** Every dataset is moved onto the same H3 hexagon grid, turned into a 0–1 score, and combined with the INFORM formula.
3. **Publish.** The notebook's export is copied to the website and to the Ask AI service, so both show the same numbers.
4. **Portal.** The website re-weights the score in your browser as you move the sliders. Ask AI answers questions using only the same data.

---

## Methodology: the INFORM approach

The score follows the method of the [INFORM Risk Index](https://drmkc.jrc.ec.europa.eu/inform-index/INFORM-Risk/Methodology), developed by the European Commission's Joint Research Centre. INFORM measures risk as a combination of **hazard & exposure**, **vulnerability** and **lack of coping capacity**. Each dimension is built from categories and components, and the dimensions are combined with a geometric mean.

![The INFORM framework: dimensions, categories and components](assets/img/inform-framework.png)

*Figure: the INFORM framework. Source: European Commission, Joint Research Centre, [INFORM Risk methodology](https://drmkc.jrc.ec.europa.eu/inform-index/INFORM-Risk/Methodology).*

We apply the same structure at the scale of a city, for heat:

| INFORM dimension | In this tool | What it measures |
|---|---|---|
| Hazard & exposure | **Heat & people exposed** | How hot a place gets, and how many people live or spend the day there |
| Vulnerability | **Vulnerable groups** | Older residents, young children, schools, kindergartens and doctors |
| Lack of coping capacity | **Lack of green** | Little vegetation or tree cover, a lot of sealed ground, a long walk to a park |

### Step 1: from raw data to a 0–1 score

Each indicator is converted to a value between 0 and 1 (a *fuzzy membership*): 0 means no need, 1 means the highest need. Values below a lower threshold get 0, values above an upper threshold get 1, and values in between rise in a straight line. For heat, the thresholds are the city median and the 95th percentile, so the score shows which places are hotter than usual for Olomouc. Population density and facility counts are log-scaled first. For green space, fixed planning thresholds are used (for example, a walk of 300 m or less to green space counts as good, and 800 m or more as poor).

### Step 2: combine indicators into dimensions

**Heat & people exposed (HE).** Heat combines:

| Heat indicator | Weight |
|---|---|
| Satellite surface temperature (Landsat, summer 2026, 30 m) | 45 % |
| Night-time minimum temperature during heatwaves | 30 % |
| Neighbourhood surface temperature (microzone mean) | 15 % |
| Daytime maximum temperature during heatwaves | 10 % |

Exposure is the number of people living (night) and spending the day (day) in the area, weighted 50/50. Heat and exposure are combined as `HE = heat^0.5 × exposure^0.5`, so a hot place where nobody lives does not rank high.

**Vulnerable groups (V):** share of residents aged 65+ (35 %), aged 75+ (20 %), children aged 0–4 (20 %), and schools, kindergartens and doctors (25 %).

**Lack of green (GD):** green supply and green access, 50/50. Supply combines vegetation from Sentinel-2 NDVI (30 %), accessible green share (20 %), sealed ground (20 %), tree cover (15 %) and green space per resident (15 %). Access is the walking distance along streets to the nearest park or forest.

### Step 3: the GI need score (our weighting method)

As in INFORM, the three dimensions are combined with a **weighted geometric mean**:

`GI need = HE^wHE × V^wV × GD^wGD`  (the weights add up to 1)

With the **Balance** preset every weight is 1/3. A geometric mean means a place needs to score on all three dimensions to rank high: a very hot place with no vulnerable residents does not come first. Values that are missing or zero are set to 0.01, so one gap does not wipe out the score.

The presets and sliders only change the weights:

| Preset | Heat & people | Vulnerable groups | Lack of green |
|---|---|---|---|
| Balance | 33 % | 33 % | 33 % |
| Cool streets | 50 % | 20 % | 30 % |
| Protect vulnerable | 30 % | 50 % | 20 % |
| Pocket parks | 20 % | 40 % | 40 % |
| Quick wins | 33 % | 33 % | 33 % + only places we can build |

The score is recalculated in your browser for every area each time a slider moves. At start-up the website checks itself: with Balance weights every area must match the score calculated in the notebook.

### Step 4: only show places we can build

"Only show places we can build" multiplies the need by a **feasibility** score (0–1): `Priority = GI need × feasibility`. Feasibility is high where there is room for green: brownfields, vacant land, parking areas and public buildings (green roofs), plus cycle paths and streets that can become green corridors. Railways, water and fast roads are taken out, because nothing can be planted there.

---

## Validation

The index was checked in two independent ways. Neither is used in the score.

**1. Residents' summer heat map** (2,091 places marked as comfortable or uncomfortable, 2020):

- In the 114 areas with at least 3 marks, GI need correlates with the share of "uncomfortable" marks (Spearman r = 0.73, significant).
- Tree cover (r = −0.81), vegetation (r = −0.74) and sealed ground (r = 0.70) all point in the expected direction.
- 56 % of "uncomfortable" marks fall in the top 20 % of areas by GI need, against 7 % of "comfortable" marks.

**2. Orthophoto of Olomouc** ([ČÚZK](https://geoportal.cuzk.cz/Default.aspx?mode=TextMeta&metadataID=CZ-CUZK-ORTOCIR-R&metadataXSL=full&side=ortofoto)): we overlaid the results on the orthophoto here in the application, especially to look at the vegetated areas. We checked that parks, forests, gardens and tree-lined streets score low for lack of green, and that high-scoring areas really are built-up and sealed with little vegetation. You can repeat the check: switch the basemap to the orthophoto with the map button and lower the opacity in Map layers.

---

## Data sources

| Topic | Data |
|---|---|
| Heat | Landsat surface temperature (summer 2026, 30 m) · Citiq heatwave day and night temperatures (2026) · microzone thermal mean |
| People | Olomouc microzones: residents, ages 65+, 75+, 0–4 · schools, kindergartens, doctors |
| Green | Sentinel-2 NDVI (summer 2026) · Copernicus Tree Cover Density (10 m) · Copernicus Imperviousness (10 m, 2024) · Copernicus Urban Atlas 2021 · OpenStreetMap streets for walking distance |
| Space to build | Brownfields · vacant land · parking · public buildings · cycle paths |
| Validation | Residents' summer heat map (2,091 places, 2020) · [ČÚZK orthophoto](https://geoportal.cuzk.cz/Default.aspx?mode=TextMeta&metadataID=CZ-CUZK-ORTOCIR-R&metadataXSL=full&side=ortofoto) |
| Map | OpenFreeMap · ČÚZK orthophoto · Mapy.com search |

**Limits.** People and vulnerable groups are counted per microzone (about 200 m), so neighbouring 75 m areas share those values. The score shows where green would help most; it is not a design or a cost plan. Green roof costs are rough estimates from published price ranges.

---

## Team

Built by **Team deCoDE**: **Victor**, **Pamela** and **Redoy** for the [UPOL Hackathon 2026](https://hackathon.upol.cz/en/).

**Source code:** [github.com/vickystickz/more-green-moravia](https://github.com/vickystickz/more-green-moravia) (the map site, the Ask AI backend and how to run them).
