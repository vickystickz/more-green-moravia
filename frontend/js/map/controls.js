// =============================================================
// map/controls.js
// Connects the buttons that float on the map (designed in Figma)
// to the MapLibre map: home, zoom, my location, and the map
// layers panel open / close.
// =============================================================

import { MAP_CONFIG } from '../config.js';

/**
 * Wire up all map buttons.
 *
 * @param {maplibregl.Map} map
 */
export function initMapControls(map) {
  // ---------- Home ----------
  // Fly back to the starting view (centre and zoom from config.js).
  document.getElementById('btn-home')
    .addEventListener('click', () => {
      map.flyTo({
        center: MAP_CONFIG.center,
        zoom: MAP_CONFIG.zoom,
        bearing: 0,
        pitch: 0,
      });
    });

  // ---------- Zoom in / out ----------
  document.getElementById('btn-zoom-in')
    .addEventListener('click', () => map.zoomIn());

  document.getElementById('btn-zoom-out')
    .addEventListener('click', () => map.zoomOut());

  // ---------- My location ----------
  // Asks the browser for the user's position and flies there.
  // Browsers only allow this on https:// or localhost.
  document.getElementById('btn-locate')
    .addEventListener('click', () => {
      if (!('geolocation' in navigator)) return;

      navigator.geolocation.getCurrentPosition(
        (pos) => {
          map.flyTo({
            center: [pos.coords.longitude, pos.coords.latitude],
            zoom: 15,
          });
        },
        (err) => console.warn('Location not available:', err.message)
      );
    });

  // ---------- Basemap switch ----------
  // TODO: switch between the light basemap and satellite imagery.
  document.getElementById('btn-basemap')
    .addEventListener('click', () => {
      console.info('Basemap switch not built yet.');
    });

  // ---------- Map layers panel: open / close ----------
  const toggle = document.getElementById('layers-toggle');
  const body = document.getElementById('layers-body');

  toggle.addEventListener('click', () => {
    const isOpen = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', String(!isOpen));
    body.hidden = isOpen; // hide when it was open, show when closed
  });
}
