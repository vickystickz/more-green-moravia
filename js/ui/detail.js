// =============================================================
// ui/detail.js
// Detail card on the right of the map, shown when a hex is
// clicked (or picked in the ranking list).
// =============================================================

import { t, num, percent } from './i18n.js';

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const pct = (share) => percent(Math.round(share * 100));

function priorityLabel(score) {
  if (score >= 0.66) return t('detail.high');
  if (score >= 0.33) return t('detail.medium');
  return t('detail.low');
}

// "Heatwave max. 31.2 °C · 85 residents/ha" — parts with missing
// values are left out; returns '' when every part is missing.
function rawLine(parts) {
  return parts.filter(Boolean).join(' · ');
}

function rawHeat(p) {
  return rawLine([
    isNum(p.raw_heatwave_tmax) && t('raw.heatwave', { v: num(p.raw_heatwave_tmax, 1) }),
    isNum(p.raw_res_density) && t('raw.density', { v: num(p.raw_res_density) }),
  ]);
}

function rawVulnerable(p) {
  return rawLine([
    isNum(p.raw_share_65plus) && t('raw.age65', { v: pct(p.raw_share_65plus) }),
    isNum(p.raw_share_0_4) && t('raw.age04', { v: pct(p.raw_share_0_4) }),
    isNum(p.raw_sensitive_facilities) && t('raw.facilities', { v: num(p.raw_sensitive_facilities) }),
  ]);
}

function rawGreen(p) {
  return rawLine([
    isNum(p.raw_tree_cover) && t('raw.tree', { v: percent(Math.round(p.raw_tree_cover)) }),
    isNum(p.raw_dist_green) && t('raw.distGreen', { v: num(p.raw_dist_green) }),
  ]);
}

function rawFeasibility(p) {
  return rawLine([
    isNum(p.raw_brownfield_share) && t('raw.brownfield', { v: pct(p.raw_brownfield_share) }),
  ]);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function factorRow(name, value, weight, raw) {
  const li = el('li', 'factor');
  const top = el('div', 'factor__row');
  const label = el('span', 'factor__name', name);
  if (weight !== null) label.append(' ', el('span', 'factor__weight', t('detail.weight', { pct: weight })));
  const v = isNum(value) ? Math.round(value * 100) : null;
  top.append(label, el('span', 'factor__value', v === null ? '–' : String(v)));

  const bar = el('span', 'score-bar factor__bar');
  bar.style.setProperty('--value', v ?? 0);
  li.append(top, bar);
  if (raw) li.append(el('p', 'factor__raw', raw));
  return li;
}

/**
 * Wire up the close button.
 * @param {() => void} onClose
 */
export function initDetail(onClose) {
  document.getElementById('detail-close')
    .addEventListener('click', onClose);
}

/**
 * Fill and show the card, or hide it when hex is null.
 *
 * @param {{ id, name, props, dims, score } | null} hex
 * @param {{ weights: Object, onlyBuildable: boolean, weightLabels: Object }} ctx
 */
export function renderDetail(hex, { onlyBuildable, weightLabels }) {
  const card = document.getElementById('detail-card');
  if (!hex) {
    card.hidden = true;
    return;
  }

  const { props: p, dims: d } = hex;
  document.getElementById('detail-title').textContent = hex.name;
  document.getElementById('detail-hex').textContent = t('detail.hex', { id: hex.id });
  document.getElementById('detail-score').textContent = `${Math.round(hex.score * 100)} / 100`;
  document.getElementById('detail-label').textContent = priorityLabel(hex.score);

  const list = document.getElementById('detail-factors');
  list.innerHTML = '';
  list.append(
    factorRow(t('factor.he'), d.he, weightLabels.he, rawHeat(p)),
    factorRow(t('factor.v'), d.v, weightLabels.v, rawVulnerable(p)),
    factorRow(t('factor.gd'), d.gd, weightLabels.gd, rawGreen(p)),
  );
  if (onlyBuildable) {
    list.append(factorRow(t('factor.feas'), d.feas, null, rawFeasibility(p)));
  }

  card.hidden = false;
}
