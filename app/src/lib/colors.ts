/**
 * A deterministic colour per team name, so a badge looks the same everywhere
 * and on every device without shipping a single image.
 *
 * Saturation and lightness are fixed at values that keep white lettering
 * legible on any resulting hue - the letter is the identity, the colour is
 * only there to make it findable at a glance.
 */
export function teamColour(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash << 5) - hash + name.charCodeAt(i)
    hash |= 0
  }
  const hue = Math.abs(hash) % 360
  return `hsl(${hue} 52% 34%)`
}

/** First letter, uppercased. Handles names that start with punctuation. */
export function initial(name: string): string {
  const m = name.match(/[\p{L}\p{N}]/u)
  return (m ? m[0] : name.charAt(0) || "?").toUpperCase()
}
