// =============================================================
// map/ai-layer.js
// "Show on map" for Ask AI answers: draws the hexagons or
// microzones one agent step found (a GeoJSON layer from the
// backend's POST /api/agent/map), coloured by their value with
// the rank on top, and zooms to them. One AI layer at a time.
// Steps about public buildings also send building outlines
// (properties.kind = 'building'): drawn in light grey on top of their
// hexagons, without numbers.
// =============================================================

import { SCORE_CLASSES, BUILDING_STYLE } from '../config.js';
import { num, t } from '../ui/i18n.js';
import { underBuildings } from './buildings.js';

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
  const before = underBuildings(map); // the Building layer stays on top
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
  // Public building footprints: light fill with a dark outline.
  map.addLayer({
    id: BUILDING_FILL,
    type: 'fill',
    source: SOURCE,
    filter: isBuilding,
    paint: { 'fill-color': BUILDING_STYLE.fill, 'fill-opacity': BUILDING_STYLE.fillOpacity },
  }, before);
  map.addLayer({
    id: BUILDING_LINE,
    type: 'line',
    source: SOURCE,
    filter: isBuilding,
    paint: { 'line-color': BUILDING_STYLE.line, 'line-width': BUILDING_STYLE.lineWidth },
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
    box.append(name, roof, ...costLines(p, current?.costs));
    popup = new maplibregl.Popup({ closeButton: false, maxWidth: '360px' })
      .setLngLat(e.lngLat).setDOMContent(box).addTo(map);
  });
  map.on('mouseenter', BUILDING_FILL, () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', BUILDING_FILL, () => { map.getCanvas().style.cursor = ''; });
}

// Green roof estimate for a building popup, as a small table in the
// Ask AI answer style (.ask-ai-table): set-up (one-off) and upkeep
// (per year) = roof area x the backend's rates per m², plus the rate
// itself, then links to the sources of those rates (layer.costs).
// Nothing when the backend sent no costs.
//
//                 About (CZK)  Range (CZK)            CZK/m²
//   Set-up        1,750,000    1,000,000–2,500,000    1,750
//   Upkeep a year    30,500       12,200–48,800       30.48
function costLines(p, costs) {
  if (!costs || typeof p.install_avg !== 'number') return [];
  const c = t('askai.currency');
  const cell = (tag, text) => {
    const el = document.createElement(tag);
    el.textContent = text;
    return el;
  };
  const row = (labelKey, prefix, rate) => {
    const per = rate?.per_m2;
    const d = per && per.avg < 100 ? 2 : 0; // small rates (upkeep) keep two decimals
    const tr = document.createElement('tr');
    tr.append(
      cell('th', t(labelKey)),
      cell('td', num(p[`${prefix}_avg`])),
      cell('td', `${num(p[`${prefix}_min`])}–${num(p[`${prefix}_max`])}`),
      cell('td', per ? num(per.avg, d) : '–'),
    );
    return tr;
  };

  const title = document.createElement('span');
  title.className = 'ai-layer-popup__title';
  title.textContent = t('askai.costTitle');

  const wrap = document.createElement('div');
  wrap.className = 'ask-ai-table ai-layer-popup__table';
  const table = document.createElement('table');
  const head = document.createElement('tr');
  head.append(
    cell('th', ''),
    cell('th', t('askai.costAbout', { c })),
    cell('th', t('askai.costRange', { c })),
    cell('th', t('askai.costPerM2', { c })),
  );
  const thead = document.createElement('thead');
  thead.append(head);
  const tbody = document.createElement('tbody');
  tbody.append(
    row('askai.costRowSetup', 'install', costs.install),
    row('askai.costRowUpkeep', 'maint', costs.maintenance),
  );
  table.append(thead, tbody);
  wrap.append(table);

  const sources = document.createElement('span');
  sources.className = 'ai-layer-popup__sources';
  sources.append(t('askai.costSources'), ' ');
  [[costs.install, 'askai.costSourceSetup'], [costs.maintenance, 'askai.costSourceUpkeep']]
    .filter(([rate]) => rate?.url)
    .forEach(([rate, key], i) => {
      if (i) sources.append(' · ');
      const link = document.createElement('a');
      link.href = rate.url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = t(key);
      link.title = rate.source; // full source name on hover
      sources.append(link);
    });

  return [title, wrap, sources];
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
