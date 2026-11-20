// =============================================================
// map/layers.js
// Adds the GI index hexagons to the map and recolours them.
//
// The scores live in MapLibre "feature state" (keyed by h3_index),
// not in the GeoJSON itself. Updating feature state for ~500 hexes
// is much faster than re-sending the whole GeoJSON, so the map
// keeps up while a slider is being dragged.
// =============================================================

import { SCORE_CLASSES, HEX_OPACITY } from '../config.js';

const SOURCE = 'gi-hexes';
const FILL = 'gi-hexes-fill';
const OUTLINE = 'gi-hexes-outline';
const SELECTED = 'gi-hexes-selected';
const VACANT = 'gi-hexes-vacant';
const BOUNDARY_SOURCE = 'microzones';
const BOUNDARY_LAYER = 'microzones-line';

// Colour expression for one feature-state value: each class gets
// one flat colour ('step'). Hexes without a value are light grey.
function colourBy(key) {
  const value = ['feature-state', key];
  return [
    'case',
    ['==', ['typeof', value], 'number'],
    ['step', value, SCORE_CLASSES[0].color,
      ...SCORE_CLASSES.slice(1).flatMap((c) => [c.from, c.color])],
    '#e6e6e6',
  ];
}

// "Brownfields and vacant land" overlay: hexes where at least 5 %
// is brownfield or vacant land / construction site.
const VACANT_FROM = 0.05;
const vacantShare = ['+',
  ['coalesce', ['get', 'raw_brownfield_share'], 0],
  ['coalesce', ['get', 'raw_vacant_share'], 0]];
let vacantVisible = false; // off by default; kept if toggled before the data loads

// Put our layers under the basemap's first label layer, so street
// and place names stay readable on top of the colours.
function firstLabelLayer(map) {
  return map.getStyle().layers.find((l) => l.type === 'symbol')?.id;
}

/**
 * Add the hexagon source and layers.
 *
 * @param {maplibregl.Map} map
 * @param {GeoJSON.FeatureCollection} geojson
 * @param {(h3: string) => void} onClick - called with the clicked hex id
 */
export function addHexLayer(map, geojson, onClick) {
  const before = firstLabelLayer(map);

  map.addSource(SOURCE, {
    type: 'geojson',
    data: geojson,
    promoteId: 'h3_index', // feature-state is keyed by h3_index
  });

  map.addLayer({
    id: FILL,
    type: 'fill',
    source: SOURCE,
    paint: {
      'fill-color': colourBy('score'),
      'fill-opacity': HEX_OPACITY,
    },
  }, before);

  map.addLayer({
    id: OUTLINE,
    type: 'line',
    source: SOURCE,
    paint: { 'line-color': '#ffffff', 'line-width': 0.5, 'line-opacity': 0.8 },
  }, before);

  // Brownfields and vacant land: thick dark outline on top of the
  // colours, under the selection outline.
  map.addLayer({
    id: VACANT,
    type: 'line',
    source: SOURCE,
    filter: ['>=', vacantShare, VACANT_FROM],
    layout: { visibility: vacantVisible ? 'visible' : 'none' },
    paint: { 'line-color': '#1F1F1F', 'line-width': 2.5 },
  }, before);

  // Thick dark outline around the selected hex.
  map.addLayer({
    id: SELECTED,
    type: 'line',
    source: SOURCE,
    filter: ['==', ['get', 'h3_index'], ''],
    paint: { 'line-color': '#3A3A3A', 'line-width': 2.5 },
  }, before);

  map.on('click', FILL, (e) => {
    const id = e.features?.[0]?.properties?.h3_index;
    if (id) onClick(id);
  });
  map.on('mouseenter', FILL, () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', FILL, () => { map.getCanvas().style.cursor = ''; });
}

/**
 * Write the current values of every hex into feature state.
 *
 * @param {maplibregl.Map} map
 * @param {Array<{ id: string, score: number, dims: Object }>} hexes
 */
export function updateHexValues(map, hexes) {
  if (!map.getSource(SOURCE)) return;
  for (const h of hexes) {
    map.setFeatureState(
      { source: SOURCE, id: h.id },
      {
        score: h.score, he: h.dims.he, v: h.dims.v, gd: h.dims.gd, feas: h.dims.feas,
        night: h.props.mu_heatwave_tmin, // Night-time heat (raw 0–1 membership)
      },
    );
  }
}

/** Colour the map by another value (score, he, night, v, gd or feas). */
export function setColourKey(map, key) {
  if (map.getLayer(FILL)) map.setPaintProperty(FILL, 'fill-color', colourBy(key));
}

/** Opacity of the hexagon colours, 0–1. */
export function setHexOpacity(map, opacity) {
  if (map.getLayer(FILL)) map.setPaintProperty(FILL, 'fill-opacity', opacity);
}

/** Outline one hex (or none with null). */
export function highlightHex(map, h3) {
  if (map.getLayer(SELECTED)) {
    map.setFilter(SELECTED, ['==', ['get', 'h3_index'], h3 ?? '']);
  }
}

/** Show or hide all hexagons (fill, outline and selection). */
export function setHexesVisible(map, visible) {
  [FILL, OUTLINE, SELECTED].forEach((id) => {
    if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
  });
}

/** Show or hide the "Brownfields and vacant land" overlay. */
export function setVacantVisible(map, visible) {
  vacantVisible = visible;
  if (map.getLayer(VACANT)) map.setLayoutProperty(VACANT, 'visibility', visible ? 'visible' : 'none');
}

/**
 * Optional microzone outlines (dashed dark lines), visible at start.
 * Added after the hexagons so the outlines are drawn ON TOP of them
 * (still under the basemap's place names).
 */
export function addBoundaryLayer(map, geojson) {
  map.addSource(BOUNDARY_SOURCE, { type: 'geojson', data: geojson });
  map.addLayer({
    id: BOUNDARY_LAYER,
    type: 'line',
    source: BOUNDARY_SOURCE,
    paint: { 'line-color': '#3A3A3A', 'line-width': 1.2, 'line-dasharray': [2, 1.5] },
  }, firstLabelLayer(map));
}

export function setBoundariesVisible(map, visible) {
  if (map.getLayer(BOUNDARY_LAYER)) {
    map.setLayoutProperty(BOUNDARY_LAYER, 'visibility', visible ? 'visible' : 'none');
  }
}

/** Show or hide the basemap's building footprints. */
export function setBuildingsVisible(map, visible) {
  map.getStyle().layers
    .filter((l) => l['source-layer'] === 'building')
    .forEach((l) => map.setLayoutProperty(l.id, 'visibility', visible ? 'visible' : 'none'));
}
