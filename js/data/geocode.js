// =============================================================
// data/geocode.js
// Turns a search text into places, using the Mapy.com "suggest"
// API (made for search-as-you-type). Only places inside the
// Olomouc box are returned.
// =============================================================

import { SEARCH_CONFIG } from '../config.js';

// The key is loaded from js/env.js. We import it dynamically, so
// if that file is missing the app still works, just without search.
let apiKey = null;
try {
  ({ MAPY_API_KEY: apiKey } = await import('../env.js'));
} catch {
  console.warn('js/env.js not found: search is disabled. Copy js/env.example.js to js/env.js.');
}

/** True when an API key is available. */
export const isSearchEnabled = () => Boolean(apiKey);

/**
 * Search for places in Olomouc.
 *
 * @param {string} query - what the user typed
 * @param {AbortSignal} [signal] - lets us cancel an old request
 *   when the user keeps typing
 * @returns {Promise<Array<{
 *   name: string,          // e.g. "Hodolany"
 *   label: string,         // type of place, e.g. "Část obce"
 *   location: string,      // e.g. "Olomouc, Česko"
 *   center: [number, number],            // [lng, lat]
 *   bbox: [number, number, number, number] | null
 * }>>}
 */
export async function searchPlaces(query, signal) {
  if (!apiKey) return [];

  const [west, south, east, north] = SEARCH_CONFIG.bbox;

  // Build the request URL. `type` may appear several times.
  // The key goes in the URL (not a header): a custom header makes
  // the browser send an extra "preflight" request before every
  // search, which doubles the waiting time.
  const params = new URLSearchParams({
    apikey: apiKey,
    query,
    lang: SEARCH_CONFIG.lang,
    // Ask for extra results, because some are filtered out below.
    limit: String(SEARCH_CONFIG.limit * 2),
    preferBBox: SEARCH_CONFIG.bbox.join(','),
  });
  SEARCH_CONFIG.types.forEach((t) => params.append('type', t));

  const res = await fetch(`${SEARCH_CONFIG.url}?${params}`, { signal });
  if (!res.ok) throw new Error(`Search failed (${res.status})`);

  const data = await res.json();

  return (data.items ?? [])
    // Keep only places inside Olomouc (the map can't pan elsewhere).
    .filter(({ position: p }) =>
      p.lon >= west && p.lon <= east && p.lat >= south && p.lat <= north)
    .slice(0, SEARCH_CONFIG.limit)
    // Convert to the simple shape the rest of the app uses.
    .map((item) => ({
      name: item.name,
      label: item.label,
      location: item.location,
      center: [item.position.lon, item.position.lat],
      bbox: item.bbox ?? null,
    }));
}
