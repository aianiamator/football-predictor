import { dict, type Lang } from "../i18n"
import type { Block, Performance } from "../types"

/**
 * The analytics half of the track record.
 *
 * Two rules run through all of it:
 *
 *  1. No rate without its denominator. "100%" over three matches is noise, and
 *     showing it bare would be the most misleading thing this product could do.
 *     Every figure carries its sample size and a plain warning while that
 *     sample is thin.
 *  2. Nothing is hidden because it looks bad. A confidence band that performs
 *     worse than a lower one is exactly what a reader needs to see, since the
 *     whole point of publishing this is to find out whether being more sure
 *     actually helps.
 */

function sampleNote(band: string, d: ReturnType<typeof dict>): string {
  switch (band) {
    case "larger_sample": return d.sampleLarger
    case "developing": return d.sampleDeveloping
    case "early": return d.sampleEarly
    default: return d.sampleVerySmall
  }
}

function Bar({ pct, colour = "#15803d" }: { pct: number | null; colour?: string }) {
  return (
    <div className="mt-1 h-3 w-full overflow-hidden rounded" style={{ background: "var(--line)" }}>
      <div
        className="h-full rounded"
        style={{ width: `${Math.max(0, Math.min(100, pct ?? 0))}%`, background: colour }}
      />
    </div>
  )
}

/** One row: a label, a rate, its sample, and a bar so the number has a shape. */
export function StatRow({
  label,
  block,
  lang,
}: {
  label: string
  block: Block
  lang: Lang
}) {
  const d = dict(lang)
  return (
    <li className="border-t pt-3" style={{ borderColor: "var(--line)" }}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="min-w-0 truncate font-semibold" style={{ fontSize: 17 }}>
          {label}
        </span>
        <span className="shrink-0 font-bold tabular-nums" style={{ fontSize: 20 }}>
          {block.hit_rate ?? 0}%
        </span>
      </div>
      <Bar pct={block.hit_rate} />
      <div className="muted mt-1" style={{ fontSize: 15 }}>
        {block.correct}/{block.completed} {d.correctLabel}
        {block.sample_band !== "larger_sample" && (
          <> · {sampleNote(block.sample_band, d)}</>
        )}
      </div>
    </li>
  )
}

export default function PerformanceBlocks({
  perf,
  lang,
}: {
  perf: Performance
  lang: Lang
}) {
  const d = dict(lang)
  const o = perf.overall
  if (!o.completed) return null

  const confLabel: Record<string, string> = {
    high: d.confHigh, strong: d.confStrong, moderate: d.confModerate, low: d.confLow,
  }
  const pickLabel: Record<string, string> = {
    home: d.homeShort, draw: d.drawShort, away: d.awayShort,
  }

  return (
    <>
      {/* Does being more sure actually help? The question the bands exist for. */}
      {perf.by_confidence.length > 0 && (
        <section className="surface rounded-xl border p-4">
          <h2 className="font-semibold" style={{ fontSize: 18 }}>{d.byConfidence}</h2>
          <p className="muted mb-3 mt-1" style={{ fontSize: 15 }}>{d.howSureWeWere}</p>
          <ul className="space-y-3">
            {perf.by_confidence.map((b) => (
              <StatRow key={b.band} label={confLabel[b.band] ?? b.band} block={b} lang={lang} />
            ))}
          </ul>
        </section>
      )}

      {/* Draws are the hard case, so they get their own line rather than
          being averaged away into an overall number. */}
      {perf.by_outcome.length > 0 && (
        <section className="surface rounded-xl border p-4">
          <h2 className="mb-3 font-semibold" style={{ fontSize: 18 }}>{d.byOutcome}</h2>
          <ul className="space-y-3">
            {perf.by_outcome.map((b) => (
              <StatRow key={b.pick} label={pickLabel[b.pick] ?? b.pick} block={b} lang={lang} />
            ))}
          </ul>
        </section>
      )}

      {perf.by_league.length > 0 && (
        <section className="surface rounded-xl border p-4">
          <h2 className="mb-3 font-semibold" style={{ fontSize: 18 }}>{d.byLeague}</h2>
          <ul className="space-y-3">
            {perf.by_league.map((b) => (
              <StatRow key={b.league_code} label={b.league} block={b} lang={lang} />
            ))}
          </ul>
        </section>
      )}

      {/* The baseline is the honest bar: what you would get with no model at
          all, on the same matches. Publishing our rate without it would let a
          number that beats nothing look like skill. */}
      {perf.baselines.always_home && (
        <section className="surface rounded-xl border p-4">
          <div className="flex items-baseline justify-between gap-2">
            <span className="muted" style={{ fontSize: 16 }}>{d.vsAlwaysHome}</span>
            <span
              className="shrink-0 font-bold tabular-nums"
              style={{
                fontSize: 20,
                color:
                  (perf.baselines.model_vs_always_home_points ?? 0) >= 0
                    ? "#15803d"
                    : "#b91c1c",
              }}
            >
              {(perf.baselines.model_vs_always_home_points ?? 0) >= 0 ? "+" : ""}
              {perf.baselines.model_vs_always_home_points ?? 0}pp
            </span>
          </div>
          <div className="muted mt-1" style={{ fontSize: 15 }}>
            {o.hit_rate}% · {perf.baselines.always_home.hit_rate}%
          </div>
        </section>
      )}
    </>
  )
}
