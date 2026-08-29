/**
 * Service worker.
 *
 * The strategy per request type matters more than it looks:
 *
 *   the page itself  network-first  - so a new deploy actually reaches people
 *   data (*.json)    network-first  - fresh forecasts matter
 *   hashed assets    cache-first    - the filename changes when they change,
 *                                     so a cached copy can never be stale
 *
 * v1 got the first one wrong. It served "/" and "/index.html" cache-first,
 * which meant that once someone had opened the app, their browser kept handing
 * them the OLD index.html forever - and that file names the old JavaScript
 * bundle. Data kept updating, code never did. Every fix shipped after their
 * first visit was invisible to them, with no error to notice. Any cache-first
 * strategy on an HTML entry point has this failure mode.
 *
 * Bump CACHE whenever this file changes; old caches are deleted on activate.
 */
const CACHE = "ff-v2"

// Pre-cached so the app opens offline. These are FALLBACKS, not the primary
// source - the fetch handler still tries the network first for the document.
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

/** Network first, falling back to whatever was cached last time. */
function freshFirst(req) {
  return fetch(req)
    .then((res) => {
      if (res && res.ok) {
        const copy = res.clone()
        caches.open(CACHE).then((c) => c.put(req, copy))
      }
      return res
    })
    .catch(() =>
      caches.match(req).then((hit) => hit || caches.match("/index.html")),
    )
}

self.addEventListener("fetch", (e) => {
  const req = e.request
  if (req.method !== "GET") return

  const url = new URL(req.url)
  if (url.origin !== self.location.origin) return

  const isDocument =
    req.mode === "navigate" ||
    url.pathname === "/" ||
    url.pathname.endsWith("/index.html")
  const isData = url.pathname.endsWith(".json")

  // The page and the data must never be served from a stale cache while the
  // network is available.
  if (isDocument || isData) {
    e.respondWith(freshFirst(req))
    return
  }

  // Everything else - /assets/index-<hash>.js and friends - carries a content
  // hash in its name, so a cached copy is always correct for that name.
  e.respondWith(
    caches.match(req).then(
      (hit) =>
        hit ??
        fetch(req).then((res) => {
          if (res && res.ok && res.type === "basic") {
            const copy = res.clone()
            caches.open(CACHE).then((c) => c.put(req, copy))
          }
          return res
        }),
    ),
  )
})
