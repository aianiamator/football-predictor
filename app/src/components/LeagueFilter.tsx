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
  const base =
    "tap flex items-center gap-2 whitespace-nowrap rounded-full border-2 px-4 font-semibold"

  return (
    <div className="-mx-4 overflow-x-auto px-4 pb-1" style={{ scrollbarWidth: "none" }}>
      <div className="flex gap-2">
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
