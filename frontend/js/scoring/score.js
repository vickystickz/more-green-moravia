// =============================================================
// scoring/score.js
// INFORM-style green infrastructure (GI) need score per hexagon.
// This is a copy of the notebook formula and must stay identical,
// so the browser and the notebook give the same numbers.
//
//   exposure = wmean(day, night)            (day_weight)
//   HE       = heat^a * exposure^(1-a)      Heat & people exposed
//   V        = vulnerability                Vulnerable groups
//   GD       = wmean(supply, access)        Lack of green
//   need     = HE^wHE * V^wV * GD^wGD       (weights sum to 1)
//   priority = need * feasibility
//
// The c_* columns are already smoothed in the notebook, so we use
// them as they are (never recompute them from the mu_* columns).
// =============================================================

import { SCORE_DEFAULTS } from '../config.js';

const FLOOR = 0.01;

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

// Missing or tiny values become FLOOR, so one zero does not wipe
// out the whole product.
const fl = (v) => Math.max(isNum(v) ? v : FLOOR, FLOOR);

/**
 * Weighted mean of the values that exist. Weights of missing values
 * are dropped and the rest renormalised.
 *
 * @param {Array<[number|null, number]>} pairs - [value, weight]
 * @returns {number|null} null when every value is missing
 */
function wmean(pairs) {
  let sum = 0;
  let wsum = 0;
  for (const [v, w] of pairs) {
    if (!isNum(v)) continue;
    sum += v * w;
    wsum += w;
  }
  return wsum > 0 ? sum / wsum : null;
}

/**
 * Read a, day_weight from the notebook's metadata.json. The keys
 * may sit at the top level or inside a nested object.
 */
export function paramsFromMetadata(meta) {
  const find = (obj, key) => {
    if (!obj || typeof obj !== 'object') return undefined;
    if (isNum(obj[key])) return obj[key];
    for (const value of Object.values(obj)) {
      const found = find(value, key);
      if (found !== undefined) return found;
    }
    return undefined;
  };

  return {
    a: find(meta, 'heat_hazard_share_a') ?? SCORE_DEFAULTS.a,
    dayWeight: find(meta, 'day_weight') ?? SCORE_DEFAULTS.dayWeight,
  };
}

/**
 * The parts of the score that do not depend on the slider
 * weights. Computed once per hex when the data loads.
 *
 * @returns {{ he: number, v: number, gd: number|null, feas: number }}
 */
export function dimensions(p, { a, dayWeight }) {
  const exposure = wmean([
    [p.c_exposure_day, dayWeight],
    [p.c_exposure_night, 1 - dayWeight],
  ]);

  return {
    he: fl(p.c_heat) ** a * fl(exposure) ** (1 - a),
    v: isNum(p.c_vulnerability) ? p.c_vulnerability : 0,
    gd: wmean([[p.c_green_supply, 0.5], [p.c_green_access, 0.5]]),
    feas: isNum(p.d_feasibility) ? p.d_feasibility : 0,
  };
}

/**
 * GI need from the three dimensions and the slider weights.
 *
 * @param {{ he: number, v: number, gd: number|null }} d
 * @param {{ he: number, v: number, gd: number }} w - sum to 1
 */
export function need(d, w) {
  return fl(d.he) ** w.he * fl(d.v) ** w.v * fl(d.gd) ** w.gd;
}

/**
 * The score shown on the map and in the list.
 * Feasibility ON: need × feasibility (priority). OFF: need.
 */
export function shownScore(d, w, onlyBuildable) {
  const n = need(d, w);
  return onlyBuildable ? n * d.feas : n;
}

/**
 * Self-test: with Balance weights the browser must match the
 * notebook's gi_need_provisional for every hex. Logs the result.
 *
 * @param {Array<{ props: Object, dims: Object }>} hexes
 */
export function selfTest(hexes) {
  const third = 1 / 3;
  const balance = { he: third, v: third, gd: third };

  let checked = 0;
  const bad = [];
  for (const h of hexes) {
    const expected = h.props.gi_need_provisional;
    if (!isNum(expected)) continue;
    checked += 1;
    const got = need(h.dims, balance);
    if (Math.abs(got - expected) >= 0.005) {
      bad.push({ h3: h.id, expected, got });
    }
  }

  if (checked === 0) {
    console.warn('INFORM check skipped: no gi_need_provisional values in the data.');
  } else if (bad.length === 0) {
    console.info(`INFORM check passed (${checked} hexes).`);
  } else {
    console.warn(`INFORM check failed: ${bad.length} of ${checked} hexes differ by 0.005 or more.`);
    console.table(bad.slice(0, 10));
  }
}
