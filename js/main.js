// =============================================================
// main.js
// Entry point of the app. Starts everything in the right order:
//   1. show the loader screen
//   2. set up the sidebar (presets + sliders)
//   3. create the map and load the data at the same time
//   4. hide the loader when the map is ready
// =============================================================

import { initMap, whenMapLoaded } from './map/map.js';
import { initMapControls } from './map/controls.js';
import { initSearch } from './ui/search.js';
import { loadMicrozones } from './data/fetch-data.js';
import { initSliders } from './ui/sliders.js';
import { initPresets } from './ui/presets.js';
import { showLoader, hideLoader, showLoaderError } from './ui/loader.js';
import { state } from './state.js';

async function init() {
  showLoader();

  // Sidebar controls work even before the map has loaded.
  const sliders = initSliders((weights) => {
    state.weights = weights;
    // TODO: recalculate scores and recolour the map.
  });
  initPresets(sliders);

  try {
    // Create the map (this returns straight away; the basemap
    // keeps loading in the background).
    const map = initMap('map');
    initMapControls(map);
    initSearch(map);

    // Start loading our data now, while the basemap loads.
    // If the file is missing we log a warning instead of failing,
    // so the map still shows. (data/processed/microzones.geojson
    // has not been created yet.)
    const zonesPromise = loadMicrozones().catch((err) => {
      console.warn('Microzone data not loaded:', err.message);
      return null;
    });

    // Wait for the basemap and the data together. Doing both at
    // once is faster than waiting for one and then the other.
    const [, zones] = await Promise.all([whenMapLoaded(map), zonesPromise]);

    // TODO: if `zones` loaded, add the microzone layer and render
    // the ranking list from it.

    hideLoader();
  } catch (err) {
    // Only the basemap failing ends up here.
    console.error(err);
    showLoaderError('Could not load the map. Please check your connection and reload.');
  }
}

init();
