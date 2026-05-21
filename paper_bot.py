from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "strategy_config.json"
LOG_PATH = ROOT / "logs" / "paper_bot.log"
NY = ZoneInfo("America/New_York")
TR = ZoneInfo("Europe/Istanbul")
BAR_MINUTES = 5
SESSION_OPEN_HOUR = 9
SESSION_OPEN_MINUTE = 30
CONDITION_RE = re.compile(r"^([A-Za-z0-9_]+)\s*(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)$")


@dataclass(frozen=True)
class Bar:
    t: datetime
    o: float
    h: float
    l: float
    c: float
    v: float
    vw: float | None = None


def log(message: str) -> None:
    stamp = datetime.now(TR).isoformat(timespec="seconds")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def state_path(dry_run: bool) -> Path:
    return ROOT / "state" / ("dry_run_state.json" if dry_run else "paper_state.json")


class Alpaca:
    def __init__(self, config: dict[str, Any]) -> None:
        load_env_file(ROOT / ".env")
        key = os.environ.get("ALPACA_API_KEY") or os.environ.get("APCA_API_KEY_ID")
        secret = os.environ.get("ALPACA_API_SECRET") or os.environ.get("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise SystemExit("ALPACA_API_KEY ve ALPACA_API_SECRET env değişkenlerini ayarla.")
        self.key = key
        self.secret = secret
        trading = config["trading"]
        self.paper_base = str(trading["paper_base_url"]).rstrip("/")
        self.data_base = str(trading["data_base_url"]).rstrip("/")
        self.feed = os.environ.get("ALPACA_DATA_FEED", str(trading.get("data_feed", "iex"))).lower()
        if self.paper_base != "https://paper-api.alpaca.markets":
            raise SystemExit("Bu bot sadece Alpaca paper URL ile calisir.")
        if self.feed != "iex":
            raise SystemExit("Ucretsiz Alpaca uyumu icin feed 'iex' olmali. SIP aboneligi yoksa calismaz.")

    def _request(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        for attempt in range(4):
            req = Request(
                url,
                data=body,
                method=method,
                headers={
                    "APCA-API-KEY-ID": self.key,
                    "APCA-API-SECRET-KEY": self.secret,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            try:
                with urlopen(req, timeout=30) as response:
                    content = response.read().decode("utf-8")
                return json.loads(content) if content else {}
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code in {429, 500, 502, 503, 504} and attempt < 3:
                    retry_after = exc.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else 2.0**attempt
                    log(f"Alpaca HTTP {exc.code}, tekrar denenecek {delay:.1f}s: {detail[:160]}")
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"Alpaca HTTP {exc.code}: {detail}") from exc
            except URLError as exc:
                if attempt < 3:
                    delay = 2.0**attempt
                    log(f"Alpaca baglanti hatasi, tekrar denenecek {delay:.1f}s: {exc}")
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"Alpaca baglanti hatasi: {exc}") from exc
        raise RuntimeError("Alpaca request retry limiti doldu.")

    def account(self) -> dict[str, Any]:
        return self._request("GET", f"{self.paper_base}/v2/account")

    def asset(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", f"{self.paper_base}/v2/assets/{symbol}")

    def submit_market_order(self, symbol: str, qty: int, side: str, client_order_id: str) -> dict[str, Any]:
        payload = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": "market",
            "time_in_force": "day",
            "client_order_id": client_order_id[:48],
        }
        return self._request("POST", f"{self.paper_base}/v2/orders", payload)

    def positions(self) -> list[dict[str, Any]]:
        data = self._request("GET", f"{self.paper_base}/v2/positions")
        return data if isinstance(data, list) else []

    def orders(self, status: str, after: datetime, limit: int = 500) -> list[dict[str, Any]]:
        params = {
            "status": status,
            "after": after.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "limit": str(limit),
            "direction": "desc",
        }
        data = self._request("GET", f"{self.paper_base}/v2/orders?{urlencode(params)}")
        return data if isinstance(data, list) else []

    def bars(self, symbols: list[str], timeframe: str, start: datetime, end: datetime) -> dict[str, list[Bar]]:
        params = {
            "symbols": ",".join(symbols),
            "timeframe": timeframe,
            "start": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "end": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "adjustment": "raw",
            "feed": self.feed,
            "limit": 10000,
        }
        result: dict[str, list[Bar]] = {}
        while True:
            data = self._request("GET", f"{self.data_base}/v2/stocks/bars?{urlencode(params)}")
            for symbol, rows in data.get("bars", {}).items():
                bucket = result.setdefault(symbol, [])
                for row in rows:
                    bucket.append(
                        Bar(
                            t=datetime.fromisoformat(row["t"].replace("Z", "+00:00")).astimezone(NY),
                            o=float(row["o"]),
                            h=float(row["h"]),
                            l=float(row["l"]),
                            c=float(row["c"]),
                            v=float(row.get("v", 0.0)),
                            vw=float(row["vw"]) if row.get("vw") is not None else None,
                        )
                    )
            token = data.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        for symbol in result:
            result[symbol] = sorted(result[symbol], key=lambda bar: bar.t)
        return result


def session_open(day: datetime) -> datetime:
    return day.astimezone(NY).replace(hour=SESSION_OPEN_HOUR, minute=SESSION_OPEN_MINUTE, second=0, microsecond=0)


def bar_close_time(day: datetime, bar_index: int) -> datetime:
    return session_open(day) + timedelta(minutes=(bar_index + 1) * BAR_MINUTES)


def exit_order_time(day: datetime, bar_index: int) -> datetime:
    # Market/day orders sent at or after 16:00 ET can queue for the next day.
    # The final intraday exit is flattened just before the regular close.
    if bar_index >= 77:
        return session_open(day).replace(hour=15, minute=59)
    return bar_close_time(day, bar_index)


def regular_session_bars(bars: list[Bar], day: datetime) -> list[Bar]:
    open_time = session_open(day)
    close_time = open_time.replace(hour=16, minute=0)
    rows = [bar for bar in bars if open_time <= bar.t < close_time]
    return sorted(rows, key=lambda bar: bar.t)[:78]


def previous_daily_bars(bars: list[Bar], day: datetime) -> list[Bar]:
    day_date = day.astimezone(NY).date()
    return sorted([bar for bar in bars if bar.t.astimezone(NY).date() < day_date], key=lambda bar: bar.t)


def cumulative_vwap(rows: list[Bar], upto: int) -> float:
    num = 0.0
    den = 0.0
    for bar in rows[: upto + 1]:
        typical = bar.vw if bar.vw is not None else (bar.h + bar.l + bar.c) / 3.0
        vol = max(bar.v, 1.0)
        num += typical * vol
        den += vol
    return num / den if den else rows[upto].c


def build_features(symbol: str, rows: list[Bar], daily: list[Bar], qqq: dict[str, float], entry_bar: int) -> dict[str, Any] | None:
    if len(rows) <= entry_bar or len(daily) < 2:
        return None
    day_open = rows[0].o
    entry = rows[entry_bar].c
    prev_close = daily[-1].c
    prev_2_close = daily[-2].c if len(daily) >= 2 else prev_close
    prev_5_base = daily[-5].c if len(daily) >= 5 else prev_2_close
    highs = [bar.h for bar in rows[: entry_bar + 1]]
    lows = [bar.l for bar in rows[: entry_bar + 1]]
    first_high = max(highs)
    first_low = min(lows)
    first_range = (first_high - first_low) / day_open if day_open else 0.0
    early = entry / day_open - 1.0 if day_open else 0.0
    # Match the research scripts' cached-table feature reconstruction:
    # entry_pos_range was approximated from early/first_range, not from
    # exact high-low location, because exact entry high/low was not persisted.
    entry_pos = (early / first_range + 0.5) if first_range else 0.5
    entry_pos = max(0.0, min(1.0, entry_pos))
    open_vol = max(sum(max(bar.v, 0.0) for bar in rows[: min(6, len(rows))]) / max(min(6, len(rows)), 1), 1.0)
    vwap = cumulative_vwap(rows, entry_bar)
    features = {
        "symbol": symbol,
        "entry_price": entry,
        "gap": day_open / prev_close - 1.0 if prev_close else 0.0,
        "prev_day_ret": prev_close / prev_2_close - 1.0 if prev_2_close else 0.0,
        "prev_5_ret": prev_close / prev_5_base - 1.0 if prev_5_base else 0.0,
        "early": early,
        "vwap_dist": entry / vwap - 1.0 if vwap else 0.0,
        "rvol": rows[entry_bar].v / open_vol,
        "entry_range_pct": first_range,
        "or_pct": first_range,
        "entry_pos_range": entry_pos,
        "pos_or": entry_pos,
        "entry_high_dist": (entry_pos - 1.0) * first_range,
        "entry_low_dist": entry_pos * first_range,
        "entry_range_expansion": 1.0,
        "first_range": first_range,
        "qqq_early": qqq.get("qqq_early", 0.0),
        "qqq_gap": qqq.get("qqq_gap", 0.0),
    }
    features["rel_early_qqq"] = features["early"] - features["qqq_early"]
    features["signal_score"] = signal_score(features)
    return features


def signal_score(row: dict[str, Any], expr: str = "default") -> float:
    if expr == "abs_early_rvol":
        return abs(float(row["early"])) + min(float(row["rvol"]), 5.0) * 0.10
    if expr == "momentum":
        return float(row["early"]) + float(row["rel_early_qqq"]) + min(float(row["rvol"]), 5.0) * 0.10
    if expr == "reversal":
        return -float(row["early"]) + abs(float(row["prev_day_ret"])) * 0.25
    if expr == "range_vwap":
        return abs(float(row["first_range"])) + abs(float(row["vwap_dist"])) * 0.50
    if expr == "flat":
        return 1.0
    return (
        min(float(row["rvol"]), 5.0) * 0.10
        + abs(float(row["first_range"])) * 8.0
        + abs(float(row["rel_early_qqq"])) * 40.0
        + abs(float(row["vwap_dist"])) * 25.0
        + abs(float(row["gap"])) * 15.0
        + abs(float(row["early"])) * 20.0
    )


def rule_passes(row: dict[str, Any], rule: str) -> bool:
    if not rule or rule == "all":
        return True
    for part in rule.split(" and "):
        match = CONDITION_RE.match(part.strip())
        if not match:
            log(f"Kural parse edilemedi: {part!r}")
            return False
        feature, op, raw = match.groups()
        value = float(row.get(feature, math.nan))
        threshold = float(raw)
        if not math.isfinite(value):
            return False
        if op == "<=" and not value <= threshold:
            return False
        if op == ">=" and not value >= threshold:
            return False
        if op == "<" and not value < threshold:
            return False
        if op == ">" and not value > threshold:
            return False
    return True


def rank_pct(values: list[float]) -> list[float]:
    if not values:
        return []
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    denom = max(len(values) - 1, 1)
    for rank, idx in enumerate(order):
        ranks[idx] = rank / denom
    return ranks


def apply_sleeve_scores(candidates: list[dict[str, Any]], expr: str) -> None:
    if not candidates:
        return
    if expr == "abs_early_rvol":
        a = rank_pct([abs(float(row["early"])) for row in candidates])
        b = rank_pct([min(float(row["rvol"]), 5.0) for row in candidates])
        for row, av, bv in zip(candidates, a, b):
            row["signal_score"] = av + bv
        return
    if expr == "momentum":
        a = rank_pct([float(row["early"]) for row in candidates])
        b = rank_pct([float(row["rel_early_qqq"]) for row in candidates])
        c = rank_pct([min(float(row["rvol"]), 5.0) for row in candidates])
        for row, av, bv, cv in zip(candidates, a, b, c):
            row["signal_score"] = av + bv + cv
        return
    if expr == "reversal":
        a = rank_pct([-float(row["early"]) for row in candidates])
        b = rank_pct([abs(float(row["prev_day_ret"])) for row in candidates])
        for row, av, bv in zip(candidates, a, b):
            row["signal_score"] = av + bv
        return
    if expr == "range_vwap":
        a = rank_pct([float(row["first_range"]) for row in candidates])
        b = rank_pct([abs(float(row["vwap_dist"])) for row in candidates])
        for row, av, bv in zip(candidates, a, b):
            row["signal_score"] = av + bv
        return
    if expr == "flat":
        for row in candidates:
            row["signal_score"] = 1.0


def is_shortable(alpaca: Alpaca, symbol: str, cache: dict[str, bool], dry_run: bool) -> bool:
    if dry_run:
        return True
    if symbol not in cache:
        asset = alpaca.asset(symbol)
        cache[symbol] = bool(asset.get("shortable")) and bool(asset.get("tradable", True))
    return cache[symbol]


def load_market(alpaca: Alpaca, symbols: list[str], now: datetime) -> tuple[dict[str, list[Bar]], dict[str, list[Bar]]]:
    start = (now - timedelta(days=20)).astimezone(NY).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.astimezone(NY) + timedelta(minutes=1)
    intraday = alpaca.bars(symbols, "5Min", start, end)
    daily = alpaca.bars(symbols, "1Day", start - timedelta(days=25), end)
    return intraday, daily


def due_entry(sleeve: dict[str, Any], today: datetime, now: datetime, grace_minutes: int, allow_late: bool) -> bool:
    scheduled = bar_close_time(today, int(sleeve["entry_bar"]))
    if now < scheduled:
        return False
    return allow_late or now <= scheduled + timedelta(minutes=grace_minutes)


def entry_window_summary(sleeves: list[dict[str, Any]], today: datetime, now: datetime, grace_minutes: int) -> str:
    windows = []
    for sleeve in sleeves:
        scheduled = bar_close_time(today, int(sleeve["entry_bar"]))
        late_until = scheduled + timedelta(minutes=grace_minutes)
        windows.append((scheduled, late_until, str(sleeve.get("id", "-"))))
    if not windows:
        return "Config içinde sleeve yok."
    first_open = min(start for start, _end, _sid in windows)
    last_close = max(end for _start, end, _sid in windows)
    if now < first_open:
        next_items = sorted(windows, key=lambda item: item[0])[:3]
        detail = ", ".join(f"{sid} {start.astimezone(TR).strftime('%H:%M')} TR" for start, _end, sid in next_items)
        return f"Yeni giriş bekleniyor. İlk pencere {first_open.astimezone(TR).strftime('%H:%M')} TR; sıradaki: {detail}."
    if now > last_close:
        return (
            f"Bugünkü giriş penceresi kapalı. Strateji {first_open.astimezone(TR).strftime('%H:%M')}-{last_close.astimezone(TR).strftime('%H:%M')} TR "
            "arasında yeni pozisyon açar; bot açık pozisyon çıkışlarını izlemeye devam ediyor."
        )
    active = [sid for start, end, sid in windows if start <= now <= end]
    if active:
        return f"Giriş penceresi açık ama bu sleeve'ler bugün işaretlenmiş olabilir: {', '.join(active)}."
    next_items = [(start, sid) for start, _end, sid in windows if start > now]
    if next_items:
        start, sid = sorted(next_items)[0]
        return f"Şu an ara pencere. Sıradaki giriş {sid} için {start.astimezone(TR).strftime('%H:%M')} TR."
    return "Bu turda yeni giriş zamanı yok."


def due_exit(position: dict[str, Any], now: datetime) -> bool:
    return now >= datetime.fromisoformat(position["exit_at"])


def position_key(day_key: str, sleeve: dict[str, Any], symbol: str) -> str:
    return f"{day_key}:{sleeve['id']}:{sleeve['side']}:{symbol}"


def submit_or_log(alpaca: Alpaca, dry_run: bool, symbol: str, qty: int, side: str, client_order_id: str) -> dict[str, Any]:
    if dry_run:
        log(f"DRY-RUN order: {side.upper()} {qty} {symbol} client_id={client_order_id[:48]}")
        return {"id": "dry-run", "symbol": symbol, "qty": qty, "side": side}
    order = alpaca.submit_market_order(symbol, qty, side, client_order_id)
    log(f"PAPER order gönderildi: {side.upper()} {qty} {symbol} order_id={order.get('id')}")
    return order


def estimate_reserved_notional(state: dict[str, Any]) -> float:
    total = 0.0
    for pos in state.get("positions", []):
        if pos.get("closed"):
            continue
        total += float(pos.get("qty", 0)) * float(pos.get("entry_price_seen", 0.0))
    return total


def sleeve_by_id(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(sleeve.get("id")): sleeve for sleeve in config.get("sleeves", [])}


def reconstruct_due_closes_from_broker(alpaca: Alpaca, config: dict[str, Any], now: datetime) -> dict[tuple[str, str], int]:
    today = now.astimezone(NY)
    day_key = today.strftime("%Y-%m-%d")
    prefix = str(config.get("trading", {}).get("client_order_prefix", "v22a7"))
    sleeves = sleeve_by_id(config)
    start = session_open(today) - timedelta(minutes=30)
    orders = alpaca.orders("all", start)
    due: dict[tuple[str, str], int] = {}
    for order in orders:
        client_id = str(order.get("client_order_id") or "")
        if not client_id.startswith(f"{prefix}-{day_key}:") or "-open" not in client_id:
            continue
        if str(order.get("status", "")).lower() not in {"filled", "partially_filled"}:
            continue
        parts = client_id.split(":")
        if len(parts) < 4:
            continue
        sleeve_id = parts[1]
        strategy_side = parts[2]
        symbol = parts[3].split("-")[0]
        sleeve = sleeves.get(sleeve_id)
        if not sleeve or strategy_side not in {"long", "short"}:
            continue
        if now < exit_order_time(today, int(sleeve["exit_bar"])):
            continue
        filled_qty = int(float(order.get("filled_qty") or order.get("qty") or 0))
        if filled_qty <= 0:
            continue
        close_side = "sell" if strategy_side == "long" else "buy"
        key = (symbol, close_side)
        due[key] = due.get(key, 0) + filled_qty
    return due


def existing_bot_client_order_ids(alpaca: Alpaca, config: dict[str, Any], now: datetime) -> set[str]:
    day_key = now.astimezone(NY).strftime("%Y-%m-%d")
    prefix = str(config.get("trading", {}).get("client_order_prefix", "v22a7"))
    start = session_open(now) - timedelta(minutes=30)
    ids: set[str] = set()
    for order in alpaca.orders("all", start):
        client_id = str(order.get("client_order_id") or "")
        if client_id.startswith(f"{prefix}-{day_key}:"):
            ids.add(client_id)
    return ids


def close_due_from_broker(args: argparse.Namespace) -> None:
    config = load_json(CONFIG_PATH, {})
    if not config:
        raise SystemExit(f"Config yok: {CONFIG_PATH}")
    alpaca = Alpaca(config)
    now = datetime.now(NY) if args.now is None else datetime.fromisoformat(args.now).astimezone(NY)
    account = alpaca.account()
    log(
        f"Broker close kontrolu equity={float(account.get('equity') or 0.0):.2f}, "
        f"dry_run={args.dry_run}, now_NY={now.isoformat(timespec='seconds')}"
    )
    due = reconstruct_due_closes_from_broker(alpaca, config, now)
    if not due:
        log("Broker order geçmişinden vadesi gelen bot çıkışı bulunmadı.")
        return
    broker_positions = {str(p.get("symbol")): int(abs(float(p.get("qty") or 0))) for p in alpaca.positions()}
    prefix = str(config.get("trading", {}).get("client_order_prefix", "v22a7"))[:12]
    day_key = now.strftime("%Y-%m-%d")
    for (symbol, close_side), qty in sorted(due.items()):
        available = broker_positions.get(symbol, 0)
        close_qty = min(int(qty), available)
        if close_qty <= 0:
            log(f"SKIP broker pozisyon yok: {symbol} due_qty={qty}")
            continue
        submit_or_log(alpaca, args.dry_run, symbol, close_qty, close_side, f"{prefix}-{day_key}:broker-close:{symbol}")


def run_once(args: argparse.Namespace) -> None:
    config = load_json(CONFIG_PATH, {})
    if not config:
        raise SystemExit(f"Config yok: {CONFIG_PATH}")
    alpaca = Alpaca(config)
    account = alpaca.account()
    equity = float(account.get("equity") or account.get("portfolio_value") or 0.0)
    buying_power = float(account.get("buying_power") or 0.0)
    now = (datetime.now(NY) if args.now is None else datetime.fromisoformat(args.now).astimezone(NY))
    today = now.astimezone(NY)
    day_key = today.strftime("%Y-%m-%d")
    state = load_json(state_path(args.dry_run), {"positions": [], "entered": {}})
    state.setdefault("positions", [])
    state.setdefault("entered", {})
    log(f"Hesap equity={equity:.2f}, buying_power={buying_power:.2f}, dry_run={args.dry_run}, now_NY={now.isoformat(timespec='seconds')}")

    # Close before opening new exposure.
    for pos in state["positions"]:
        if pos.get("closed"):
            continue
        if not due_exit(pos, now):
            continue
        close_side = "sell" if pos["side"] == "long" else "buy"
        client_prefix = str(config.get("trading", {}).get("client_order_prefix", "v22a7"))[:12]
        submit_or_log(alpaca, args.dry_run, pos["symbol"], int(pos["qty"]), close_side, f"{client_prefix}-{pos['key']}-close")
        pos["closed"] = True
        pos["closed_at"] = now.isoformat()
    save_json(state_path(args.dry_run), state)

    sleeves = list(config.get("sleeves", []))
    grace = int(config.get("trading", {}).get("entry_grace_minutes", 10))
    entry_sleeves = [s for s in sleeves if due_entry(s, today, now, grace, args.allow_late_entry)]
    entry_sleeves = [s for s in entry_sleeves if not state["entered"].get(f"{day_key}:{s['id']}")]
    if not entry_sleeves:
        log(entry_window_summary(sleeves, today, now, grace))
        return

    symbols = list(config["symbols"])
    intraday, daily = load_market(alpaca, symbols, now)
    qqq_rows = regular_session_bars(intraday.get("QQQ", []), today)
    qqq_daily = previous_daily_bars(daily.get("QQQ", []), today)
    qqq_by_entry: dict[int, dict[str, float]] = {}
    for entry_bar in sorted({int(s["entry_bar"]) for s in entry_sleeves}):
        qqq_features = build_features("QQQ", qqq_rows, qqq_daily, {}, entry_bar)
        qqq_by_entry[entry_bar] = {
            "qqq_early": float(qqq_features.get("early", 0.0)) if qqq_features else 0.0,
            "qqq_gap": float(qqq_features.get("gap", 0.0)) if qqq_features else 0.0,
        }
    shortable_cache: dict[str, bool] = {}
    max_gross = float(config.get("trading", {}).get("max_total_gross_exposure", 2.0))
    min_buying_power_buffer = float(config.get("trading", {}).get("min_buying_power_buffer_fraction", 0.05))
    available_buying_power = max(0.0, buying_power - estimate_reserved_notional(state))
    client_prefix = str(config.get("trading", {}).get("client_order_prefix", "v22a7"))[:12]
    broker_client_order_ids = set() if args.dry_run else existing_bot_client_order_ids(alpaca, config, now)

    for sleeve in sorted(entry_sleeves, key=lambda s: (int(s["entry_bar"]), s["id"])):
        entry_bar = int(sleeve["entry_bar"])
        qqq = qqq_by_entry.get(entry_bar, {"qqq_early": 0.0, "qqq_gap": 0.0})
        candidates = []
        for symbol in symbols:
            rows = regular_session_bars(intraday.get(symbol, []), today)
            features = build_features(symbol, rows, previous_daily_bars(daily.get(symbol, []), today), qqq, entry_bar)
            if not features or not rule_passes(features, str(sleeve["rule"])):
                continue
            candidates.append(features)
        apply_sleeve_scores(candidates, str(sleeve.get("score_expr", "default")))
        picks = sorted(candidates, key=lambda row: row["signal_score"], reverse=True)[: int(sleeve["top_n"])]
        state["entered"][f"{day_key}:{sleeve['id']}"] = True
        if not picks:
            log(f"{sleeve['id']} {sleeve['side']} sinyal yok.")
            continue
        sleeve_budget = equity * float(sleeve["effective_capital_weight"]) * min(float(sleeve["leverage"]), max_gross)
        per_trade = sleeve_budget / max(len(picks), 1)
        log(f"{sleeve['id']} {sleeve['side']} {len(picks)} sinyal, sleeve_budget={sleeve_budget:.2f}, per_trade={per_trade:.2f}")
        for pick in picks:
            symbol = pick["symbol"]
            if sleeve["side"] == "short" and not is_shortable(alpaca, symbol, shortable_cache, args.dry_run):
                log(f"SKIP shortable değil: {symbol}")
                continue
            qty = int(math.floor(per_trade / float(pick["entry_price"])))
            if qty <= 0:
                log(f"SKIP bütçe yetmedi: {symbol} price={pick['entry_price']:.2f}, per_trade={per_trade:.2f}")
                continue
            notional = qty * float(pick["entry_price"])
            if notional > available_buying_power * (1.0 - min_buying_power_buffer):
                log(f"SKIP buying_power limiti: {symbol} notional={notional:.2f}, available_bp={available_buying_power:.2f}")
                continue
            order_side = "buy" if sleeve["side"] == "long" else "sell"
            key = position_key(day_key, sleeve, symbol)
            client_order_id = f"{client_prefix}-{key}-open"[:48]
            if client_order_id in broker_client_order_ids:
                log(f"SKIP duplicate broker order: {client_order_id}")
                continue
            order = submit_or_log(alpaca, args.dry_run, symbol, qty, order_side, client_order_id)
            broker_client_order_ids.add(client_order_id)
            available_buying_power = max(0.0, available_buying_power - notional)
            state["positions"].append(
                {
                    "key": key,
                    "symbol": symbol,
                    "side": sleeve["side"],
                    "qty": qty,
                    "sleeve_id": sleeve["id"],
                    "entry_price_seen": pick["entry_price"],
                    "entry_at": now.isoformat(),
                    "exit_bar": int(sleeve["exit_bar"]),
                    "exit_at": exit_order_time(today, int(sleeve["exit_bar"])).isoformat(),
                    "order_id": order.get("id"),
                    "closed": False,
                }
            )
            save_json(state_path(args.dry_run), state)
    save_json(state_path(args.dry_run), state)


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper-only Alpaca bot for v22 aday 7.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Sinyal ve emirleri sadece logla.")
    mode.add_argument("--execute", action="store_true", help="Alpaca paper hesaba gerçek paper emir gönder.")
    parser.add_argument("--loop", action="store_true", help="Sürekli çalış, 30 saniyede bir kontrol et.")
    parser.add_argument("--allow-late-entry", action="store_true", help="Günün giriş saatleri geçtiyse de sinyal üret. Test için kullan.")
    parser.add_argument("--now", help="Test için ISO zaman override, örn 2026-05-20T10:00:00-04:00.")
    parser.add_argument("--max-minutes", type=float, default=0.0, help="Loop modunda bu dakika dolunca temiz cik. GitHub Actions icin.")
    parser.add_argument("--close-due-from-broker", action="store_true", help="State dosyasi olmadan Alpaca order history'den bugunku bot pozisyonlarini kapat.")
    parser.add_argument("--auto-window", action="store_true", help="Her turda broker cikislarini ve yeni giris penceresini birlikte kontrol et.")
    args = parser.parse_args()
    args.dry_run = not args.execute
    started = time.monotonic()
    while True:
        try:
            if args.auto_window:
                close_due_from_broker(args)
                run_once(args)
            elif args.close_due_from_broker:
                close_due_from_broker(args)
            else:
                run_once(args)
        except Exception as exc:
            log(f"HATA: {exc}")
            if not args.loop:
                raise
        if not args.loop:
            break
        if args.max_minutes and (time.monotonic() - started) >= args.max_minutes * 60:
            log(f"max-minutes doldu ({args.max_minutes}); bot temiz cikiyor.")
            break
        time.sleep(30)


if __name__ == "__main__":
    main()
