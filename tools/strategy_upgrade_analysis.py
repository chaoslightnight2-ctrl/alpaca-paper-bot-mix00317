from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


FEATURES = [
    "gap",
    "prev_day_ret",
    "prev_5_ret",
    "early",
    "vwap_dist",
    "rvol",
    "or_pct",
    "pos_or",
    "first_range",
    "qqq_early",
    "qqq_gap",
    "rel_early_qqq",
    "entry_high_dist",
    "entry_low_dist",
]


@dataclass(frozen=True)
class Edge:
    name: str
    side: str
    entry_bar: int
    exit_bar: int
    top_n: int
    leverage: float
    conditions: tuple[str, ...]
    score_expr: str


def desktop() -> Path:
    return next((Path.home() / "OneDrive").glob("Masa*"))


def load_table(path: Path) -> pd.DataFrame:
    df = pd.read_pickle(path).copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "symbol", "entry_bar"]).reset_index(drop=True)
    df["entry_low_dist"] = df["pos_or"].clip(0, 1) * df["first_range"].fillna(0)
    df["entry_high_dist"] = -(1.0 - df["pos_or"].clip(0, 1)) * df["first_range"].fillna(0)
    return add_score_columns(df)


def add_score_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["_score_abs_early_rvol"] = out["early"].abs().rank(pct=True) + out["rvol"].clip(0, 5).rank(pct=True)
    out["_score_momentum"] = out["early"].rank(pct=True) + out["rel_early_qqq"].rank(pct=True) + out["rvol"].clip(0, 5).rank(pct=True)
    out["_score_reversal"] = (-out["early"]).rank(pct=True) + out["prev_day_ret"].abs().rank(pct=True)
    out["_score_range_vwap"] = out["first_range"].rank(pct=True) + out["vwap_dist"].abs().rank(pct=True)
    out["_score_flat"] = 1.0
    return out


def parse_condition(cond: str) -> tuple[str, str, float]:
    parts = cond.split()
    if len(parts) != 3:
        raise ValueError(f"Bad condition: {cond}")
    return parts[0], parts[1], float(parts[2])


def condition_mask(df: pd.DataFrame, cond: str) -> pd.Series:
    feature, op, value = parse_condition(cond)
    if op == ">":
        return df[feature] > value
    if op == ">=":
        return df[feature] >= value
    if op == "<":
        return df[feature] < value
    if op == "<=":
        return df[feature] <= value
    raise ValueError(cond)


def conditions_mask(df: pd.DataFrame, conditions: tuple[str, ...]) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for cond in conditions:
        mask &= condition_mask(df, cond)
    return mask


def edge_daily_returns(df: pd.DataFrame, edge: Edge, cost_bps: float, conditions: tuple[str, ...] | None = None) -> pd.Series:
    part = df[df["entry_bar"] == edge.entry_bar].copy()
    if part.empty:
        return pd.Series(dtype=float)
    use_conditions = edge.conditions if conditions is None else conditions
    part = part[conditions_mask(part, use_conditions)].copy()
    ret_col = f"{edge.side}_ret_{edge.exit_bar}"
    if part.empty or ret_col not in part.columns:
        return pd.Series(dtype=float)
    part = part.dropna(subset=[ret_col])
    if part.empty:
        return pd.Series(dtype=float)
    part["_score"] = part[f"_score_{edge.score_expr}"]
    ranked = part.sort_values(["date", "_score"], ascending=[True, False]).groupby("date").head(edge.top_n)
    daily = ranked.groupby("date")[ret_col].mean()
    return (daily - cost_bps / 10000.0) * edge.leverage


def combine_daily(parts: list[pd.Series], weights: list[float]) -> pd.Series:
    idx = sorted(set().union(*[set(part.index) for part in parts]))
    out = pd.Series(0.0, index=pd.DatetimeIndex(idx))
    for part, weight in zip(parts, weights):
        out = out.add(part.reindex(out.index).fillna(0.0) * weight, fill_value=0.0)
    return out.sort_index()


def metrics(daily: pd.Series, initial: float) -> dict[str, Any]:
    daily = daily.sort_index().fillna(0.0)
    equity = initial * (1.0 + daily).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1.0
    years = {str(year): float(((1.0 + group).prod() - 1.0) * 100.0) for year, group in daily.groupby(daily.index.year)}
    gains = daily[daily > 0].sum()
    losses = -daily[daily < 0].sum()
    return {
        "final_equity": float(equity.iloc[-1]),
        "max_drawdown_pct": float(dd.min() * 100.0),
        "win_trade_days_pct": float((daily[daily != 0] > 0).mean() * 100.0),
        "trade_days": int((daily != 0).sum()),
        "profit_factor": float(gains / losses) if losses > 0 else float("inf"),
        "years_pct": years,
        "ratio_2023_2025": ratio_2023_2025(years),
        "min_2026_required_pct": min_2026_required(years),
        "passes_2026_quarter_rule": years.get("2026", -math.inf) >= min_2026_required(years),
    }


def ratio_2023_2025(years_pct: dict[str, float]) -> float:
    vals = [years_pct.get(year) for year in ("2023", "2024", "2025")]
    vals = [float(v) for v in vals if v is not None and math.isfinite(float(v))]
    if len(vals) < 3 or min(vals) <= 0:
        return float("inf")
    return max(vals) / min(vals)


def min_2026_required(years_pct: dict[str, float]) -> float:
    vals = [years_pct.get(year) for year in ("2023", "2024", "2025")]
    vals = [float(v) for v in vals if v is not None and math.isfinite(float(v))]
    if len(vals) < 3:
        return float("inf")
    return sum(vals) / len(vals) / 4.0


def monte_carlo(daily: pd.Series, paths: int, horizon: int, initial: float, seed: int) -> dict[str, Any]:
    active = daily[daily != 0].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    finals = np.empty(paths)
    dds = np.empty(paths)
    for i in range(paths):
        sample = rng.choice(active, size=horizon, replace=True)
        equity = initial * np.cumprod(1.0 + sample)
        peak = np.maximum.accumulate(equity)
        finals[i] = equity[-1]
        dds[i] = np.min(equity / peak - 1.0) * 100.0
    pct = {"p1": 1, "p5": 5, "p25": 25, "p50": 50, "p75": 75, "p95": 95, "p99": 99}
    return {
        "final_equity_tl": {key: float(np.percentile(finals, value)) for key, value in pct.items()},
        "return_pct": {key: float((np.percentile(finals, value) / initial - 1.0) * 100.0) for key, value in pct.items()},
        "max_drawdown_pct": {key: float(np.percentile(dds, value)) for key, value in pct.items()},
        "loss_probability_pct": float(np.mean(finals < initial) * 100.0),
        "prob_final_above_50k_pct": float(np.mean(finals > 50000.0) * 100.0),
    }


def operational_mc(daily: pd.Series, paths: int, horizon: int, initial: float, seed: int) -> dict[str, Any]:
    scenarios = {
        "github_current_base": (0.90, 0.95, 4.0, 12.0, 0.010, 0.015),
        "github_improved_loop_base": (0.97, 0.985, 3.0, 6.0, 0.004, 0.010),
        "github_improved_loop_conservative": (0.90, 0.95, 5.0, 12.0, 0.010, 0.015),
        "github_bad_cron_stress_after_loop": (0.65, 0.88, 8.0, 20.0, 0.020, 0.025),
    }
    active = daily[daily != 0].to_numpy(dtype=float)
    results = {}
    for offset, (name, params) in enumerate(scenarios.items()):
        entry_capture, close_capture, extra_bps, delay_bps, tail_prob, tail_loss = params
        rng = np.random.default_rng(seed + offset * 1000)
        finals = np.empty(paths)
        for i in range(paths):
            sample = rng.choice(active, size=horizon, replace=True)
            entry_ok = rng.random(horizon) < entry_capture
            close_ok = rng.random(horizon) < close_capture
            adjusted = np.where(entry_ok, sample, 0.0)
            trade_mask = adjusted != 0.0
            adjusted[trade_mask] -= extra_bps / 10000.0
            delayed = trade_mask & (~close_ok)
            adjusted[delayed] -= delay_bps / 10000.0
            tail = delayed & (rng.random(horizon) < tail_prob)
            adjusted[tail] -= tail_loss
            finals[i] = initial * np.prod(1.0 + adjusted)
        results[name] = {
            "entry_capture_prob": entry_capture,
            "close_capture_prob": close_capture,
            "final_equity_tl": {
                "p5": float(np.percentile(finals, 5)),
                "p50": float(np.percentile(finals, 50)),
                "p95": float(np.percentile(finals, 95)),
            },
            "loss_probability_pct": float(np.mean(finals < initial) * 100.0),
        }
    return results


def parse_edges(raw: str) -> list[Edge]:
    payload = json.loads(raw)
    edges = []
    for item in payload:
        conditions = item.get("conditions", ())
        if isinstance(conditions, str):
            conditions = tuple(part.strip() for part in conditions.split(" and ") if part.strip())
        edges.append(
            Edge(
                name=str(item["name"]),
                side=str(item["side"]),
                entry_bar=int(item["entry_bar"]),
                exit_bar=int(item["exit_bar"]),
                top_n=int(item["top_n"]),
                leverage=float(item["leverage"]),
                conditions=tuple(conditions),
                score_expr=str(item["score_expr"]),
            )
        )
    return edges


def parse_weights(raw: str) -> list[float]:
    return [float(x) for x in json.loads(raw)]


def mix_daily(df: pd.DataFrame, edges: list[Edge], weights: list[float], cost_bps: float) -> tuple[pd.Series, list[pd.Series]]:
    parts = [edge_daily_returns(df, edge, cost_bps) for edge in edges]
    return combine_daily(parts, weights), parts


def candidate_report(name: str, daily: pd.Series, paths: int, horizon: int, initial: float, seed: int) -> dict[str, Any]:
    return {
        "name": name,
        "historical": metrics(daily, initial),
        "one_year_monte_carlo": monte_carlo(daily, paths, horizon, initial, seed),
        "operational_monte_carlo": operational_mc(daily, paths, horizon, initial, seed + 500000),
    }


def ablation_report(df: pd.DataFrame, edges: list[Edge], weights: list[float], cost_bps: float, initial: float, paths: int, horizon: int) -> dict[str, Any]:
    base_daily, _ = mix_daily(df, edges, weights, cost_bps)
    base_mc = monte_carlo(base_daily, paths, horizon, initial, 7100)
    base_p50 = base_mc["final_equity_tl"]["p50"]
    remove_edge = []
    for idx, edge in enumerate(edges):
        keep_edges = [item for j, item in enumerate(edges) if j != idx]
        keep_weights = [w for j, w in enumerate(weights) if j != idx]
        total = sum(keep_weights) or 1.0
        keep_weights = [w / total for w in keep_weights]
        daily, _ = mix_daily(df, keep_edges, keep_weights, cost_bps)
        p50 = monte_carlo(daily, max(5000, paths // 10), horizon, initial, 8100 + idx)["final_equity_tl"]["p50"]
        remove_edge.append({"removed_edge": edge.name, "p50_tl": p50, "delta_vs_base_tl": p50 - base_p50})
    remove_condition = []
    for edge_idx, edge in enumerate(edges):
        for cond_idx, cond in enumerate(edge.conditions):
            new_edges = list(edges)
            new_conditions = tuple(c for j, c in enumerate(edge.conditions) if j != cond_idx)
            new_edges[edge_idx] = Edge(
                edge.name,
                edge.side,
                edge.entry_bar,
                edge.exit_bar,
                edge.top_n,
                edge.leverage,
                new_conditions,
                edge.score_expr,
            )
            daily, _ = mix_daily(df, new_edges, weights, cost_bps)
            p50 = monte_carlo(daily, max(5000, paths // 10), horizon, initial, 9100 + edge_idx * 100 + cond_idx)["final_equity_tl"]["p50"]
            remove_condition.append({"edge": edge.name, "removed_condition": cond, "p50_tl": p50, "delta_vs_base_tl": p50 - base_p50})
    return {
        "base_p50_tl": base_p50,
        "remove_edge": remove_edge,
        "remove_condition": remove_condition,
    }


def choose_candidates(top_mixes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in top_mixes.iterrows():
        years = json.loads(row["years"])
        years_pct = {key: float(value) * 100.0 for key, value in years.items()}
        ratio = ratio_2023_2025(years_pct)
        min_2026 = min_2026_required(years_pct)
        passes = ratio <= 1.5 and years_pct.get("2026", -math.inf) >= min_2026
        if passes:
            rows.append({**row.to_dict(), "years_pct_parsed": years_pct, "ratio_calc": ratio, "min_2026_required_pct": min_2026})
    out = pd.DataFrame(rows)
    return out.sort_values("p50", ascending=False).reset_index(drop=True)


def write_strategy_config(path: Path, selected: pd.Series, initial_config: dict[str, Any]) -> None:
    weights = parse_weights(selected["weights"])
    edges = parse_edges(selected["edges_json"])
    sleeves = []
    for idx, (weight, edge) in enumerate(zip(weights, edges), start=1):
        sleeves.append(
            {
                "parent_source": "intraday_feature_combo_search_v2_fast/top_mixes.csv",
                "kind": "regime_balanced_feature_combo_edge",
                "side": edge.side,
                "entry_bar": edge.entry_bar,
                "exit_bar": edge.exit_bar,
                "top_n": edge.top_n,
                "weight": weight,
                "leverage": edge.leverage,
                "rule": " and ".join(edge.conditions),
                "score_expr": edge.score_expr,
                "id": f"m0348_s{idx:03d}",
                "weight_normalized_all_sides": weight,
                "effective_capital_weight": weight,
                "sizing_method": "paper_weighted_edge",
            }
        )
    config = dict(initial_config)
    config["strategy_name"] = "mix_00348_regime_balanced_feature_combo_no_lookahead_paper"
    config["source"] = "qunatskills/checkpoints/intraday_feature_combo_search_v2_fast/top_mixes.csv"
    config["selection_note"] = (
        "Candidate selected after feature ablation and regime/year-balance review. "
        "Rules use entry-time features only; paper-only, not live trading."
    )
    config["created_from_1y_mc_p50"] = None
    config["created_from_1y_mc_p1"] = None
    config["created_from_1y_mc_p5"] = None
    config["ratio_2023_2025"] = float(selected["ratio_calc"])
    config["years_pct"] = selected["years_pct_parsed"]
    config["trading"] = dict(config["trading"])
    config["trading"]["entry_grace_minutes"] = 15
    config["trading"]["client_order_prefix"] = "m0348"
    config["trading"]["paper_only"] = True
    config["trading"]["live_trading_enabled"] = False
    config["sleeves"] = sleeves
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=desktop() / "qunatprototype" / "quant_ml_bot" / "reports" / "alpaca_intraday_table.pkl")
    parser.add_argument("--checkpoint", type=Path, default=desktop() / "qunatskills" / "checkpoints" / "intraday_feature_combo_search_v2_fast")
    parser.add_argument("--config", type=Path, default=Path("strategy_config.json"))
    parser.add_argument("--out", type=Path, default=Path("strategy_upgrade_report.json"))
    parser.add_argument("--candidate-config", type=Path, default=Path("strategy_config.candidate_mix_00348.json"))
    parser.add_argument("--paths", type=int, default=50000)
    parser.add_argument("--horizon", type=int, default=252)
    parser.add_argument("--initial", type=float, default=10000.0)
    parser.add_argument("--cost-bps", type=float, default=12.0)
    args = parser.parse_args()

    df = load_table(args.data)
    top_mixes = pd.read_csv(args.checkpoint / "top_mixes.csv")
    current_row = top_mixes[top_mixes["name"] == "mix_00317"].iloc[0]
    filtered = choose_candidates(top_mixes)
    selected = filtered.iloc[0]

    current_edges = parse_edges(current_row["edges_json"])
    current_weights = parse_weights(current_row["weights"])
    selected_edges = parse_edges(selected["edges_json"])
    selected_weights = parse_weights(selected["weights"])
    current_daily, _ = mix_daily(df, current_edges, current_weights, args.cost_bps)
    selected_daily, _ = mix_daily(df, selected_edges, selected_weights, args.cost_bps)

    report = {
        "constraints": {
            "max_ratio_2023_2025": 1.5,
            "min_2026_return": "2026 return >= average(2023,2024,2025) / 4",
            "cost_bps": args.cost_bps,
            "no_lookahead_note": "Signals use entry-time features; future return columns are labels only.",
        },
        "current": candidate_report("mix_00317_current", current_daily, args.paths, args.horizon, args.initial, 3100),
        "selected": candidate_report(str(selected["name"]), selected_daily, args.paths, args.horizon, args.initial, 4100),
        "top_filtered_candidates": filtered.head(10)[
            ["name", "p50", "p5", "max_drawdown_pct", "profit_factor", "trade_days", "ratio_calc", "min_2026_required_pct", "years_pct_parsed"]
        ].to_dict(orient="records"),
        "feature_ablation_selected": ablation_report(
            df, selected_edges, selected_weights, args.cost_bps, args.initial, args.paths, args.horizon
        ),
        "feature_ablation_current": ablation_report(
            df, current_edges, current_weights, args.cost_bps, args.initial, args.paths, args.horizon
        ),
    }
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    initial_config = json.loads(args.config.read_text(encoding="utf-8"))
    write_strategy_config(args.candidate_config, selected, initial_config)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
