// =============================================================
// ui/ask-ai.js
// "Ask AI" panel: a right-hand column opened from the Ask AI
// button on the map. Questions go to our own backend
// (AGENT_CONFIG in config.js), which streams back server-sent
// events: `step` (a query the agent ran), `answer` (markdown),
// `done`, or `error`. Never put an AI API key in front-end code:
// the backend holds it.
//
// Steps that found places carry a `layer`. Each gets a "Show on
// map" button under the answer: the layer goes to POST /map, and
// the GeoJSON that comes back is drawn by map/ai-layer.js.
// =============================================================

import { AGENT_CONFIG } from '../config.js';
import { t } from './i18n.js';
import { showAiLayer, clearAiLayer } from '../map/ai-layer.js';

/**
 * @param {() => maplibregl.Map | null} getMap - the map, once it exists
 */
export function initAskAi(getMap = () => null) {
  const app = document.querySelector('.app');
  const button = document.getElementById('ask-ai');
  if (!AGENT_CONFIG.enabled) {
    button.hidden = true; // turned off in config.js
    return;
  }
  const panel = document.getElementById('ask-ai-panel');
  const closeBtn = document.getElementById('ask-ai-close');
  const form = document.getElementById('ask-ai-form');
  const input = document.getElementById('ask-ai-input');
  const send = document.getElementById('ask-ai-send');
  const body = panel.querySelector('.ask-ai-panel__body');
  const thread = document.getElementById('ask-ai-thread');
  const chip = document.getElementById('ai-layer-chip');
  const chipTitle = document.getElementById('ai-layer-title');
  const chipClear = document.getElementById('ai-layer-clear');

  // Earlier turns, sent with each question so follow-ups work.
  // Nothing is stored on the server.
  const history = [];
  let busy = false;

  // The slide is a CSS transition (see css/components/ask-ai.css).
  // Opening: show the panel, then add the class on the next frame so
  // the column grows from 0. Closing: remove the class, then hide the
  // panel once the slide has finished.
  let hideTimer = null;
  const isOpen = () => app.classList.contains('is-ask-ai-open');
  const slideMs = () => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return 0;
    return parseFloat(getComputedStyle(app).getPropertyValue('--ask-ai-duration')) || 0;
  };

  function setOpen(open) {
    clearTimeout(hideTimer);
    button.setAttribute('aria-expanded', String(open));

    if (open) {
      panel.hidden = false;
      void panel.offsetWidth; // apply the closed state before animating
      app.classList.add('is-ask-ai-open');
      input.focus({ preventScroll: true });
    } else {
      app.classList.remove('is-ask-ai-open');
      hideTimer = setTimeout(() => { panel.hidden = true; }, slideMs());
      button.focus();
    }
  }

  function updateSend() {
    send.disabled = busy || input.value.trim() === '';
  }

  button.addEventListener('click', () => setOpen(!isOpen()));
  closeBtn.addEventListener('click', () => setOpen(false));

  panel.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') setOpen(false);
  });

  // A suggestion fills the message box.
  panel.querySelectorAll('.ask-ai-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      input.value = chip.textContent.trim();
      updateSend();
      input.focus();
    });
  });

  input.addEventListener('input', updateSend);

  // ---------------------------------------------------------
  // Show on map
  // ---------------------------------------------------------
  let activeMapBtn = null;
  let mapRequest = 0; // only the latest click may draw

  function setActiveMapBtn(btn) {
    activeMapBtn?.classList.remove('is-active');
    activeMapBtn?.setAttribute('aria-pressed', 'false');
    activeMapBtn = btn;
    btn?.classList.add('is-active');
    btn?.setAttribute('aria-pressed', 'true');
  }

  function clearMap() {
    mapRequest++;
    clearAiLayer(getMap());
    setActiveMapBtn(null);
    chip.hidden = true;
  }

  chipClear.addEventListener('click', clearMap);

  async function showOnMap(btn, item) {
    const map = getMap();
    if (!map) return;
    if (btn === activeMapBtn) {
      clearMap();
      return;
    }
    const request = ++mapRequest;
    btn.classList.add('is-loading');
    btn.disabled = true;
    btn.parentNode.querySelector('.ask-ai-msg__map-error')?.remove();
    try {
      const layer = await fetchLayer(item.layer);
      if (request !== mapRequest) return;
      showAiLayer(map, layer);
      setActiveMapBtn(btn);
      chipTitle.textContent = layer.title || item.title;
      chip.hidden = false;
      // On phones the panel covers the map: get out of the way.
      if (matchMedia('(max-width: 768px)').matches) setOpen(false);
    } catch (err) {
      console.warn('Ask AI map:', err);
      if (request === mapRequest) {
        btn.parentNode.append(el('p', 'ask-ai-msg__map-error',
          err instanceof AgentError ? err.message : t('askai.mapError')));
      }
    } finally {
      btn.classList.remove('is-loading');
      btn.disabled = false;
    }
  }

  // One button per step that found places (same layer only once).
  function addMapButtons(reply, items) {
    const seen = new Set();
    const unique = items.filter((i) => {
      const key = JSON.stringify(i.layer);
      return !seen.has(key) && seen.add(key);
    });
    if (!unique.length) return;

    const box = el('div', 'ask-ai-msg__maps');
    for (const item of unique) {
      const btn = el('button', 'ask-ai-map-btn');
      btn.type = 'button';
      btn.setAttribute('aria-pressed', 'false');
      const icon = document.createElement('img');
      icon.src = 'assets/icons/map.svg';
      icon.width = 14;
      icon.height = 14;
      icon.alt = '';
      const label = unique.length === 1 ? t('askai.showOnMap') : item.title;
      btn.append(icon, el('span', '', label));
      btn.title = item.title;
      btn.addEventListener('click', () => showOnMap(btn, item));
      box.append(btn);
    }
    reply.querySelector('.ask-ai-msg__text').after(box);
  }

  // Enter sends, Shift+Enter adds a new line.
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (busy || !question) return;
    input.value = '';
    ask(question);
  });

  // ---------------------------------------------------------
  // One question → one streamed answer
  // ---------------------------------------------------------
  async function ask(question) {
    busy = true;
    updateSend();
    body.classList.add('has-messages');

    addBubble('user').textContent = question;
    const reply = addBubble('assistant');
    reply.classList.add('is-pending');
    const status = el('p', 'ask-ai-msg__status', t('askai.thinking'));
    const steps = el('ol', 'ask-ai-msg__steps');
    reply.append(status, steps);
    scrollDown();

    let answer = null;
    const layers = [];
    try {
      await streamChat(question, history, {
        step(data) {
          const li = el('li', data.ok ? '' : 'is-failed', data.label || data.tool);
          steps.append(li);
          if (data.ok && data.layer) {
            layers.push({ layer: data.layer, title: data.layer.title || data.label || data.tool });
          }
          scrollDown();
        },
        answer(data) {
          answer = data.text;
        },
        error(data) {
          throw new AgentError(data.message || t('askai.error'));
        },
      });
      if (answer == null) throw new AgentError(t('askai.error'));

      reply.classList.remove('is-pending');
      status.remove();
      const text = el('div', 'ask-ai-msg__text');
      text.innerHTML = renderMarkdown(answer);
      reply.prepend(text);
      addMapButtons(reply, layers);
      collapseSteps(steps);

      history.push({ role: 'user', content: question });
      history.push({ role: 'assistant', content: answer.slice(0, AGENT_CONFIG.maxTurnChars) });
      history.splice(0, Math.max(0, history.length - AGENT_CONFIG.maxHistory));
    } catch (err) {
      console.warn('Ask AI:', err);
      reply.classList.remove('is-pending');
      reply.classList.add('is-error');
      status.textContent = err instanceof AgentError ? err.message : t('askai.errorNetwork');
      steps.remove();
    } finally {
      busy = false;
      updateSend();
      scrollDown();
      input.focus({ preventScroll: true });
    }
  }

  function addBubble(role) {
    const bubble = el('div', `ask-ai-msg ask-ai-msg--${role}`);
    thread.append(bubble);
    return bubble;
  }

  function scrollDown() {
    body.scrollTop = body.scrollHeight;
  }

  // After the answer, the query list folds into "N queries run".
  function collapseSteps(steps) {
    if (!steps.children.length) {
      steps.remove();
      return;
    }
    const details = el('details', 'ask-ai-msg__details');
    details.append(el('summary', '', t('askai.steps', { n: steps.children.length })), steps);
    steps.parentNode?.append(details);
  }
}

class AgentError extends Error {}

// POST the question and call handlers[event](data) for each
// server-sent event as it arrives.
async function streamChat(message, history, handlers) {
  if (!AGENT_CONFIG.baseUrl) throw new AgentError(t('askai.soon'));
  const res = await fetch(AGENT_CONFIG.baseUrl + AGENT_CONFIG.chatPath, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ message, history, stream: true }),
  });

  if (!res.ok) {
    let detail = '';
    try {
      const json = await res.json();
      detail = json.error?.message || (typeof json.detail === 'string' ? json.detail : '');
    } catch { /* not JSON */ }
    throw new AgentError(detail || t('askai.error'));
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replace(/\r\n/g, '\n');
    let cut;
    while ((cut = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      dispatch(frame, handlers);
    }
  }
}

// A step's `layer` → GeoJSON layer (backend: POST /map).
async function fetchLayer(spec) {
  const res = await fetch(AGENT_CONFIG.baseUrl + AGENT_CONFIG.mapPath, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(spec),
  });
  if (!res.ok) throw new AgentError(t('askai.mapError'));
  const layer = await res.json();
  if (!layer.features?.features?.length) throw new AgentError(t('askai.mapEmpty'));
  return layer;
}

function dispatch(frame, handlers) {
  let event = 'message';
  const data = [];
  for (const line of frame.split('\n')) {
    if (line.startsWith(':')) continue; // heartbeat comment
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
  }
  if (!data.length || !handlers[event]) return;
  handlers[event](JSON.parse(data.join('\n')));
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

// ---------------------------------------------------------
// Small markdown renderer for the answers: paragraphs,
// headings, lists, tables, **bold**, *italic*, `code`.
// Everything is HTML-escaped first, so model output cannot
// inject markup.
// ---------------------------------------------------------
const escapeHtml = (s) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function inline(s) {
  return escapeHtml(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');
}

const cells = (row) => row.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());

export function renderMarkdown(md) {
  const lines = md.replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      out.push(`<h4>${inline(heading[2])}</h4>`);
      i++;
      continue;
    }

    // Table: header row, then a |---|---| separator.
    if (line.includes('|') && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] || '')) {
      const head = cells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes('|')) rows.push(cells(lines[i++]));
      out.push(
        '<div class="ask-ai-table"><table><thead><tr>' +
          head.map((c) => `<th>${inline(c)}</th>`).join('') +
          '</tr></thead><tbody>' +
          rows.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`).join('') +
          '</tbody></table></div>',
      );
      continue;
    }

    const listItem = /^\s*(?:[-*+]|\d+[.)])\s+/;
    if (listItem.test(line)) {
      const ordered = /^\s*\d/.test(line);
      const items = [];
      while (i < lines.length && listItem.test(lines[i])) {
        items.push(`<li>${inline(lines[i].replace(listItem, ''))}</li>`);
        i++;
      }
      const tag = ordered ? 'ol' : 'ul';
      out.push(`<${tag}>${items.join('')}</${tag}>`);
      continue;
    }

    const para = [];
    while (
      i < lines.length && lines[i].trim() &&
      !listItem.test(lines[i]) && !/^#{1,6}\s/.test(lines[i]) &&
      !(lines[i].includes('|') && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] || ''))
    ) {
      para.push(inline(lines[i]));
      i++;
    }
    out.push(`<p>${para.join('<br>')}</p>`);
  }
  return out.join('');
}
