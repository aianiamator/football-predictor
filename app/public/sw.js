/**
 * Service worker.
 *
 * App shell: cache-first, so a repeat visit costs almost no data.
 * Data files: network-first with a cache fallback, so a reader who opens the
 * app on a dead connection still sees the last forecasts they downloaded.
 *
 * Bump CACHE when the shell changes; old caches are deleted on activate.
 */
const CACHE = "ff-v1"
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/icon.svg"]

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()),
  )
})

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener("fetch", (e) => {
  const req = e.request
  if (req.method !== "GET") return

  const url = new URL(req.url)
  const isData = url.pathname.endsWith(".json")

  if (isData) {
    // Fresh forecasts matter, but stale ones beat a blank screen.
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone()
          caches.open(CACHE).then((c) => c.put(req, copy))
          return res
        })
        .catch(() => caches.match(req)),
    )
    return
  }

  if (url.origin !== self.location.origin) return

  e.respondWith(
    caches.match(req).then(
      (hit) =>
        hit ??
        fetch(req).then((res) => {
          if (res.ok && res.type === "basic") {
            const copy = res.clone()
            caches.open(CACHE).then((c) => c.put(req, copy))
          }
          return res
        }),
    ),
  )
})
