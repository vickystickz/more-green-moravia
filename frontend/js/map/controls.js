// =============================================================
// map/controls.js
// Connects the buttons that float on the map (designed in Figma)
// to the MapLibre map: home, zoom, my location, and the map
// layers panel open / close.
// =============================================================

import { MAP_CONFIG } from '../config.js';
import { isOrthoOn, setOrthoBasemap } from './basemap.js';

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
  // Toggles between the light basemap and the ČÚZK orthophoto.
  // aria-pressed = true while the orthophoto is shown.
  const basemapBtn = document.getElementById('btn-basemap');
  basemapBtn.setAttribute('aria-pressed', 'false');
  basemapBtn.addEventListener('click', () => {
    const on = !isOrthoOn();
    setOrthoBasemap(map, on);
    basemapBtn.setAttribute('aria-pressed', String(on));
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
