// =============================================================
// ui/ranking.js
// "Where to act first": the 5 places with the highest shown score.
// Each microzone appears once (its best hex); when two top hexes
// share a microzone, the next microzone is shown instead.
// =============================================================

import { t } from './i18n.js';

const TOP_N = 5;

/**
 * Redraw the list.
 *
 * @param {Array<{ id, name, score }>} hexes
 * @param {string|null} selectedId - h3 of the open detail card
 * @param {(h3: string) => void} onPick - row clicked
 */
export function renderRanking(hexes, selectedId, onPick) {
  const list = document.getElementById('ranking-list');

  const sorted = hexes
    .filter((h) => Number.isFinite(h.score))
    .sort((a, b) => b.score - a.score);

  const rows = [];
  const seen = new Set();
  for (const h of sorted) {
    if (seen.has(h.name)) continue;
    seen.add(h.name);
    rows.push(h);
    if (rows.length === TOP_N) break;
  }

  list.innerHTML = '';

  if (rows.length === 0) {
    const li = document.createElement('li');
    li.className = 'ranking-empty';
    li.textContent = t('ranking.empty');
    list.append(li);
    return;
  }

  rows.forEach((h) => {
    const value = Math.round(h.score * 100);

    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.className = 'zone-row';
    btn.type = 'button';
    if (h.id === selectedId) btn.setAttribute('aria-current', 'true');

    const name = document.createElement('span');
    name.className = 'zone-row__name';
    name.textContent = h.name;

    const score = document.createElement('span');
    score.className = 'zone-row__score';
    const bar = document.createElement('span');
    bar.className = 'score-bar';
    bar.style.setProperty('--value', value);
    score.append(`${value} / 100`, bar);

    btn.append(name, score);
    btn.addEventListener('click', () => onPick(h.id));

    li.append(btn);
    list.append(li);
  });
}
