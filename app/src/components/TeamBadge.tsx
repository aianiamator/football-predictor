import { initial, teamColour } from "../lib/colors"

/** A circle with the club's first letter. No images, ever. */
export default function TeamBadge({ name, size = 44 }: { name: string; size?: number }) {
  return (
    <div
      aria-hidden="true"
      className="flex shrink-0 items-center justify-center rounded-full font-bold text-white"
      style={{
        width: size,
        height: size,
        background: teamColour(name),
        fontSize: Math.round(size * 0.45),
      }}
    >
      {initial(name)}
    </div>
  )
}
