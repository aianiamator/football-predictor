import ThreeWayBar from "./ThreeWayBar"
import TeamBadge from "./TeamBadge"
import Stars from "./Stars"
import SpeakButton from "./SpeakButton"
import { dict, forecastSentence, type Lang } from "../i18n"
import { initial } from "../lib/colors"
import type { LeagueMeta, Prediction } from "../types"

export function kickoffLabel(p: Prediction, lang: Lang): { day: string; time: string } {
  const d = dict(lang)
  // kickoff_utc is authoritative: the reader's device converts it to their own
  // zone. Falling back to the raw date only when the engine had no time.
  const dt = p.kickoff_utc ? new Date(p.kickoff_utc) : new Date(`${p.date}T12:00:00Z`)

  const today = new Date()
  const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString()
  const tomorrow = new Date(today.getTime() + 86400000)

  let day: string
  if (sameDay(dt, today)) day = d.today
  else if (sameDay(dt, tomorrow)) day = d.tomorrow
  else day = dt.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })

  const time = p.kickoff_utc
    ? dt.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    : ""
  return { day, time }
}

export default function MatchCard({
  p,
  lang,
  voice,
  league,
  onOpen,
}: {
  p: Prediction
  lang: Lang
  voice: string
  league?: LeagueMeta
  onOpen: () => void
}) {
  const d = dict(lang)
  const { day, time } = kickoffLabel(p, lang)
  const sentence = forecastSentence(lang, p.summary_key, p.summary_args, p.summary)
  const barLabel = `${p.home_team} ${p.home_win_pct}%, draw ${p.draw_pct}%, ${p.away_team} ${p.away_win_pct}%`

  return (
    <article className="surface rounded-xl border p-4">
      {/* League and country, small - it identifies, it does not compete. */}
      <div className="muted flex items-center gap-2" style={{ fontSize: 15 }}>
        <span aria-hidden="true">{league?.flag ?? ""}</span>
        <span>{league?.name ?? p.league}</span>
      </div>

      {/* Date and kick-off, large. */}
      <div className="mt-1 flex items-baseline gap-2 font-semibold" style={{ fontSize: 20 }}>
        <span>{day}</span>
        {time && <span className="tabular-nums">{time}</span>}
      </div>

      <button
        type="button"
        onClick={onOpen}
        className="mt-3 block w-full text-left"
        aria-label={`${p.home_team} v ${p.away_team}`}
      >
        <div className="flex items-center gap-3">
          <TeamBadge name={p.home_team} />
          <span className="min-w-0 flex-1 truncate font-bold" style={{ fontSize: 19 }}>
            {p.home_team}
          </span>
          <span className="min-w-0 flex-1 truncate text-right font-bold" style={{ fontSize: 19 }}>
            {p.away_team}
          </span>
          <TeamBadge name={p.away_team} />
        </div>

        <div className="mt-3">
          <ThreeWayBar
            home={p.home_win_pct}
            draw={p.draw_pct}
            away={p.away_win_pct}
            homeLabel={initial(p.home_team)}
            drawLabel={d.drawShort}
            awayLabel={initial(p.away_team)}
            ariaLabel={barLabel}
          />
        </div>
      </button>

      <div className="mt-3 flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <Stars filled={p.confidence_stars} colour={p.confidence_colour} />
          <p className="mt-1" style={{ fontSize: 18, lineHeight: 1.45 }}>
            {sentence}
          </p>
        </div>
        <SpeakButton text={sentence} voiceLang={voice} label={d.listen} />
      </div>
    </article>
  )
}
