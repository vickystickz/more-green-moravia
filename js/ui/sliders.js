// =============================================================
// ui/sliders.js
// Weight sliders for heat, flood risk, vulnerable groups and
// green deficit.
//
// Each slider goes from 0 to 100. The percentage shown next to it
// is that factor's SHARE of the total, so the four always add up
// to 100% (e.g. all sliders equal → 25% each).
// =============================================================

const DEFAULT_VALUE = 50;

/**
 * Wire up the sliders and the Reset button.
 *
 * @param {(weights: Object<string, number>) => void} onChange
 *   called with the new weights (shares from 0 to 1) whenever a
 *   slider moves
 * @returns {{ setValues: (values: Object<string, number>) => void }}
 *   lets other modules (presets) move the sliders
 */
export function initSliders(onChange) {
  const sliders = [...document.querySelectorAll('.range[data-factor]')];

  // Read all sliders, update the labels and the green fill, then
  // tell the rest of the app about the new weights.
  function update() {
    const total = sliders.reduce((sum, s) => sum + Number(s.value), 0);
    const weights = {};

    sliders.forEach((slider) => {
      const factor = slider.dataset.factor;
      const value = Number(slider.value);

      // Share of the total; if every slider is at 0, share equally.
      const share = total === 0 ? 1 / sliders.length : value / total;
      weights[factor] = share;

      // Paint the green part of the track (see sliders.css).
      slider.style.setProperty('--value', value);

      // Show the share as a whole percentage.
      const output = document.querySelector(`[data-value-for="${factor}"]`);
      if (output) output.textContent = `${Math.round(share * 100)}%`;
    });

    onChange?.(weights);
  }

  // Update while dragging.
  sliders.forEach((slider) => slider.addEventListener('input', update));

  // Reset: every slider back to the middle.
  document.getElementById('reset-weights')
    .addEventListener('click', () => {
      sliders.forEach((slider) => { slider.value = DEFAULT_VALUE; });
      update();
    });

  // Draw the starting state.
  update();

  return {
    // Set several sliders at once, e.g. { heat: 80, flood: 20 }.
    setValues(values) {
      sliders.forEach((slider) => {
        const v = values[slider.dataset.factor];
        if (v !== undefined) slider.value = v;
      });
      update();
    },
  };
}
