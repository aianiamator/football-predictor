import type { LeagueMeta } from "../types"

/**
 * Large filter buttons, one per league plus All. Selected is filled, the rest
 * outlined - so the current choice is obvious from fill alone, without reading.
 *
 * This row scrolls horizontally BY ITSELF. The page never does.
 */
export default function LeagueFilter({
  leagues,
  selected,
  onSelect,
  allLabel,
}: {
  leagues: LeagueMeta[]
  selected: string | null
  onSelect: (code: string | null) => void
  allLabel: string
}) {
  // shrink-0 is load-bearing. Without it flexbox compresses each button down to
  // the 56px minimum tap size and clips the league name to a letter or two,
  // which is exactly the failure this row exists to avoid.
  const base =
    "tap shrink-0 flex items-center gap-2 whitespace-nowrap rounded-full border-2 px-4 font-semibold"

  return (
    <div className="-mx-4 overflow-x-auto px-4 pb-1" style={{ scrollbarWidth: "none" }}>
      <div className="flex w-max gap-2">
        <button
          type="button"
          onClick={() => onSelect(null)}
          aria-pressed={selected === null}
          className={
            base +
            (selected === null
              ? " border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
              : " surface")
          }
          style={{ fontSize: 18 }}
        >
          {allLabel}
        </button>

        {leagues.map((l) => {
          const on = selected === l.code
          return (
            <button
              key={l.code}
              type="button"
              onClick={() => onSelect(l.code)}
              aria-pressed={on}
              className={
                base +
                (on
                  ? " border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                  : " surface")
              }
              style={{ fontSize: 18 }}
            >
              <span aria-hidden="true">{l.flag}</span>
              <span>{l.name}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
