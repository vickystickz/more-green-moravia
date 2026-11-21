---
title: The warmest nights
questions:
  - Where are the warmest nights?
  - Where does it stay hot at night?
  - Which areas have tropical nights?
---
Steps:
1. rank_areas: metric `raw_heatwave_tmin`, level hex, limit 5, filter `raw_residents` gt 0,
   show `raw_lst_copernicus`.
2. locate_hexagons with all h3_index values at once.

Table: Place | Microzone | Night min. (°C) | Surface (°C, satellite)

Why (one bullet): sealed ground and buildings store heat by day and release it at night.
A night minimum of 20 °C or more is a tropical night.
