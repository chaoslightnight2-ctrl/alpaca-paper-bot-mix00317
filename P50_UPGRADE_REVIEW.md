# P50 Upgrade Review

Initial capital: 10,000 TL  
Monte Carlo paths: 50,000  
Status: research and operational changes only; not committed yet.

## 1. GitHub operational p50

The bot now has an `--auto-window` mode. In this mode every loop checks:

- broker-history due closes
- local state due closes
- entry windows
- duplicate broker client order IDs

The workflow also changes scheduled checks from every 10 minutes to every 5 minutes and keeps each auto-window run alive for 8 minutes.

| Operating model | p50 final TL | p5 final TL | p1 final TL |
| --- | ---: | ---: | ---: |
| Previous GitHub base | 62,835 | 27,584 | 19,782 |
| New looped auto-window base | 75,816 | 32,129 | 22,299 |
| New looped conservative | 61,685 | 26,711 | 18,997 |
| Ideal exact window | 87,457 | 36,522 | 25,551 |

Verdict: this is the cleanest p50 improvement because it does not change the trading edge or add overfit strategy rules.

## 2. Feature ablation

Current strategy: `mix_00317_intraday_feature_combo_no_lookahead_paper`

Key ablation results using the same one-year active-day MC method:

| Variant | p50 final TL | Issue |
| --- | ---: | --- |
| Current rebuilt | 93,356 | Baseline from reconstructed checkpoint data |
| Remove `short_e3_x77_00431` | about 124,000 | Higher p50, but less diversified |
| Long sleeve only | 308,879 | Very unstable year distribution |
| Long sleeve without `prev_day_ret > 0.007851` | 343,336 | Strong p50, but fails year-balance and 2026 rule |
| Long + `short_e2_x60_00514`, long without `prev_day_ret` | 276,416 | Long/short, but fails year-balance and 2026 rule |

Important feature finding:

- `pos_or <= 0.363486` in the main long sleeve is important. Removing it crushed p50 in the ablation run.
- `prev_day_ret > 0.007851` in the main long sleeve increases stability less than expected and suppresses p50, but removing it makes the strategy much more 2023-heavy.
- The smaller short sleeves look like p50 drag under active-day MC, but they help keep the strategy less one-dimensional.

## 3. Regime-based combination

Tested a regime gate using QQQ entry-time features. The strongest constrained candidate was:

`aggr_if_rvol > 1.284983 else flat`

This uses the aggressive long/short sleeve only when QQQ relative volume at the early entry window is high.

| Metric | Value |
| --- | ---: |
| Active-day MC p50 | 137,279 TL |
| Calendar-day MC p50 | 16,812 TL |
| Historical 2023 | 66.09% |
| Historical 2024 | 74.97% |
| Historical 2025 | 57.16% |
| Historical 2026 | 23.82% |
| 2023-2025 ratio | 1.31 |
| 2026 quarter rule | Pass |
| Trade days | 166 |

Verdict: not recommended as the active paper strategy yet. The active-day p50 looks good, but the calendar-day p50 exposes that it trades too rarely. This is useful as a research lead, not a deployment change.

## Decision

Recommended commit scope:

- Keep current `mix_00317` strategy active.
- Commit the GitHub auto-window operational improvement.
- Commit the analysis scripts and reports.
- Do not switch to the aggressive ablation or regime strategy yet.

Reason: the operational change lifts the realistic GitHub p50 from 62,835 TL to 75,816 TL without increasing strategy overfit risk.
