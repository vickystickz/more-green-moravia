---
title: Hot areas with many older residents
questions:
  - Where are hot areas with many older residents?
  - Where do older people suffer most from heat?
  - Which hot places have many seniors?
---
Steps:
1. rank_areas: metric `he`, level hex, limit 5,
   filters `raw_residents` gt 0 and `raw_share_65plus` gte 25,
   show `raw_share_65plus` and `raw_heatwave_tmin`.
   If fewer than 3 places come back, run it again with `raw_share_65plus` gte 20.
2. locate_hexagons with all h3_index values at once.

Table: Place | Microzone | Heat score | Aged 65+

Why (one bullet): warm nights and many residents; older people cope worst when
nights stay warm.
