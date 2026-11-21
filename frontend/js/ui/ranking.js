// =============================================================
// ui/ranking.js
// "Where to act first": the 5 microzones with the highest shown
// score. Small hexagons (r10) sit next to each other, so the list
// ranks microzones, not hexes:
//   - each microzone is ranked by its highest hex score
//   - "N priority areas" = its hexes in the city's top 10 %
//   - clicking a row opens the microzone's best hex
// =============================================================

import { t, getLang } from './i18n.js';

const TOP_N = 5;
const TOP_SHARE = 0.1; // "priority area" = in the top 10 % of hexes

/** Score that a hex must reach to be in the top 10 % (sorted desc). */
function topThreshold(sorted) {
  if (!sorted.length) return Infinity;
  const n = Math.max(1, Math.ceil(sorted.length * TOP_SHARE));
  return sorted[n - 1].score;
}

/** "3 priority areas" / "3 prioritní oblasti", with the right plural. */
function areasLabel(n) {
  const form = new Intl.PluralRules(getLang()).select(n);
  const key = `ranking.areas.${form}`;
  const text = t(key, { n });
  return text === key ? t('ranking.areas.other', { n }) : text;
}

/**
 * Redraw the list.
 *
 * @param {Array<{ id, name, props, score }>} hexes
 * @param {string|null} selectedId - h3 of the open detail card
 * @param {(h3: string) => void} onPick - row clicked (best hex of the microzone)
 */
export function renderRanking(hexes, selectedId, onPick) {
  const list = document.getElementById('ranking-list');

  const sorted = hexes
    .filter((h) => Number.isFinite(h.score))
    .sort((a, b) => b.score - a.score);
  const threshold = topThreshold(sorted);

  // Group by microzone. `sorted` is best first, so the first hex
  // seen for a microzone is its best one.
  const zones = new Map();
  for (const h of sorted) {
    const key = h.props.mz_id ?? h.name;
    let z = zones.get(key);
    if (!z) {
      z = { best: h, priority: 0, ids: new Set() };
      zones.set(key, z);
    }
    z.ids.add(h.id);
    if (h.score >= threshold) z.priority += 1;
  }
  const rows = [...zones.values()].slice(0, TOP_N); // Map keeps insertion order = best first

  list.innerHTML = '';

  if (rows.length === 0) {
    const li = document.createElement('li');
    li.className = 'ranking-empty';
    li.textContent = t('ranking.empty');
    list.append(li);
    return;
  }

  rows.forEach(({ best, priority, ids }) => {
    const value = Math.round(best.score * 100);

    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.className = 'zone-row';
    btn.type = 'button';
    if (ids.has(selectedId)) btn.setAttribute('aria-current', 'true');

    const text = document.createElement('span');
    text.className = 'zone-row__text';
    const name = document.createElement('span');
    name.className = 'zone-row__name';
    name.textContent = best.name;
    const meta = document.createElement('span');
    meta.className = 'zone-row__meta';
    meta.textContent = areasLabel(priority);
    text.append(name, meta);

    const score = document.createElement('span');
    score.className = 'zone-row__score';
    const bar = document.createElement('span');
    bar.className = 'score-bar';
    bar.style.setProperty('--value', value);
    score.append(`${value} / 100`, bar);

    btn.append(text, score);
    btn.addEventListener('click', () => onPick(best.id));

    li.append(btn);
    list.append(li);
  });
}
