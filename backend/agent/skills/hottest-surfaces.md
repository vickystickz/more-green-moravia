---
title: The hottest surfaces
questions:
  - Where are the hottest surfaces in the city?
  - Where is the ground hottest?
  - Which places heat up most in the sun?
---
Steps:
1. rank_areas: metric `raw_lst_copernicus` (Landsat daytime surface temperature),
   level hex, limit 5, show `raw_sealing` and `raw_tree_cover`.
2. locate_hexagons with all h3_index values at once.

Table: Place | Microzone | Surface (°C) | Sealed ground | Tree cover

Why (one bullet): sealed ground, car parks and large roofs heat up most in the sun;
trees and vegetation keep surfaces cooler. Surface temperature is the main heat input
(45 %).
