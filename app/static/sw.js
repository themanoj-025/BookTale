/* ═══════════════════════════════════════════════════════════════
   BookTale Service Worker v1.0
   Cache-first for static assets, network-first for API/HTML,
   stale-while-revalidate for cover images.
   ═══════════════════════════════════════════════════════════════ */

const CACHE_NAME = 'booktale-v1';
const STATIC_CACHE = 'booktale-static-v1';
const COVER_CACHE = 'booktale-covers-v1';
const API_CACHE = 'booktale-api-v1';

// Assets to pre-cache on install
const PRECACHE_URLS = [
  '/static/css/booktale.css',
  '/static/js/api.js',
  '/static/js/toast.js',
  '/static/js/theme.js',
  '/static/js/search.js',
  '/static/js/animations.js',
  '/static/manifest.json',
  '/static/offline.html'
];

// CDN resources to cache (versioned)
const CDN_CACHE_URLS = [
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.2/font/bootstrap-icons.css',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js'
];

/* ─── Install ────────────────────────────────────────────────── */
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => {
      return cache.addAll(PRECACHE_URLS).catch(err => {
        console.warn('[SW] Pre-cache partial failure:', err);
      }).then(() => {
        // Also cache CDN resources
        return caches.open(CACHE_NAME).then(cache => {
          return cache.addAll(CDN_CACHE_URLS).catch(err => {
            console.warn('[SW] CDN cache partial failure:', err);
          });
        });
      });
    }).then(() => {
      // Skip waiting so the new SW activates immediately
      return self.skipWaiting();
    })
  );
});

/* ─── Activate ───────────────────────────────────────────────── */
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          // Delete old cache versions
          if (cacheName !== STATIC_CACHE && cacheName !== COVER_CACHE &&
              cacheName !== API_CACHE && cacheName !== CACHE_NAME) {
            console.log('[SW] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      // Take control of all clients immediately
      return self.clients.claim();
    })
  );
});

/* ─── Strategy: Cache-First (Static Assets) ──────────────────── */
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) {
    // Return cached, then refresh in background
    fetchAndCache(request, STATIC_CACHE).catch(() => {});
    return cached;
  }
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    // If offline and not in cache, serve offline page for navigation requests
    if (request.mode === 'navigate') {
      return caches.match('/static/offline.html');
    }
    throw err;
  }
}

/* ─── Strategy: Network-First (API & HTML pages) ─────────────── */
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok || response.type === 'opaqueredirect') {
      const cache = await caches.open(API_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    // Offline fallback for navigation
    if (request.mode === 'navigate') {
      return caches.match('/static/offline.html');
    }
    // Return a basic offline JSON response for API calls
    if (request.destination === '' || request.url.includes('/api/')) {
      return new Response(
        JSON.stringify({ success: false, error: 'You are offline. Please check your connection.', offline: true }),
        { status: 503, headers: { 'Content-Type': 'application/json' } }
      );
    }
    throw err;
  }
}

/* ─── Strategy: Stale-While-Revalidate (Cover Images) ────────── */
async function staleWhileRevalidate(request) {
  const cache = await caches.open(COVER_CACHE);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request).then(async response => {
    if (response.ok) {
      // Only cache image responses
      const contentType = response.headers.get('Content-Type') || '';
      if (contentType.startsWith('image/') || request.url.includes('cover')) {
        cache.put(request, response.clone());
      }
    }
    return response;
  }).catch(() => {
    // Fetch failed, return cached or fallback
    return cached || null;
  });

  if (cached) {
    // Return cached immediately, but still fetch in background
    fetchPromise.catch(() => {});
    return cached;
  }

  const result = await fetchPromise;
  if (result) {
    return result;
  }

  // Ultimate fallback — return a minimal placeholder
  return new Response(
    '<svg xmlns="http://www.w3.org/2000/svg" width="140" height="210" viewBox="0 0 140 210"><rect fill="#1a1a22" width="140" height="210"/><text fill="#5c5a75" font-family="sans-serif" font-size="12" x="70" y="105" text-anchor="middle">Offline</text></svg>',
    { headers: { 'Content-Type': 'image/svg+xml', 'Cache-Control': 'no-store' } }
  );
}

/* ─── Helper: fetch and cache ────────────────────────────────── */
async function fetchAndCache(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    return null;
  }
}

/* ─── Should we skip caching this request? ──────────────────── */
function shouldSkipCache(url) {
  // Skip non-GET requests
  // Skip socket.io and analytics
  return url.includes('/socket.io') ||
         url.includes('analytics') ||
         url.endsWith('.map') ||
         url.includes('__pycache__');
}

/* ─── Fetch Handler ──────────────────────────────────────────── */
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests and internal SW requests
  if (request.method !== 'GET' || shouldSkipCache(url.href)) {
    return;
  }

  // Strategy selection based on request type
  if (isStaticAsset(request, url)) {
    // Cache-first for static assets
    event.respondWith(cacheFirst(request));
  } else if (isCoverImage(request, url)) {
    // Stale-while-revalidate for cover images
    event.respondWith(staleWhileRevalidate(request));
  } else if (isApiRequest(request, url)) {
    // Network-first for API calls
    event.respondWith(networkFirst(request));
  } else if (request.mode === 'navigate') {
    // Network-first for HTML navigation
    event.respondWith(networkFirst(request));
  }
  // Everything else passes through normally
});

/* ─── URL classification helpers ─────────────────────────────── */
function isStaticAsset(request, url) {
  const path = url.pathname;
  return path.startsWith('/static/') ||
         path.endsWith('.css') ||
         path.endsWith('.js') ||
         path.endsWith('.woff2') ||
         path.endsWith('.woff') ||
         path.endsWith('.ttf') ||
         path.endsWith('.svg') ||
         path.endsWith('.png') ||
         path.endsWith('.jpg') ||
         path.endsWith('.jpeg') ||
         path.endsWith('.webp') ||
         path.endsWith('.ico') ||
         path.endsWith('.json') ||
         url.hostname === 'cdn.jsdelivr.net' ||
         url.hostname === 'fonts.googleapis.com' ||
         url.hostname === 'fonts.gstatic.com';
}

function isCoverImage(request, url) {
  const path = url.pathname;
  return path.startsWith('/covers/') ||
         url.hostname === 'covers.openlibrary.org' ||
         url.hostname === 'books.google.com' ||
         path.includes('cover');
}

function isApiRequest(request, url) {
  return url.pathname.startsWith('/api/');
}

/* ─── Message Handling ───────────────────────────────────────── */
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data && event.data.type === 'CLEAR_CACHES') {
    caches.keys().then(names => {
      Promise.all(names.map(name => caches.delete(name))).then(() => {
        event.ports[0].postMessage({ success: true });
      });
    });
  }
});
