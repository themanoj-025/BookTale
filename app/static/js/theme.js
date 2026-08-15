/**
 * theme.js — BookTale Theme Manager
 * Handles light/dark/sepia theme toggle, persistence, and accessibility mode
 */

(function() {
  'use strict';

  const THEMES = ['light', 'dark', 'sepia'];
  const THEME_KEY = 'booktale_theme';
  const ACCESSIBLE_KEY = 'booktale_accessible';

  function getSavedTheme() {
    return localStorage.getItem(THEME_KEY) || 'light';
  }

  function setTheme(theme) {
    if (!THEMES.includes(theme)) return;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    
    // Update toggle button icon
    const toggleBtn = document.querySelector('.theme-toggle');
    if (toggleBtn) {
      const icon = toggleBtn.querySelector('i');
      if (icon) {
        const icons = { light: 'bi-moon-stars-fill', dark: 'bi-sun-fill', sepia: 'bi-book-half' };
        icon.className = 'bi ' + (icons[theme] || 'bi-moon-stars-fill');
      }
      toggleBtn.setAttribute('aria-pressed', theme !== 'light' ? 'true' : 'false');
      toggleBtn.setAttribute('aria-label', `Switch to ${THEMES[(THEMES.indexOf(theme) + 1) % 3]} mode`);
    }
  }

  function cycleTheme() {
    const current = getSavedTheme();
    const next = THEMES[(THEMES.indexOf(current) + 1) % 3];
    setTheme(next);
  }

  function setAccessible(enabled) {
    const btn = document.getElementById('accessibilityToggle');
    if (enabled) {
      document.documentElement.setAttribute('data-mode', 'accessible');
      localStorage.setItem(ACCESSIBLE_KEY, 'true');
      if (btn) {
        btn.classList.add('active');
        btn.setAttribute('aria-pressed', 'true');
        btn.setAttribute('aria-label', 'Disable accessibility mode');
      }
    } else {
      document.documentElement.removeAttribute('data-mode');
      localStorage.setItem(ACCESSIBLE_KEY, 'false');
      if (btn) {
        btn.classList.remove('active');
        btn.setAttribute('aria-pressed', 'false');
        btn.setAttribute('aria-label', 'Toggle accessibility mode (OpenDyslexic font, high contrast, reduced motion)');
      }
    }
    // Dispatch custom event so other modules can react
    document.dispatchEvent(new CustomEvent('accessibilityChanged', { detail: { enabled } }));
  }

  function toggleAccessible() {
    const current = localStorage.getItem(ACCESSIBLE_KEY) === 'true';
    setAccessible(!current);
    if (typeof window.showToast === 'function') {
      window.showToast(!current ? '♿ Accessibility mode enabled' : 'Accessibility mode disabled', 'info');
    }
  }

  function init() {
    // Restore saved theme
    const savedTheme = getSavedTheme();
    setTheme(savedTheme);

    // Restore accessibility mode
    const accessible = localStorage.getItem(ACCESSIBLE_KEY) === 'true';
    if (accessible) {
      setAccessible(true);
    }

    // Wire up theme toggle button
    const toggleBtn = document.querySelector('.theme-toggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', function(e) {
        e.preventDefault();
        // Cycle: light → dark → sepia → light
        const current = getSavedTheme();
        const next = THEMES[(THEMES.indexOf(current) + 1) % 3];
        setTheme(next);
      });
    }

    // Wire up accessibility toggle button
    const accBtn = document.getElementById('accessibilityToggle');
    if (accBtn) {
      accBtn.addEventListener('click', function(e) {
        e.preventDefault();
        toggleAccessible();
      });
    }

    // Listen for system preference changes
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', function(e) {
      // Only auto-switch if user hasn't set a preference
      if (!localStorage.getItem(THEME_KEY)) {
        setTheme(e.matches ? 'dark' : 'light');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Export for use in inline scripts
  window.booktaleTheme = { setTheme, cycleTheme, getSavedTheme, setAccessible, toggleAccessible };
})();
