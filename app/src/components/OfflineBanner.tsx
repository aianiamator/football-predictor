import { dict, type Lang } from "../i18n"

/**
 * Shown when a refresh failed. It says what is true - you are seeing saved
 * data - rather than pretending everything is fine or blocking the screen.
 */
export default function OfflineBanner({ lang, hasCache }: { lang: Lang; hasCache: boolean }) {
  const d = dict(lang)
  return (
    <div
      role="status"
      className="mb-3 flex items-center gap-2 rounded-lg border border-amber-500 bg-amber-50 px-3 py-2 text-amber-900 dark:bg-amber-950 dark:text-amber-100"
      style={{ fontSize: 16 }}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="shrink-0">
        <path d="M12 3v10M12 17.5v.5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
        <circle cx="12" cy="12" r="9.5" stroke="currentColor" strokeWidth="1.6" />
      </svg>
      <span>{hasCache ? `${d.offline} — ${d.showingSaved}` : d.offline}</span>
    </div>
  )
}
