// =============================================================
// map/buildings.js
// The "Building" layer: footprints from buildings_with_class
// (data/olomouc_buildings.geojson), in the same style as the
// public buildings of an Ask AI answer (BUILDING_STYLE).
//
// The file is fetched the first time the layer is shown. The
// footprints are drawn on top of the hexagons and overlays (under
// the basemap's street and place names); clicks still reach the
// hexagons underneath.
// =============================================================

import { DATA_PATHS, BUILDING_STYLE } from '../config.js';

const SOURCE = 'buildings';
const FILL = 'buildings-fill';
const LINE = 'buildings-line';

let wanted = false;
let loading = null;

function firstLabelLayer(map) {
  return map.getStyle().layers.find((l) => l.type === 'symbol')?.id;
}

async function addLayers(map) {
  const res = await fetch(DATA_PATHS.buildings);
  if (!res.ok) throw new Error(`Could not load ${DATA_PATHS.buildings} (${res.status})`);
  const data = await res.json();
  if (map.getSource(SOURCE)) return;
  // On top of our data layers, under the labels.
  const before = firstLabelLayer(map);
  const visibility = wanted ? 'visible' : 'none';
  map.addSource(SOURCE, { type: 'geojson', data });
  map.addLayer({
    id: FILL,
    type: 'fill',
    source: SOURCE,
    layout: { visibility },
    paint: { 'fill-color': BUILDING_STYLE.fill, 'fill-opacity': BUILDING_STYLE.fillOpacity },
  }, before);
  map.addLayer({
    id: LINE,
    type: 'line',
    source: SOURCE,
    layout: { visibility },
    // Thinner when zoomed out, so the city doesn't turn dark.
    paint: {
      'line-color': BUILDING_STYLE.line,
      'line-width': ['interpolate', ['linear'], ['zoom'], 13, 0.3, 16, BUILDING_STYLE.lineWidth],
    },
  }, before);
}

/**
 * Layer id to insert other data layers before, so the building
 * footprints stay on top of them (or the first label layer when the
 * buildings are not loaded yet).
 */
export function underBuildings(map) {
  return map.getLayer(LINE) && map.getLayer(FILL) ? FILL : firstLabelLayer(map);
}

/** Show or hide the building footprints (loads them the first time). */
export function showBuildingLayer(map, visible) {
  wanted = visible;
  if (map.getSource(SOURCE)) {
    [FILL, LINE].forEach((id) => map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none'));
    return;
  }
  if (!visible || loading) return;
  loading = addLayers(map).catch((err) => {
    console.warn('Building layer not loaded:', err.message);
    loading = null; // try again next time
  });
}
