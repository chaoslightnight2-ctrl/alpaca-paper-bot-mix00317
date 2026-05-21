# Operational Monte Carlo - 1Y

Initial capital: 10,000 TL  
Paths: 50,000  
Horizon: 252 trading days

This keeps the same `mix_00317` strategy rules and applies operational haircuts for GitHub scheduling, missed entries, delayed closes, and extra execution costs.

| Scenario | Entry capture | Close capture | p50 final TL | p5 final TL | p1 final TL | Loss probability |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `ideal_local_or_vps_exact_windows` | 100.0% | 100.0% | 87,457 | 36,522 | 25,551 | 0.002% |
| `github_frequent_checks_base` | 90.0% | 95.0% | 62,835 | 27,584 | 19,782 | 0.012% |
| `github_looped_auto_window_base` | 97.0% | 98.5% | 75,816 | 32,129 | 22,299 | 0.004% |
| `github_looped_auto_window_conservative` | 90.0% | 95.0% | 61,685 | 26,711 | 18,997 | 0.022% |
| `github_delayed_conservative` | 70.0% | 85.0% | 36,277 | 17,376 | 12,903 | 0.188% |
| `github_bad_cron_stress` | 45.0% | 70.0% | 18,751 | 10,369 | 8,187 | 3.966% |

## Interpretation

- `github_looped_auto_window_base` is the new working estimate after changing scheduled runs to short looped auto-window checks.
- The p50 moved from 62,835 TL to 75,816 TL under the base GitHub operating model.
- This is still below the ideal exact-window p50 because GitHub Actions can start late and fills are not guaranteed.
- `github_looped_auto_window_conservative` is kept as a harsher operating estimate if cron delays remain frequent.
