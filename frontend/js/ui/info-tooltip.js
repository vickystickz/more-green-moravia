// =============================================================
// ui/info-tooltip.js
// Custom popup for the (i) icons next to the weight sliders and the
// "Only show places we can build" switch. On hover or keyboard
// focus it shows what the factor or filter means, in the
// same dark style as the preset tooltips. The text comes from
// data-info (a key in data/lang/*.json), so it follows the
// language switch.
// =============================================================

import { t } from './i18n.js';
import { place } from './preset-tooltip.js';

export function initInfoTooltip() {
  const tip = document.getElementById('info-tooltip');
  const icons = [...document.querySelectorAll('.weight__info[data-info]')];
  if (!tip || !icons.length) return;

  function show(icon) {
    tip.textContent = t(icon.dataset.info);
    tip.hidden = false;
    place(tip, icon);
  }

  function hide() {
    tip.hidden = true;
  }

  icons.forEach((icon) => {
    icon.addEventListener('mouseenter', () => show(icon));
    icon.addEventListener('mouseleave', hide);
    icon.addEventListener('focus', () => show(icon));
    icon.addEventListener('blur', hide);
    // The icon sits inside a <label>: a click must not move focus
    // to the slider or flip the switch.
    icon.addEventListener('click', (e) => { e.preventDefault(); show(icon); });
  });

  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hide(); });
  document.querySelector('.sidebar')
    ?.addEventListener('scroll', hide, { passive: true });
}
