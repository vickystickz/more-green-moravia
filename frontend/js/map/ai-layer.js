// =============================================================
// map/ai-layer.js
// "Show on map" for Ask AI answers: draws the hexagons or
// microzones one agent step found (a GeoJSON layer from the
// backend's POST /api/agent/map), coloured by their value with
// the rank on top, and zooms to them. One AI layer at a time.
// Steps about public buildings also send building outlines
// (properties.kind = 'building'): drawn in blue on top of their
// hexagons, without numbers.
// =============================================================

import { SCORE_CLASSES } from '../config.js';
import { num, t } from '../ui/i18n.js';

const SOURCE = 'ai-layer';
const FILL = 'ai-layer-fill';
const LINE = 'ai-layer-line';
const BUILDING_FILL = 'ai-layer-building-fill';
const BUILDING_LINE = 'ai-layer-building-line';
const LABEL = 'ai-layer-label';
const LAYERS = [FILL, LINE, BUILDING_FILL, BUILDING_LINE, LABEL];

const isBuilding = ['==', ['get', 'kind'], 'building'];
const notBuilding = ['!=', ['get', 'kind'], 'building'];

let popup = null;
let current = null; // the MapLayer on the map, or null

function firstLabelLayer(map) {
  return map.getStyle().layers.find((l) => l.type === 'symbol')?.id;
}

// Same five colours as the GI index, split at the layer's own
// legend breaks (score classes, or quantiles for raw values).
function colour(breaks) {
  const steps = [...new Set((breaks || []).filter(Number.isFinite))].sort((a, b) => a - b);
  const value = ['get', 'value'];
  const ramp = steps.length
    ? ['step', value, SCORE_CLASSES[0].color,
      ...steps.slice(0, 4).flatMap((b, i) => [b, SCORE_CLASSES[i + 1].color])]
    : SCORE_CLASSES[3].color;
  return ['case', ['==', ['typeof', value], 'number'], ramp, '#e6e6e6'];
}

function formatValue(value, unit) {
  if (typeof value !== 'number') return value ?? '–';
  const text = num(value, Number.isInteger(value) ? 0 : 1);
  return unit ? `${text} ${unit}` : text;
}

function addLayers(map) {
  const before = firstLabelLayer(map);
  map.addSource(SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
  map.addLayer({
    id: FILL,
    type: 'fill',
    source: SOURCE,
    filter: notBuilding,
    paint: { 'fill-color': '#e6e6e6', 'fill-opacity': 0.85 },
  }, before);
  map.addLayer({
    id: LINE,
    type: 'line',
    source: SOURCE,
    filter: notBuilding,
    paint: { 'line-color': '#18002C', 'line-width': 2 },
  }, before);
  // Public buildings: same blue as the "Public buildings" overlay.
  map.addLayer({
    id: BUILDING_FILL,
    type: 'fill',
    source: SOURCE,
    filter: isBuilding,
    paint: { 'fill-color': '#2F6FB3', 'fill-opacity': 0.9 },
  }, before);
  map.addLayer({
    id: BUILDING_LINE,
    type: 'line',
    source: SOURCE,
    filter: isBuilding,
    paint: { 'line-color': '#0B2F57', 'line-width': 1.5 },
  }, before);
  // Rank numbers on top of everything, basemap labels included.
  map.addLayer({
    id: LABEL,
    type: 'symbol',
    source: SOURCE,
    filter: ['all', ['has', 'rank'], notBuilding], // buildings are not numbered
    layout: {
      'text-field': ['to-string', ['get', 'rank']],
      'text-font': ['Noto Sans Regular'],
      'text-size': 13,
      'text-allow-overlap': false,
    },
    paint: { 'text-color': '#18002C', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
  });

  // Microzones have no detail card, so clicking one shows its value.
  // (A clicked hexagon already opens the detail card.)
  map.on('click', FILL, (e) => {
    if (!current || current.level !== 'microzone') return;
    const p = e.features?.[0]?.properties;
    if (!p) return;
    popup?.remove();
    const box = document.createElement('div');
    box.className = 'ai-layer-popup';
    const name = document.createElement('strong');
    name.textContent = `${p.rank ? `${p.rank}. ` : ''}${String(p.name).replace(/^Mikrozóna\s+/i, '')}`;
    const value = document.createElement('span');
    value.textContent = `${current.legend.label}: ${formatValue(p.value, current.legend.unit)}`;
    box.append(name, value);
    popup = new maplibregl.Popup({ closeButton: false, maxWidth: '240px' })
      .setLngLat(e.lngLat).setDOMContent(box).addTo(map);
  });
  map.on('mouseenter', FILL, () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', FILL, () => { map.getCanvas().style.cursor = ''; });

  // A building: its name (or type), roof area and roof shape.
  map.on('click', BUILDING_FILL, (e) => {
    const p = e.features?.[0]?.properties;
    if (!p) return;
    e.preventDefault();
    popup?.remove();
    const box = document.createElement('div');
    box.className = 'ai-layer-popup';
    const name = document.createElement('strong');
    const label = p.name || String(p.type || '').replace(/_/g, ' ');
    name.textContent = label;
    const roof = document.createElement('span');
    roof.textContent = [
      typeof p.roof_m2 === 'number' && t('askai.roofArea', { v: num(p.roof_m2) }),
      p.roof_shape === 'flat' && t('askai.flatRoof'),
    ].filter(Boolean).join(' · ');
    box.append(name, roof);
    popup = new maplibregl.Popup({ closeButton: false, maxWidth: '240px' })
      .setLngLat(e.lngLat).setDOMContent(box).addTo(map);
  });
  map.on('mouseenter', BUILDING_FILL, () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', BUILDING_FILL, () => { map.getCanvas().style.cursor = ''; });
}

/**
 * Draw one Ask AI map layer and zoom to it.
 *
 * @param {maplibregl.Map} map
 * @param {{ level: string, legend: Object, features: GeoJSON.FeatureCollection,
 *           bbox: number[] | null }} layer - the backend's MapLayer
 */
export function showAiLayer(map, layer) {
  if (!map.getSource(SOURCE)) addLayers(map);
  popup?.remove();
  current = layer;
  map.getSource(SOURCE).setData(layer.features);
  map.setPaintProperty(FILL, 'fill-color', colour(layer.legend?.breaks));
  LAYERS.forEach((id) => map.setLayoutProperty(id, 'visibility', 'visible'));

  if (layer.bbox) {
    const [w, s, e, n] = layer.bbox;
    map.fitBounds([[w, s], [e, n]], { padding: 60, maxZoom: 16, duration: 800 });
  }
}

/** Remove the Ask AI layer from the map. */
export function clearAiLayer(map) {
  popup?.remove();
  current = null;
  if (!map?.getSource(SOURCE)) return;
  map.getSource(SOURCE).setData({ type: 'FeatureCollection', features: [] });
  LAYERS.forEach((id) => map.setLayoutProperty(id, 'visibility', 'none'));
}
