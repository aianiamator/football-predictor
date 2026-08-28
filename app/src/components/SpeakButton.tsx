import { useEffect, useState } from "react"
import { isSpeechAvailable, speak, stopSpeaking, pickVoice } from "../lib/speech"
import type { Lang } from "../i18n"

/**
 * Reads a forecast aloud. Hidden entirely when the device has no speech at
 * all, because a button that does nothing is worse than no button.
 *
 * The voice is chosen for the reader's language, preferring Nigerian English
 * when the language itself is not installed - see lib/speech.ts.
 */
export default function SpeakButton({
  text,
  lang,
  label,
  size = 56,
}: {
  text: string
  lang: Lang
  label: string
  size?: number
}) {
  const [speaking, setSpeaking] = useState(false)
  const [voiceName, setVoiceName] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    pickVoice(lang).then((v) => {
      if (alive) setVoiceName(v?.name ?? null)
    })
    return () => {
      alive = false
    }
  }, [lang])

  if (!isSpeechAvailable()) return null

  const toggle = () => {
    if (speaking) {
      stopSpeaking()
      setSpeaking(false)
      return
    }
    void speak(text, lang)
    setSpeaking(true)
    // No reliable "finished" event across Android browsers, so estimate from
    // the length of the sentence.
    window.setTimeout(() => setSpeaking(false), Math.max(3000, text.length * 80))
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={voiceName ? `${label} (${voiceName})` : label}
      title={voiceName ?? undefined}
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
