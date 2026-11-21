# Agent skills

Each `.md` file here tells the Ask AI agent how to answer a kind of question.
They are added to the agent's instructions for every question, so editing a file
changes how it answers. No code changes needed.

- **Locally:** the running server reads the files again for every question, so
  just save and ask again.
- **On Render:** commit and push; the next deploy has the change.

## Two kinds of skill

- **General** (no `questions` in the header): rules for every answer.
  `answer-style.md` sets how short answers are, the table and the
  "Show on map" line.
- **Playbook** (with `questions`): what to do for one type of question.

## Add a playbook

Copy one of the files, rename it (e.g. `cycle-routes.md`) and edit it:

```markdown
---
title: Short name of the question type
questions:
  - The question as users ask it
  - Another way to ask the same thing
---
Steps:
1. rank_areas: metric `score`, level hex, limit 5, filter `raw_residents` gt 0.
2. locate_hexagons with all h3_index values at once.

Table: Place | Microzone | Score

Why (one bullet): ...
```

Tips:

- Put metric names in backticks, e.g. `raw_dist_green`. The tests check that
  every backticked name is a real metric, so a typo fails the test run.
- Filter values use the scale the tools show: scores 0-100, shares in % (so
  "at least 5 %" is `gte 5`).
- Tools: `index_overview`, `rank_areas`, `summarize_areas`, `describe_metric`,
  `area_detail`, `locate_hexagons`, `public_buildings` (individual public
  buildings with roof area; its map shows the buildings on top of their areas). Their options are in `agent/tools.py` and
  `agent/query.py`.
- To switch a skill off without deleting it, start its file name with `_`.
- Check your edits with `uv run pytest tests/test_skills.py`.
