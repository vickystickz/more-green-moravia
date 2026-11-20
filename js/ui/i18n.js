// =============================================================
// ui/i18n.js
// English / Czech text. All words shown to users live in
// data/lang/en.json and data/lang/cs.json (same keys in both).
//
//   HTML: <span data-i18n="ranking.title">…</span>           → text
//         <input data-i18n-attr="placeholder:search.placeholder">
//         (several attributes: "aria-label:a.b,title:c.d")
//   JS:   t('detail.hex', { id }) → "Hex 89…" / "Šestiúhelník 89…"
//
// Which language opens (first match wins):
//   1. the address: …/cz/ or …/en/  (folders made by the deploy
//      workflow, see .github/workflows/deploy.yml), or ?lang=cz
//   2. the last choice in this browser (localStorage)
//   3. Czech if the browser is set to Czech, else English
//
// In the address Czech is "cz" (what people type); in the code and
// the language files it is "cs" (the official language code).
// =============================================================

const LANGS = ['en', 'cs'];
const URL_CODE = { en: 'en', cs: 'cz' }; // code → address segment
const fromUrlCode = (code) => ({ en: 'en', cz: 'cs', cs: 'cs' })[String(code).toLowerCase()];
const STORAGE_KEY = 'mgm-lang';

const dicts = { en: {}, cs: {} };
let lang = 'en';
const listeners = [];
const warned = new Set();

async function loadDict(code) {
  try {
    const res = await fetch(`data/lang/${code}.json`);
    if (!res.ok) throw new Error(res.status);
    dicts[code] = await res.json();
  } catch (err) {
    console.warn(`Language file data/lang/${code}.json not loaded (${err.message}).`);
  }
}

function savedLang() {
  try { return localStorage.getItem(STORAGE_KEY); } catch { return null; }
}

// Language folder in the address: …/more-green-moravia/cz/ → 'cs'.
function langFromPath() {
  const last = location.pathname.replace(/\/(index\.html)?$/, '').split('/').pop();
  return fromUrlCode(last);
}

const langFromQuery = () => fromUrlCode(new URLSearchParams(location.search).get('lang'));

/** Load both dictionaries and pick the starting language. */
export async function initI18n() {
  await Promise.all(LANGS.map(loadDict));
  const saved = savedLang();
  const browser = (navigator.language || '').toLowerCase().startsWith('cs') ? 'cs' : 'en';
  lang = langFromPath() ?? langFromQuery()
    ?? (LANGS.includes(saved) ? saved : browser);
  applyDom();
}

// Keep the address in step with the language, without reloading:
//   …/cz/ ↔ …/en/   and   ?lang=cz ↔ ?lang=en.
// The main page (no language in the address) is left as it is,
// because the en/ and cz/ folders only exist on the live site.
function updateUrl() {
  const url = new URL(location.href);
  if (langFromPath()) {
    url.pathname = url.pathname.replace(/\/(en|cz|cs)(\/(index\.html)?)?$/i, `/${URL_CODE[lang]}/`);
  } else if (langFromQuery()) {
    url.searchParams.set('lang', URL_CODE[lang]);
  } else {
    return;
  }
  history.replaceState(history.state, '', url);
}

/** Current language code: 'en' or 'cs'. */
export const getLang = () => lang;

/**
 * Text for a key in the current language, with {name} placeholders
 * filled from `vars`. Falls back to English, then to the key.
 */
export function t(key, vars = {}) {
  let text = dicts[lang][key] ?? dicts.en[key];
  if (text === undefined) {
    if (!warned.has(key)) { warned.add(key); console.warn(`Missing text: ${key}`); }
    text = key;
  }
  return text.replace(/\{(\w+)\}/g, (_, name) => (vars[name] ?? `{${name}}`));
}

// Number formatting: 31.2 (EN) / 31,2 (CS).
const formatters = {};
export function num(value, decimals = 0) {
  const k = `${lang}-${decimals}`;
  formatters[k] ??= new Intl.NumberFormat(lang === 'cs' ? 'cs-CZ' : 'en-GB', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return formatters[k].format(value);
}

/** Whole percentage: "33%" (EN) / "33 %" (CS). */
export const percent = (n) => t('fmt.percent', { n: num(n) });

/** Translate every element marked with data-i18n / data-i18n-attr. */
export function applyDom(root = document) {
  document.documentElement.lang = lang;
  root.querySelectorAll('[data-i18n]').forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  root.querySelectorAll('[data-i18n-attr]').forEach((el) => {
    el.dataset.i18nAttr.split(',').forEach((pair) => {
      const [attr, key] = pair.split(':').map((s) => s.trim());
      el.setAttribute(attr, t(key));
    });
  });
}

/** Run `fn` every time the language changes (to redraw JS-made text). */
export function onLangChange(fn) {
  listeners.push(fn);
}

export function setLang(code) {
  if (!LANGS.includes(code) || code === lang) return;
  lang = code;
  try { localStorage.setItem(STORAGE_KEY, code); } catch { /* private mode */ }
  updateUrl();
  applyDom();
  listeners.forEach((fn) => fn(lang));
}

/** The EN / CZ button in the header. */
export function initLangSwitch() {
  document.getElementById('lang-switch')
    .addEventListener('click', () => setLang(lang === 'en' ? 'cs' : 'en'));
}
