// =============================================================
// ui/sliders.js
// Weight sliders for the three INFORM dimensions:
//   he = Heat & people exposed, v = Vulnerable groups,
//   gd = Lack of green.
//
// Rules:
//   - the three weights always add up to 100%
//   - moving one slider rescales the other two proportionally
//   - no weight goes below MIN_WEIGHT (10%), because a weight of 0
//     would drop that dimension out of the multiplicative formula
// =============================================================

import { FACTORS, MIN_WEIGHT } from '../config.js';
import { percent } from './i18n.js';

const MAX_WEIGHT = 1 - MIN_WEIGHT * (FACTORS.length - 1); // 80%

/**
 * Rescale the other weights after `factor` was set to `value`.
 *
 * @param {Object<string, number>} weights - current, sum to 1
 * @returns {Object<string, number>} new weights, sum to 1
 */
export function rebalance(weights, factor, value) {
  const v = Math.min(Math.max(value, MIN_WEIGHT), MAX_WEIGHT);
  const others = FACTORS.filter((f) => f !== factor);
  const rest = 1 - v;
  const oldSum = others.reduce((s, f) => s + weights[f], 0);

  const next = { [factor]: v };
  others.forEach((f) => {
    next[f] = oldSum > 0 ? (rest * weights[f]) / oldSum : rest / others.length;
  });

  // Keep the minimum: lift any weight below it and take the
  // difference from the other one (only two others, so this is exact).
  const [a, b] = others;
  if (next[a] < MIN_WEIGHT) { next[a] = MIN_WEIGHT; next[b] = rest - MIN_WEIGHT; }
  if (next[b] < MIN_WEIGHT) { next[b] = MIN_WEIGHT; next[a] = rest - MIN_WEIGHT; }
  return next;
}

/**
 * Whole percentages for display that add up to 100 (largest
 * remainder). Equal weights show 33 / 33 / 33, like the Balance
 * preset is usually described.
 */
export function toPercents(weights) {
  const values = FACTORS.map((f) => weights[f] * 100);
  if (values.every((x) => Math.abs(x - values[0]) < 1e-9)) {
    return Object.fromEntries(FACTORS.map((f) => [f, Math.round(values[0])]));
  }
  const floors = values.map(Math.floor);
  let left = 100 - floors.reduce((s, x) => s + x, 0);
  values
    .map((x, i) => [x - floors[i], i])
    .sort((p, q) => q[0] - p[0])
    .forEach(([, i]) => { if (left > 0) { floors[i] += 1; left -= 1; } });
  return Object.fromEntries(FACTORS.map((f, i) => [f, floors[i]]));
}

/**
 * Wire up the sliders.
 *
 * @param {Object<string, number>} initial - starting weights
 * @param {(weights: Object<string, number>) => void} onInput -
 *   called when the user drags a slider
 * @returns {{ set: (weights: Object<string, number>) => void }}
 *   moves the sliders without calling onInput (used by presets)
 */
export function initSliders(initial, onInput) {
  const sliders = Object.fromEntries(
    [...document.querySelectorAll('.range[data-factor]')]
      .map((el) => [el.dataset.factor, el]));
  let weights = { ...initial };

  function draw() {
    const pct = toPercents(weights);
    FACTORS.forEach((f) => {
      const slider = sliders[f];
      if (!slider) return;
      slider.value = String(Math.round(weights[f] * 100));
      // Paint the green part of the track up to the knob (see
      // sliders.css). The slider runs from min to max, not 0–100.
      const min = Number(slider.min);
      const max = Number(slider.max);
      const fill = ((Number(slider.value) - min) / (max - min)) * 100;
      slider.style.setProperty('--value', fill);
      const output = document.querySelector(`[data-value-for="${f}"]`);
      if (output) output.textContent = percent(pct[f]);
    });
  }

  Object.entries(sliders).forEach(([factor, slider]) => {
    slider.addEventListener('input', () => {
      weights = rebalance(weights, factor, Number(slider.value) / 100);
      draw();
      onInput({ ...weights });
    });
  });

  draw();

  return {
    set(next) {
      weights = { ...next };
      draw();
    },
  };
}
