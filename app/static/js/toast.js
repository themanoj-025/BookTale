/* ═══════════════════════════════════════════════════════════════════
   toast.js — BookTale Queue-based Toast Notification System
   ═══════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  // ── Config ─────────────────────────────────────────────────────
  const DEFAULTS = {
    duration: 3500,
    maxVisible: 4,
    animationDuration: 300,
  };

  // ── State ──────────────────────────────────────────────────────
  let container = null;
  let queue = [];
  let visibleCount = 0;

  // ── Container Setup ─────────────────────────────────────────────
  function getContainer() {
    if (container) return container;
    container = document.getElementById('bt-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'bt-toast-container';
      document.body.appendChild(container);
    }
    return container;
  }

  // ── Icons ───────────────────────────────────────────────────────
  const ICONS = {
    success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#16A34A" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>',
    error:   '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#DC2626" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    warning: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#D97706" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    info:    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
  };

  // ── Show Toast ──────────────────────────────────────────────────
  function showToast(message, type, duration) {
    type = type || 'info';
    duration = duration || DEFAULTS.duration;

    // Add to queue
    queue.push({ message, type, duration });
    processQueue();
  }

  function processQueue() {
    if (visibleCount >= DEFAULTS.maxVisible || queue.length === 0) return;

    const item = queue.shift();
    visibleCount++;

    const el = document.createElement('div');
    el.className = 'bt-toast';
    el.setAttribute('role', 'alert');
    el.setAttribute('aria-live', 'assertive');
    el.dataset.type = item.type;

    el.innerHTML = `
      <div class="bt-toast-icon">${ICONS[item.type] || ICONS.info}</div>
      <div class="bt-toast-body">
        <div class="bt-toast-message">${escapeHtml(item.message)}</div>
      </div>
      <button class="bt-toast-close" aria-label="Dismiss notification" type="button">&times;</button>
    `;

    const c = getContainer();
    c.appendChild(el);

    // Trigger entrance animation (reflow needed)
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        el.classList.add('bt-toast-visible');
      });
    });

    // Close button
    el.querySelector('.bt-toast-close').addEventListener('click', function () {
      dismissToast(el, true);
    });

    // Auto dismiss
    const autoTimer = setTimeout(() => {
      dismissToast(el, false);
    }, item.duration);

    el._autoTimer = autoTimer;

    // Allow processing more from queue (for next slot)
    setTimeout(() => processQueue(), 80);
  }

  function dismissToast(el, immediate) {
    if (el._dismissed) return;
    el._dismissed = true;

    clearTimeout(el._autoTimer);
    el.classList.remove('bt-toast-visible');

    // After animation ends, remove from DOM
    const animDuration = immediate ? 200 : DEFAULTS.animationDuration;
    setTimeout(() => {
      if (el.parentNode) el.parentNode.removeChild(el);
      visibleCount = Math.max(0, visibleCount - 1);
      processQueue();
    }, animDuration);
  }

  // ── Escape HTML ─────────────────────────────────────────────────
  function escapeHtml(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  // ── Global Access ───────────────────────────────────────────────
  window.showToast = showToast;

  // Also expose BookTale namespace
  window.BookTale = window.BookTale || {};
  window.BookTale.toast = { show: showToast };

})();
