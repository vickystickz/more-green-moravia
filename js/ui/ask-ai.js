// =============================================================
// ui/ask-ai.js
// "Ask AI" panel: a right-hand column opened from the Ask AI
// button on the map. There is no backend yet, so sending a
// question only shows "Coming soon". Never put an AI API key in
// front-end code: when this is built, the browser must call our
// own backend, which holds the key.
// =============================================================

export function initAskAi() {
  const app = document.querySelector('.app');
  const button = document.getElementById('ask-ai');
  const panel = document.getElementById('ask-ai-panel');
  const closeBtn = document.getElementById('ask-ai-close');
  const form = document.getElementById('ask-ai-form');
  const input = document.getElementById('ask-ai-input');
  const send = document.getElementById('ask-ai-send');
  const soon = document.getElementById('ask-ai-soon');

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
    send.disabled = input.value.trim() === '';
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

  input.addEventListener('input', () => {
    soon.hidden = true;
    updateSend();
  });

  // Enter sends, Shift+Enter adds a new line.
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    if (send.disabled) return;
    soon.hidden = false;
  });
}
