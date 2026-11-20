// =============================================================
// ui/presets.js
// Preset tiles. A preset sets the three weights and the
// "Only show places we can build" toggle in one click.
// Green roofs needs building energy data, so it is shown but
// disabled for now.
//
// The words (title, short text, tooltip explanation) are in
// data/lang/*.json under preset.<id>.title / .text / .explain.
// =============================================================

import { t, onLangChange } from './i18n.js';

const third = 1 / 3;
const BALANCE = { he: third, v: third, gd: third };

export const PRESETS = {
  'balance': { weights: BALANCE, onlyBuildable: false },
  'cool-street': { weights: { he: 0.5, v: 0.2, gd: 0.3 }, onlyBuildable: false },
  'protect-vulnerable': { weights: { he: 0.3, v: 0.5, gd: 0.2 }, onlyBuildable: false },
  'pocket-parks': { weights: { he: 0.2, v: 0.4, gd: 0.4 }, onlyBuildable: false },
  'quick-wins': { weights: BALANCE, onlyBuildable: true },
};

// Shown but not clickable yet (tooltip text only).
export const COMING_SOON = ['green-roofs'];

/**
 * Wire up the preset tiles and the Reset button.
 *
 * @param {(preset: { weights: Object, onlyBuildable: boolean }) => void} apply
 *   sets the weights and the toggle, then redraws
 * @returns {{ markCustom: () => void }} call when the user moves a
 *   slider by hand, so no preset looks selected
 */
export function initPresets(apply) {
  const tiles = [...document.querySelectorAll('.preset[data-preset]')];
  const note = document.getElementById('preset-note');
  let current = 'balance'; // preset id, or 'custom'

  function drawNote() {
    note.innerHTML = '';
    const strong = document.createElement('strong');
    strong.textContent = `${t(`preset.${current}.title`)}:`;
    note.append(strong, ` ${t(`preset.${current}.text`)}`);
  }

  function select(id) {
    const preset = PRESETS[id];
    if (!preset) return;
    current = id;
    tiles.forEach((tile) => tile.setAttribute('aria-pressed', String(tile.dataset.preset === id)));
    drawNote();
    apply(preset);
  }

  tiles.forEach((tile) => {
    tile.addEventListener('click', () => {
      // "Limited data" presets are visible but do nothing yet.
      if (tile.getAttribute('aria-disabled') === 'true') return;
      select(tile.dataset.preset);
    });
  });

  // Reset = Balance weights, toggle off.
  document.getElementById('reset-weights')
    .addEventListener('click', () => select('balance'));

  drawNote();
  onLangChange(drawNote);

  return {
    markCustom() {
      current = 'custom';
      tiles.forEach((tile) => tile.setAttribute('aria-pressed', 'false'));
      drawNote();
    },
  };
}
