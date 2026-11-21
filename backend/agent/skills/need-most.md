---
title: Where green infrastructure is needed most
questions:
  - Where is green infrastructure needed most?
  - Which areas need greenery the most?
  - Where should the city start planting trees?
---
Steps:
1. rank_areas: metric `score`, level hex, limit 5, filter `raw_residents` gt 0.
   Pass the preset or weights if the user mentioned one.
2. locate_hexagons with all 5 h3_index values at once.

Table: Place | Microzone | Score

Why (one bullet): the factor that is highest for most of these places
(heat & people exposed, vulnerable groups or lack of green).
