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
  was_correct: number
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

export type TrackRecord = {
  overall: { matches_settled: number; accuracy_pct: number | null }
  by_league: LeagueRecord[]
  recent: SettledMatch[]
  awaiting?: AwaitingMatch[]
}
