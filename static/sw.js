
const CACHE_NAME = 'investcrypto-v1.0.0';
const API_CACHE_NAME = 'investcrypto-api-v1.0.0';

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

// Notifications push avancées
self.addEventListener('push', event => {
  if (!event.data) return;
  
  const data = event.data.json();
  const options = {
    body: data.body || 'Nouvelle notification Ttrust',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/icon-72x72.png',
    image: data.image || null,
    vibrate: data.vibrate || [200, 100, 200],
    sound: data.sound || null,
    data: data.data || {},
    actions: data.actions || [
      {
        action: 'view',
        title: 'Voir',
        icon: '/static/icons/icon-32x32.png'
      },
      {
        action: 'dismiss',
        title: 'Ignorer',
        icon: '/static/icons/icon-32x32.png'
      }
    ],
    requireInteraction: data.requireInteraction || false,
    tag: data.tag || 'default',
    renotify: data.renotify || false,
    silent: data.silent || false,
    timestamp: Date.now(),
    dir: 'ltr',
    lang: 'fr'
  };
  
  // Notification personnalisée selon le type
  if (data.type === 'investment') {
    options.actions = [
      { action: 'view_dashboard', title: '📊 Dashboard', icon: '/static/icons/icon-32x32.png' },
      { action: 'view_profits', title: '💰 Profits', icon: '/static/icons/icon-32x32.png' },
      { action: 'dismiss', title: 'Ignorer', icon: '/static/icons/icon-32x32.png' }
    ];
  } else if (data.type === 'security') {
    options.actions = [
      { action: 'view_security', title: '🔐 Sécurité', icon: '/static/icons/icon-32x32.png' },
      { action: 'lock_account', title: '🔒 Verrouiller', icon: '/static/icons/icon-32x32.png' }
    ];
    options.requireInteraction = true;
    options.vibrate = [300, 100, 300, 100, 300];
  }
  
  event.waitUntil(
    self.registration.showNotification(data.title || 'Ttrust', options)
  );
});

// Cache avancé pour mode hors ligne
const OFFLINE_CACHE_NAME = 'ttrust-offline-v1';
const OFFLINE_PAGES = [
  '/dashboard',
  '/profile',
  '/investment-history',
  '/support',
  '/security'
];

// Mise en cache des pages importantes
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(OFFLINE_CACHE_NAME)
      .then(cache => {
        return cache.addAll(OFFLINE_PAGES);
      })
  );
});

// Synchronisation en arrière-plan pour les données critiques
self.addEventListener('sync', event => {
  if (event.tag === 'sync-investments') {
    event.waitUntil(syncInvestmentData());
  } else if (event.tag === 'sync-security-logs') {
    event.waitUntil(syncSecurityLogs());
  }
});

async function syncInvestmentData() {
  try {
    // Synchroniser les données d'investissement en attente
    const pendingData = await getStoredPendingData('investments');
    if (pendingData.length > 0) {
      for (const data of pendingData) {
        await fetch('/api/sync-investment', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        });
      }
      await clearStoredPendingData('investments');
    }
  } catch (error) {
    console.error('[SW] Erreur sync investissements:', error);
  }
}

async function syncSecurityLogs() {
  try {
    const pendingLogs = await getStoredPendingData('security');
    if (pendingLogs.length > 0) {
      await fetch('/api/sync-security', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ logs: pendingLogs })
      });
      await clearStoredPendingData('security');
    }
  } catch (error) {
    console.error('[SW] Erreur sync sécurité:', error);
  }
}

async function getStoredPendingData(type) {
  const db = await openDB();
  const transaction = db.transaction(['pending'], 'readonly');
  const store = transaction.objectStore('pending');
  const data = await store.getAll();
  return data.filter(item => item.type === type);
}

async function clearStoredPendingData(type) {
  const db = await openDB();
  const transaction = db.transaction(['pending'], 'readwrite');
  const store = transaction.objectStore('pending');
  const data = await store.getAll();
  
  for (const item of data) {
    if (item.type === type) {
      await store.delete(item.id);
    }
  }
}

// IndexedDB pour stockage hors ligne
function openDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('TtrustOfflineDB', 1);
    
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      
      if (!db.objectStoreNames.contains('pending')) {
        const store = db.createObjectStore('pending', { keyPath: 'id', autoIncrement: true });
        store.createIndex('type', 'type', { unique: false });
        store.createIndex('timestamp', 'timestamp', { unique: false });
      }
      
      if (!db.objectStoreNames.contains('userdata')) {
        const userStore = db.createObjectStore('userdata', { keyPath: 'key' });
      }
      
      if (!db.objectStoreNames.contains('security')) {
        const securityStore = db.createObjectStore('security', { keyPath: 'id', autoIncrement: true });
        securityStore.createIndex('timestamp', 'timestamp', { unique: false });
      }
    };
  });
}

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
