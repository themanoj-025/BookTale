/**
 * charts.js — Chart.js Initialization Manager
 * Ensures all Chart.js canvases render with real data — never left blank
 */

(function() {
  'use strict';

  var chartInstances = {};
  var MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  var COLORS = {
    primary: '#6366f1',
    accent: '#a855f7',
    success: '#22c55e',
    warning: '#eab308',
    danger: '#ef4444',
    info: '#3b82f6',
    pink: '#ec4899'
  };

  function initCharts() {
    // Find all chart canvases and initialize them
    var canvases = document.querySelectorAll('canvas[data-chart]');
    canvases.forEach(function(canvas) {
      var chartType = canvas.getAttribute('data-chart');
      var endpoint = canvas.getAttribute('data-endpoint');
      if (chartType && endpoint) {
        fetchChartData(endpoint, chartType, canvas);
      }
    });

    // Monthly Trends chart (common on dashboard and reports)
    initMonthlyTrendsChart();
    
    // Challenge Monthly Progress
    initChallengeChart();
    
    // Category Distribution
    initCategoryChart();
    
    // Rating Distribution
    initRatingChart();
    
    // Report Charts
    initReportCharts();
  }

  function fetchChartData(endpoint, chartType, canvas) {
    fetch(endpoint)
      .then(function(r) { return r.json(); })
      .then(function(data) {
        renderChart(canvas, chartType, data);
      })
      .catch(function(err) {
        console.warn('Chart data fetch error for', endpoint, err);
        // Show empty state on canvas instead of blank
        var parent = canvas.parentElement;
        if (parent) {
          canvas.style.display = 'none';
          var fallback = parent.querySelector('.chart-fallback');
          if (!fallback) {
            fallback = document.createElement('div');
            fallback.className = 'chart-fallback text-center text-muted small py-4';
            fallback.textContent = 'Chart data unavailable';
            parent.appendChild(fallback);
          }
        }
      });
  }

  function renderChart(canvas, type, data) {
    if (!canvas || !data) return;
    var ctx = canvas.getContext('2d');
    if (!ctx) return;

    var config = getChartConfig(type, data, canvas);
    if (!config) return;

    // Destroy existing instance if any
    if (chartInstances[canvas.id]) {
      chartInstances[canvas.id].destroy();
    }

    try {
      chartInstances[canvas.id] = new Chart(ctx, config);
    } catch (e) {
      console.warn('Chart init error for', canvas.id, e);
    }
  }

  function getChartConfig(type, data, canvas) {
    var baseConfig = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#94a3b8' }
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(0,0,0,0.04)' },
          ticks: { color: getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#94a3b8' }
        }
      }
    };

    switch (type) {
      case 'bar':
        return {
          type: 'bar',
          data: {
            labels: data.labels || [],
            datasets: [{
              data: data.values || [],
              backgroundColor: COLORS.primary,
              borderRadius: 6,
              borderSkipped: false
            }]
          },
          options: Object.assign({}, baseConfig, {
            ariaLabel: canvas.getAttribute('aria-label') || 'Bar chart'
          })
        };

      case 'line':
        return {
          type: 'line',
          data: {
            labels: data.labels || [],
            datasets: [{
              data: data.values || [],
              borderColor: COLORS.primary,
              backgroundColor: 'rgba(99,102,241,0.1)',
              fill: true,
              tension: 0.4,
              pointRadius: 4,
              pointBackgroundColor: COLORS.primary
            }]
          },
          options: Object.assign({}, baseConfig)
        };

      case 'doughnut':
        return {
          type: 'doughnut',
          data: {
            labels: data.labels || [],
            datasets: [{
              data: data.values || [],
              backgroundColor: [COLORS.primary, COLORS.accent, COLORS.success, COLORS.warning, COLORS.danger, COLORS.info, COLORS.pink, '#64748b'],
              borderWidth: 0
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: true, position: 'bottom', labels: { color: getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#94a3b8', padding: 12 } }
            }
          }
        };

      default:
        return null;
    }
  }

  function initMonthlyTrendsChart() {
    var canvas = document.getElementById('monthly-trends-chart');
    if (!canvas) return;

    fetch('/api/analytics/monthly')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data && data.values && data.values.length) {
          renderChart(canvas, 'bar', {
            labels: data.labels || MONTHS,
            values: data.values
          });
        } else {
          // Provide default empty data rather than blank chart
          renderChart(canvas, 'bar', {
            labels: MONTHS,
            values: new Array(12).fill(0)
          });
        }
      })
      .catch(function() {
        renderChart(canvas, 'bar', { labels: MONTHS, values: new Array(12).fill(0) });
      });
  }

  function initChallengeChart() {
    var canvas = document.getElementById('challenge-monthly-chart');
    if (!canvas) return;

    fetch('/api/reading-challenge/stats')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var months = data.monthly_progress || data.months || [];
        renderChart(canvas, 'bar', {
          labels: months.map(function(m) { return m.month || m.label || '?'; }),
          values: months.map(function(m) { return m.books || m.count || 0; })
        });
      })
      .catch(function() {
        renderChart(canvas, 'bar', { labels: MONTHS, values: new Array(12).fill(0) });
      });
  }

  function initCategoryChart() {
    var canvas = document.getElementById('category-chart');
    if (!canvas) return;

    fetch('/api/analytics/categories')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data && data.labels && data.labels.length) {
          renderChart(canvas, 'doughnut', data);
        } else {
          canvas.parentElement.innerHTML = '<div class="text-center text-muted small py-4">No category data</div>';
        }
      })
      .catch(function() {
        canvas.parentElement.innerHTML = '<div class="text-center text-muted small py-4">No category data</div>';
      });
  }

  function initRatingChart() {
    var canvas = document.getElementById('rating-chart');
    if (!canvas) return;

    // This is typically a horizontal bar chart showing rating distribution
    fetch('/api/analytics/ratings')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data && data.labels && data.labels.length) {
          renderChart(canvas, 'bar', data);
        }
      })
      .catch(function() {});
  }

  function initReportCharts() {
    // Reports page may have multiple charts
    var reportChart = document.getElementById('report-monthly-chart');
    if (reportChart) {
      fetch('/api/analytics/monthly')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          renderChart(reportChart, 'bar', {
            labels: data.labels || MONTHS,
            values: data.values || new Array(12).fill(0)
          });
        })
        .catch(function() {
          renderChart(reportChart, 'bar', { labels: MONTHS, values: new Array(12).fill(0) });
        });
    }
  }

  // ─── Init on DOMContentLoaded ───────────────────────────────

  function init() {
    // Wait for Chart.js to be available
    var checkChart = setInterval(function() {
      if (typeof Chart !== 'undefined') {
        clearInterval(checkChart);
        initCharts();
      }
    }, 100);

    // Stop checking after 5 seconds
    setTimeout(function() { clearInterval(checkChart); }, 5000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.booktaleCharts = { initCharts, renderChart };
})();
