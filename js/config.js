// =============================================================
// config.js
// App-wide settings in one place, so values are never repeated
// across files. Change things here, not inside the modules.
// =============================================================

// -------------------------------------------------------------
// Map settings
// -------------------------------------------------------------
export const MAP_CONFIG = {
  // Basemap style (vector tiles). OpenFreeMap Positron is free,
  // needs no API key, and its light grey look keeps our data
  // layers the main focus of the map.
  style: 'https://tiles.openfreemap.org/styles/positron',
  center: [17.2509, 49.5938], // Olomouc city centre
  zoom: 12.5,   // starting zoom: the whole city is visible
  minZoom: 11,  // furthest out: the whole city fits in view
  maxZoom: 18,  // street level is the most detail we need

  // Users cannot pan outside this box. It is the Olomouc city
  // boundary (approx. 17.17–17.37 E, 49.53–49.67 N) plus a small
  // margin so the edge districts are not stuck at the screen edge.
  // Format: [[west, south], [east, north]] in [lng, lat].
  maxBounds: [
    [17.13, 49.51],
    [17.41, 49.69],
  ],
};

// -------------------------------------------------------------
// Search (geocoding) with the Mapy.com API by Seznam.
// The API key lives in js/env.js (not committed).
// Docs: https://developer.mapy.com/rest-api/funkce/geokodovani/
// -------------------------------------------------------------
export const SEARCH_CONFIG = {
  url: 'https://api.mapy.com/v1/suggest',
  lang: 'cs',     // Czech names (Křenovice, not Krenovice)
  limit: 6,       // max results in the dropdown
  minChars: 1,    // start searching from the first letter
  // Debounce: wait this long after the last key press before
  // asking the API. Short enough to feel instant, long enough to
  // skip most in-between letters when typing fast.
  debounceMs: 150,

  // Places we want: city parts, streets, addresses, landmarks.
  types: [
    'regional.municipality_part',
    'regional.street',
    'regional.address',
    'poi',
  ],

  // Rank results inside Olomouc first. Format: minLon,minLat,maxLon,maxLat
  // (same box as MAP_CONFIG.maxBounds). Results outside it are
  // also removed in geocode.js, because the map cannot go there.
  bbox: [17.13, 49.51, 17.41, 49.69],
};

// -------------------------------------------------------------
// Data files
// -------------------------------------------------------------
export const DATA_PATHS = {
  microzones: 'data/processed/microzones.geojson',
};

// -------------------------------------------------------------
// Scoring factors (one weight slider each)
// -------------------------------------------------------------
export const FACTORS = ['heat', 'vulnerable', 'greenDeficit'];
