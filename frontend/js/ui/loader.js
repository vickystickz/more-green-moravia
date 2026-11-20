// Loader screen shown while the map and data load.
import { t } from './i18n.js';

const el = () => document.getElementById('loader');

export function showLoader() {
  el()?.classList.remove('is-hidden', 'is-error');
}

export function hideLoader() {
  el()?.classList.add('is-hidden');
}

export function showLoaderError(key = 'loader.error') {
  const loader = el();
  if (!loader) return;
  loader.classList.add('is-error');
  const msg = loader.querySelector('.loader__message');
  if (msg) {
    msg.dataset.i18n = key; // re-translated if the language changes
    msg.textContent = t(key);
  }
}
