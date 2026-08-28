/** Placeholders shaped like the real cards, never a bare spinner. */
export default function Skeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="surface rounded-xl border p-4">
          <div className="skeleton mb-3 h-4 w-1/3 rounded" />
          <div className="mb-4 flex items-center gap-3">
            <div className="skeleton h-11 w-11 rounded-full" />
            <div className="skeleton h-5 flex-1 rounded" />
            <div className="skeleton h-11 w-11 rounded-full" />
          </div>
          <div className="skeleton h-11 w-full rounded-lg" />
        </div>
      ))}
    </div>
  )
}
