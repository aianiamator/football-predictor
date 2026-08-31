import { useMemo, useState } from "react"
import LeagueFilter from "../components/LeagueFilter"
import MatchCard from "../components/MatchCard"
import Skeleton from "../components/Skeleton"
import { dict, type Lang } from "../i18n"
import type { LeagueMeta, Prediction } from "../types"

export default function Matches({
  predictions,
  leagues,
  loading,
  lang,
  onOpen,
}: {
  predictions: Prediction[] | null
  leagues: LeagueMeta[]
  loading: boolean
  lang: Lang
  onOpen: (p: Prediction) => void
}) {
  const d = dict(lang)
  const [selected, setSelected] = useState<string | null>(null)

  const byCode = useMemo(() => {
    const m = new Map<string, LeagueMeta>()
    for (const l of leagues) m.set(l.code, l)
    return m
  }, [leagues])

  // Only offer filters for leagues that actually have fixtures right now.
  // Drop anything that has already kicked off.
  //
  // The engine filters at publish time, but time keeps passing afterwards: a
  // file published at 23:55 legitimately contained that morning's 10:15 match,
  // and by the time someone opens the app it is long finished. Filtering here
  // too means the list stays truthful between publishes instead of only at the
  // moment one happens.
  //
  // `now` is captured per render rather than memoised, so simply reopening the
  // app re-evaluates it.
  const upcoming = useMemo(() => {
    if (!predictions) return []
    const now = Date.now()
    return predictions.filter((p) => {
      if (p.kickoff_utc) return new Date(p.kickoff_utc).getTime() > now
      // No kick-off time published: fall back to the calendar date.
      return p.date >= new Date().toISOString().slice(0, 10)
    })
  }, [predictions])

  const present = useMemo(() => {
    const codes = new Set(upcoming.map((p) => p.league_code))
    return leagues.filter((l) => codes.has(l.code))
  }, [upcoming, leagues])

  const shown = useMemo(() => {
    return selected ? upcoming.filter((p) => p.league_code === selected) : upcoming
  }, [upcoming, selected])

  return (
    <div>
      {present.length > 1 && (
        <div className="mb-4">
          <LeagueFilter
            leagues={present}
            selected={selected}
            onSelect={setSelected}
            allLabel={d.all}
          />
        </div>
      )}

      {loading && !predictions ? (
        <Skeleton />
      ) : shown.length === 0 ? (
        <div className="surface rounded-xl border p-6 text-center">
          <div className="mb-2" style={{ fontSize: 40 }} aria-hidden="true">
            ⚽
          </div>
          <p className="font-semibold" style={{ fontSize: 20 }}>
            {d.noMatches}
          </p>
          <p className="muted mt-1" style={{ fontSize: 17 }}>
            {d.noMatchesHint}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {shown.map((p) => (
            <MatchCard
              key={p.id}
              p={p}
              lang={lang}
              league={byCode.get(p.league_code)}
              onOpen={() => onOpen(p)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
