# Local Guard Reliability Layer

GitHub Actions schedule is best-effort. It can start late or be dropped under load, so it cannot provide exact-time guarantees.

This repo therefore supports a Windows Task Scheduler guard that runs the paper bot locally. GitHub remains a backup layer.

## Installed Tasks

`install_windows_scheduled_tasks.ps1` creates:

| Task | Local time | Duration | Purpose |
| --- | ---: | ---: | --- |
| `AlpacaPaperBot-MainSessionGuard` | 16:15 TR, Mon-Fri | 430 min | Covers entry and all intraday exits |
| `AlpacaPaperBot-CloseBackupGuard` | 21:10 TR, Mon-Fri | 135 min | Backup close guard |

Both tasks run:

```powershell
python paper_bot.py --execute --auto-window --loop --max-minutes ...
```

The bot is still paper-only because `strategy_config.json` has:

- `paper_only: true`
- `live_trading_enabled: false`
- Alpaca paper endpoint locked

## Install

```powershell
.\install_windows_scheduled_tasks.ps1 -Mode execute
```

Use dry-run mode for a non-ordering test:

```powershell
.\install_windows_scheduled_tasks.ps1 -Mode dry_run
```

## Manual Smoke Test

```powershell
.\run_local_guard.ps1 -Mode dry_run -MaxMinutes 1
```

## Limits

This is stronger than GitHub cron, but no retail setup can be truly 100% guaranteed. It still depends on:

- Windows being awake
- internet being available
- Alpaca API being reachable
- valid paper API keys
- market/data availability

For the strongest setup, use this local guard plus GitHub scheduled backup plus a VPS/systemd timer if you want another machine-level backup.
