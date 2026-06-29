const CACHE_NAME = 'myCloudNote-v1.0.0';
const BASE_PATH = '/myCloudNotes/';

// Fichiers à mettre en cache pour fonctionnement hors ligne
const STATIC_CACHE_URLS = [
  BASE_PATH,
  BASE_PATH + 'index.html',
  'https://cdnjs.cloudflare.com/ajax/libs/pouchdb/8.0.1/pouchdb.min.js'
];

// Installation du Service Worker
self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installation...');
  
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[Service Worker] Mise en cache des fichiers statiques');
      return cache.addAll(STATIC_CACHE_URLS);
    })
  );
  
  // Force le nouveau service worker à devenir actif immédiatement
  self.skipWaiting();
});

// Activation du Service Worker
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activation...');
  
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          // Supprimer les anciens caches
          if (cacheName !== CACHE_NAME) {
            console.log('[Service Worker] Suppression ancien cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  
  // Prendre le contrôle de toutes les pages immédiatement
  return self.clients.claim();
});

// Interception des requêtes
self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);
  
  // Ignorer les requêtes non-GET
  if (event.request.method !== 'GET') {
    return;
  }
  
  // Stratégie pour les requêtes API : Network First (toujours essayer le réseau d'abord)
  if (requestUrl.pathname.includes('/mcn/')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          return response;
        })
        .catch(() => {
          // En cas d'échec réseau pour l'API, retourner une réponse offline
          return new Response(
            JSON.stringify({ 
              error: 'Hors ligne', 
              offline: true 
            }), 
            {
              headers: { 'Content-Type': 'application/json' },
              status: 503
            }
          );
        })
    );
    return;
  }
  
  // Stratégie pour PouchDB/CouchDB : Network First
  if (requestUrl.hostname.includes('couchdb.mcn') && requestUrl.port === '5984') {
    event.respondWith(
      fetch(event.request).catch(() => {
        // PouchDB gère lui-même le mode offline
        return new Response(null, { status: 503 });
      })
    );
    return;
  }
  
  // Stratégie Cache First pour les fichiers statiques
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        // Fichier trouvé dans le cache
        return cachedResponse;
      }
      
      // Fichier non trouvé dans le cache, récupérer du réseau
      return fetch(event.request).then((response) => {
        // Ne pas mettre en cache les réponses non-OK
        if (!response || response.status !== 200 || response.type === 'error') {
          return response;
        }
        
        // Cloner la réponse car elle ne peut être utilisée qu'une seule fois
        const responseToCache = response.clone();
        
        // Mettre en cache uniquement les ressources du même domaine
        if (requestUrl.origin === location.origin || 
            requestUrl.hostname === 'cdnjs.cloudflare.com') {
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        
        return response;
      }).catch(() => {
        // En cas d'échec réseau, retourner la page index.html du cache
        if (event.request.mode === 'navigate') {
          return caches.match(BASE_PATH + 'index.html');
        }
      });
    })
  );
});

// Écouter les messages du client
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'CACHE_URLS') {
    event.waitUntil(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.addAll(event.data.urls);
      })
    );
  }
});

// Gestion de la synchronisation en arrière-plan (optionnel)
self.addEventListener('sync', (event) => {
  console.log('[Service Worker] Synchronisation en arrière-plan:', event.tag);
  
  if (event.tag === 'sync-notes') {
    event.waitUntil(
      // PouchDB gère la synchronisation automatiquement
      Promise.resolve()
    );
  }
}); 