// =============================================================
// map/map.js
// Creates the MapLibre map.
// This file only sets up the base map. Our own buttons are wired
// in controls.js, and our data layers are added in layers.js.
// =============================================================

import { MAP_CONFIG } from '../config.js';

// `maplibregl` is a global variable created by the MapLibre
// <script> tag in index.html. It is loaded before our modules,
// so it is always available here.

/**
 * Create the map inside the given HTML element.
 *
 * @param {string} containerId - id of the element that holds the map
 * @returns {maplibregl.Map} the map instance
 */
export function initMap(containerId) {
  // 1. Create the map with the settings from config.js.
  const map = new maplibregl.Map({
    container: containerId,
    style: MAP_CONFIG.style,
    center: MAP_CONFIG.center,
    zoom: MAP_CONFIG.zoom,
    minZoom: MAP_CONFIG.minZoom,
    maxZoom: MAP_CONFIG.maxZoom,
    maxBounds: MAP_CONFIG.maxBounds,
    attributionControl: false, // added below in a compact form
  });

  // 2. No rotation: a rotated choropleth map is harder to read.
  //    (Zoom buttons are our own, styled from the design; see
  //    controls.js.)
  map.dragRotate.disable();
  map.touchZoomRotate.disableRotation();

  // 3. Scale bar. Required on a cartographic map so readers
  //    can judge distances.
  map.addControl(
    new maplibregl.ScaleControl({ maxWidth: 100, unit: 'metric' }),
    'bottom-right'
  );

  // 4. Attribution. The basemap licence requires that the data
  //    sources are credited. "compact" folds it into an (i) button.
  map.addControl(
    new maplibregl.AttributionControl({
      compact: true,
      // Credit for the search results (Mapy.com terms of use).
      customAttribution: 'Search © <a href="https://mapy.com" target="_blank" rel="noopener">Mapy.com</a>',
    }),
    'bottom-right'
  );

  // MapLibre opens the compact attribution at start. Fold it back
  // into the (i) button once the map loads, so it doesn't cover
  // the map; users can click (i) to read it.
  map.once('load', () => {
    map.getContainer()
      .querySelector('.maplibregl-ctrl-attrib')
      ?.classList.remove('maplibregl-compact-show');
  });

  return map;
}

/**
 * Wait until the map style has fully loaded.
 * Layers and sources can only be added after this point.
 *
 * @param {maplibregl.Map} map
 * @returns {Promise<void>} resolves when the map is ready,
 *   rejects if the basemap fails to load
 */
export function whenMapLoaded(map) {
  return new Promise((resolve, reject) => {
    // Already loaded (e.g. called a second time): continue at once.
    if (map.loaded()) {
      resolve();
      return;
    }

    map.once('load', () => resolve());

    // An error before 'load' usually means the basemap style
    // could not be fetched (no internet, wrong URL).
    map.once('error', (event) => {
      if (!map.loaded()) reject(event.error);
    });
  });
}
