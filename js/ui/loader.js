// Loader screen shown while the map and data load.
const el = () => document.getElementById('loader');

export function showLoader() {
  el()?.classList.remove('is-hidden', 'is-error');
}

export function hideLoader() {
  el()?.classList.add('is-hidden');
}

export function showLoaderError(message) {
  const loader = el();
  if (!loader) return;
  loader.classList.add('is-error');
  const msg = loader.querySelector('.loader__message');
  if (msg) msg.textContent = message;
}
