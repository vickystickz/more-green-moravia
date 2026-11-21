// =============================================================
// main.js
// Entry point of the app. Starts everything in the right order:
//   1. show the loader screen
//   2. set up the sidebar (presets, sliders, toggle)
//   3. create the map and load the data at the same time
//   4. add the hexagons, run the self-test, draw the list
//   5. hide the loader
// Every slider, preset or toggle change calls refresh(), which
// rescores all hexes and redraws the map, list and detail card.
// =============================================================

import { initMap, whenMapLoaded } from './map/map.js';
import { initMapControls } from './map/controls.js';
import {
  addHexLayer, updateHexValues, setColourKey, highlightHex,
  addBoundaryLayer, setBoundariesVisible, setBuildingsVisible, setHexesVisible,
  setVacantVisible, setPublicVisible,
  setHexOpacity,
} from './map/layers.js';
import { initSearch } from './ui/search.js';
import { loadHexes, loadMetadata, loadBoundaries } from './data/fetch-data.js';
import { paramsFromMetadata, dimensions, shownScore, selfTest } from './scoring/score.js';
import { initSliders, toPercents } from './ui/sliders.js';
import { initPresets } from './ui/presets.js';
import { initPresetTooltip } from './ui/preset-tooltip.js';
import { initInfoTooltip } from './ui/info-tooltip.js';
import { renderRanking } from './ui/ranking.js';
import { initDetail, renderDetail } from './ui/detail.js';
import { initLayerPanel } from './ui/layer-panel.js';
import { initAskAi } from './ui/ask-ai.js';
import { showLoader, hideLoader, showLoaderError } from './ui/loader.js';
import { initI18n, initLangSwitch, onLangChange, t, percent } from './ui/i18n.js';
import { MAP_LAYERS } from './config.js';
import { state } from './state.js';

let map = null;

// ---------- Helpers ----------

// "Mikrozóna Kosmonautů" → "Kosmonautů"
function displayName(mzId) {
  if (!mzId) return t('area.unnamed');
  return String(mzId).replace(/^Mikrozóna\s+/i, '');
}

// Lower case, no accents: "Křenovice" and "krenovice" match.
const normalize = (text) =>
  text.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();

// Centre and bounding box of a (Multi)Polygon, from its vertices.
function geometryInfo(geometry) {
  const rings = geometry.type === 'MultiPolygon'
    ? geometry.coordinates.map((poly) => poly[0])
    : [geometry.coordinates[0]];
  const points = rings.flatMap((ring) => ring.slice(0, -1)); // drop closing point
  let sx = 0; let sy = 0;
  let w = Infinity; let s = Infinity; let e = -Infinity; let n = -Infinity;
  for (const [x, y] of points) {
    sx += x; sy += y;
    w = Math.min(w, x); e = Math.max(e, x);
    s = Math.min(s, y); n = Math.max(n, y);
  }
  return { center: [sx / points.length, sy / points.length], bbox: [w, s, e, n] };
}

const findHex = (id) => state.hexes.find((h) => h.id === id) ?? null;

// ---------- Redraw everything ----------

function refresh() {
  for (const h of state.hexes) {
    h.score = shownScore(h.dims, state.weights, state.onlyBuildable);
  }
  if (map) updateHexValues(map, state.hexes);
  renderRanking(state.hexes, state.selectedHex, (id) => selectHex(id, true));
  renderDetail(findHex(state.selectedHex), {
    onlyBuildable: state.onlyBuildable,
    weightLabels: Object.fromEntries(
      Object.entries(toPercents(state.weights)).map(([k, v]) => [k, percent(v)])),
  });
}

function selectHex(id, fly = false) {
  state.selectedHex = id;
  if (map) {
    highlightHex(map, id);
    const hex = findHex(id);
    if (fly && hex) map.flyTo({ center: hex.center, zoom: Math.max(map.getZoom(), 15) });
  }
  refresh();
}

// Microzones whose name matches the search text, best hex first.
function searchMicrozones(query) {
  const q = normalize(query);
  if (!q) return [];
  const zones = new Map();
  for (const h of state.hexes) {
    if (!normalize(h.name).includes(q)) continue;
    const z = zones.get(h.name);
    if (!z) {
      zones.set(h.name, { best: h, bbox: [...h.bbox] });
    } else {
      if (h.score > z.best.score) z.best = h;
      z.bbox = [
        Math.min(z.bbox[0], h.bbox[0]), Math.min(z.bbox[1], h.bbox[1]),
        Math.max(z.bbox[2], h.bbox[2]), Math.max(z.bbox[3], h.bbox[3]),
      ];
    }
  }
  return [...zones.entries()]
    // Names that start with the query first, then alphabetical.
    .sort(([a], [b]) =>
      Number(!normalize(a).startsWith(q)) - Number(!normalize(b).startsWith(q))
      || a.localeCompare(b, 'cs'))
    .slice(0, 4)
    .map(([name, z]) => ({
      name,
      label: t('search.microzone'),
      location: 'Olomouc',
      center: z.best.center,
      bbox: z.bbox,
      onPick: () => selectHex(z.best.id),
    }));
}

// ---------- Start ----------

async function init() {
  showLoader();

  // Load the EN / CS texts first, so everything below is drawn in
  // the right language from the start.
  await initI18n();
  initLangSwitch();

  // Sidebar controls work even before the map has loaded.
  const toggle = document.getElementById('only-buildable');

  const presets = initPresets((preset) => {
    state.weights = { ...preset.weights };
    state.onlyBuildable = preset.onlyBuildable;
    sliders.set(state.weights);
    toggle.checked = state.onlyBuildable;
    refresh();
  });

  initPresetTooltip();
  initInfoTooltip();

  const sliders = initSliders(state.weights, (weights) => {
    state.weights = weights;
    presets.markCustom();
    refresh();
  });

  toggle.addEventListener('change', () => {
    state.onlyBuildable = toggle.checked;
    refresh();
  });

  // New language: redraw the text that JS wrote (sliders, list,
  // detail card). HTML text is already done by i18n.js.
  onLangChange(() => {
    sliders.set(state.weights);
    refresh();
  });

  initDetail(() => {
    state.selectedHex = null;
    if (map) highlightHex(map, null);
    refresh();
  });
  // Drawing an Ask AI layer switches the other map layers off;
  // removing it brings back Green infrastructure need.
  let panel = null;
  initAskAi(() => map, {
    onMapLayer: () => panel?.hideAll(),
    onMapLayerCleared: () => panel?.showDefault(),
  });

  try {
    // Create the map (this returns straight away; the basemap
    // keeps loading in the background).
    map = initMap('map');
    initMapControls(map);
    initSearch(map, searchMicrozones);

    panel = initLayerPanel({
      // id = view to colour the hexagons by, or null = hide them
      onLayer: (id) => {
        state.activeLayer = id;
        setHexesVisible(map, id !== null);
        if (id) {
          const layer = MAP_LAYERS.find((l) => l.id === id);
          setColourKey(map, layer.key, layer.classes);
        }
      },
      onBoundaries: (visible) => setBoundariesVisible(map, visible),
      onBuildings: (visible) => setBuildingsVisible(map, visible),
      onVacant: (visible) => setVacantVisible(map, visible),
      onPublic: (visible) => setPublicVisible(map, visible),
      onOpacity: (opacity) => setHexOpacity(map, opacity),
    });

    // Load the data while the basemap loads. If the hex file is
    // missing we log a warning, so the map still shows.
    const hexesPromise = loadHexes().catch((err) => {
      console.warn('GI index data not loaded:', err.message);
      return null;
    });

    const [, hexes, meta, boundaries] = await Promise.all([
      whenMapLoaded(map), hexesPromise, loadMetadata(), loadBoundaries(),
    ]);

    if (hexes) {
      const params = paramsFromMetadata(meta);
      state.hexes = hexes.features
        .filter((f) => f.properties?.h3_index && f.geometry)
        .map((f) => ({
          id: f.properties.h3_index,
          name: displayName(f.properties.mz_id),
          props: f.properties,
          dims: dimensions(f.properties, params),
          score: null,
          ...geometryInfo(f.geometry),
        }));

      selfTest(state.hexes);
      addHexLayer(map, hexes, (id) => selectHex(id));
    }

    // After the hexagons, so the outlines are drawn on top of them.
    if (boundaries) {
      addBoundaryLayer(map, boundaries);
      panel.showBoundaryOption();
    }

    refresh();
    hideLoader();
  } catch (err) {
    // Only the basemap failing ends up here.
    console.error(err);
    showLoaderError('loader.error');
  }
}

init();
