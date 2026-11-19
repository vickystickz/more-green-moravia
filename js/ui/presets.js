// =============================================================
// ui/presets.js
// Preset tiles: Balance, Cool street, Sponge city, Green roofs,
// Pocket parks, Quick wins. Picking a preset moves the weight
// sliders to that preset's values.
// =============================================================

// Slider values (0–100) and the explanation for each preset.
// TODO: agree the real values with the team; these are a start.
const PRESETS = {
  'balance': {
    title: 'Balance',
    text: 'Not sure yet? Each factors weighted equally.',
    values: { heat: 50, flood: 50, vulnerable: 50, greenDeficit: 50 },
  },
  'cool-street': {
    title: 'Cool street',
    text: 'Focus on the hottest streets first.',
    values: { heat: 90, flood: 20, vulnerable: 60, greenDeficit: 40 },
  },
  'sponge-city': {
    title: 'Sponge city',
    text: 'Focus on areas where rain water causes problems.',
    values: { heat: 20, flood: 90, vulnerable: 40, greenDeficit: 40 },
  },
  'green-roofs': {
    title: 'Green roofs',
    text: 'Dense built-up areas with little ground space for greenery.',
    values: { heat: 60, flood: 50, vulnerable: 30, greenDeficit: 80 },
  },
  'pocket-parks': {
    title: 'Pocket parks',
    text: 'Small green spaces where people lack nearby parks.',
    values: { heat: 40, flood: 20, vulnerable: 70, greenDeficit: 90 },
  },
  'quick-wins': {
    title: 'Quick wins',
    text: 'High impact areas that are easy to start with.',
    values: { heat: 60, flood: 60, vulnerable: 60, greenDeficit: 60 },
  },
};

/**
 * Wire up the preset tiles.
 *
 * @param {{ setValues: Function }} sliders - returned by initSliders()
 */
export function initPresets(sliders) {
  const tiles = [...document.querySelectorAll('.preset[data-preset]')];
  const note = document.getElementById('preset-note');

  tiles.forEach((tile) => {
    tile.addEventListener('click', () => {
      const preset = PRESETS[tile.dataset.preset];
      if (!preset) return;

      // Only the clicked tile is selected.
      tiles.forEach((t) => t.setAttribute('aria-pressed', String(t === tile)));

      // Update the explanation box (title in bold, then the text).
      note.innerHTML = '';
      const strong = document.createElement('strong');
      strong.textContent = `${preset.title}:`;
      note.append(strong, ` ${preset.text}`);

      // Move the sliders to this preset's values.
      sliders.setValues(preset.values);
    });
  });
}
