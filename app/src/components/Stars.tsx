/**
 * Confidence as filled stars out of three.
 *
 * The COUNT carries the meaning; colour only reinforces it. That ordering
 * matters for anyone who cannot distinguish the colours.
 */
export default function Stars({ filled, colour }: { filled: number; colour: string }) {
  return (
    <span className="inline-flex shrink-0 gap-0.5" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <svg key={i} width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4 6.1 20.5l1.2-6.5L2.5 9.4l6.6-.9z"
            fill={i < filled ? colour : "transparent"}
            stroke={colour}
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
        </svg>
      ))}
    </span>
  )
}
