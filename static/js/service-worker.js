const CACHE_NAME = 'la-tribu-cache-v1';
const OFFLINE_URL = '/';

// Archivos estáticos críticos para guardar en la instalación
const PRECACHE_ASSETS = [
    '/',
    '/static/manifest.json',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js',
    'https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css'
];

// 1. INSTALACIÓN: Guardamos los recursos estáticos básicos
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[Service Worker] Pre-caching recursos críticos');
                return cache.addAll(PRECACHE_ASSETS);
            })
            .then(() => self.skipWaiting())
    );
});

// 2. ACTIVACIÓN: Limpiamos cachés viejas si actualizamos la versión
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keyList) => {
            return Promise.all(keyList.map((key) => {
                if (key !== CACHE_NAME) {
                    console.log('[Service Worker] Eliminando caché antigua', key);
                    return caches.delete(key);
                }
            }));
        })
    );
    return self.clients.claim();
});

// 3. FETCH: Interceptamos las peticiones
self.addEventListener('fetch', (event) => {
    // Solo manejamos peticiones GET
    if (event.request.method !== 'GET') return;

    // Estrategia: Network First (Red primero, luego caché) para HTML/Datos
    // Estrategia: Cache First (Caché primero) para estáticos (imágenes, css, js)
    
    const isStatic = event.request.url.includes('/static/') || 
                     event.request.url.includes('cdn.jsdelivr') || 
                     event.request.url.includes('cdnjs.cloudflare');

    if (isStatic) {
        // Cache First para estáticos
        event.respondWith(
            caches.match(event.request).then((cachedResponse) => {
                if (cachedResponse) {
                    return cachedResponse;
                }
                return fetch(event.request).then((networkResponse) => {
                    return caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, networkResponse.clone());
                        return networkResponse;
                    });
                });
            })
        );
    } else {
        // Network First para navegación y datos
        event.respondWith(
            fetch(event.request)
                .then((networkResponse) => {
                    return caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, networkResponse.clone());
                        return networkResponse;
                    });
                })
                .catch(() => {
                    // Si falla la red, intentamos devolver lo que haya en caché
                    return caches.match(event.request);
                })
        );
    }
});