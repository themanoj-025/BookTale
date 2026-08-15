/**
 * recommendations.js — ML-Powered Book Recommendations
 * Fetches personalized recommendations from the ML model API and renders them
 */

(function() {
  'use strict';

  function loadRecommendations() {
    // For You section — personalized
    loadPersonalizedRecs();

    // Trending section
    loadTrendingRecs();

    // Bestsellers / Popular
    loadPopularRecs();
  }

  function loadPersonalizedRecs() {
    var container = document.getElementById('rec-personalized');
    if (!container) return;

    showSkeleton(container);

    fetch('/api/recommendations/me')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!data || !data.books || !data.books.length) {
          container.innerHTML = '<div class="empty-state"><div class="empty-icon">📚</div><div class="empty-title">No personalized recommendations yet</div><div class="empty-desc">Read and rate more books to get AI-powered suggestions.</div></div>';
          return;
        }

        container.innerHTML = '<div class="book-grid">' +
          data.books.slice(0, 6).map(function(book) {
            var strategy = data.strategy === 'personalized' ? '✨ AI Pick' : '🔥 Popular';
            return '<article class="book-card" aria-label="Book: ' + esc(book.title) + '">' +
              '<figure><a href="/books/' + (book.book_id || book.id) + '">' +
              '<div class="book-cover-placeholder" style="background:linear-gradient(135deg,#6366f1,#a855f7);">📖</div>' +
              '</a>' +
              '<div class="ai-badge" style="position:absolute;top:6px;left:6px;" title="Recommended based on your reading history">' + strategy + '</div>' +
              '</figure>' +
              '<figcaption><h3 style="font-size:.85rem;font-weight:700;margin-top:.3rem;"><a href="/books/' + (book.book_id || book.id) + '">' + esc(book.title) + '</a></h3>' +
              '<p style="font-size:.75rem;color:var(--text-muted)">' + esc(book.authors || book.author || 'Unknown') + '</p>' +
              '</figcaption></article>';
          }).join('') + '</div>';
      })
      .catch(function(err) {
        console.error('Recommendations error:', err);
        container.innerHTML = '<div class="empty-state"><div class="empty-icon">⚠️</div><div class="empty-title">Could not load recommendations</div></div>';
      });
  }

  function loadTrendingRecs() {
    var container = document.getElementById('rec-trending');
    if (!container) return;

    fetch('/api/books/trending')
      .then(function(r) { return r.json(); })
      .then(function(books) {
        if (!books || !books.length) {
          container.innerHTML = '<div class="text-center text-muted small py-3">No trending books yet</div>';
          return;
        }
        container.innerHTML = '<div class="horizontal-scroll">' +
          books.slice(0, 8).map(function(book) {
            return '<div class="book-card" style="width:160px;flex-shrink:0;">' +
              '<figure><a href="/books/' + (book.book_id || book.id) + '">' +
              '<div class="book-cover-placeholder" style="background:linear-gradient(135deg,#a855f7,#ec4899);aspect-ratio:2/3;border-radius:8px;">📖</div>' +
              '</a></figure>' +
              '<figcaption><div style="font-size:.8rem;font-weight:600;margin-top:.25rem;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(book.title) + '</div>' +
              '<div style="font-size:.7rem;color:var(--text-muted)">' + esc(book.author || 'Unknown') + '</div></figcaption></div>';
          }).join('') + '</div>';
      })
      .catch(function() {
        if (container) container.innerHTML = '<div class="text-center text-muted small py-3">No data</div>';
      });
  }

  function loadPopularRecs() {
    var container = document.getElementById('rec-popular');
    if (!container) return;

    fetch('/api/books?sort=popular')
      .then(function(r) { return r.json(); })
      .then(function(books) {
        if (!books || !books.length) {
          container.innerHTML = '<div class="text-center text-muted small py-3">No books yet</div>';
          return;
        }
        container.innerHTML = '<div class="horizontal-scroll">' +
          books.slice(0, 8).map(function(book) {
            return '<div class="book-card" style="width:160px;flex-shrink:0;">' +
              '<figure><a href="/books/' + (book.book_id || book.id) + '">' +
              '<div class="book-cover-placeholder" style="background:linear-gradient(135deg,#6366f1,#818cf8);aspect-ratio:2/3;border-radius:8px;">📖</div>' +
              '</a></figure>' +
              '<figcaption><div style="font-size:.8rem;font-weight:600;margin-top:.25rem;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(book.title) + '</div>' +
              '<div style="font-size:.7rem;color:var(--text-muted)">' + esc(book.author || 'Unknown') + '</div></figcaption></div>';
          }).join('') + '</div>';
      })
      .catch(function() {});
  }

  // ─── Utility ────────────────────────────────────────────────

  function showSkeleton(container) {
    container.innerHTML = '<div class="book-grid">' +
      '<div class="skeleton" style="height:280px;border-radius:10px;"></div>'.repeat(6) +
      '</div>';
  }

  function esc(text) {
    if (!text) return '';
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(String(text)));
    return d.innerHTML;
  }

  // ─── Init ───────────────────────────────────────────────────

  function init() {
    if (document.getElementById('rec-personalized') ||
        document.getElementById('recommendations-page')) {
      loadRecommendations();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.booktaleRecs = { loadRecommendations, loadPersonalizedRecs, loadTrendingRecs };
})();
