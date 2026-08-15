/**
 * streak.js — Reading Streak Tracker 🔥
 * Tracks consecutive days with reading activity. Shows flame icon in top bar and profile.
 */

(function() {
  'use strict';

  function loadStreak() {
    fetch('/api/reading-streak')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var count = data.streak || 0;
        updateStreakUI(count);
      })
      .catch(function() {});
  }

  function updateStreakUI(count) {
    // Update streak in top bar
    var streakEl = document.getElementById('streakBadge');
    if (streakEl) {
      if (count > 0) {
        streakEl.style.display = 'inline-flex';
        streakEl.innerHTML = '🔥 <span>' + count + '</span>';
        streakEl.setAttribute('title', count + '-day reading streak!');
        streakEl.setAttribute('aria-label', count + ' day reading streak');
      } else {
        streakEl.style.display = 'none';
      }
    }

    // Update on profile page
    var profileStreak = document.getElementById('profileStreak');
    if (profileStreak) {
      profileStreak.textContent = count > 0 ? '🔥 ' + count + '-day streak' : 'No streak yet';
    }

    // Trigger toast for milestone streaks
    if (count === 7) {
      if (window.showToast) showToast('🔥 7-day reading streak! Keep it up!', 'success');
    } else if (count === 30) {
      if (window.showToast) showToast('🏆 30-day reading streak! You\'re on fire!', 'success');
    } else if (count === 100) {
      if (window.showToast) showToast('💯 100-day reading streak! Incredible dedication!', 'success');
    }
  }

  function init() {
    if (document.getElementById('streakBadge') || document.getElementById('profileStreak')) {
      loadStreak();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.booktaleStreak = { loadStreak, updateStreakUI };
})();
