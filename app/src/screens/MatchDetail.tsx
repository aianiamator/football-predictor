import ThreeWayBar from "../components/ThreeWayBar"
import TeamBadge from "../components/TeamBadge"
import Stars from "../components/Stars"
import SpeakButton from "../components/SpeakButton"
import PickBadge from "../components/PickBadge"
import { kickoffLabel } from "../components/MatchCard"
import { dict, forecastSentence, type Lang } from "../i18n"
import { initial } from "../lib/colors"
import type { LeagueMeta, Prediction } from "../types"

/** Whole goals as full balls, the remainder as a half-size one. */
function GoalDots({ value, colour }: { value: number; colour: string }) {
  const whole = Math.floor(value)
  const rest = value - whole
  return (
    <span className="inline-flex items-center gap-1" aria-hidden="true">
      {Array.from({ length: Math.min(whole, 8) }).map((_, i) => (
        <span key={i} style={{ fontSize: 22 }}>
          ⚽
        </span>
      ))}
      {rest >= 0.25 && <span style={{ fontSize: 13, opacity: 0.85 }}>⚽</span>}
      <span className="ml-1 font-bold tabular-nums" style={{ fontSize: 22, color: colour }}>
        {value.toFixed(1)}
      </span>
    </span>
  )
}

/** Over/under as a donut. Never labelled with market jargon. */
function Donut({ pct, over, under }: { pct: number; over: string; under: string }) {
  const r = 52
  const c = 2 * Math.PI * r
  const filled = (pct / 100) * c
  return (
    <div className="flex items-center gap-4">
      <svg width="130" height="130" viewBox="0 0 130 130" role="img" aria-label={`${over}: ${pct}%`}>
        <circle cx="65" cy="65" r={r} fill="none" stroke="#cbd5e1" strokeWidth="20" />
        <circle
          cx="65"
          cy="65"
          r={r}
          fill="none"
          stroke="#15803d"
          strokeWidth="20"
          strokeDasharray={`${filled} ${c - filled}`}
          strokeDashoffset={c / 4}
          transform="rotate(-90 65 65)"
        />
        <text
          x="65"
          y="72"
          textAnchor="middle"
          fontSize="26"
          fontWeight="700"
          fill="currentColor"
        >
          {pct}%
        </text>
      </svg>
      <div style={{ fontSize: 17 }}>
        <div className="mb-2 flex items-center gap-2">
          <span className="inline-block h-4 w-4 rounded" style={{ background: "#15803d" }} />
          <span className="font-semibold">{over}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block h-4 w-4 rounded" style={{ background: "#cbd5e1" }} />
          <span className="muted">{under}</span>
        </div>
      </div>
    </div>
  )
}

export default function MatchDetail({
  p,
  league,
  lang,
  onBack,
}: {
  p: Prediction
  league?: LeagueMeta
  lang: Lang
  onBack: () => void
}) {
  const d = dict(lang)
  const { day, time } = kickoffLabel(p, lang)
  const sentence = forecastSentence(lang, p.summary_key, p.summary_args, p.summary)

  const eh = p.expected_goals_home ?? 0
  const ea = p.expected_goals_away ?? 0
  const lines = p.likely_scorelines ?? []
  const maxProb = lines.length ? Math.max(...lines.map((l) => l.prob)) : 1

  // Everything the speaker reads, in the reader's language.
  const spoken = [
    `${p.home_team} ${p.home_win_pct}%.`,
    `${d.drawShort === "=" ? "Draw" : d.drawShort} ${p.draw_pct}%.`,
    `${p.away_team} ${p.away_win_pct}%.`,
    sentence,
    p.likely_score ? `${d.mostLikelyScore}: ${p.likely_score}.` : "",
  ]
    .filter(Boolean)
    .join(" ")

  return (
    <div className="pb-24">
      <div className="muted flex items-center gap-2" style={{ fontSize: 16 }}>
        <span aria-hidden="true">{league?.flag ?? ""}</span>
        <span>{league?.name ?? p.league}</span>
      </div>

      <div className="mt-1 flex items-baseline gap-2 font-bold" style={{ fontSize: 24 }}>
        <span>{day}</span>
        {time && <span className="tabular-nums">{time}</span>}
      </div>

      <div className="mt-4 flex items-center gap-3">
        <TeamBadge name={p.home_team} size={52} />
        <span className="min-w-0 flex-1 truncate font-bold" style={{ fontSize: 21 }}>
          {p.home_team}
        </span>
        <span className="min-w-0 flex-1 truncate text-right font-bold" style={{ fontSize: 21 }}>
          {p.away_team}
        </span>
        <TeamBadge name={p.away_team} size={52} />
      </div>

      <div className="mt-4">
        <ThreeWayBar
          home={p.home_win_pct}
          draw={p.draw_pct}
          away={p.away_win_pct}
          height={64}
          homeLabel={initial(p.home_team)}
          drawLabel={d.drawShort}
          awayLabel={initial(p.away_team)}
          ariaLabel={`${p.home_team} ${p.home_win_pct}%, draw ${p.draw_pct}%, ${p.away_team} ${p.away_win_pct}%`}
        />
      </div>

      <PickBadge p={p} lang={lang} />

      <div className="mt-4 flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <Stars filled={p.confidence_stars} colour={p.confidence_colour} />
          <p className="mt-1" style={{ fontSize: 18, lineHeight: 1.45 }}>
            {sentence}
          </p>
        </div>
        <SpeakButton text={spoken} lang={lang} label={d.listen} />
      </div>

      {/* Likely goals */}
      <section className="surface mt-5 rounded-xl border p-4">
        <h2 className="muted mb-3 font-semibold" style={{ fontSize: 16 }}>
          {d.likelyGoals}
        </h2>
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <span className="min-w-0 truncate font-semibold" style={{ fontSize: 18 }}>
              {p.home_team}
            </span>
            <GoalDots value={eh} colour="#15803d" />
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="min-w-0 truncate font-semibold" style={{ fontSize: 18 }}>
              {p.away_team}
            </span>
            <GoalDots value={ea} colour="#1d4ed8" />
          </div>
        </div>
      </section>

      {/* Most likely score */}
      {p.likely_score && (
        <section className="surface mt-4 rounded-xl border p-4">
          <h2 className="muted mb-1 font-semibold" style={{ fontSize: 16 }}>
            {d.mostLikelyScore}
          </h2>
          <div className="text-center font-bold tabular-nums" style={{ fontSize: 60, lineHeight: 1.1 }}>
            {p.likely_score}
          </div>

          {lines.length > 1 && (
            <>
              <h3 className="muted mb-2 mt-4 font-semibold" style={{ fontSize: 16 }}>
                {d.otherScores}
              </h3>
              <div className="space-y-2">
                {lines.slice(0, 5).map((l, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="w-12 shrink-0 font-bold tabular-nums" style={{ fontSize: 18 }}>
                      {l.home_goals}-{l.away_goals}
                    </span>
                    <div className="h-5 flex-1 overflow-hidden rounded" style={{ background: "var(--line)" }}>
                      <div
                        className="h-full rounded"
                        style={{ width: `${(l.prob / maxProb) * 100}%`, background: "#64748b" }}
                      />
                    </div>
                    <span className="muted w-12 shrink-0 text-right tabular-nums" style={{ fontSize: 16 }}>
                      {Math.round(l.prob * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      )}

      {/* Over/under, only where backtesting found a real edge. */}
      {typeof p.over_2_5_pct === "number" && (
        <section className="surface mt-4 rounded-xl border p-4">
          <Donut pct={p.over_2_5_pct} over={d.threeOrMore} under={d.twoOrFewer} />
        </section>
      )}

      {/* Fixed back button: always reachable, never more than one tap away. */}
      <div className="fixed inset-x-0 bottom-0 border-t p-3" style={{ background: "var(--bg)", borderColor: "var(--line)" }}>
        <button
          type="button"
          onClick={onBack}
          className="tap mx-auto flex w-full max-w-lg items-center justify-center gap-2 rounded-xl bg-slate-900 font-bold text-white dark:bg-slate-100 dark:text-slate-900"
          style={{ fontSize: 19 }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M15 5l-7 7 7 7" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {d.back}
        </button>
      </div>
    </div>
  )
}
