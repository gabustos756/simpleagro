// ==========================================
// EduAgro Modo Campo Service Worker
// Versioned Resilient Caches & Offline Strategy
// ==========================================

const CACHE_SHELL_NAME = 'eduagro-shell-v2';
const CACHE_DATA_NAME = 'eduagro-data-v2';

const APP_SHELL_ASSETS = [
  '/campo',
  '/static/css/main.css',
  '/static/js/campo-offline.js',
  '/static/manifest.webmanifest',
  '/static/icons/icon.svg'
];

// 1. Install Event: Cache App Shell de forma resiliente
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_SHELL_NAME).then(async (cache) => {
      console.log('[Service Worker] Instalando y precacheando App Shell resiliente...');
      for (const asset of APP_SHELL_ASSETS) {
        try {
          const response = await fetch(asset, { credentials: 'same-origin' });
          if (response.ok && !response.redirected) {
            await cache.put(asset, response);
          }
        } catch (err) {
          console.warn('[Service Worker] No se pudo precachear:', asset, err);
        }
      }
    }).then(() => self.skipWaiting())
  );
});

// 2. Activate Event: Limpiar cachés antiguos
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_SHELL_NAME && cacheName !== CACHE_DATA_NAME) {
            console.log('[Service Worker] Eliminando caché antiguo:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// 3. Fetch Event Strategy:
// - /static/ -> Cache-First
// - /campo -> Network-First con Fallback a Caché
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  if (event.request.method !== 'GET') return;

  // Archivos estáticos (/static/): Cache-First con fallback a red
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(event.request).then((networkResponse) => {
          if (networkResponse && networkResponse.ok) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_SHELL_NAME).then((cache) => cache.put(event.request, responseClone));
          }
          return networkResponse;
        });
      })
    );
    return;
  }

  // Ruta /campo: Network-First con Fallback a Caché
  if (url.pathname === '/campo') {
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.ok && !networkResponse.redirected) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_SHELL_NAME).then((cache) => cache.put('/campo', responseClone));
          }
          return networkResponse;
        })
        .catch(() => {
          console.log('[Service Worker] Dispositivo Offline: Devolviendo /campo desde caché');
          return caches.match('/campo').then((cachedPage) => {
            if (cachedPage) return cachedPage;
            return new Response(
              '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>EduAgro Offline</title><link rel="stylesheet" href="/static/css/main.css"></head><body style="padding:2rem;text-align:center;"><h1>📡 EduAgro Modo Campo - Sin Conexión</h1><p>No se pudo conectar al servidor y la vista no está cacheada aún.</p><a href="/campo" class="btn-touch btn-agro" style="margin-top:1rem;display:inline-flex;width:auto;">Reintentar</a></body></html>',
              { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
            );
          });
        })
    );
    return;
  }
});

// 4. Background Sync Listener
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-campo-actions') {
    console.log('[Service Worker] Background Sync activado');
    event.waitUntil(
      self.clients.matchAll().then((clients) => {
        clients.forEach((client) => client.postMessage({ type: 'TRIGGER_SYNC' }));
      })
    );
  }
});
