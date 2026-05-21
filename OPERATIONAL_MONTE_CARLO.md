# Operational Monte Carlo - 1Y

Initial capital: 10,000 TL  
Paths: 50,000  
Horizon: 252 trading days

This is not a new strategy search. It keeps the same `mix_00317` rules and applies operational haircuts for GitHub scheduling, missed entries, delayed closes, and extra execution costs.

| Scenario | Entry capture | Close capture | p50 final TL | p5 final TL | p1 final TL | Loss probability |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `ideal_local_or_vps_exact_windows` | 100% | 100% | 87,457 | 36,522 | 25,551 | 0.002% |
| `github_frequent_checks_base` | 90% | 95% | 62,835 | 27,584 | 19,782 | 0.012% |
| `github_delayed_conservative` | 70% | 85% | 36,253 | 17,427 | 13,007 | 0.166% |
| `github_bad_cron_stress` | 45% | 70% | 18,843 | 10,365 | 8,147 | 4.042% |

## Interpretation

- `ideal_local_or_vps_exact_windows` is the best comparison to the previous paper-config MC.
- `github_frequent_checks_base` is the more realistic GitHub Actions estimate after adding frequent auto-window checks and broker-history close logic.
- `github_delayed_conservative` assumes more missed entry windows and delayed closes.
- `github_bad_cron_stress` is a harsh stress case based on unreliable cron behavior.

Current operational working estimate for GitHub Actions should use `github_frequent_checks_base`, not the ideal p50.
