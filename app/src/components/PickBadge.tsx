import { dict, type Lang } from "../i18n"
import type { Prediction } from "../types"

const CONF_LABEL: Record<string, keyof ReturnType<typeof dict>> = {
  high: "confHigh",
  strong: "confStrong",
  moderate: "confModerate",
  low: "confLow",
}

// Colour follows the same scale as the confidence stars, so the two never
// disagree on screen. Warm stone for low, matching the rule that grey means
// exactly one thing per screen.
const CONF_COLOUR: Record<string, string> = {
  high: "#15803d",
  strong: "#166534",
  moderate: "#b45309",
  low: "#78716c",
}

/**
 * What the model actually picked, how sure it was, and by how much.
 *
 * The margin is the part readers cannot work out at a glance. 41/27/32 and
 * 41/18/41 share a top number but the first has a 9-point edge and the second
 * is a dead heat. Showing the gap stops the top percentage being read as
 * confidence on its own.
 *
 * A fixture with no separable favourite says so plainly rather than naming an
 * arbitrary side - and the engine leaves those unscored, so the badge and the
 * track record tell the same story.
 */
export default function PickBadge({ p, lang }: { p: Prediction; lang: Lang }) {
  const d = dict(lang)
  if (!p.model_pick) return null

  const tie = p.model_pick === "TIE"
  const team =
    p.model_pick === "H" ? p.home_team : p.model_pick === "A" ? p.away_team : d.drawShort
  const band = p.confidence_band ?? "low"
  const colour = tie ? CONF_COLOUR.low : CONF_COLOUR[band] ?? CONF_COLOUR.low

  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2" style={{ fontSize: 18 }}>
      <span className="muted">{d.modelPick}:</span>
      <span className="font-bold" style={{ color: colour }}>
        {tie ? d.tooCloseToCall : team}
      </span>
      {!tie && (
        <>
          <span
            className="rounded px-2 py-0.5 font-semibold text-white"
            // 18px, matching the body-text floor. A confidence label is
            // information, not decoration, and this audience is on cheap
            // screens - shrinking it to make the row tidier would trade the
            // wrong thing. The row wraps instead.
            style={{ background: colour, fontSize: 18 }}
          >
            {d[CONF_LABEL[band] ?? "confLow"] as string}
          </span>
          {typeof p.confidence_margin === "number" && (
            <span className="muted tabular-nums" style={{ fontSize: 17 }}>
              {d.edge} {Math.round(p.confidence_margin)}pp
            </span>
          )}
        </>
      )}
    </div>
  )
}
