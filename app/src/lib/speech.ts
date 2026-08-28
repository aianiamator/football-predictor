/**
 * Reading a forecast aloud. This matters more than it looks: some readers will
 * use it instead of the text, not alongside it.
 *
 * Voices for Nigerian languages are rare on cheap Android devices, so we try
 * the exact language, then the base language, then anything English, then let
 * the platform decide. Speaking in the wrong accent beats silence.
 */
export function isSpeechAvailable(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window
}

function pickVoice(want: string): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices()
  if (!voices.length) return null
  const lower = want.toLowerCase()
  const base = lower.split("-")[0]
  return (
    voices.find((v) => v.lang.toLowerCase() === lower) ??
    voices.find((v) => v.lang.toLowerCase().startsWith(base)) ??
    voices.find((v) => v.lang.toLowerCase().startsWith("en")) ??
    null
  )
}

export function speak(text: string, voiceLang: string): void {
  if (!isSpeechAvailable() || !text) return
  const synth = window.speechSynthesis
  synth.cancel() // never let two forecasts talk over each other

  const u = new SpeechSynthesisUtterance(text)
  const voice = pickVoice(voiceLang)
  if (voice) {
    u.voice = voice
    u.lang = voice.lang
  } else {
    u.lang = voiceLang
  }
  u.rate = 0.95 // slightly slower: this is being read, not skimmed
  synth.speak(u)
}

export function stopSpeaking(): void {
  if (isSpeechAvailable()) window.speechSynthesis.cancel()
}
