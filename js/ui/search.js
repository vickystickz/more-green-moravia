// =============================================================
// ui/search.js
// The search bar on the map: shows suggestions while typing and
// moves the map to the place the user picks.
// Matching microzones from our own data come first (no API key
// needed), then streets and places from the Mapy.com API.
// Keyboard: ↑ / ↓ to move, Enter to pick, Esc to close.
// =============================================================

import { SEARCH_CONFIG } from '../config.js';
import { searchPlaces, isSearchEnabled } from '../data/geocode.js';
import { t, getLang } from './i18n.js';

/**
 * Wire up the search bar.
 *
 * @param {maplibregl.Map} map
 * @param {(query: string) => Array} [localSearch] - microzones whose
 *   name matches, in the same shape as searchPlaces() results
 */
export function initSearch(map, localSearch = () => []) {
  const form = document.getElementById('map-search');
  const input = document.getElementById('search-input');
  const list = document.getElementById('search-results');

  // Without an API key, only our own microzone names are searched.
  const useApi = isSearchEnabled();

  let results = [];  // suggestions currently in the list
  let active = -1;   // highlighted suggestion (-1 = none)
  let timer = null;  // debounce timer

  // Every answer from the API, by query text, e.g. "hod" → [...].
  // Used to show suggestions instantly while the next answer is
  // still on its way (the API can take 1–2 seconds).
  const cache = new Map();

  // ---------- Typing: suggestions while you type ----------
  //
  // On every key press:
  //   1. Show instant suggestions from earlier answers (no waiting).
  //   2. Debounce: once typing pauses for SEARCH_CONFIG.debounceMs,
  //      ask the API for fresh results.
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const query = input.value.trim();

    if (query.length < SEARCH_CONFIG.minChars) {
      close();
      return;
    }

    // 1. Instant suggestions (microzones + earlier API answers)
    const instant = suggestFromCache(query);
    if (instant || !useApi || localSearch(query).length > 0) {
      show(instant ?? []);
    } else if (results.length === 0) {
      showMessage(t('search.searching'));
    }

    // 2. Fresh results (skip if we already asked for this exact text)
    if (useApi && !cache.has(cacheKey(query))) {
      timer = setTimeout(() => runSearch(query), SEARCH_CONFIG.debounceMs);
    }
  });

  // Ask the API. Older requests are NOT cancelled: their answers
  // still help, because they fill the cache for instant suggestions.
  async function runSearch(query) {
    try {
      const found = await searchPlaces(query);
      cache.set(cacheKey(query), found);

      // Refresh the list if it still fits what is typed now.
      const instant = suggestFromCache(input.value.trim());
      if (instant) show(instant);
      else if (cacheKey(input.value.trim()) === cacheKey(query)) show([]);
    } catch (err) {
      console.warn(err);
      showMessage(t('search.error'));
    }
  }

  /**
   * Suggestions for `query` from earlier answers, without the API.
   * Uses the answer for the longest earlier text that `query`
   * starts with (e.g. "hod" when typing "hodo"), keeping only the
   * places whose name still matches.
   *
   * @returns {Array|null} null when nothing useful is cached
   */
  function suggestFromCache(query) {
    const q = cacheKey(query);
    if (cache.has(q)) return cache.get(q); // exact answer

    // Longest cached prefix of what is typed now.
    let best = null;
    for (const key of cache.keys()) {
      if (q.startsWith(key) && (!best || key.length > best.length)) best = key;
    }
    if (!best) return null;

    const typed = normalize(query);
    const matches = cache.get(best).filter((place) =>
      normalize(place.name).includes(typed));
    return matches.length > 0 ? matches : null;
  }

  // Lower case, no accents: "Křenovice" and "krenovice" match.
  // Cache keys also carry the language, because the API answers
  // with place types in that language ("Street" / "Ulice").
  function normalize(text) {
    return text.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
  }
  const cacheKey = (text) => `${getLang()}:${normalize(text)}`;

  // Replace the current suggestions and redraw the list.
  // Matching microzones always come first.
  function show(found) {
    results = [...localSearch(input.value.trim()), ...found];
    active = -1;
    render();
  }

  // Re-open the last suggestions when the user clicks back into
  // the search box.
  input.addEventListener('focus', () => {
    if (results.length > 0 && input.value.trim()) render();
  });

  // ---------- Draw the suggestion list ----------
  function render() {
    list.innerHTML = '';

    if (results.length === 0) {
      showMessage(t('search.none'));
      return;
    }

    results.forEach((place, i) => {
      const li = document.createElement('li');
      li.className = 'search-result';
      li.id = `search-result-${i}`;
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', String(i === active));

      const name = document.createElement('span');
      name.className = 'search-result__name';
      name.textContent = place.name;

      const meta = document.createElement('span');
      meta.className = 'search-result__meta';
      meta.textContent = `${place.label} · ${place.location}`;

      li.append(name, meta);

      // mousedown (not click) fires before the input loses focus.
      li.addEventListener('mousedown', (e) => {
        e.preventDefault();
        choose(i);
      });

      list.append(li);
    });

    open();
  }

  // A single grey line, e.g. "No places found".
  function showMessage(text) {
    list.innerHTML = '';
    const li = document.createElement('li');
    li.className = 'search-message';
    li.textContent = text;
    list.append(li);
    open();
  }

  // ---------- Pick a place: move the map there ----------
  function choose(i) {
    const place = results[i];
    if (!place) return;

    input.value = place.name;
    close();

    // Areas (city parts, streets) have a bbox: fit them in view.
    // Single points (addresses) don't: zoom to street level.
    if (place.bbox) {
      map.fitBounds(
        [[place.bbox[0], place.bbox[1]], [place.bbox[2], place.bbox[3]]],
        { padding: 60, maxZoom: 16 } // 16: close, but still shows the surroundings
      );
    } else {
      map.flyTo({ center: place.center, zoom: 17 });
    }

    // Microzones also open the detail card of their top hex.
    place.onPick?.();
  }

  // ---------- Keyboard ----------
  input.addEventListener('keydown', (e) => {
    if (list.hidden || results.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((active + 1) % results.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((active - 1 + results.length) % results.length);
    } else if (e.key === 'Escape') {
      close();
    }
  });

  // Enter: pick the highlighted result, or the first one.
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    if (results.length > 0) choose(active >= 0 ? active : 0);
  });

  function setActive(i) {
    active = i;
    [...list.children].forEach((li, j) =>
      li.setAttribute('aria-selected', String(j === i)));
    input.setAttribute('aria-activedescendant', `search-result-${i}`);
  }

  // ---------- Open / close the list ----------
  function open() {
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
  }

  function close() {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
  }

  // Close when the user clicks somewhere else.
  input.addEventListener('blur', close);
}
