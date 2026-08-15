/* ═══════════════════════════════════════════════════════════════════
   api.js — BookTale Shared Fetch Client (IIFE)
   All fetch calls go through this module.
   Handles JSON envelope format, shows toast on error, retries 503.
   ═══════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  /**
   * Convenience: ensure toast.js is loaded (showToast global)
   */
  function _showErrorToast(msg) {
    if (typeof showToast === 'function') {
      showToast(msg, 'error', 5000);
    } else {
      console.error('[BookTale API]', msg);
    }
  }

  /**
   * Debounce a function call.
   */
  function debounce(fn, ms) {
    var timer;
    var debounced = function () {
      var args = arguments;
      var ctx = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(ctx, args); }, ms);
    };
    debounced.cancel = function () { clearTimeout(timer); };
    return debounced;
  }

  /**
   * Main API request function.
   *
   * @param {string} url       — The endpoint
   * @param {object} [opts]    — Fetch options
   * @param {object} [cfg]     — { retries, silent }
   * @returns {Promise<any>}
   */
  async function api(url, opts, cfg) {
    opts = opts || {};
    cfg = cfg || {};
    var retries = cfg.retries !== undefined ? cfg.retries : 1;
    var silent = cfg.silent || false;

    var defaultHeaders = {
      'Accept': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    };

    var body = opts.body;
    if (body && typeof body === 'object' && !(body instanceof FormData)) {
      defaultHeaders['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }

    var mergedOpts = {
      credentials: 'same-origin',
    };
    // Copy opts properties
    for (var key in opts) {
      if (opts.hasOwnProperty(key)) {
        mergedOpts[key] = opts[key];
      }
    }
    mergedOpts.body = body;
    // Merge headers
    mergedOpts.headers = {};
    for (var hk in defaultHeaders) {
      if (defaultHeaders.hasOwnProperty(hk)) mergedOpts.headers[hk] = defaultHeaders[hk];
    }
    if (opts.headers) {
      for (var ohk in opts.headers) {
        if (opts.headers.hasOwnProperty(ohk)) mergedOpts.headers[ohk] = opts.headers[ohk];
      }
    }

    var lastErr;

    for (var attempt = 0; attempt <= retries; attempt++) {
      try {
        var res = await fetch(url, mergedOpts);
        var ct = (res.headers.get('content-type') || '').toLowerCase();
        var payload;

        if (ct.indexOf('application/json') !== -1) {
          payload = await res.json();
        } else {
          var text = await res.text();
          if (!res.ok) {
            throw new Error(text.slice(0, 200) || 'HTTP ' + res.status);
          }
          return text;
        }

        if (!res.ok || payload.success === false) {
          var errMsg = payload.error || payload.message || 'Request failed (' + res.status + ')';
          if (!silent) _showErrorToast(errMsg);
          throw new Error(errMsg);
        }

        return payload.data !== undefined ? payload.data : payload;
      } catch (err) {
        lastErr = err;
        if (attempt < retries) {
          var msg = err.message || '';
          var isRetryable =
            msg.indexOf('503') !== -1 ||
            msg.indexOf('Service Unavailable') !== -1 ||
            msg.indexOf('Failed to fetch') !== -1 ||
            msg.indexOf('NetworkError') !== -1;
          if (isRetryable) {
            await new Promise(function (r) { setTimeout(r, 600 * (attempt + 1)); });
            continue;
          }
        }
      }
    }

    if (!lastErr) lastErr = new Error('Request failed');
    if (!silent) _showErrorToast(lastErr.message);
    throw lastErr;
  }

  /**
   * Shorthand helpers.
   */
  function get(url, cfg) { return api(url, { method: 'GET' }, cfg); }

  function post(url, data, cfg) { return api(url, { method: 'POST', body: data }, cfg); }

  function put(url, data, cfg) { return api(url, { method: 'PUT', body: data }, cfg); }

  function del(url, cfg) { return api(url, { method: 'DELETE' }, cfg); }

  // ── Expose globally ──────────────────────────────────────────────
  window.BookTale = window.BookTale || {};
  window.BookTale.api = {
    request: api,
    get: get,
    post: post,
    put: put,
    del: del,
    debounce: debounce,
  };

  // Also expose individual helpers for inline use
  window.api = api;
  window.debounce = debounce;

})();
