// Fetches and prepares the GeoJSON data.
import { DATA_PATHS } from '../config.js';

export async function loadMicrozones() {
  const res = await fetch(DATA_PATHS.microzones);
  if (!res.ok) throw new Error(`Could not load ${DATA_PATHS.microzones}`);
  return res.json();
}
