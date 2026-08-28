import { useState } from "react"
import { isSpeechAvailable, speak, stopSpeaking } from "../lib/speech"

/**
 * Reads a forecast aloud. Hidden entirely when the device has no speech,
 * because a button that does nothing is worse than no button.
 */
export default function SpeakButton({
  text,
  voiceLang,
  label,
  size = 56,
}: {
  text: string
  voiceLang: string
  label: string
  size?: number
}) {
  const [speaking, setSpeaking] = useState(false)
  if (!isSpeechAvailable()) return null

  const toggle = () => {
    if (speaking) {
      stopSpeaking()
      setSpeaking(false)
      return
    }
    speak(text, voiceLang)
    setSpeaking(true)
    // There is no reliable "finished" event across Android browsers, so fall
    // back to a rough estimate from the length of the sentence.
    window.setTimeout(() => setSpeaking(false), Math.max(3000, text.length * 80))
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      className="tap surface flex shrink-0 items-center justify-center rounded-full border active:scale-95"
      style={{ width: size, height: size }}
    >
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M4 9v6h4l5 4V5L8 9H4z" fill="currentColor" />
        {speaking ? (
          <path d="M17 8l4 8M21 8l-4 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        ) : (
          <>
            <path d="M16.5 8.5a5 5 0 010 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <path d="M19 6a8 8 0 010 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </>
        )}
      </svg>
    </button>
  )
}
