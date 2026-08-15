/**
 * feed.js — Social Feed Manager
 * Post composition, feed loading, real-time updates, empty states
 */

(function() {
  'use strict';

  let currentTab = 'following';
  let feedCache = {};

  function showSkeleton(containerId) {
    const c = document.getElementById(containerId);
    if (!c) return;
    c.innerHTML = '<div class="skeleton-post" role="status" aria-label="Loading">' +
      '<div class="skeleton-avatar"></div>' +
      '<div class="skeleton-content"><div class="skeleton-line w60"></div><div class="skeleton-line"></div><div class="skeleton-line w40"></div></div></div>'.repeat(3);
  }

  function showEmptyState(containerId, icon, title, desc, ctaText, ctaHref) {
    const c = document.getElementById(containerId);
    if (!c) return;
    c.innerHTML = '<div class="empty-state animate-in">' +
      '<div class="empty-icon">' + icon + '</div>' +
      '<div class="empty-title">' + title + '</div>' +
      '<div class="empty-desc">' + desc + '</div>' +
      (ctaText && ctaHref ? '<a href="' + ctaHref + '" class="empty-cta">' + ctaText + '</a>' : '') +
      '</div>';
  }

  function showError(containerId, message) {
    const c = document.getElementById(containerId);
    if (!c) return;
    c.innerHTML = '<div class="empty-state animate-in">' +
      '<div class="empty-icon">⚠️</div>' +
      '<div class="empty-title">Something went wrong</div>' +
      '<div class="empty-desc">' + (message || "Couldn't load posts. Please try again.") + '</div>' +
      '<button class="empty-cta" onclick="booktaleFeed.refreshFeed()">Try Again</button>' +
      '</div>';
  }

  function renderPost(post) {
    return '<article class="post-card animate-d1" aria-label="Post by @' + post.user_id + '">' +
      '<div class="post-card-body">' +
      '<div class="post-card-header">' +
      '<span class="post-author-name">' + (post.user_name || post.user_id) + '</span>' +
      '<small style="color:var(--text-muted)">@' + post.user_id + '</small>' +
      '<small style="color:var(--text-dim);margin-left:auto">' + timeAgo(post.created_at) + '</small>' +
      '</div>' +
      '<div class="post-content-text">' + escapeHtml(post.content || '') + '</div>' +
      (post.book_id ? '<a href="/books/' + post.book_id + '" class="vibe-tag">📚 ' + escapeHtml(post.book_title || 'Book') + '</a>' : '') +
      '<footer class="post-actions">' +
      '<button class="post-action" onclick="booktaleFeed.likePost(\'' + post.post_id + '\',this)" aria-label="Like" aria-pressed="false">♥ <span>' + (post.likes || 0) + '</span></button>' +
      '<button class="post-action" onclick="window.location.href=\'/feed#comment-' + post.post_id + '\'" aria-label="Comment">💬 <span>' + (post.comments || 0) + '</span></button>' +
      '<button class="post-action" onclick="booktaleFeed.repost(\'' + post.post_id + '\',this)" aria-label="Repost" aria-pressed="false">↻</button>' +
      '</footer></div></article>';
  }

  function loadFeed(tab) {
    currentTab = tab || 'following';
    const containerId = 'feed-content';
    const c = document.getElementById(containerId);
    if (!c) return;

    showSkeleton(containerId);

    // Update tabs
    document.querySelectorAll('.feed-tab').forEach(function(t) {
      const isActive = t.getAttribute('data-tab') === currentTab;
      t.classList.toggle('active', isActive);
      t.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    const endpoint = '/api/feed?tab=' + currentTab + '&page=1';

    fetch(endpoint)
      .then(function(r) {
        if (!r.ok) throw new Error('API error: ' + r.status);
        return r.json();
      })
      .then(function(data) {
        if (!data || !Array.isArray(data) || data.length === 0) {
          handleEmptyTab(currentTab, containerId);
          return;
        }
        c.innerHTML = data.map(renderPost).join('');
      })
      .catch(function(err) {
        console.error('Feed error:', err);
        showError(containerId, "Couldn't load posts. Check your connection and try again.");
      });
  }

  function handleEmptyTab(tab, containerId) {
    var icon, title, desc, ctaText, ctaHref;
    if (tab === 'following') {
      icon = '👥'; title = 'Follow some readers'; desc = 'Follow some readers to see their posts here';
      ctaText = 'Explore Readers →'; ctaHref = '/explore';
    } else if (tab === 'trending') {
      icon = '🔥'; title = 'No trending posts yet'; desc = 'Be the first to post something great';
      ctaText = 'Be the first to post'; ctaHref = '#';
    } else {
      icon = '🔍'; title = 'Discover readers'; desc = 'Find readers with similar interests';
      ctaText = 'Find Readers'; ctaHref = '/search?entity=users';
    }
    showEmptyState(containerId, icon, title, desc, ctaText, ctaHref);
  }

  function submitPost() {
    const textarea = document.getElementById('post-content');
    const content = textarea ? textarea.value.trim() : '';
    if (!content) {
      if (window.showToast) showToast('Write something to post', 'error');
      return;
    }

    const btn = document.getElementById('submit-post');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Posting...'; }

    fetch('/api/posts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) throw new Error(data.error);
      if (textarea) textarea.value = '';
      updateCharCount();
      if (window.showToast) showToast('Post created!', 'success');
      loadFeed(currentTab);
    })
    .catch(function(err) {
      if (window.showToast) showToast(err.message || 'Failed to post', 'error');
    })
    .finally(function() {
      if (btn) { btn.disabled = false; btn.innerHTML = 'Post'; }
    });
  }

  function likePost(postId, btn) {
    fetch('/api/posts/' + postId + '/like', { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.error) throw new Error(data.error);
        var isLiked = btn.classList.toggle('liked');
        btn.setAttribute('aria-pressed', isLiked ? 'true' : 'false');
        var countSpan = btn.querySelector('span');
        if (countSpan) countSpan.textContent = data.likes || 0;
      })
      .catch(function(err) {
        if (window.showToast) showToast(err.message || 'Error', 'error');
      });
  }

  function repost(postId, btn) {
    fetch('/api/posts/' + postId + '/repost', { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.error) throw new Error(data.error);
        var isReposted = btn.classList.toggle('reposted');
        btn.setAttribute('aria-pressed', isReposted ? 'true' : 'false');
        if (window.showToast) showToast(isReposted ? 'Reposted!' : 'Repost removed', 'success');
      })
      .catch(function(err) {
        if (window.showToast) showToast(err.message || 'Error', 'error');
      });
  }

  // ─── Utility ────────────────────────────────────────────────

  function timeAgo(dateStr) {
    if (!dateStr) return '';
    var date = new Date(dateStr);
    var now = new Date();
    var diff = Math.floor((now - date) / 1000);
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h';
    if (diff < 2592000) return Math.floor(diff / 86400) + 'd';
    return date.toLocaleDateString();
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  }

  function updateCharCount() {
    var textarea = document.getElementById('post-content');
    var counter = document.getElementById('char-count');
    if (textarea && counter) {
      counter.textContent = textarea.value.length + ' / 500';
    }
  }

  // ─── Init ───────────────────────────────────────────────────

  function init() {
    // Set up compose box
    var textarea = document.getElementById('post-content');
    if (textarea) {
      textarea.addEventListener('input', updateCharCount);
      var submitBtn = document.getElementById('submit-post');
      if (submitBtn) {
        submitBtn.addEventListener('click', submitPost);
      }
      textarea.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.key === 'Enter') {
          e.preventDefault();
          submitPost();
        }
      });
    }

    // Set up feed tabs
    document.querySelectorAll('.feed-tab').forEach(function(tab) {
      tab.addEventListener('click', function() {
        loadFeed(this.getAttribute('data-tab'));
      });
    });

    // Initial load
    var feedContent = document.getElementById('feed-content');
    if (feedContent) {
      loadFeed('following');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.booktaleFeed = { loadFeed, submitPost, likePost, repost, refreshFeed: function() { loadFeed(currentTab); } };
})();
