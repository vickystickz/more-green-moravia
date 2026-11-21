---
title: Public buildings for green roofs
questions:
  - Which public buildings in hot areas could get green roofs?
  - Where could schools or offices get green roofs?
  - Which public roofs should be greened first?
  - Which schools are in the hottest places?
---
Public buildings are schools, kindergartens, offices, hospitals, university
buildings and libraries.

Steps:

1. public_buildings: metric `he`, limit 5, min_roof_m2 300.
   For schools or another type only, ask for limit 20 and keep the first 5 of that type.
   If the user asks for flat roofs, set flat_roofs_only.
   No locate_hexagons call: this tool already gives the streets.

Table: Building | Street | Roof (m²) | Heat score

- "Building": its name; when it has none, its type in words ("school", "civic building").
- Add "(flat roof)" after the roof area when roof_shape is flat.

Why (one bullet): hot places with large public roofs, where the city can act
quickly on its own buildings (green roofs or greened courtyards).

Then add this line before the Show on map line, speaking to the user:
"On the map, the buildings are shown in blue on top of their areas."
