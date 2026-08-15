/**
 * utils.js — Shared Utility Functions for BookTale
 * Defines showToast, closeAllModals, escapeHtml, timeAgo and other shared helpers
 */

(function () {
  "use strict";

  // ─── Toast Notifications ────────────────────────────────────

  function showToast(msg, type) {
    type = type || "info";
    var container = document.getElementById("toastContainer");
    if (!container) {
      container = document.createElement("div");
      container.id = "toastContainer";
      container.className = "toast-container";
      document.body.appendChild(container);
    }

    var t = document.createElement("div");
    t.className = "toast-msg " + type;

    var icons = {
      success: "bi-check-circle-fill text-success",
      error: "bi-x-circle-fill text-danger",
      info: "bi-info-circle-fill text-info",
    };

    t.innerHTML =
      '<i class="bi ' +
      (icons[type] || icons.info) +
      '"></i> ' +
      escapeHtml(msg) +
      '<div class="toast-progress"></div>';

    container.appendChild(t);

    setTimeout(function () {
      t.style.opacity = "0";
      t.style.transform = "translateX(100%)";
      t.style.transition = "all .3s ease-in";
      setTimeout(function () {
        t.remove();
      }, 350);
    }, 4000);
  }

  // ─── Modal Management ───────────────────────────────────────

  function closeAllModals() {
    document.querySelectorAll(".modal.show").forEach(function (m) {
      if (typeof bootstrap !== "undefined") {
        var bs = bootstrap.Modal.getInstance(m);
        if (bs) bs.hide();
      }
      m.classList.remove("show");
      m.style.display = "none";
    });
  }

  // ─── HTML Escaping ──────────────────────────────────────────

  function escapeHtml(text) {
    if (!text) return "";
    var d = document.createElement("div");
    d.appendChild(document.createTextNode(String(text)));
    return d.innerHTML;
  }

  // ─── JS-string-inside-HTML-attribute Escaping ────────────────
  // For values embedded in inline handlers like onclick="fn('VALUE')":
  // the value must survive (1) the HTML attribute parse (double quotes)
  // and (2) the JS single-quoted string parse (backslashes + quotes).
  // Order matters: backslashes first, then quotes, then double quotes.
  function jsStr(text) {
    return String(text == null ? "" : text)
      .replace(/\\/g, "\\\\")
      .replace(/'/g, "\\'")
      .replace(/"/g, "&quot;");
  }

  // ─── Time Ago ──────────────────────────────────────────────

  function timeAgo(dateStr) {
    if (!dateStr) return "";
    var date = new Date(dateStr);
    var now = new Date();
    var diff = Math.floor((now - date) / 1000);
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m";
    if (diff < 86400) return Math.floor(diff / 3600) + "h";
    if (diff < 2592000) return Math.floor(diff / 86400) + "d";
    return date.toLocaleDateString();
  }

  // ─── Spell Number ───────────────────────────────────────────

  function formatNumber(num) {
    if (num === null || num === undefined) return "—";
    if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
    if (num >= 1000) return (num / 1000).toFixed(1) + "K";
    return num.toLocaleString();
  }

  // ─── Debounce ───────────────────────────────────────────────

  function debounce(fn, delay) {
    var timer;
    return function () {
      var args = arguments;
      var ctx = this;
      clearTimeout(timer);
      timer = setTimeout(function () {
        fn.apply(ctx, args);
      }, delay);
    };
  }

  // ─── Export to window ───────────────────────────────────────

  window.showToast = showToast;
  window.closeAllModals = closeAllModals;
  window.booktaleUtils = {
    escapeHtml: escapeHtml,
    jsStr: jsStr,
    timeAgo: timeAgo,
    formatNumber: formatNumber,
    debounce: debounce,
    showToast: showToast,
    closeAllModals: closeAllModals,
  };
})();
