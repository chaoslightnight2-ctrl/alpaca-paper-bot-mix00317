from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def drawdown_pct(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity / peak - 1.0) * 100.0)


def simulate(
    daily: np.ndarray,
    paths: int,
    horizon: int,
    initial: float,
    seed: int,
    entry_capture_prob: float,
    close_capture_prob: float,
    extra_cost_bps: float,
    delayed_close_penalty_bps: float,
    missed_close_tail_prob: float,
    missed_close_tail_loss: float,
) -> dict:
    rng = np.random.default_rng(seed)
    active = daily[daily != 0.0]
    finals = np.empty(paths)
    dds = np.empty(paths)
    active_trade_days = np.empty(paths)
    for i in range(paths):
        sample = rng.choice(active, size=horizon, replace=True)
        entry_ok = rng.random(horizon) < entry_capture_prob
        close_ok = rng.random(horizon) < close_capture_prob
        adjusted = np.where(entry_ok, sample, 0.0)

        # Entry/exit infrastructure cost. Only days with an attempted trade pay it.
        trade_mask = adjusted != 0.0
        adjusted[trade_mask] -= extra_cost_bps / 10000.0

        # If a close job is delayed, apply a conservative execution penalty.
        delayed_mask = trade_mask & (~close_ok)
        adjusted[delayed_mask] -= delayed_close_penalty_bps / 10000.0

        # Rare missed-close shock: if GitHub misses the exit window badly, paper can
        # carry exposure longer than modeled. This is deliberately conservative.
        tail_mask = delayed_mask & (rng.random(horizon) < missed_close_tail_prob)
        adjusted[tail_mask] -= missed_close_tail_loss

        equity = initial * np.cumprod(1.0 + adjusted)
        finals[i] = equity[-1]
        dds[i] = drawdown_pct(equity)
        active_trade_days[i] = np.count_nonzero(trade_mask)

    pct = {"p1": 1, "p5": 5, "p25": 25, "p50": 50, "p75": 75, "p95": 95, "p99": 99}
    return {
        "entry_capture_prob": entry_capture_prob,
        "close_capture_prob": close_capture_prob,
        "extra_cost_bps": extra_cost_bps,
        "delayed_close_penalty_bps": delayed_close_penalty_bps,
        "missed_close_tail_prob": missed_close_tail_prob,
        "missed_close_tail_loss_pct": missed_close_tail_loss * 100.0,
        "final_equity_tl": {k: float(np.percentile(finals, v)) for k, v in pct.items()},
        "return_pct": {k: float((np.percentile(finals, v) / initial - 1.0) * 100.0) for k, v in pct.items()},
        "max_drawdown_pct": {k: float(np.percentile(dds, v)) for k, v in pct.items()},
        "loss_probability_pct": float(np.mean(finals < initial) * 100.0),
        "prob_final_above_50k_pct": float(np.mean(finals > 50000.0) * 100.0),
        "prob_final_above_100k_pct": float(np.mean(finals > 100000.0) * 100.0),
        "active_trade_days": {k: float(np.percentile(active_trade_days, v)) for k, v in pct.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily", type=Path, default=Path("current_bot_equity_curve.csv"))
    parser.add_argument("--out", type=Path, default=Path("operational_monte_carlo_1y.json"))
    parser.add_argument("--paths", type=int, default=50000)
    parser.add_argument("--horizon", type=int, default=252)
    parser.add_argument("--initial", type=float, default=10000.0)
    parser.add_argument("--seed", type=int, default=20260521)
    args = parser.parse_args()

    df = pd.read_csv(args.daily)
    daily = df["net_return"].to_numpy(dtype=float)
    scenarios = {
        "ideal_local_or_vps_exact_windows": {
            "entry_capture_prob": 1.00,
            "close_capture_prob": 1.00,
            "extra_cost_bps": 0.0,
            "delayed_close_penalty_bps": 0.0,
            "missed_close_tail_prob": 0.0,
            "missed_close_tail_loss": 0.0,
        },
        "github_frequent_checks_base": {
            "entry_capture_prob": 0.90,
            "close_capture_prob": 0.95,
            "extra_cost_bps": 4.0,
            "delayed_close_penalty_bps": 12.0,
            "missed_close_tail_prob": 0.01,
            "missed_close_tail_loss": 0.015,
        },
        "github_looped_auto_window_base": {
            "entry_capture_prob": 0.97,
            "close_capture_prob": 0.985,
            "extra_cost_bps": 3.0,
            "delayed_close_penalty_bps": 6.0,
            "missed_close_tail_prob": 0.004,
            "missed_close_tail_loss": 0.010,
        },
        "github_looped_auto_window_conservative": {
            "entry_capture_prob": 0.90,
            "close_capture_prob": 0.95,
            "extra_cost_bps": 5.0,
            "delayed_close_penalty_bps": 12.0,
            "missed_close_tail_prob": 0.010,
            "missed_close_tail_loss": 0.015,
        },
        "github_delayed_conservative": {
            "entry_capture_prob": 0.70,
            "close_capture_prob": 0.85,
            "extra_cost_bps": 8.0,
            "delayed_close_penalty_bps": 25.0,
            "missed_close_tail_prob": 0.025,
            "missed_close_tail_loss": 0.025,
        },
        "github_bad_cron_stress": {
            "entry_capture_prob": 0.45,
            "close_capture_prob": 0.70,
            "extra_cost_bps": 12.0,
            "delayed_close_penalty_bps": 40.0,
            "missed_close_tail_prob": 0.05,
            "missed_close_tail_loss": 0.04,
        },
    }

    result = {
        "initial_capital_tl": args.initial,
        "horizon_trading_days": args.horizon,
        "mc_paths": args.paths,
        "source_daily_file": str(args.daily),
        "note": "Operational MC applies GitHub scheduling, missed-entry, delayed-close, and extra execution-cost haircuts to the fixed strategy daily return distribution.",
        "scenarios": {},
    }
    for idx, (name, params) in enumerate(scenarios.items()):
        result["scenarios"][name] = simulate(
            daily=daily,
            paths=args.paths,
            horizon=args.horizon,
            initial=args.initial,
            seed=args.seed + idx * 1000,
            **params,
        )

    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
