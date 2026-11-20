// =============================================================
// config.js
// App-wide settings in one place, so values are never repeated
// across files. Change things here, not inside the modules.
// =============================================================

// Keys from js/env.js (not committed). Imported dynamically so the
// app still runs, minus search and Ask AI, when the file is missing.
let env = {};
try {
  env = await import('./env.js');
} catch {
  /* geocode.js already warns about the missing file */
}

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
// Ask AI: our own backend (backend/, FastAPI). The browser never
// talks to the AI provider directly; the key stays on the server.
// Its address is AGENT_API_URL in js/env.js. The backend must
// list this site's origin in CORS_ORIGINS.
// -------------------------------------------------------------
export const AGENT_CONFIG = {
  enabled: false,              // false = Ask AI button hidden (turned off for now)
  baseUrl: String(env.AGENT_API_URL || '').replace(/\/+$/, ''), // '' = Ask AI off
  chatPath: '/api/agent/chat', // POST, server-sent events
  mapPath: '/api/agent/map',   // POST a step's layer → GeoJSON ("Show on map")
  maxHistory: 24,              // turns sent back for follow-ups (backend limit)
  maxTurnChars: 8000,          // per turn (backend limit)
};

// -------------------------------------------------------------
// Data files (relative paths, so they work on GitHub Pages)
// Both files are exported by the GI index notebook. Put them in
// the data/ folder with exactly these names.
// -------------------------------------------------------------
export const DATA_PATHS = {
  // ?v=… busts the browser/CDN cache: bump it after every new export.
  hexes: 'data/olomouc_gi_h3_r9.geojson?v=4',
  metadata: 'data/olomouc_gi_h3_r9_metadata.json?v=4',
  // Optional microzone outlines. If this file does not exist, the
  // "Microzone boundaries" checkbox is not shown.
  boundaries: 'data/olomouc_microzones.geojson',
};

// -------------------------------------------------------------
// Scoring (INFORM-style, must match the notebook)
// -------------------------------------------------------------

// The three dimensions that have a weight slider.
//   he = Heat & people exposed, v = Vulnerable groups,
//   gd = Lack of green (green deficit)
export const FACTORS = ['he', 'v', 'gd'];

// Used when metadata.json is missing or lacks these values.
export const SCORE_DEFAULTS = {
  a: 0.5,         // heat_hazard_share_a: share of heat hazard vs exposure
  dayWeight: 0.5, // day_weight fallback only; the real value comes from metadata.json
};

export const MIN_WEIGHT = 0.1; // 10%: a 0 weight would drop out of the product

// Classified colours for every map layer: 5 equal classes of
// 20 points (0–20, 20–40, 40–60, 60–80, 80–100). Light = low need,
// dark red = high need. The map legend is built from this list,
// so the legend and the map always match.
export const SCORE_CLASSES = [
  { from: 0.0, color: '#f7efd9' },
  { from: 0.2, color: '#f6cf7f' },
  { from: 0.4, color: '#eb9550' },
  { from: 0.6, color: '#cf5734' },
  { from: 0.8, color: '#962320' },
];

// Starting opacity of the hexagon colours (the user can change it
// with the slider in the Map layers panel).
export const HEX_OPACITY = 0.7;

// Layers the user can colour the map by (one at a time).
// `key` is the feature-state value set in map/layers.js;
// `label` is the text key in data/lang/*.json;
// `legend` (optional) = text keys for the left / middle / right
// legend labels (default: Low / Medium / High).
export const MAP_LAYERS = [
  { id: 'score', key: 'score', label: 'layers.score' },
  { id: 'he', key: 'he', label: 'factor.he' },
  { id: 'night', key: 'night', label: 'layers.night' }, // mu_heatwave_tmin
  { id: 'v', key: 'v', label: 'factor.v' },
  { id: 'gd', key: 'gd', label: 'factor.gd' },
  { id: 'sealing', key: 'sealing', label: 'layers.sealing', legend: ['legend.zero', null, 'legend.full'] }, // raw_sealing 0–1
  { id: 'feas', key: 'feas', label: 'factor.feas' },
];
