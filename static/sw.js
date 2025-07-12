const CACHE_NAME = 'ttrust-v1.1.0';
const STATIC_CACHE = 'ttrust-static-v1.1.0';
const DYNAMIC_CACHE = 'ttrust-dynamic-v1.1.0';

// Ressources à mettre en cache immédiatement
const STATIC_CACHE_URLS = [
  '/',
  '/static/manifest.json',
  '/dashboard',
  '/staking-plans',
  '/projects',
  '/profile',
  '/support',
  // CSS externes
  'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap',
  // Offline fallback
  '/static/offline.html'
];

// URLs d'API à mettre en cache
const API_CACHE_PATTERNS = [
  /\/api\//,
  /\/dashboard/,
  /\/staking-plans/,
  /\/projects/,
  /\/profile/
];

// Installation du Service Worker
self.addEventListener('install', event => {
  console.log('[SW] Installing...');

  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[SW] Caching static resources');
        return cache.addAll(STATIC_CACHE_URLS.map(url => new Request(url, {
          cache: 'reload'
        })));
      })
      .then(() => {
        console.log('[SW] Installation completed');
        return self.skipWaiting();
      })
      .catch(error => {
        console.error('[SW] Installation failed:', error);
      })
  );
});

// Activation du Service Worker
self.addEventListener('activate', event => {
  console.log('[SW] Activating...');

  event.waitUntil(
    Promise.all([
      // Nettoyer les anciens caches
      caches.keys().then(cacheNames => {
        return Promise.all(
          cacheNames.map(cacheName => {
            if (cacheName !== CACHE_NAME && cacheName !== API_CACHE_NAME) {
              console.log('[SW] Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      }),
      // Prendre le contrôle de tous les clients
      self.clients.claim()
    ]).then(() => {
      console.log('[SW] Activation completed');
    })
  );
});

// Stratégies de cache
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Ignorer les requêtes non-HTTP
  if (!request.url.startsWith('http')) {
    return;
  }

  // Stratégie pour les pages HTML
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(networkFirstWithFallback(request));
    return;
  }

  // Stratégie pour les API
  if (API_CACHE_PATTERNS.some(pattern => pattern.test(url.pathname))) {
    event.respondWith(networkFirstWithCache(request));
    return;
  }

  // Stratégie pour les ressources statiques
  if (isStaticResource(request)) {
    event.respondWith(cacheFirstWithNetwork(request));
    return;
  }

  // Par défaut: network first
  event.respondWith(networkFirstWithCache(request));
});

// Stratégie: Network First avec fallback
async function networkFirstWithFallback(request) {
  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (error) {
    console.log('[SW] Network failed, trying cache:', request.url);

    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    // Fallback vers la page offline pour les requêtes de navigation
    if (request.mode === 'navigate') {
      return caches.match('/static/offline.html');
    }

    throw error;
  }
}

// Stratégie: Network First avec cache
async function networkFirstWithCache(request) {
  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      const cache = await caches.open(API_CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (error) {
    console.log('[SW] Network failed, trying cache:', request.url);

    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    throw error;
  }
}

// Stratégie: Cache First avec network fallback
async function cacheFirstWithNetwork(request) {
  const cachedResponse = await caches.match(request);

  if (cachedResponse) {
    // Mise à jour en arrière-plan
    fetch(request).then(response => {
      if (response.ok) {
        const cache = caches.open(CACHE_NAME);
        cache.then(c => c.put(request, response));
      }
    }).catch(() => {});

    return cachedResponse;
  }

  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (error) {
    console.error('[SW] Both cache and network failed:', request.url);
    throw error;
  }
}

// Vérifier si c'est une ressource statique
function isStaticResource(request) {
  const url = new URL(request.url);
  return url.pathname.includes('/static/') ||
         url.hostname !== location.hostname ||
         request.destination === 'image' ||
         request.destination === 'font' ||
         request.destination === 'style' ||
         request.destination === 'script';
}

// Gestion des messages
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }

  if (event.data && event.data.type === 'GET_VERSION') {
    event.ports[0].postMessage({ version: CACHE_NAME });
  }
});

// Synchronisation en arrière-plan
self.addEventListener('sync', event => {
  if (event.tag === 'background-sync') {
    event.waitUntil(doBackgroundSync());
  }
});

async function doBackgroundSync() {
  try {
    // Synchroniser les données en attente
    console.log('[SW] Background sync triggered');

    // Ici vous pouvez ajouter la logique pour synchroniser les données
    // Par exemple, envoyer les transactions en attente

  } catch (error) {
    console.error('[SW] Background sync failed:', error);
  }
}

// Notifications push
self.addEventListener('push', event => {
  if (!event.data) return;

  const data = event.data.json();
  const options = {
    body: data.body || 'Nouvelle notification Ttrust',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/badge-72x72.png',
    vibrate: [200, 100, 200],
    data: data.data || {},
    actions: [
      {
        action: 'view',
        title: 'Voir',
        icon: '/static/icons/view-24x24.png'
      },
      {
        action: 'dismiss',
        title: 'Ignorer',
        icon: '/static/icons/dismiss-24x24.png'
      }
    ],
    requireInteraction: data.requireInteraction || false,
    tag: data.tag || 'default'
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'Ttrust', options)
  );
});

// Gestion des clics sur notifications
self.addEventListener('notificationclick', event => {
  event.notification.close();

  if (event.action === 'view') {
    event.waitUntil(
      clients.openWindow(event.notification.data.url || '/dashboard')
    );
  } else if (event.action !== 'dismiss') {
    event.waitUntil(
      clients.openWindow('/dashboard')
    );
  }
});