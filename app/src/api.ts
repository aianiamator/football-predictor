/**
 * Data loading. Three static files, no client library, no key.
 *
 * Strategy is cache-first: whatever was saved last time renders immediately,
 * then a background fetch refreshes it. On a slow or expensive connection the
 * reader sees content straight away and pays only for the refresh — and if the
 * refresh fails, they keep the saved copy plus an honest offline banner.
 */
import type { Meta, Prediction, TrackRecord } from "./types"

// Where the published JSON lives. Set VITE_DATA_URL at build time to point at
// Cloudflare; defaults to same-origin /data for local development.
const BASE = (import.meta.env.VITE_DATA_URL ?? "/data").replace(/\/$/, "")

const CACHE_PREFIX = "ff.cache."
// Saved data older than this is still shown, but a refresh is prioritised.
export const STALE_AFTER_MS = 60 * 60 * 1000

type Cached<T> = { at: number; data: T }

export function readCache<T>(name: string): Cached<T> | null {
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + name)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Cached<T>
    if (typeof parsed?.at !== "number") return null
    return parsed
  } catch {
    return null
  }
}

function writeCache<T>(name: string, data: T) {
  try {
    localStorage.setItem(CACHE_PREFIX + name, JSON.stringify({ at: Date.now(), data }))
  } catch {
    // Quota or private mode. The app still works, it just will not be offline-ready.
  }
}

async function fetchJson<T>(file: string): Promise<T> {
  const res = await fetch(`${BASE}/${file}`, { cache: "no-cache" })
  if (!res.ok) throw new Error(`${file}: ${res.status}`)
  return (await res.json()) as T
}

/**
 * Return cached data at once (if any), then fetch fresh and call `onFresh`.
 * Never throws: a failed refresh is reported through `onError` so the UI can
 * show a banner while continuing to display what it already has.
 */
export function loadWithCache<T>(
  file: string,
  onFresh: (data: T, cached: boolean) => void,
  onError: () => void,
): void {
  const cached = readCache<T>(file)
  if (cached) onFresh(cached.data, true)

  fetchJson<T>(file)
    .then((fresh) => {
      writeCache(file, fresh)
      onFresh(fresh, false)
    })
    .catch(() => {
      onError()
    })
}

export const files = {
  predictions: "predictions.json",
  track: "track-record.json",
  meta: "meta.json",
}

export type { Meta, Prediction, TrackRecord }
