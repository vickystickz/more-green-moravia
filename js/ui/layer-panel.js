// =============================================================
// ui/layer-panel.js
// "Map layers" panel. Every layer has an eye button.
//
// Hexagon views (Green infrastructure need, Heat & people exposed,
// …) are different colourings of the SAME hexagons, so only one
// can be visible at a time:
//   - eye of a hidden view  → show that view (the others turn off)
//   - eye of the shown view → hide the hexagons completely
// Brownfields and vacant land, Microzone boundaries and Building
// switch on and off on their own.
// =============================================================

import { MAP_LAYERS, SCORE_CLASSES, HEX_OPACITY } from '../config.js';
import { t, percent, onLangChange } from './i18n.js';

function eyeButton(pressed) {
  const btn = document.createElement('button');
  btn.className = 'eye-btn';
  btn.type = 'button';
  btn.setAttribute('aria-pressed', String(pressed));
  const img = document.createElement('img');
  img.src = 'assets/icons/eye.svg';
  img.width = 12.6;
  img.height = 12.6;
  img.alt = '';
  btn.append(img);
  return btn;
}

/**
 * @param {{
 *   onLayer: (id: string|null) => void,  // null = hexagons hidden
 *   onBoundaries: (visible: boolean) => void,
 *   onBuildings: (visible: boolean) => void,
 *   onVacant: (visible: boolean) => void,
 *   onOpacity: (opacity: number) => void,  // 0–1
 * }} handlers
 * @returns {{ showBoundaryOption: () => void }}
 */
export function initLayerPanel({ onLayer, onBoundaries, onBuildings, onVacant, onOpacity }) {
  const group = document.getElementById('layer-choice');
  const legend = document.getElementById('legend');
  const legendTitle = document.getElementById('legend-title');

  // Legend boxes: one per class, with its range as a tooltip.
  const scale = document.getElementById('legend-scale');
  SCORE_CLASSES.forEach((c, i) => {
    const box = document.createElement('span');
    box.style.background = c.color;
    const to = SCORE_CLASSES[i + 1]?.from ?? 1;
    box.title = `${Math.round(c.from * 100)}–${Math.round(to * 100)}`;
    scale.append(box);
  });

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

  let active = MAP_LAYERS[0].id;
  const eyes = new Map();
  const names = new Map();

  // Legend labels under the colour boxes: Low / Medium / High, or
  // the layer's own (e.g. 0% … 100% for Sealed ground).
  const legendLabels = ['legend-low', 'legend-mid', 'legend-high'].map((id) => document.getElementById(id));
  const DEFAULT_LEGEND = ['legend.low', 'legend.medium', 'legend.high'];

  function draw() {
    eyes.forEach((btn, id) => btn.setAttribute('aria-pressed', String(id === active)));
    legend.hidden = active === null;
    opacityControl.hidden = active === null; // nothing to fade when hidden
    if (!active) return;
    const layer = MAP_LAYERS.find((l) => l.id === active);
    legendTitle.textContent = t(layer.label);
    const keys = layer.legend ?? DEFAULT_LEGEND;
    legendLabels.forEach((span, i) => { span.textContent = keys[i] ? t(keys[i]) : ''; });
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
      active = active === layer.id ? null : layer.id;
      draw();
      onLayer(active);
    });
    eyes.set(layer.id, eye);
    names.set(layer.id, name);
    row.append(name, eye);
    group.append(row);
  });
  translate();
  onLangChange(translate);

  // Independent on/off layers.
  function wireToggle(selector, onChange) {
    const eye = document.querySelector(selector);
    eye.addEventListener('click', () => {
      const visible = eye.getAttribute('aria-pressed') !== 'true';
      eye.setAttribute('aria-pressed', String(visible));
      onChange(visible);
    });
  }
  wireToggle('.eye-btn[data-layer="boundaries"]', onBoundaries);
  wireToggle('.eye-btn[data-layer="buildings"]', onBuildings);
  wireToggle('.eye-btn[data-layer="vacant"]', onVacant);

  return {
    showBoundaryOption() {
      document.getElementById('boundary-row').hidden = false;
    },
  };
}
