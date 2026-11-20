// =============================================================
// data/fetch-data.js
// Loads the GI index hexagons, the notebook parameters and
// (if present) the microzone boundaries.
// =============================================================

import { DATA_PATHS } from '../config.js';

async function getJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Could not load ${path} (${res.status})`);
  return res.json();
}

/** H3 hexagons with the index columns (GeoJSON FeatureCollection). */
export const loadHexes = () => getJson(DATA_PATHS.hexes);

/** Notebook parameters. Missing file → {} (defaults are used). */
export const loadMetadata = () => getJson(DATA_PATHS.metadata).catch((err) => {
  console.warn(`${err.message}: using default a and day_weight.`);
  return {};
});

/** Microzone outlines, or null when the file does not exist. */
export const loadBoundaries = () => getJson(DATA_PATHS.boundaries).catch(() => null);
