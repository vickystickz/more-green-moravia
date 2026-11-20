// =============================================================
// ui/preset-tooltip.js
// Custom tooltip for the preset tiles. On hover or keyboard focus
// it explains what clicking the preset does: in plain words, the
// three weights it sets, and whether "Only show places we can
// build" is switched on.
// =============================================================

import { PRESETS, COMING_SOON } from './presets.js';
import { toPercents } from './sliders.js';
import { t, percent } from './i18n.js';

const FACTORS = ['he', 'v', 'gd'];

const GAP = 8; // px between the tile and the tooltip

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Fill the tooltip for one preset id.
function fill(tip, id) {
  tip.innerHTML = '';
  const preset = PRESETS[id];
  if (!preset && !COMING_SOON.includes(id)) return false;

  tip.append(el('p', 'preset-tooltip__title', t(`preset.${id}.title`)));
  tip.append(el('p', 'preset-tooltip__text', t(`preset.${id}.explain`)));

  if (preset) {
    const pct = toPercents(preset.weights);
    const list = el('ul', 'preset-tooltip__weights');
    FACTORS.forEach((key) => {
      const li = el('li');
      const bar = el('span', 'score-bar');
      bar.style.setProperty('--value', pct[key]);
      li.append(el('span', 'preset-tooltip__name', t(`factor.${key}`)), bar,
        el('span', 'preset-tooltip__pct', percent(pct[key])));
      list.append(li);
    });
    tip.append(list);

    tip.append(el('p', 'preset-tooltip__toggle', t('tooltip.toggle', {
      state: t(preset.onlyBuildable ? 'tooltip.on' : 'tooltip.off'),
    })));
    tip.append(el('p', 'preset-tooltip__hint', t('tooltip.hint')));
  }
  return true;
}

// Place the tooltip to the right of the tile (or below it when
// there is no room, e.g. on phones), kept inside the window.
// Also used by info-tooltip.js.
export function place(tip, tile) {
  const r = tile.getBoundingClientRect();
  const t = tip.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  let left = r.right + GAP;
  let top = r.top;
  if (left + t.width > vw - GAP) {
    left = Math.min(Math.max(GAP, r.left), vw - t.width - GAP);
    top = r.bottom + GAP;
  }
  top = Math.min(top, vh - t.height - GAP);

  tip.style.left = `${Math.max(GAP, left)}px`;
  tip.style.top = `${Math.max(GAP, top)}px`;
}

export function initPresetTooltip() {
  const tip = document.getElementById('preset-tooltip');
  const tiles = [...document.querySelectorAll('.preset[data-preset]')];

  function show(tile) {
    if (!fill(tip, tile.dataset.preset)) return;
    tip.hidden = false;
    tile.setAttribute('aria-describedby', tip.id);
    place(tip, tile);
  }

  function hide(tile) {
    tip.hidden = true;
    tile?.removeAttribute('aria-describedby');
  }

  tiles.forEach((tile) => {
    tile.addEventListener('mouseenter', () => show(tile));
    tile.addEventListener('mouseleave', () => hide(tile));
    tile.addEventListener('focus', () => show(tile));
    tile.addEventListener('blur', () => hide(tile));
  });

  // Esc closes it (keyboard users); scrolling the sidebar would
  // leave it floating in the wrong place, so hide it then too.
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hide(); });
  document.querySelector('.sidebar')
    ?.addEventListener('scroll', () => hide(), { passive: true });
}
