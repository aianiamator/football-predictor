-- Run this once in the Supabase SQL editor.
-- The app reads with the anon key. Only the engine writes, using the
-- service key, which must never appear in frontend code.

create table if not exists predictions (
  id                    bigserial primary key,
  league_code           text not null,
  league                text not null,
  country               text,
  date                  date not null,
  kickoff               text,
  home_team             text not null,
  away_team             text not null,
  home_win_pct          int not null,
  draw_pct              int not null,
  away_win_pct          int not null,
  -- Null for leagues where over/under showed no edge in backtesting.
  -- The app hides the section entirely when this is null.
  over_2_5_pct          int,
  -- both_score_pct removed: no measurable edge over baseline.
  clean_sheet_home_pct  int,
  clean_sheet_away_pct  int,
  expected_goals_home   numeric,
  expected_goals_away   numeric,
  likely_score          text,
  likely_scorelines     jsonb,
  confidence            text,
  confidence_stars      int,
  confidence_colour     text,
  summary               text,
  generated_at          timestamptz default now(),
  -- Filled in after the match is played, by the results job.
  actual_home_goals     int,
  actual_away_goals     int,
  was_correct           boolean,
  unique (league_code, date, home_team, away_team)
);

create index if not exists predictions_date_idx on predictions (date desc);
create index if not exists predictions_league_idx on predictions (league_code, date desc);

create table if not exists team_ratings (
  id          bigserial primary key,
  league_code text not null,
  league      text not null,
  team        text not null,
  attack      numeric,
  defence     numeric,
  overall     numeric,
  updated_at  timestamptz default now(),
  unique (league_code, team)
);

-- Public accuracy record. This is the trust asset — never edit it by hand.
create or replace view accuracy_record as
select
  league,
  count(*)                                            as matches_settled,
  round(100.0 * avg(case when was_correct then 1 else 0 end), 1) as accuracy_pct,
  min(date)                                           as since
from predictions
where was_correct is not null
group by league;

alter table predictions   enable row level security;
alter table team_ratings  enable row level security;

create policy "public read predictions"
  on predictions for select using (true);

create policy "public read ratings"
  on team_ratings for select using (true);

-- No insert/update/delete policies: writes are service-key only.
