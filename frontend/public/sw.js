/* 考拉出海 PWA Service Worker
 * 策略：
 *  - /assets/*  哈希指纹包  → cache-first（Vite 产物名带 hash，安全可永久缓存）
 *  - 静态图标/manifest        → stale-while-revalidate
 *  - 导航请求（HTML）          → network-first，离线回退到缓存的 index.html
 *  - /api/*                   → 一律 network-only，绝不缓存（含登录态/敏感数据）
 */

const VERSION = 'v1';
const STATIC_CACHE = `smsc-static-${VERSION}`;
const RUNTIME_CACHE = `smsc-runtime-${VERSION}`;
const OFFLINE_URL = '/index.html';

const PRECACHE_URLS = [
  '/index.html',
  '/manifest.webmanifest',
  '/favicon.svg',
  '/icon-192.png',
  '/icon-512.png',
  '/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_URLS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== STATIC_CACHE && k !== RUNTIME_CACHE)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

function isApiRequest(url) {
  return url.pathname.startsWith('/api/');
}

function isHashedAsset(url) {
  return url.pathname.startsWith('/assets/');
}

function isStaticIcon(url) {
  return /\.(svg|png|ico|webmanifest)$/i.test(url.pathname);
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // 永不缓存 API
  if (isApiRequest(url)) return;

  // 哈希指纹包：cache-first
  if (isHashedAsset(url)) {
    event.respondWith(
      caches.match(req).then((cached) => {
        if (cached) return cached;
        return fetch(req).then((res) => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(RUNTIME_CACHE).then((c) => c.put(req, clone));
          }
          return res;
        });
      })
    );
    return;
  }

  // 图标/manifest：stale-while-revalidate
  if (isStaticIcon(url)) {
    event.respondWith(
      caches.open(STATIC_CACHE).then(async (cache) => {
        const cached = await cache.match(req);
        const fetchPromise = fetch(req)
          .then((res) => {
            if (res.ok) cache.put(req, res.clone());
            return res;
          })
          .catch(() => cached);
        return cached || fetchPromise;
      })
    );
    return;
  }

  // 导航请求（HTML）：network-first，失败回退 index.html
  if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res.ok && url.pathname === '/index.html') {
            const clone = res.clone();
            caches.open(STATIC_CACHE).then((c) => c.put(OFFLINE_URL, clone));
          }
          return res;
        })
        .catch(() => caches.match(OFFLINE_URL))
    );
  }
});
