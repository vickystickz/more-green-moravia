// =============================================================
// ui/layer-panel.js
// "Map layers" panel. Every layer has an eye button.
//
// Hexagon views (Green infrastructure need, Heat & people exposed,
// …) are different colourings of the SAME hexagons, so only one
// can be visible at a time:
//   - eye of a hidden view  → show that view (the others turn off)
//   - eye of the shown view → hide the hexagons completely
// The chosen view sits on top with its legend and opacity slider;
// the other views are listed under it, in MAP_LAYERS order.
// Brownfields and vacant land, Public buildings, Microzone
// boundaries and Building switch on and off on their own.
// =============================================================

import { MAP_LAYERS, SCORE_CLASSES, HEX_OPACITY } from '../config.js';
import { t, num, percent, onLangChange } from './i18n.js';

const EYE_ON = 'assets/icons/eye.svg';
const EYE_OFF = 'assets/icons/eye-off.svg';

/** Set an eye button on/off: aria-pressed + open or crossed-out eye. */
function setPressed(btn, pressed) {
  btn.setAttribute('aria-pressed', String(pressed));
  btn.querySelector('img').src = pressed ? EYE_ON : EYE_OFF;
}

function eyeButton(pressed) {
  const btn = document.createElement('button');
  btn.className = 'eye-btn';
  btn.type = 'button';
  const img = document.createElement('img');
  img.width = 12.6;
  img.height = 12.6;
  img.alt = '';
  btn.append(img);
  setPressed(btn, pressed);
  return btn;
}

/**
 * @param {{
 *   onLayer: (id: string|null) => void,  // null = hexagons hidden
 *   onBoundaries: (visible: boolean) => void,
 *   onBuildings: (visible: boolean) => void,
 *   onVacant: (visible: boolean) => void,
 *   onPublic: (visible: boolean) => void,
 *   onOpacity: (opacity: number) => void,  // 0–1
 * }} handlers
 * @returns {{ showBoundaryOption: () => void, hideAll: () => void, showDefault: () => void }}
 */
export function initLayerPanel({ onLayer, onBoundaries, onBuildings, onVacant, onPublic, onOpacity }) {
  const currentSlot = document.getElementById('layer-current-row');
  const others = document.getElementById('layer-choice');
  const legend = document.getElementById('legend');

  // Legend boxes: one per class, with its range as a tooltip. Redrawn
  // when the shown layer has its own colours (e.g. green vegetation).
  const scale = document.getElementById('legend-scale');
  let scaleClasses = null;
  function drawScale(classes) {
    if (classes === scaleClasses) return;
    scaleClasses = classes;
    scale.replaceChildren(...classes.map((c, i) => {
      const box = document.createElement('span');
      box.style.background = c.color;
      const to = classes[i + 1]?.from ?? 1;
      box.title = c.title ?? `${Math.round(c.from * 100)}–${Math.round(to * 100)}`;
      return box;
    }));
  }
  drawScale(SCORE_CLASSES);

  // Numbers at the class breaks (0, 20, … 100), each under the edge
  // between two boxes; the layer's unit goes on the last one.
  const ticks = document.getElementById('legend-ticks');
  function drawTicks(layer, classes) {
    const scaleBy = layer.tickScale ?? 100;
    const n = classes.length;
    const step = classes[n - 1].from - classes[n - 2].from;
    const values = [...classes.map((c) => c.from), classes[n - 1].from + step];
    ticks.replaceChildren(...values.map((v, i) => {
      const value = Math.round(v * scaleBy * 10) / 10;
      const last = i === values.length - 1;
      const span = document.createElement('span');
      span.style.left = `${(i / n) * 100}%`;
      span.textContent = last && layer.tickUnit === '%'
        ? percent(value)
        : `${num(value, Number.isInteger(value) ? 0 : 1)}${last && layer.tickUnit ? layer.tickUnit : ''}`;
      return span;
    }));
  }

  // Opacity slider: hexagon fill + legend boxes.
  const opacityControl = document.querySelector('.opacity-control');
  const opacityInput = document.getElementById('hex-opacity');
  const opacityValue = document.getElementById('hex-opacity-value');
  function setOpacity(value) {
    opacityInput.style.setProperty('--value', value); // green track fill
    opacityValue.textContent = percent(value);
    legend.style.setProperty('--hex-opacity', value / 100);
  }
  opacityInput.value = String(Math.round(HEX_OPACITY * 100));
  setOpacity(Number(opacityInput.value));
  opacityInput.addEventListener('input', () => {
    const value = Number(opacityInput.value);
    setOpacity(value);
    onOpacity(value / 100);
  });

  // `selected` = the view shown on top (stays there when hidden, so
  // the panel doesn't jump); `active` = the view on the map, or null.
  let selected = MAP_LAYERS[0].id;
  let active = selected;
  const rows = new Map();
  const eyes = new Map();
  const names = new Map();

  // Legend labels under the colour boxes: Low … High, or the
  // layer's own (e.g. 0% … 100% for Sealed ground).
  const legendLabels = ['legend-low', 'legend-mid', 'legend-high'].map((id) => document.getElementById(id));
  const DEFAULT_LEGEND = ['legend.low', null, 'legend.high'];
  // Grey box + text for hexes without a value (only some layers).
  const legendNote = document.getElementById('legend-note');
  const legendNoteText = document.getElementById('legend-note-text');

  function draw() {
    eyes.forEach((btn, id) => setPressed(btn, id === active));
    // Chosen view on top, the rest below in their usual order.
    currentSlot.replaceChildren(rows.get(selected));
    MAP_LAYERS.forEach((l) => { if (l.id !== selected) others.append(rows.get(l.id)); });

    legend.hidden = active === null;
    opacityControl.hidden = active === null; // nothing to fade when hidden
    if (!active) return;
    const layer = MAP_LAYERS.find((l) => l.id === active);
    drawScale(layer.classes ?? SCORE_CLASSES);
    drawTicks(layer, layer.classes ?? SCORE_CLASSES);
    const keys = layer.legend ?? DEFAULT_LEGEND;
    legendLabels.forEach((span, i) => { span.textContent = keys[i] ? t(keys[i]) : ''; });
    legendNote.hidden = !layer.note;
    legendNoteText.textContent = layer.note ? t(layer.note) : '';
  }

  // Text that JS wrote: redo it in the new language.
  function translate() {
    MAP_LAYERS.forEach((layer) => {
      const name = t(layer.label);
      names.get(layer.id).textContent = name;
      eyes.get(layer.id).setAttribute('aria-label', t('layers.showHide', { name }));
    });
    setOpacity(Number(opacityInput.value));
    draw();
  }

  MAP_LAYERS.forEach((layer) => {
    const row = document.createElement('div');
    row.className = 'layer-row';
    const name = document.createElement('span');
    name.className = 'layer-row__name';
    const eye = eyeButton(false);
    eye.addEventListener('click', () => {
      if (active === layer.id) {
        active = null;
      } else {
        active = selected = layer.id;
      }
      draw();
      onLayer(active);
    });
    rows.set(layer.id, row);
    eyes.set(layer.id, eye);
    names.set(layer.id, name);
    row.append(name, eye);
  });
  translate();
  onLangChange(translate);

  // Independent on/off layers.
  const toggles = [];
  function wireToggle(selector, onChange) {
    const eye = document.querySelector(selector);
    setPressed(eye, eye.getAttribute('aria-pressed') === 'true'); // right icon from the start
    toggles.push({ eye, onChange });
    eye.addEventListener('click', () => {
      const visible = eye.getAttribute('aria-pressed') !== 'true';
      setPressed(eye, visible);
      onChange(visible);
    });
  }
  wireToggle('.eye-btn[data-layer="boundaries"]', onBoundaries);
  wireToggle('.eye-btn[data-layer="buildings"]', onBuildings);
  wireToggle('.eye-btn[data-layer="vacant"]', onVacant);
  wireToggle('.eye-btn[data-layer="public"]', onPublic);

  return {
    showBoundaryOption() {
      document.getElementById('boundary-row').hidden = false;
    },
    // Turn every layer off (used when an Ask AI layer is drawn).
    hideAll() {
      if (active !== null) {
        active = null;
        draw();
        onLayer(null);
      }
      toggles.forEach(({ eye, onChange }) => {
        if (eye.getAttribute('aria-pressed') !== 'true') return;
        setPressed(eye, false);
        onChange(false);
      });
    },
    // Show the default view, Green infrastructure need (used when
    // an Ask AI layer is removed).
    showDefault() {
      const id = MAP_LAYERS[0].id;
      if (active === id) return;
      active = selected = id;
      draw();
      onLayer(active);
    },
  };
}
