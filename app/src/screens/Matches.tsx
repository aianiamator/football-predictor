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
  voice,
  onOpen,
}: {
  predictions: Prediction[] | null
  leagues: LeagueMeta[]
  loading: boolean
  lang: Lang
  voice: string
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
  const present = useMemo(() => {
    if (!predictions) return []
    const codes = new Set(predictions.map((p) => p.league_code))
    return leagues.filter((l) => codes.has(l.code))
  }, [predictions, leagues])

  const shown = useMemo(() => {
    if (!predictions) return []
    return selected ? predictions.filter((p) => p.league_code === selected) : predictions
  }, [predictions, selected])

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
              voice={voice}
              league={byCode.get(p.league_code)}
              onOpen={() => onOpen(p)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
