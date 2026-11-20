// Single source of truth for the current preset, weights and selection.
const third = 1 / 3;

export const state = {
  preset: 'balance',
  weights: { he: third, v: third, gd: third }, // always sum to 1
  onlyBuildable: false,  // "Only show places we can build"
  activeLayer: 'score',  // map colour: score | he | v | gd | feas
  hexes: [],             // [{ id, props, dims, name, center, bbox, score }]
  selectedHex: null,     // h3_index of the open detail card
};
