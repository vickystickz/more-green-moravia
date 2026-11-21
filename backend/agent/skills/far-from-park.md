---
title: Neighbourhoods far from a park
questions:
  - Which neighbourhoods are far from a park?
  - Where do people live far from green space?
  - Which districts have no park nearby?
---
"Neighbourhoods" means microzones.

Steps:
1. rank_areas: metric `raw_dist_green`, level microzone, agg avg, limit 5,
   filter `raw_residents` gt 0, show `raw_residents`.

Table: Microzone | Walk to park (m) | Residents

Why (one bullet): the distance is the walk along streets to the nearest park or
forest of at least 0.5 ha.
