// =============================================================
// ui/ask-ai.js
// "Ask AI" panel. There is no backend yet, so the panel only says
// "Coming soon". Never put an AI API key in front-end code: when
// this is built, the browser must call our own backend, which
// holds the key.
// =============================================================

export function initAskAi() {
  const button = document.getElementById('ask-ai');
  const panel = document.getElementById('ask-ai-panel');

  button.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
    button.setAttribute('aria-expanded', String(!panel.hidden));
  });

  document.getElementById('ask-ai-panel')
    .addEventListener('submit', (e) => e.preventDefault());
}
