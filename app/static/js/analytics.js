/**
 * analytics.js — Reading Analytics Dashboard
 * Charts: books per month, genres, pages over time, ratings, reading pace
 */

(function() {
  'use strict';

  function loadAnalytics() {
    loadBooksPerMonth();
    loadGenreDistribution();
    loadPagesOverTime();
    loadRatingDistribution();
    loadReadingPace();
  }

  function loadBooksPerMonth() {
    var canvas = document.getElementById('analytics-books-month');
    if (!canvas) return;
    fetch('/api/analytics/books-monthly')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        renderChart(canvas, 'bar', {
          labels: data.labels || getMonths(),
          values: data.values || new Array(12).fill(0)
        }, '#6366f1');
      })
      .catch(function() {
        renderChart(canvas, 'bar', { labels: getMonths(), values: new Array(12).fill(0) }, '#6366f1');
      });
  }

  function loadGenreDistribution() {
    var canvas = document.getElementById('analytics-genres');
    if (!canvas) return;
    fetch('/api/analytics/categories')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data && data.labels && data.labels.length) {
          renderChart(canvas, 'doughnut', data);
        }
      })
      .catch(function() {});
  }

  function loadPagesOverTime() {
    var canvas = document.getElementById('analytics-pages');
    if (!canvas) return;
    fetch('/api/analytics/pages-monthly')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        renderChart(canvas, 'line', {
          labels: data.labels || getMonths(),
          values: data.values || new Array(12).fill(0)
        }, '#22c55e');
      })
      .catch(function() {
        renderChart(canvas, 'line', { labels: getMonths(), values: new Array(12).fill(0) }, '#22c55e');
      });
  }

  function loadRatingDistribution() {
    var canvas = document.getElementById('analytics-ratings');
    if (!canvas) return;
    fetch('/api/analytics/ratings')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data && data.labels && data.labels.length) {
          renderChart(canvas, 'bar', data, '#eab308');
        }
      })
      .catch(function() {});
  }

  function loadReadingPace() {
    var canvas = document.getElementById('analytics-pace');
    if (!canvas) return;
    fetch('/api/analytics/reading-pace')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        renderChart(canvas, 'line', {
          labels: data.labels || getMonths(),
          values: data.values || new Array(12).fill(0)
        }, '#a855f7');
      })
      .catch(function() {
        renderChart(canvas, 'line', { labels: getMonths(), values: new Array(12).fill(0) }, '#a855f7');
      });
  }

  function renderChart(canvas, type, data, color) {
    if (!canvas || !data) return;
    var ctx = canvas.getContext('2d');
    if (!ctx || typeof Chart === 'undefined') return;

    if (canvas._chart) canvas._chart.destroy();

    var configs = {
      bar: {
        type: 'bar',
        data: {
          labels: data.labels || [],
          datasets: [{ data: data.values || [], backgroundColor: color || '#6366f1', borderRadius: 6 }]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false } },
            y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.04)' } }
          }
        }
      },
      line: {
        type: 'line',
        data: {
          labels: data.labels || [],
          datasets: [{ data: data.values || [], borderColor: color || '#6366f1', backgroundColor: (color || '#6366f1') + '20', fill: true, tension: 0.4 }]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false } },
            y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.04)' } }
          }
        }
      },
      doughnut: {
        type: 'doughnut',
        data: {
          labels: data.labels || [],
          datasets: [{ data: data.values || [], backgroundColor: ['#6366f1','#a855f7','#22c55e','#eab308','#ef4444','#3b82f6','#ec4899','#64748b'], borderWidth: 0 }]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: true, position: 'bottom', labels: { padding: 12 } } }
        }
      }
    };

    var config = configs[type];
    if (config) {
      try { canvas._chart = new Chart(ctx, config); } catch(e) {}
    }
  }

  function getMonths() {
    return ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  }

  function init() {
    if (document.getElementById('analytics-page') || document.querySelector('[data-analytics]')) {
      var check = setInterval(function() {
        if (typeof Chart !== 'undefined') {
          clearInterval(check);
          loadAnalytics();
        }
      }, 100);
      setTimeout(function() { clearInterval(check); }, 5000);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
