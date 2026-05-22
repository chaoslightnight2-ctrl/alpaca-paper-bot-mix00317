# VPS Deployment

GitHub Actions cron is not exact-time infrastructure. GitHub documents that scheduled workflows can be delayed or dropped during high load. Source: https://docs.github.com/actions/reference/events-that-trigger-workflows

For the bot to run while your computer is off, use an always-on VPS and systemd timers. This is the primary timing layer; GitHub Actions remains only a backup.

## What This Installs

System timezone:

- `Europe/Istanbul`

Timers:

| Timer | Time | Accuracy | Duration | Purpose |
| --- | ---: | ---: | ---: | --- |
| `alpaca-paper-bot-main.timer` | Mon-Fri 16:15 TR | `AccuracySec=1s` | 430 min | Covers entry and all intraday exits |
| `alpaca-paper-bot-close.timer` | Mon-Fri 21:10 TR | `AccuracySec=1s` | 135 min | Backup close guard |

Services run:

```bash
paper_bot.py --execute --auto-window --loop
```

The bot remains paper-only because `strategy_config.json` requires:

- `paper_only: true`
- `live_trading_enabled: false`
- `https://paper-api.alpaca.markets`

## Install On Ubuntu VPS

```bash
git clone https://github.com/chaoslightnight2-ctrl/alpaca-paper-bot-mix00317.git
cd alpaca-paper-bot-mix00317
bash deploy/vps/install_systemd.sh
sudo nano /etc/alpaca-paper-bot.env
```

Put only paper keys in `/etc/alpaca-paper-bot.env`:

```env
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
ALPACA_DATA_FEED=iex
```

## Check

```bash
bash deploy/vps/check_status.sh
```

Manual smoke test:

```bash
sudo systemctl start alpaca-paper-bot-main.service
journalctl -u alpaca-paper-bot-main.service -f
```

## Reliability Reality

This can run while your computer is off because the VPS stays on. It is also much more accurate than GitHub cron. Still, no setup can be mathematically 100% guaranteed because failures can happen at:

- VPS provider
- network route
- Alpaca API
- market data feed
- server disk/CPU
- exchange/broker side

For stronger redundancy, run two independent VPS providers but keep only one account allowed to open positions, or use the second as close-only monitoring.
