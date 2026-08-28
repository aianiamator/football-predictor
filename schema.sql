-- SQLite store for the forecasting engine. Lives on the Hetzner box.
-- Created automatically by engine/store.py; you never run this by hand.
--
-- This file is the durable record. The app never reads it: the engine
-- publishes derived static JSON, which Cloudflare serves. So there is no
-- API key anywhere in the frontend, because there is no API.
--
-- The reason this is a database and not just the JSON files: the track
-- record is the product's trust asset, and a forecast must be frozen once
-- the match it describes has been settled. That is enforced below by a
-- trigger, not by convention.

create table if not exists predictions (
  id                    integer primary key autoincrement,
  league_code           text    not null,
  league                text    not null,
  country               text,
  date                  text    not null,          -- ISO yyyy-mm-dd
  kickoff               text,
  home_team             text    not null,
  away_team             text    not null,

  -- The forecast. Frozen once the match is settled.
  home_win_pct          integer not null,
  draw_pct              integer not null,
  away_win_pct          integer not null,
  -- Null for leagues where over/under showed no edge in backtesting.
  -- The app hides the section entirely when this is null.
  over_2_5_pct          integer,
  -- both_teams_score is deliberately absent: +0.71pp edge over baseline
  -- with a Brier score worse than baseline means no information.
  clean_sheet_home_pct  integer,
  clean_sheet_away_pct  integer,
  expected_goals_home   real,
  expected_goals_away   real,
  likely_score          text,
  likely_scorelines     text,                       -- JSON array
  confidence            text,
  confidence_stars      integer,
  confidence_colour     text,
  summary               text,

  -- When this fixture was FIRST forecast. Never updated.
  first_published_at    text    not null,
  -- When the forecast was last refreshed (only while unsettled).
  generated_at          text    not null,

  -- Filled in by the settle job, only for matches that have finished.
  actual_home_goals     integer,
  actual_away_goals     integer,
  was_correct           integer,                    -- 0/1
  settled_at            text,

  unique (league_code, date, home_team, away_team)
);

create index if not exists predictions_date_idx    on predictions (date desc);
create index if not exists predictions_league_idx  on predictions (league_code, date desc);
create index if not exists predictions_settled_idx on predictions (was_correct, date desc);

create table if not exists team_ratings (
  id          integer primary key autoincrement,
  league_code text not null,
  league      text not null,
  team        text not null,
  attack      real,
  defence     real,
  overall     real,
  updated_at  text,
  unique (league_code, team)
);

-- A settled forecast is immutable. Any attempt to rewrite the numbers or the
-- wording of a match that has already been scored aborts the transaction.
-- This is the guarantee that makes the public track record meaningful.
drop trigger if exists predictions_freeze_settled;
create trigger predictions_freeze_settled
before update on predictions
for each row
when old.was_correct is not null
  and (
       new.home_win_pct       is not old.home_win_pct
    or new.draw_pct           is not old.draw_pct
    or new.away_win_pct       is not old.away_win_pct
    or new.over_2_5_pct       is not old.over_2_5_pct
    or new.expected_goals_home is not old.expected_goals_home
    or new.expected_goals_away is not old.expected_goals_away
    or new.likely_score       is not old.likely_score
    or new.likely_scorelines  is not old.likely_scorelines
    or new.summary            is not old.summary
    or new.confidence_stars   is not old.confidence_stars
    or new.first_published_at is not old.first_published_at
  )
begin
  select raise(ABORT, 'settled forecasts are immutable');
end;

-- The public accuracy record. Never edited by hand, never filtered.
drop view if exists accuracy_record;
create view accuracy_record as
select
  league_code,
  league,
  count(*)                                             as matches_settled,
  round(100.0 * avg(case when was_correct = 1 then 1.0 else 0.0 end), 1) as accuracy_pct,
  min(date)                                            as since
from predictions
where was_correct is not null
group by league_code, league;
