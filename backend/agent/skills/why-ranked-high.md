---
title: Why an area is ranked high
questions:
  - Why is this area ranked so high?
  - Why does this place score so high?
  - What makes this microzone a priority?
---
"This area" is the place the user named, or the first place in your previous answer.
If neither gives a place, ask which area they mean (one short question) and stop.

Steps:
1. area_detail for that place's microzone, by name (it is in the table of your
   previous answer). Pass the preset or weights from the conversation, if any.

Table: Factor | Score | Rank in city
Rows: Heat & people exposed, Vulnerable groups, Lack of green (plus Space to build
when "only places we can build" is on).

Why (two bullets at most): the measured values behind the highest factor, e.g.
night min. °C, residents per ha, share aged 65+, tree cover %, sealed ground %,
walk to the nearest park.
If `val_perceived_heat` has a value, add one short line: what share of residents'
reports called it uncomfortable on hot days (2020 survey; not part of the score).
