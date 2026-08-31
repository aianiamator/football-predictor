import Skeleton from "../components/Skeleton"
import ThreeWayBar from "../components/ThreeWayBar"
import PerformanceBlocks from "../components/PerformanceBlocks"
import { dict, type Lang } from "../i18n"
import { initial } from "../lib/colors"
import type { LeagueMeta, TrackRecord as TR } from "../types"

/**
 * The trust screen.
 *
 * It is never hidden, never filtered, and never sorted to flatter. Misses are
 * drawn exactly as prominently as hits, because a track record that only shows
 * wins is not a track record.
 */
export default function TrackRecord({
  data,
  leagues,
  loading,
  lang,
}: {
  data: TR | null
  leagues: LeagueMeta[]
  loading: boolean
  lang: Lang
}) {
  const d = dict(lang)
  const flagOf = (code: string) => leagues.find((l) => l.code === code)?.flag ?? ""

  if (loading && !data) return <Skeleton count={3} />

  const settled = data?.overall?.matches_settled ?? 0
  const awaiting = data?.awaiting ?? []
  // The published list is capped; the count must be the true total.
  const awaitingTotal = data?.awaiting_total ?? awaiting.length

  return (
    <div className="space-y-4">
      {/* Played, but the result is not published yet.
          This section exists so a match never silently vanishes between being
          forecast and being scored. Without it, a reader cannot tell the
          difference between "waiting" and "quietly dropped because it was
          wrong" - and that doubt would undermine the whole screen. */}
      {awaiting.length > 0 && (
        <section className="surface rounded-xl border p-4">
          <h2 className="font-semibold" style={{ fontSize: 18 }}>
            {d.awaitingResults} ({awaitingTotal})
          </h2>
          <p className="muted mb-3 mt-1" style={{ fontSize: 15, lineHeight: 1.5 }}>
            {d.awaitingHint}
          </p>
          <ul className="space-y-3">
            {awaiting.map((m, i) => (
              <li
                key={i}
                className="border-t pt-3"
                style={{ borderColor: "var(--line)" }}
              >
                {/* League NAME as well as the flag. Windows has no country
                    flag glyphs and renders the underlying letters instead, so
                    a flag alone leaves a Windows reader looking at "PT" with
                    no idea which competition that is. The name costs one line
                    and works on every platform. */}
                <div className="muted mb-1 flex items-baseline gap-2" style={{ fontSize: 15 }}>
                  <span aria-hidden="true">{flagOf(m.league_code)}</span>
                  <span className="min-w-0 flex-1 truncate">{m.league}</span>
                  <span className="shrink-0">{m.date}</span>
                </div>
                <div className="mb-1 truncate font-semibold" style={{ fontSize: 17 }}>
                  {m.home_team} v {m.away_team}
                </div>
                <ThreeWayBar
                  home={m.home_win_pct}
                  draw={m.draw_pct}
                  away={m.away_win_pct}
                  height={28}
                  homeLabel={initial(m.home_team)}
                  drawLabel={d.drawShort}
                  awayLabel={initial(m.away_team)}
                  ariaLabel={`${m.home_team} ${m.home_win_pct}%, draw ${m.draw_pct}%, ${m.away_team} ${m.away_win_pct}%`}
                />
              </li>
            ))}
          </ul>
        </section>
      )}

      {settled === 0 ? (
        <div className="surface rounded-xl border p-6 text-center">
          <p className="font-semibold" style={{ fontSize: 20 }}>
            {d.noneSettled}
          </p>
          <p className="muted mt-1" style={{ fontSize: 17 }}>
            {d.noneSettledHint}
          </p>
        </div>
      ) : (
        <>
          {/* Overall */}
          <section className="surface rounded-xl border p-4">
            <div className="muted font-semibold" style={{ fontSize: 16 }}>
              {d.overallRecord}
            </div>
            <div className="flex items-end gap-3">
              <span className="font-bold tabular-nums" style={{ fontSize: 48, lineHeight: 1.1 }}>
                {data?.overall?.accuracy_pct ?? 0}%
              </span>
              <span className="muted pb-2" style={{ fontSize: 17 }}>
                {settled} {d.settled}
              </span>
            </div>
            <Bar pct={data?.overall?.accuracy_pct ?? 0} />
            {data?.performance?.overall && (
              <div className="muted mt-2" style={{ fontSize: 15, lineHeight: 1.5 }}>
                {data.performance.overall.correct}/{data.performance.overall.completed}{" "}
                {d.correctLabel}
                {data.performance.overall.sample_band !== "larger_sample" && (
                  <>
                    {" · "}
                    {data.performance.overall.sample_band === "very_small"
                      ? d.sampleVerySmall
                      : data.performance.overall.sample_band === "early"
                        ? d.sampleEarly
                        : d.sampleDeveloping}
                  </>
                )}
                {data.performance.overall.unscored_ties > 0 && (
                  <> · {data.performance.overall.unscored_ties} {d.tooCloseToCall}</>
                )}
              </div>
            )}
          </section>

          {data?.performance && <PerformanceBlocks perf={data.performance} lang={lang} />}

          {/* Per league */}
          {(data?.by_league ?? []).map((l) => (
            <section key={l.league_code} className="surface rounded-xl border p-4">
              <div className="flex items-center gap-2 font-semibold" style={{ fontSize: 18 }}>
                <span aria-hidden="true">{flagOf(l.league_code)}</span>
                <span className="min-w-0 truncate">{l.league}</span>
              </div>
              <div className="mt-1 flex items-end gap-3">
                <span className="font-bold tabular-nums" style={{ fontSize: 36, lineHeight: 1.1 }}>
                  {l.accuracy_pct ?? 0}%
                </span>
                <span className="muted pb-1" style={{ fontSize: 16 }}>
                  {l.matches_settled} {d.settled} · {d.since} {l.since}
                </span>
              </div>
              <Bar pct={l.accuracy_pct ?? 0} />
            </section>
          ))}

          {/* Last 20, hits and misses together */}
          <section className="surface rounded-xl border p-4">
            <h2 className="mb-3 font-semibold" style={{ fontSize: 18 }}>
              {d.recentForecasts}
            </h2>
            <ul className="space-y-2">
              {(data?.recent ?? []).map((m, i) => {
                const tie = m.was_correct === null || m.was_correct === undefined
                const hit = m.was_correct === 1
                const pcts = { H: m.home_win_pct, D: m.draw_pct, A: m.away_win_pct }
                const forecast = (Object.keys(pcts) as (keyof typeof pcts)[]).reduce((a, b) =>
                  pcts[a] >= pcts[b] ? a : b,
                )
                const forecastLabel =
                  forecast === "H" ? m.home_team : forecast === "A" ? m.away_team : d.drawShort
                return (
                  <li key={i} className="flex items-center gap-3 border-t pt-2" style={{ borderColor: "var(--line)" }}>
                    <span
                      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-bold text-white"
                      style={{ background: tie ? "#78716c" : hit ? "#15803d" : "#b91c1c" }}
                      aria-label={tie ? d.tooCloseToCall : hit ? d.correct : d.missed}
                    >
                      {tie ? (
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                          <path d="M5 12h14" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                        </svg>
                      ) : hit ? (
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                          <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      ) : (
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                          <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                        </svg>
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold" style={{ fontSize: 17 }}>
                        {m.home_team} {m.actual_home_goals}–{m.actual_away_goals} {m.away_team}
                      </span>
                      <span className="muted block truncate" style={{ fontSize: 15 }}>
                        {forecastLabel} · {m.date}
                      </span>
                    </span>
                  </li>
                )
              })}
            </ul>
          </section>
        </>
      )}

      {/* Always shown, settled or not. */}
      <p
        className="muted rounded-xl border p-4"
        style={{ fontSize: 16, lineHeight: 1.55, borderColor: "var(--line)" }}
      >
        {d.drawWarning}
      </p>
    </div>
  )
}

function Bar({ pct }: { pct: number }) {
  return (
    <div className="mt-2 h-4 w-full overflow-hidden rounded" style={{ background: "var(--line)" }}>
      <div className="h-full rounded" style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: "#15803d" }} />
    </div>
  )
}
