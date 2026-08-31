/** Mirrors exactly what engine/store.py publishes. Nothing more is fetched. */

export type Scoreline = { home_goals: number; away_goals: number; prob: number }

export type Prediction = {
  id: number
  league_code: string
  league: string
  date: string
  kickoff_utc: string | null
  home_team: string
  away_team: string
  home_win_pct: number
  draw_pct: number
  away_win_pct: number
  confidence_stars: number
  confidence_colour: string
  summary_key: string | null
  summary_args: Record<string, unknown> | null
  summary: string
  // Decision layer, computed once by the engine and stored with the forecast.
  model_pick?: "H" | "D" | "A" | "TIE" | null
  confidence_band?: "high" | "strong" | "moderate" | "low" | null
  margin_band?: "clear_edge" | "reasonable_edge" | "small_edge" | "too_close" | null
  confidence_margin?: number | null
  // Present on the detail payload.
  over_2_5_pct?: number | null
  clean_sheet_home_pct?: number | null
  clean_sheet_away_pct?: number | null
  expected_goals_home?: number | null
  expected_goals_away?: number | null
  likely_score?: string | null
  likely_scorelines?: Scoreline[] | null
}

export type LeagueMeta = {
  code: string
  name: string
  country: string
  flag: string
}

export type Meta = {
  published_at: string
  upcoming: number
  settled: number
  leagues: LeagueMeta[]
}

export type SettledMatch = {
  league_code: string
  league: string
  date: string
  home_team: string
  away_team: string
  home_win_pct: number
  draw_pct: number
  away_win_pct: number
  actual_home_goals: number
  actual_away_goals: number
  actual_result?: string | null
  model_pick?: string | null
  confidence_band?: string | null
  /** null when the fixture was too close to call and deliberately unscored. */
  was_correct: number | null
}

export type LeagueRecord = {
  league_code: string
  league: string
  matches_settled: number
  accuracy_pct: number | null
  since: string
}

/** Played, but the results feed has not caught up yet. The forecast here is
 *  already frozen in the store - it is what was said BEFORE anyone knew the
 *  answer, which is the point of showing it. */
export type AwaitingMatch = {
  league_code: string
  league: string
  date: string
  home_team: string
  away_team: string
  home_win_pct: number
  draw_pct: number
  away_win_pct: number
}

export type Block = {
  completed: number
  correct: number
  incorrect: number
  hit_rate: number | null
  brier: number | null
  sample_band: "very_small" | "early" | "developing" | "larger_sample"
}

export type Performance = {
  overall: Block & {
    total_forecasts: number
    pending: number
    not_played: number
    unscored_ties: number
  }
  by_confidence: (Block & { band: string })[]
  by_outcome: (Block & { pick: string })[]
  by_league: (Block & { league_code: string; league: string })[]
  calibration: {
    band: string
    predictions: number
    correct: number
    actual_rate: number | null
    average_predicted: number
    gap: number | null
    sample_band: string
  }[]
  baselines: {
    always_home?: { completed: number; correct: number; hit_rate: number | null }
    base_rates?: { completed: number; brier: number }
    model_vs_always_home_points?: number | null
    model_vs_base_rates_brier?: number | null
  }
  model_versions: Record<string, number>
}

export type TrackRecord = {
  overall: { matches_settled: number; accuracy_pct: number | null }
  by_league: LeagueRecord[]
  recent: SettledMatch[]
  awaiting?: AwaitingMatch[]
  /** True total waiting; the list above is capped for byte size. */
  awaiting_total?: number
  performance?: Performance
}
