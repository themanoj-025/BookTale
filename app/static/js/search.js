/**
 * search.js — Global Search Overlay (Ctrl+K)
 * Unified search with 300ms debounce
 */

(function() {
  'use strict';

  var searchTimeout;

  function openSearchOverlay() {
    var overlay = document.getElementById('searchOverlay');
    if (!overlay) return;
    overlay.classList.add('active');
    setTimeout(function() {
      var input = document.getElementById('searchOverlayInput');
      if (input) input.focus();
    }, 100);
    document.body.style.overflow = 'hidden';
  }

  function closeSearchOverlay() {
    var overlay = document.getElementById('searchOverlay');
    if (!overlay) return;
    overlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  function searchBooks(query) {
    var resultsEl = document.getElementById('searchResults');
    if (!resultsEl) return;

    if (query.length < 2) {
      resultsEl.innerHTML = '<div class="text-center py-4 text-muted small" role="status">Type to search books...</div>';
      return;
    }

    // Debounce 300ms
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(function() {
      resultsEl.innerHTML = '<div class="text-center py-4 text-muted small" role="status" aria-label="Searching"><div class="spinner-border spinner-border-sm me-2"></div>Searching...</div>';

      fetch('/api/search?q=' + encodeURIComponent(query))
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (!data || (Array.isArray(data) && data.length === 0) || (data.books && data.books.length === 0)) {
            resultsEl.innerHTML = '<div class="text-center py-4 text-muted small" role="status">No results found for "' + esc(query) + '"</div>';
            return;
          }

          var items = data.books || data;
          resultsEl.innerHTML = items.slice(0, 8).map(function(item) {
            var id = item.book_id || item.id;
            var title = item.title || 'Unknown';
            var author = item.author || item.authors || 'Unknown';
            return '<div class="sr-item" role="option" onclick="window.location.href=\'/books/' + id + '\'" onkeydown="if(event.key===\'Enter\')window.location.href=\'/books/' + id + '\'" tabindex="0">' +
              '<div style="width:32px;height:48px;border-radius:6px;background:linear-gradient(135deg,var(--color-primary),var(--color-accent));flex-shrink:0;display:flex;align-items:center;justify-content:center;color:white;font-size:.6rem;font-weight:700;">📖</div>' +
              '<div style="flex:1;min-width:0;"><div class="fw-bold small">' + esc(title) + '</div><small class="text-muted">' + esc(author) + '</small></div>' +
              '<small class="text-muted">' + esc(item.category || '') + '</small>' +
              '</div>';
          }).join('');
        })
        .catch(function() {
          resultsEl.innerHTML = '<div class="text-center py-4 text-muted small" role="status">Search error. Please try again.</div>';
        });
    }, 300);
  }

  function searchUsers(query) {
    // For user-specific search (used on Who to Follow, etc.)
    if (query.length < 2) return Promise.resolve([]);
    return fetch('/api/search/users?q=' + encodeURIComponent(query))
      .then(function(r) { return r.json(); })
      .catch(function() { return []; });
  }

  function esc(text) {
    if (!text) return '';
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(String(text)));
    return d.innerHTML;
  }

  // ─── Init ───────────────────────────────────────────────────

  function init() {
    // Wire up global search input
    document.querySelectorAll('.global-search input').forEach(function(input) {
      input.addEventListener('click', function(e) {
        openSearchOverlay();
      });
      input.addEventListener('focus', function(e) {
        openSearchOverlay();
      });
    });

    // Wire up search overlay input
    var searchInput = document.getElementById('searchOverlayInput');
    if (searchInput) {
      searchInput.addEventListener('input', function() {
        searchBooks(this.value);
      });
    }

    // Close on escape
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        closeSearchOverlay();
      }
    });

    // Close on click outside
    var overlay = document.getElementById('searchOverlay');
    if (overlay) {
      overlay.addEventListener('click', function(e) {
        if (e.target === this) closeSearchOverlay();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Export
  window.openSearchOverlay = openSearchOverlay;
  window.closeSearchOverlay = closeSearchOverlay;
  window.searchBooks = searchBooks;
})();
