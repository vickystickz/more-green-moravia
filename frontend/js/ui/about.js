// =============================================================
// ui/about.js
// "About this tool" window, opened by the (i) button next to the
// intro title. Its text is plain Markdown in data/about/<lang>.md
// (en.md, cs.md), so the methodology, data sources and team can be
// updated without touching the code. Czech falls back to English
// when cs.md is missing.
// =============================================================

import { getLang, onLangChange, t } from './i18n.js';

// Raise after editing the Markdown, so browsers fetch the new text.
const VERSION = 5;
const path = (lang) => `data/about/${lang}.md?v=${VERSION}`;

const cache = new Map(); // lang -> rendered HTML

async function loadHtml(lang) {
  if (cache.has(lang)) return cache.get(lang);
  let res = await fetch(path(lang));
  if (!res.ok && lang !== 'en') res = await fetch(path('en'));
  if (!res.ok) throw new Error(`about: HTTP ${res.status}`);
  const html = renderAbout(await res.text());
  cache.set(lang, html);
  return html;
}

/** Wire the (i) button to the About window. */
export function initAbout() {
  const button = document.getElementById('about-open');
  const dialog = document.getElementById('about-dialog');
  const body = document.getElementById('about-body');
  if (!button || !dialog) return;

  const fill = async () => {
    try {
      body.innerHTML = await loadHtml(getLang());
    } catch {
      body.textContent = t('about.error');
    }
  };

  button.addEventListener('click', async () => {
    body.textContent = t('about.loading');
    dialog.showModal();
    await fill();
    body.scrollTop = 0;
  });
  document.getElementById('about-close').addEventListener('click', () => dialog.close());
  // A click on the dark backdrop (outside the box) closes it too.
  dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
  onLangChange(() => { if (dialog.open) fill(); });
}

// ---------------------------------------------------------
// Markdown → HTML for the About text: # ## ### headings,
// paragraphs, lists, tables, > notes, --- dividers, images on
// their own line, [links](…), **bold**, *italic*, `code`.
// HTML comments are dropped. Everything is HTML-escaped first,
// and only http(s) or relative URLs are kept.
// ---------------------------------------------------------
const escapeHtml = (s) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const safeUrl = (url) => (/^(https?:\/\/|[\w./-]+$)/i.test(url) && !/^javascript:/i.test(url) ? url : '#');

function inline(s) {
  return escapeHtml(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, text, url) => {
      const href = safeUrl(url);
      const external = /^https?:/i.test(href) ? ' target="_blank" rel="noopener"' : '';
      return `<a href="${href}"${external}>${text}</a>`;
    })
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');
}

const cells = (row) => row.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
const isTableStart = (line, next) => line.includes('|') && /^\s*\|?\s*:?-{2,}/.test(next || '');
const listItem = /^\s*(?:[-*+]|\d+[.)])\s+/;
const image = /^!\[([^\]]*)\]\(([^)\s]+)\)\s*$/;
const isBlockStart = (line, next) =>
  /^#{1,6}\s/.test(line) || listItem.test(line) || /^>/.test(line) ||
  /^-{3,}\s*$/.test(line) || image.test(line) || isTableStart(line, next);

export function renderAbout(md) {
  const lines = md.replace(/\r\n/g, '\n').replace(/<!--[\s\S]*?-->/g, '').split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      const level = Math.min(heading[1].length + 1, 4); // # → h2 (the window title is h2-level)
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      i++;
      continue;
    }

    if (/^-{3,}\s*$/.test(line)) { out.push('<hr>'); i++; continue; }

    const img = line.match(image);
    if (img) {
      const [, alt, src] = img;
      out.push(`<figure><img src="${safeUrl(src)}" alt="${escapeHtml(alt)}" loading="lazy"></figure>`);
      i++;
      continue;
    }

    if (/^>/.test(line)) {
      const note = [];
      while (i < lines.length && /^>/.test(lines[i])) note.push(inline(lines[i++].replace(/^>\s?/, '')));
      out.push(`<aside class="about-note">${note.join('<br>')}</aside>`);
      continue;
    }

    if (isTableStart(line, lines[i + 1])) {
      const head = cells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes('|')) rows.push(cells(lines[i++]));
      out.push(
        '<div class="ask-ai-table about-table"><table><thead><tr>' +
          head.map((c) => `<th>${inline(c)}</th>`).join('') +
          '</tr></thead><tbody>' +
          rows.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`).join('') +
          '</tbody></table></div>',
      );
      continue;
    }

    if (listItem.test(line)) {
      const tag = /^\s*\d/.test(line) ? 'ol' : 'ul';
      const items = [];
      while (i < lines.length && listItem.test(lines[i])) {
        items.push(`<li>${inline(lines[i++].replace(listItem, ''))}</li>`);
      }
      out.push(`<${tag}>${items.join('')}</${tag}>`);
      continue;
    }

    const para = [];
    while (i < lines.length && lines[i].trim() && !(para.length && isBlockStart(lines[i], lines[i + 1]))) {
      para.push(inline(lines[i++]));
    }
    out.push(`<p>${para.join(' ')}</p>`);
  }
  return out.join('');
}
