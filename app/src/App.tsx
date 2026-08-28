import { useEffect, useState } from "react"
import Footer from "./components/Footer"
import LanguagePicker from "./components/LanguagePicker"
import OfflineBanner from "./components/OfflineBanner"
import Matches from "./screens/Matches"
import MatchDetail from "./screens/MatchDetail"
import TrackRecord from "./screens/TrackRecord"
import { files, loadWithCache, readCache } from "./api"
import { dict, loadLang, saveLang, type Lang } from "./i18n"
import type { Meta, Prediction, TrackRecord as TR } from "./types"
import { stopSpeaking } from "./lib/speech"

type View = { name: "matches" } | { name: "record" } | { name: "detail"; p: Prediction }

export default function App() {
  const [lang, setLang] = useState<Lang>(loadLang)
  const [view, setView] = useState<View>({ name: "matches" })

  const [predictions, setPredictions] = useState<Prediction[] | null>(null)
  const [track, setTrack] = useState<TR | null>(null)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [failed, setFailed] = useState(false)
  const [loading, setLoading] = useState(true)

  const d = dict(lang)

  useEffect(() => {
    // Cached data renders on the first paint; the network only refreshes it.
    let done = 0
    const finish = () => {
      if (++done >= 3) setLoading(false)
    }
    loadWithCache<Prediction[]>(files.predictions, (data) => { setPredictions(data); setFailed(false); finish() }, () => { setFailed(true); finish() })
    loadWithCache<TR>(files.track, (data) => { setTrack(data); finish() }, finish)
    loadWithCache<Meta>(files.meta, (data) => { setMeta(data); finish() }, finish)
  }, [])

  // Back button and swipe-back close the detail view rather than leaving the app.
  useEffect(() => {
    const onPop = () => {
      stopSpeaking()
      setView((v) => (v.name === "detail" ? { name: "matches" } : v))
    }
    window.addEventListener("popstate", onPop)
    return () => window.removeEventListener("popstate", onPop)
  }, [])

  const openDetail = (p: Prediction) => {
    stopSpeaking()
    window.history.pushState({ detail: p.id }, "")
    setView({ name: "detail", p })
  }

  const closeDetail = () => {
    stopSpeaking()
    if (window.history.state?.detail) window.history.back()
    else setView({ name: "matches" })
  }

  const changeLang = (l: Lang) => {
    stopSpeaking()
    setLang(l)
    saveLang(l)
  }

  const leagues = meta?.leagues ?? []
  const hasCache = !!readCache(files.predictions)

  if (view.name === "detail") {
    return (
      <div className="mx-auto min-h-screen max-w-lg px-4 pt-4">
        <MatchDetail
          p={view.p}
          league={leagues.find((l) => l.code === view.p.league_code)}
          lang={lang}
          onBack={closeDetail}
        />
      </div>
    )
  }

  return (
    <div className="mx-auto min-h-screen max-w-lg px-4 pt-4">
      <header className="mb-4">
        <h1 className="font-bold" style={{ fontSize: 26 }}>
          {d.appName}
        </h1>
      </header>

      {/* Two destinations, always both visible. No hamburger, no drawer. */}
      <nav className="mb-4 flex gap-2" aria-label={d.appName}>
        <TabButton on={view.name === "matches"} onClick={() => setView({ name: "matches" })}>
          {d.matches}
        </TabButton>
        <TabButton on={view.name === "record"} onClick={() => setView({ name: "record" })}>
          {d.trackRecord}
        </TabButton>
      </nav>

      {failed && <OfflineBanner lang={lang} hasCache={hasCache} />}

      {view.name === "matches" ? (
        <Matches
          predictions={predictions}
          leagues={leagues}
          loading={loading}
          lang={lang}
          onOpen={openDetail}
        />
      ) : (
        <TrackRecord data={track} leagues={leagues} loading={loading} lang={lang} />
      )}

      <div className="mt-6">
        <LanguagePicker lang={lang} onChange={changeLang} />
      </div>

      <Footer lang={lang} />
    </div>
  )
}

function TabButton({
  on,
  onClick,
  children,
}: {
  on: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      className={
        "tap flex-1 rounded-xl border-2 px-3 font-bold" +
        (on
          ? " border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
          : " surface")
      }
      style={{ fontSize: 18 }}
    >
      {children}
    </button>
  )
}
