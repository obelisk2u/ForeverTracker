# Statistic definitions (version 1)

Code: `backend/app/analytics/definitions.py`, `character_stats.py`.
Each stored aggregate records `definitions_version`. Changing a definition means bumping the version and running
`python -m app.cli rebuild`.

## Shared rules

* **Unit of analysis**: a character's participation in a canonical (reconciled) run. Duplicate observations of one
  run never count twice.
* **Eligible per-run metric**: status `observed`, coverage `complete_session`, participant presence at least 90% of
  the run, run not in progress.
* **Missing data** is excluded, never treated as zero. Every statistic reports its `sample_size`, the number
  `excluded` and the reasons (`incomplete_coverage`, `metric_unavailable`, `partial_presence`, `run_in_progress`).
* **Minimum sample**: `STATS_MIN_SAMPLE` (default 1) for profiles; below it the value is `null` with
  `note: insufficient_sample`.
* Quarantined and invalidated observations, and merged-away runs, are excluded everywhere.

## Per-character statistics

| Key | Definition | Eligible observations | Denominator |
|---|---|---|---|
| `runs_observed` | Count of canonical runs the character took part in | All visible runs | — |
| `completions_confirmed` | Runs with `outcome = completed`, `completion_confidence = verified`, and the character still present within 2 minutes of the run's end | All runs | — |
| `deaths_per_run_mean` | Mean of the resolved `deaths` metric | Eligible per-run deaths | Eligible runs |
| `deaths_per_run_median` | Median of the same | Same | Same |
| `death_free_run_pct` | Share of eligible runs with 0 deaths | Same | Eligible runs |
| `deaths_observed_total` | Sum of every resolved death value, any coverage | All runs with a deaths value | — (a **lower bound**, labelled so) |
| `dps_median` | Median per-run DPS (damage ÷ meter combat seconds) | Eligible runs where the character's role was not healer | Eligible runs |
| `hps_median` | Median per-run HPS | Eligible runs in the healer role | Eligible runs |
| `interrupts_per_run_mean` | Mean meter interrupts | Eligible runs | Eligible runs |
| `completed_run_duration_mean` | Mean duration of confirmed completions | Confirmed completions with presence ≥ 90% | Those runs |
| `boss_kills_observed` | Successful boss pulls in the character's runs | All runs | — |
| `by_dungeon[]` | Runs, confirmed completions, deaths/run and median DPS per dungeon | As above, per dungeon | — |
| `data_quality` | Runs with complete death coverage, with complete meter coverage, reconciled from several observers, in progress or unknown | — | — |

Trends (`/progression`): weekly buckets (Monday 00:00 UTC) of the same eligible per-run values. A week without eligible
runs has `value: null`, and charts leave a gap instead of interpolating.

## What these numbers are not

They are not complete histories, they are not verified by Blizzard, and they are not a measure of a player's skill:
DPS depends on role, group, gear and what the meter recorded. The website says so next to the numbers.
