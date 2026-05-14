// Service Worker minimal — solo pre-cachea iconos.
// Su propósito principal es ayudar a iOS/Android a registrar correctamente
// los iconos de la app la primera vez que se visita la landing.
// NO interceptamos fetch del panel de Streamlit (solo iconos del landing).

const CACHE = "interfs-landing-v3";
const ICONS = [
  "./apple-touch-icon.png?v=3",
  "./apple-touch-icon-precomposed.png?v=3",
  "./apple-touch-icon-180.png?v=3",
  "./apple-touch-icon-152.png?v=3",
  "./apple-touch-icon-167.png?v=3",
  "./apple-touch-icon-120.png?v=3",
  "./icon-192.png?v=3",
  "./icon-512.png?v=3",
  "./manifest.json?v=3",
  "./favicon.ico?v=3",
  "./inter_verde.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ICONS).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = event.request.url;
  // Solo cacheamos iconos y manifest. El panel pasa directo.
  if (url.includes("apple-touch-icon") || url.includes("favicon") ||
      url.includes("icon-") || url.includes("manifest.json") ||
      url.includes("inter_verde.png")) {
    event.respondWith(
      caches.match(event.request).then((r) => r || fetch(event.request))
    );
  }
});
