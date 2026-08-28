/**
 * Reading a forecast aloud.
 *
 * This matters more than it looks: some readers will use it INSTEAD of the
 * text, not alongside it. So the voice choice is not cosmetic.
 *
 * What this can and cannot do
 * ---------------------------
 * The browser can only use voices already installed on the reader's device.
 * An app cannot ship a voice, and cannot install one. So the job here is to
 * pick the best thing present and degrade sensibly, never to pretend.
 *
 * The ranking below is deliberate:
 *
 *   1. The actual language (yo-NG, ha-NG, ig-NG) when the device has it.
 *   2. Failing that, NIGERIAN ENGLISH. A Nigerian English voice reading
 *      Yoruba or Igbo text pronounces the vowels and names far closer to
 *      right than an American one, which mangles them.
 *   3. Then other African English - Ghana, South Africa, Kenya.
 *   4. Then British English, which is closer to Nigerian English than
 *      American is, Nigerian English being historically British-derived.
 *   5. American English only as a last resort before the device default.
 *
 * Android device voices come from Google Text-to-Speech. Which languages a
 * given phone actually has depends on what the owner has downloaded, so the
 * same app will sound different on two handsets. That is a property of the
 * platform, not something the code can fix.
 */
import type { Lang } from "../i18n"

/** Best first. Matched against a voice's language tag and its name. */
const PREFERENCES: Record<Lang, string[]> = {
  en: ["en-ng", "en-gh", "en-za", "en-ke", "en-gb", "en"],
  pcm: ["en-ng", "pcm", "en-gh", "en-za", "en-gb", "en"],
  yo: ["yo-ng", "yo", "en-ng", "en-gh", "en-za", "en-gb", "en"],
  ha: ["ha-ng", "ha", "en-ng", "en-gh", "en-za", "en-gb", "en"],
  ig: ["ig-ng", "ig", "en-ng", "en-gh", "en-za", "en-gb", "en"],
}

/** The tag set on the utterance when no matching voice exists. */
const UTTERANCE_LANG: Record<Lang, string> = {
  en: "en-NG",
  pcm: "en-NG",
  yo: "yo-NG",
  ha: "ha-NG",
  ig: "ig-NG",
}

export function isSpeechAvailable(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window
}

/**
 * Chrome returns an EMPTY list from getVoices() until it has loaded them and
 * fired voiceschanged. Reading it once means the first tap of the speaker gets
 * whatever the platform default is - usually an American voice - and only
 * later taps get the right one. So wait for the list, once, and cache it.
 */
let cached: SpeechSynthesisVoice[] | null = null
let pending: Promise<SpeechSynthesisVoice[]> | null = null

function loadVoices(): Promise<SpeechSynthesisVoice[]> {
  if (cached?.length) return Promise.resolve(cached)
  if (pending) return pending

  pending = new Promise((resolve) => {
    const now = window.speechSynthesis.getVoices()
    if (now.length) {
      cached = now
      return resolve(now)
    }
    const done = () => {
      cached = window.speechSynthesis.getVoices()
      resolve(cached)
    }
    window.speechSynthesis.addEventListener("voiceschanged", done, { once: true })
    // Some Android builds never fire the event. Do not hang on them.
    window.setTimeout(done, 1200)
  })
  return pending
}

function score(voice: SpeechSynthesisVoice, prefs: string[]): number {
  const tag = voice.lang.toLowerCase().replace("_", "-")
  const name = voice.name.toLowerCase()

  for (let i = 0; i < prefs.length; i++) {
    const p = prefs[i]
    if (tag === p) return i
    // A region-less preference such as "yo" should match "yo-NG".
    if (!p.includes("-") && tag.split("-")[0] === p) return i + 0.5
  }
  // Some Android voices carry the country in the NAME rather than the tag.
  if (name.includes("nigeria")) return prefs.length
  return Number.POSITIVE_INFINITY
}

export async function pickVoice(lang: Lang): Promise<SpeechSynthesisVoice | null> {
  const voices = await loadVoices()
  if (!voices.length) return null

  const prefs = PREFERENCES[lang] ?? PREFERENCES.en
  let best: SpeechSynthesisVoice | null = null
  let bestScore = Number.POSITIVE_INFINITY

  for (const v of voices) {
    const s = score(v, prefs)
    if (s < bestScore) {
      best = v
      bestScore = s
    }
  }
  // Everything scored Infinity means nothing matched even loosely. Prefer any
  // non-American English over the raw default.
  if (!best || bestScore === Number.POSITIVE_INFINITY) {
    best =
      voices.find((v) => /^en/i.test(v.lang) && !/us/i.test(v.lang)) ??
      voices.find((v) => /^en/i.test(v.lang)) ??
      null
  }
  return best
}

/** True when the device has a voice for the reader's actual language. */
export async function hasNativeVoice(lang: Lang): Promise<boolean> {
  if (lang === "en" || lang === "pcm") return true
  const voices = await loadVoices()
  return voices.some((v) => v.lang.toLowerCase().replace("_", "-").startsWith(lang))
}

export async function speak(text: string, lang: Lang): Promise<void> {
  if (!isSpeechAvailable() || !text) return
  const synth = window.speechSynthesis
  synth.cancel() // never let two forecasts talk over each other

  const voice = await pickVoice(lang)
  const u = new SpeechSynthesisUtterance(text)
  if (voice) {
    u.voice = voice
    u.lang = voice.lang
  } else {
    u.lang = UTTERANCE_LANG[lang] ?? "en-NG"
  }
  u.rate = 0.92  // this is being read to someone, not skimmed
  u.pitch = 1
  synth.speak(u)
}

export function stopSpeaking(): void {
  if (isSpeechAvailable()) window.speechSynthesis.cancel()
}

/**
 * Clear the cached voice list. Only used by tests, which need to simulate
 * different devices; nothing in the app calls it.
 */
export function __resetVoiceCache(): void {
  cached = null
  pending = null
}
