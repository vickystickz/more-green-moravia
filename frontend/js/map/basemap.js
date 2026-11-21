// =============================================================
// map/basemap.js
// Switches the basemap between the light vector map (Positron)
// and the ČÚZK orthophoto of Czechia.
//
// We don't call map.setStyle(): that would remove our own data
// layers. Instead the orthophoto is a raster layer at the very
// bottom of the stack, and the Positron fills and lines are hidden
// while it is shown. Positron's labels (street and place names)
// stay on top, so the photo still reads as a map.
// =============================================================

import { BASEMAP_CONFIG } from '../config.js';
import { showBuildingLayer } from './buildings.js';

const ORTHO = 'ortho';

let orthoOn = false;
let buildingsWanted = true; // the "Building" eye in the Map layers panel

// Basemap layers that would cover the photo: the background and
// every fill / line drawn from the vector tiles. Labels (symbol
// layers) and our own GeoJSON layers are left alone.
function coveringLayers(map) {
  const sources = map.getStyle().sources;
  return map.getStyle().layers.filter((l) =>
    l.type === 'background' ||
    (l.type !== 'symbol' && sources[l.source]?.type === 'vector'));
}

const isBuilding = (l) => l['source-layer'] === 'building';

// Add the orthophoto the first time it is needed, so its tiles
// are only downloaded by people who switch to it.
function ensureOrtho(map) {
  if (map.getSource(ORTHO)) return;
  map.addSource(ORTHO, {
    type: 'raster',
    tiles: [BASEMAP_CONFIG.ortho.tiles],
    tileSize: 256,
    maxzoom: BASEMAP_CONFIG.ortho.maxzoom,
    attribution: BASEMAP_CONFIG.ortho.attribution,
  });
  map.addLayer(
    { id: ORTHO, type: 'raster', source: ORTHO },
    map.getStyle().layers[0]?.id // under everything else
  );
}

// The basemap's own building footprints are always hidden: the
// "Building" layer (map/buildings.js) replaces them.
function apply(map) {
  if (orthoOn) ensureOrtho(map);
  if (map.getLayer(ORTHO)) {
    map.setLayoutProperty(ORTHO, 'visibility', orthoOn ? 'visible' : 'none');
  }
  coveringLayers(map).forEach((l) => {
    const visible = !orthoOn && !isBuilding(l);
    map.setLayoutProperty(l.id, 'visibility', visible ? 'visible' : 'none');
  });
  showBuildingLayer(map, buildingsWanted); // shown on both basemaps
}

/** Is the orthophoto basemap shown? */
export function isOrthoOn() {
  return orthoOn;
}

/**
 * Show the orthophoto (true) or the light vector basemap (false).
 *
 * @param {maplibregl.Map} map
 * @param {boolean} on
 */
export function setOrthoBasemap(map, on) {
  orthoOn = on;
  if (map.isStyleLoaded()) apply(map);
  else map.once('load', () => apply(map));
}

/**
 * Show or hide the "Building" layer (buildings_with_class), on the
 * light basemap and on the orthophoto alike (the photo is always the
 * bottom layer, so the footprints are drawn on top of it).
 */
export function setBuildingsVisible(map, visible) {
  buildingsWanted = visible;
  const update = () => {
    map.getStyle().layers.filter(isBuilding)
      .forEach((l) => map.setLayoutProperty(l.id, 'visibility', 'none'));
    showBuildingLayer(map, visible);
  };
  if (map.isStyleLoaded()) update();
  else map.once('load', update);
}
