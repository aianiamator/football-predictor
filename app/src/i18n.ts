/**
 * Interface text in five languages.
 *
 * The engine publishes `summary_key` plus `summary_args` rather than an English
 * sentence to be parsed. So translating a forecast is a template lookup, not
 * pattern-matching prose that changes whenever anyone rewords it.
 *
 * Adding a language: add the code to `Lang`, add an entry to LANGS, and add one
 * block to STRINGS. Nothing else in the app needs to change. TypeScript will
 * point at anything you missed.
 *
 * TRANSLATION NOTE: the Yoruba, Hausa, Igbo and Pidgin strings below need a
 * native speaker's review before launch. They are careful, not authoritative.
 * Nothing in the app depends on their exact wording.
 */

export type Lang = "en" | "pcm" | "yo" | "ha" | "ig"

export const LANGS: { code: Lang; label: string; voice: string }[] = [
  { code: "en", label: "English", voice: "en-GB" },
  { code: "pcm", label: "Pidgin", voice: "en-NG" },
  { code: "yo", label: "Yorùbá", voice: "yo-NG" },
  { code: "ha", label: "Hausa", voice: "ha-NG" },
  { code: "ig", label: "Igbo", voice: "ig-NG" },
]

export type Dict = {
  appName: string
  matches: string
  trackRecord: string
  all: string
  today: string
  tomorrow: string
  listen: string
  back: string
  noMatches: string
  noMatchesHint: string
  offline: string
  showingSaved: string
  loading: string
  likelyGoals: string
  mostLikelyScore: string
  otherScores: string
  threeOrMore: string
  twoOrFewer: string
  cleanSheet: string
  homeShort: string
  drawShort: string
  awayShort: string
  settled: string
  since: string
  recentForecasts: string
  correct: string
  missed: string
  noneSettled: string
  noneSettledHint: string
  awaitingResults: string
  awaitingHint: string
  overallRecord: string
  drawWarning: string
  footer: string
  // Forecast sentences, keyed by the engine's summary_key.
  evenly_matched: (a: { home: string; away: string }) => string
  strong_favourite: (a: { team: string; draw_pct: number }) => string
  more_likely: (a: { team: string }) => string
  small_edge: (a: { team: string }) => string
}

export const STRINGS: Record<Lang, Dict> = {
  en: {
    appName: "Match Forecasts",
    matches: "Matches",
    trackRecord: "How we have done",
    all: "All",
    today: "Today",
    tomorrow: "Tomorrow",
    listen: "Listen",
    back: "Back",
    noMatches: "No matches to show yet",
    noMatchesHint: "New forecasts arrive before each round of games.",
    offline: "You are offline",
    showingSaved: "Showing saved forecasts",
    loading: "Loading",
    likelyGoals: "Likely goals",
    mostLikelyScore: "Most likely score",
    otherScores: "Other possible scores",
    threeOrMore: "3 or more goals",
    twoOrFewer: "2 or fewer",
    cleanSheet: "Keeps a clean sheet",
    homeShort: "H",
    drawShort: "=",
    awayShort: "A",
    settled: "matches finished",
    since: "since",
    recentForecasts: "Last 20 forecasts",
    correct: "Right",
    missed: "Wrong",
    noneSettled: "No finished matches yet",
    noneSettledHint: "This fills in as matches are played. Nothing is hidden.",
    awaitingResults: "Played, waiting for the result",
    awaitingHint:
      "These matches have been played. Our forecast is already locked and shown below. The result is not published yet.",
    overallRecord: "Overall",
    drawWarning:
      "No method forecasts football reliably. About a quarter of all matches end in a draw, and a draw is the hardest result to call.",
    footer:
      "Forecasts are statistical estimates from past results. Football is unpredictable — even strong favourites lose.",
    evenly_matched: (a) => `${a.home} and ${a.away} look evenly matched. A draw is very possible.`,
    strong_favourite: (a) =>
      `${a.team} are the strong favourite, but ${a.draw_pct} in 100 games like this end in a draw.`,
    more_likely: (a) => `${a.team} are more likely to win. A draw is still common here.`,
    small_edge: (a) => `${a.team} have a small edge, but this one is close and could go any way.`,
  },

  pcm: {
    appName: "Match Forecast",
    matches: "Matches",
    trackRecord: "How we don do",
    all: "All",
    today: "Today",
    tomorrow: "Tomorrow",
    listen: "Listen",
    back: "Go back",
    noMatches: "No match dey show now",
    noMatchesHint: "New forecast dey come before each round of games.",
    offline: "You no dey online",
    showingSaved: "We dey show wetin we save",
    loading: "E dey load",
    likelyGoals: "Goals wey fit enter",
    mostLikelyScore: "Score wey most likely",
    otherScores: "Other score wey fit happen",
    threeOrMore: "3 goals or pass",
    twoOrFewer: "2 goals or less",
    cleanSheet: "No go collect goal",
    homeShort: "H",
    drawShort: "=",
    awayShort: "A",
    settled: "matches wey don finish",
    since: "since",
    recentForecasts: "Last 20 forecast",
    correct: "Correct",
    missed: "Miss",
    noneSettled: "No match don finish yet",
    noneSettledHint: "E go fill up as dem play matches. We no dey hide anything.",
    awaitingResults: "Dem don play, we dey wait for result",
    awaitingHint:
      "Dem don play these matches. Wetin we talk don lock already, e dey below. The result never come out.",
    overallRecord: "Altogether",
    drawWarning:
      "No method fit forecast football well well. Like one quarter of all matches dey end for draw, and draw na the hardest one to call.",
    footer:
      "Forecast na estimate from wetin happen before. Football no get master — even strong favourite dey lose.",
    evenly_matched: (a) => `${a.home} and ${a.away} balance well well. Draw fit happen.`,
    strong_favourite: (a) =>
      `${a.team} be strong favourite, but ${a.draw_pct} for every 100 game like this dey end for draw.`,
    more_likely: (a) => `${a.team} fit win pass. But draw still dey common here.`,
    small_edge: (a) => `${a.team} get small edge, but this one tight — e fit go any side.`,
  },

  yo: {
    appName: "Àsọtẹ́lẹ̀ Ìdíje",
    matches: "Àwọn ìdíje",
    trackRecord: "Bí a ṣe ṣe",
    all: "Gbogbo",
    today: "Òní",
    tomorrow: "Ọ̀la",
    listen: "Gbọ́",
    back: "Padà",
    noMatches: "Kò sí ìdíje láti fihàn",
    noMatchesHint: "Àsọtẹ́lẹ̀ tuntun yóò dé ṣáájú ìdíje kọ̀ọ̀kan.",
    offline: "O kò sí lórí ayélujára",
    showingSaved: "À ń fi àsọtẹ́lẹ̀ tí a fi pamọ́ hàn",
    loading: "Ń gbé wọlé",
    likelyGoals: "Gôlù tí ó ṣeé ṣe",
    mostLikelyScore: "Àbájáde tí ó ṣeé ṣe jùlọ",
    otherScores: "Àwọn àbájáde mìíràn",
    threeOrMore: "Gôlù 3 tàbí jù",
    twoOrFewer: "Gôlù 2 tàbí kéré",
    cleanSheet: "Kò ní gba gôlù",
    homeShort: "H",
    drawShort: "=",
    awayShort: "A",
    settled: "ìdíje tí ó parí",
    since: "láti",
    recentForecasts: "Àsọtẹ́lẹ̀ 20 tí ó kẹ́yìn",
    correct: "Tọ̀nà",
    missed: "Kùnà",
    noneSettled: "Kò sí ìdíje tí ó parí síbẹ̀",
    noneSettledHint: "Yóò kún bí a ṣe ń ṣe ìdíje. A kò fi ohunkóhun pamọ́.",
    awaitingResults: "Wọ́n ti ṣeré, à ń dúró de àbájáde",
    awaitingHint:
      "Àwọn ìdíje wọ̀nyí ti wáyé. Àsọtẹ́lẹ̀ wa ti wà ní títì, ó wà nísàlẹ̀. Àbájáde kò tíì jáde.",
    overallRecord: "Lápapọ̀",
    drawWarning:
      "Kò sí ọ̀nà tí ó lè sọ àsọtẹ́lẹ̀ bọ́ọ̀lù ní pípé. Nǹkan bí ìdámẹ́rin gbogbo ìdíje ni ó ń parí ní ìdọ́gba, ìdọ́gba sì ni ó ṣòro jùlọ láti sọ.",
    footer:
      "Àsọtẹ́lẹ̀ jẹ́ ìṣirò láti àbájáde àtẹ̀yìnwá. Bọ́ọ̀lù kò ṣeé sọ tẹ́lẹ̀ — àwọn ẹgbẹ́ tó lágbára pàápàá máa ń pàdánù.",
    evenly_matched: (a) => `${a.home} àti ${a.away} dọ́gba. Ìdọ́gba ṣeé ṣe gan-an.`,
    strong_favourite: (a) =>
      `${a.team} ni ó lágbára jù, ṣùgbọ́n ${a.draw_pct} nínú 100 ìdíje bí èyí ni ó ń parí ní ìdọ́gba.`,
    more_likely: (a) => `${a.team} ló ṣeé ṣe kí ó ṣẹ́gun. Ṣùgbọ́n ìdọ́gba ṣì wọ́pọ̀ níbí.`,
    small_edge: (a) => `${a.team} ní àǹfààní kékeré, ṣùgbọ́n èyí sún mọ́ra — ó lè yí padà.`,
  },

  ha: {
    appName: "Hasashen Wasanni",
    matches: "Wasanni",
    trackRecord: "Yadda muka yi",
    all: "Duka",
    today: "Yau",
    tomorrow: "Gobe",
    listen: "Saurara",
    back: "Koma",
    noMatches: "Babu wasa da za a nuna tukuna",
    noMatchesHint: "Sabbin hasashe suna zuwa kafin kowane zagaye.",
    offline: "Ba ka kan layi ba",
    showingSaved: "Muna nuna hasashen da aka ajiye",
    loading: "Ana lodi",
    likelyGoals: "Kwallayen da ake tsammani",
    mostLikelyScore: "Sakamakon da ya fi yiwuwa",
    otherScores: "Sauran sakamako masu yiwuwa",
    threeOrMore: "Kwallaye 3 ko sama",
    twoOrFewer: "Kwallaye 2 ko kasa",
    cleanSheet: "Ba za a ci su ba",
    homeShort: "H",
    drawShort: "=",
    awayShort: "A",
    settled: "wasannin da suka kare",
    since: "tun",
    recentForecasts: "Hasashe 20 na karshe",
    correct: "Daidai",
    missed: "Kuskure",
    noneSettled: "Babu wasan da ya kare tukuna",
    noneSettledHint: "Zai cika yayin da ake buga wasanni. Ba mu boye komai.",
    awaitingResults: "An buga, muna jiran sakamako",
    awaitingHint:
      "An riga an buga wadannan wasannin. Hasashenmu ya riga ya kulle, yana kasa. Ba a fitar da sakamako ba tukuna.",
    overallRecord: "Gaba daya",
    drawWarning:
      "Babu hanyar da za ta yi hasashen kwallon kafa daidai. Kusan kashi daya cikin hudu na dukkan wasanni na kare da canjaras, kuma canjaras shi ne mafi wuyar hasashe.",
    footer:
      "Hasashe kiyasi ne daga sakamakon baya. Kwallon kafa ba a san ta ba — har ma masu karfi suna sha kaye.",
    evenly_matched: (a) => `${a.home} da ${a.away} sun yi daidai. Canjaras na iya faruwa.`,
    strong_favourite: (a) =>
      `${a.team} su ne suka fi karfi, amma ${a.draw_pct} cikin wasanni 100 irin wannan na kare da canjaras.`,
    more_likely: (a) => `${a.team} sun fi yiwuwar cin nasara. Amma canjaras na nan da yawa.`,
    small_edge: (a) => `${a.team} suna da dan gaba kadan, amma wannan na kusa — kowa na iya yi.`,
  },

  ig: {
    appName: "Amụma Egwuregwu",
    matches: "Egwuregwu",
    trackRecord: "Otú anyị si mee",
    all: "Niile",
    today: "Taa",
    tomorrow: "Echi",
    listen: "Gee ntị",
    back: "Laghachi",
    noMatches: "Enweghị egwuregwu a ga-egosi ugbu a",
    noMatchesHint: "Amụma ọhụrụ na-abịa tupu agbamgba ọ bụla.",
    offline: "Ị nọghị n'ịntanetị",
    showingSaved: "Anyị na-egosi amụma echekwara",
    loading: "Na-ebu",
    likelyGoals: "Gool ndị pụrụ ịba",
    mostLikelyScore: "Ọnụọgụ kacha pụta ìhè",
    otherScores: "Ọnụọgụ ndị ọzọ pụrụ ime",
    threeOrMore: "Gool 3 maọbụ karịa",
    twoOrFewer: "Gool 2 maọbụ ntakịrị",
    cleanSheet: "Agaghị eti ha gool",
    homeShort: "H",
    drawShort: "=",
    awayShort: "A",
    settled: "egwuregwu gwụchara",
    since: "kemgbe",
    recentForecasts: "Amụma 20 ikpeazụ",
    correct: "Ziri ezi",
    missed: "Ezighi ezi",
    noneSettled: "Ọ dịghị egwuregwu gwụchara",
    noneSettledHint: "Ọ ga-ejupụta ka a na-agba egwuregwu. Anyị anaghị ezochi ihe ọ bụla.",
    awaitingResults: "Egwuriela ya, anyị na-eche nsonaazụ",
    awaitingHint:
      "Egwuriela egwuregwu ndị a. Amụma anyị akpọchiela, ọ dị n'okpuru. Ebipụtabeghị nsonaazụ.",
    overallRecord: "N'ozuzu",
    drawWarning:
      "Ọ dịghị usoro na-ebu amụma bọọlụ nke ọma. Ihe dị ka otu ụzọ n'ụzọ anọ nke egwuregwu niile na-akwụsị n'ọhaneze, ọhaneze bụkwa nke kacha sie ike ịkọ.",
    footer:
      "Amụma bụ atụmatụ sitere na ihe gaferela. A maghị ihe bọọlụ ga-eme — ọbụna ndị siri ike na-efunahụ.",
    evenly_matched: (a) => `${a.home} na ${a.away} hà nhata. Ọhaneze nwere ike ime.`,
    strong_favourite: (a) =>
      `${a.team} bụ ndị kacha ike, mana ${a.draw_pct} n'ime egwuregwu 100 dị ka nke a na-akwụsị n'ọhaneze.`,
    more_likely: (a) => `${a.team} nwere ike imeri karịa. Mana ọhaneze ka na-adịkarị ebe a.`,
    small_edge: (a) => `${a.team} nwere obere uru, mana nke a dị nso — ọ nwere ike ịga akụkụ ọ bụla.`,
  },
}

export function dict(lang: Lang): Dict {
  return STRINGS[lang] ?? STRINGS.en
}

/** Rebuild a forecast sentence in the reader's language. */
export function forecastSentence(
  lang: Lang,
  key: string | null,
  args: Record<string, unknown> | null,
  fallback: string,
): string {
  const d = dict(lang)
  const a = (args ?? {}) as never
  switch (key) {
    case "evenly_matched":
      return d.evenly_matched(a)
    case "strong_favourite":
      return d.strong_favourite(a)
    case "more_likely":
      return d.more_likely(a)
    case "small_edge":
      return d.small_edge(a)
    default:
      // An unknown key means the engine added a pattern this build predates.
      // Show the English the engine already wrote rather than nothing at all.
      return fallback
  }
}

const KEY = "ff.lang"

export function loadLang(): Lang {
  try {
    const saved = localStorage.getItem(KEY) as Lang | null
    if (saved && STRINGS[saved]) return saved
  } catch {
    /* private mode - fall through to the device language */
  }
  const nav = (navigator.language || "en").toLowerCase()
  for (const l of LANGS) if (nav.startsWith(l.code)) return l.code
  return "en"
}

export function saveLang(l: Lang) {
  try {
    localStorage.setItem(KEY, l)
  } catch {
    /* nothing to do: the choice simply will not persist */
  }
}
