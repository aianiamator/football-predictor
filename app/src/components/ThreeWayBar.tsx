/**
 * The single most important element in the app.
 *
 * One full-width bar split into three segments sized by the forecast. A reader
 * should be able to take in the whole forecast from its shape alone, before
 * reading a single word — which is the point, because some readers will not
 * read the words at all.
 *
 * Two deliberate decisions:
 *
 * 1. Colours are the darker shades of green / slate / blue rather than the
 *    brightest ones. White bold text on bright green fails contrast on a cheap
 *    LCD in daylight; these pass AA for large text. Legibility beats vibrancy
 *    when the bar IS the content.
 * 2. The draw segment is a cool slate, while low confidence is shown in a warm
 *    stone. Grey must not mean two different things in one screen.
 */

type Props = {
  home: number
  draw: number
  away: number
  height?: number
  homeLabel: string
  drawLabel: string
  awayLabel: string
  /** Screen-reader description; the visual is meaningless to a screen reader. */
  ariaLabel: string
}

// Below this width a percentage cannot render legibly inside its segment, so
// it is hidden. The segment itself is always drawn - the shape must stay true.
const MIN_PCT_FOR_LABEL = 13

const SEGMENTS = [
  { key: "home", bg: "#15803d" },
  { key: "draw", bg: "#64748b" },
  { key: "away", bg: "#1d4ed8" },
] as const

export default function ThreeWayBar({
  home,
  draw,
  away,
  height = 44,
  homeLabel,
  drawLabel,
  awayLabel,
  ariaLabel,
}: Props) {
  // Normalise defensively: rounding upstream can leave a total of 99 or 101,
  // and a bar that does not fill its track reads as a rendering bug.
  const total = home + draw + away || 1
  const parts = [
    { ...SEGMENTS[0], value: home, width: (home / total) * 100, label: homeLabel },
    { ...SEGMENTS[1], value: draw, width: (draw / total) * 100, label: drawLabel },
    { ...SEGMENTS[2], value: away, width: (away / total) * 100, label: awayLabel },
  ]

  const fontSize = Math.max(16, Math.round(height * 0.42))

  return (
    <div>
      <div
        role="img"
        aria-label={ariaLabel}
        className="flex w-full overflow-hidden rounded-lg"
        style={{ height }}
      >
        {parts.map((p) => (
          <div
            key={p.key}
            className="flex items-center justify-center transition-all duration-300"
            style={{ width: `${p.width}%`, background: p.bg }}
          >
            {p.width >= MIN_PCT_FOR_LABEL && (
              <span
                className="font-bold text-white tabular-nums"
                style={{ fontSize }}
              >
                {p.value}%
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Which segment is which, aligned underneath. Position carries the
          meaning; these letters only confirm it. */}
      <div className="mt-1 flex w-full" aria-hidden="true">
        {parts.map((p) => (
          <div
            key={p.key}
            className="muted text-center font-semibold"
            style={{ width: `${p.width}%`, fontSize: 15 }}
          >
            {p.width >= 8 ? p.label : ""}
          </div>
        ))}
      </div>
    </div>
  )
}
