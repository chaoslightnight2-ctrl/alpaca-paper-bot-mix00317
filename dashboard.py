from __future__ import annotations

import csv
import json
import os
import re
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
TR = ZoneInfo("Europe/Istanbul")
STATIC = ROOT / "dashboard_static"
CONFIG = ROOT / "strategy_config.json"
MC = ROOT / "current_bot_monte_carlo_50k.json"
EQUITY = ROOT / "current_bot_equity_curve.csv"
LOG = ROOT / "logs" / "paper_bot.log"
PAPER_STATE = ROOT / "state" / "paper_state.json"
DRY_STATE = ROOT / "state" / "dry_run_state.json"
ENV = ROOT / ".env"
SHUTDOWN_EVENT: threading.Event | None = None
LIVE_CACHE: dict = {"ts": 0.0, "data": None}
LIVE_CACHE_SECONDS = 60.0
LOG_TS_RE = re.compile(r"^\[(?P<ts>[^\]]+)\]\s*(?P<msg>.*)$")
ORDER_LOG_RE = re.compile(
    r"(?P<mode>DRY-RUN order|PAPER order[^:]*):\s+"
    r"(?P<side>[A-Z]+)\s+(?P<qty>\d+)\s+(?P<symbol>[A-Z0-9.]+)"
    r"(?:\s+client_id=(?P<client_id>\S+)|.*order_id=(?P<order_id>\S+))?"
)
SIGNAL_LOG_RE = re.compile(
    r"(?P<sleeve>m?\d*[A-Za-z0-9_]+)\s+(?P<side>long|short)\s+"
    r"(?P<count>\d+)\s+sinyal,\s+sleeve_budget=(?P<budget>[0-9.]+),\s+per_trade=(?P<per_trade>[0-9.]+)"
)


FEATURES_TR = {
    "prev_day_ret": "Dunku kapanis getirisi",
    "prev_5_ret": "Son 5 gun kapanis getirisi",
    "early": "Acilistan sonraki ilk hareket",
    "gap": "Acilis boslugu",
    "vwap_dist": "VWAP'a uzaklik",
    "entry_high_dist": "Giris aninda gun ici tepeye uzaklik",
    "entry_low_dist": "Giris aninda gun ici dibe uzaklik",
    "qqq_early": "QQQ erken hareketi",
    "qqq_gap": "QQQ acilis boslugu",
    "rel_early_qqq": "Sembole ozgu QQQ'ya gore guc",
    "rvol": "Goreceli hacim",
    "first_range": "Erken seans hareket araligi",
    "or_pct": "Erken seans hareket araligi",
    "pos_or": "Giris aninda erken araliktaki konum",
}


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def alpaca_get(path: str) -> dict | list:
    env = load_env_file(ENV)
    key = env.get("ALPACA_API_KEY") or os.environ.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_API_SECRET") or os.environ.get("ALPACA_API_SECRET")
    if not key or not secret:
        return {"_error": ".env icinde Alpaca key/secret yok"}
    request = Request(
        f"https://paper-api.alpaca.markets{path}",
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=12) as response:
            content = response.read().decode("utf-8")
        return json.loads(content) if content else {}
    except Exception as exc:
        return {"_error": str(exc)}


def live_alpaca() -> dict:
    now = time.monotonic()
    cached = LIVE_CACHE.get("data")
    if cached is not None and now - float(LIVE_CACHE.get("ts", 0.0)) < LIVE_CACHE_SECONDS:
        data = dict(cached)
        data["cached"] = True
        data["cache_age_seconds"] = round(now - float(LIVE_CACHE.get("ts", 0.0)), 1)
        return data
    account = alpaca_get("/v2/account")
    positions = alpaca_get("/v2/positions")
    orders = alpaca_get("/v2/orders?status=open&limit=100&direction=desc")
    activities = alpaca_get("/v2/account/activities/FILL?page_size=100")
    data = {
        "account": account,
        "positions": positions if isinstance(positions, list) else [],
        "orders": orders if isinstance(orders, list) else [],
        "fills": activities if isinstance(activities, list) else [],
        "cached": False,
        "cache_age_seconds": 0.0,
        "cache_seconds": LIVE_CACHE_SECONDS,
        "errors": {
            "account": account.get("_error") if isinstance(account, dict) else None,
            "positions": positions.get("_error") if isinstance(positions, dict) else None,
            "orders": orders.get("_error") if isinstance(orders, dict) else None,
            "fills": activities.get("_error") if isinstance(activities, dict) else None,
        },
    }
    LIVE_CACHE["ts"] = now
    LIVE_CACHE["data"] = data
    return data


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": str(exc)}


def tail(path: Path, lines: int = 180) -> list[str]:
    if not path.exists():
        return []
    try:
        data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    return data[-lines:]


def parse_time(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=TR)
        return dt.astimezone(TR)
    except Exception:
        return None


def log_events(lines: list[str]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    last_signal: dict[str, str] | None = None
    for line in lines:
        ts_match = LOG_TS_RE.match(line)
        ts = ts_match.group("ts") if ts_match else ""
        msg = ts_match.group("msg") if ts_match else line
        signal_match = SIGNAL_LOG_RE.search(msg)
        if signal_match:
            last_signal = {
                "timestamp": ts,
                "type": "signal",
                "sleeve": signal_match.group("sleeve"),
                "side": signal_match.group("side"),
                "count": signal_match.group("count"),
                "budget": signal_match.group("budget"),
                "per_trade": signal_match.group("per_trade"),
                "raw": msg,
            }
            events.append(last_signal)
            continue
        order_match = ORDER_LOG_RE.search(msg)
        if order_match:
            events.append(
                {
                    "timestamp": ts,
                    "type": "order",
                    "mode": order_match.group("mode"),
                    "symbol": order_match.group("symbol"),
                    "side": order_match.group("side"),
                    "qty": order_match.group("qty"),
                    "client_id": order_match.group("client_id") or "",
                    "order_id": order_match.group("order_id") or "",
                    "sleeve": last_signal.get("sleeve", "") if last_signal else "",
                    "raw": msg,
                }
            )
            continue
        if "SKIP" in msg or "HATA:" in msg or "sinyal yok" in msg:
            events.append({"timestamp": ts, "type": "notice", "raw": msg})
    return events[-80:]


def bot_runtime_status(logs: list[str], config: dict, paper_state: dict, dry_state: dict) -> dict:
    last_ts = None
    last_line = ""
    for line in reversed(logs):
        match = LOG_TS_RE.match(line)
        if match:
            last_ts = parse_time(match.group("ts"))
            last_line = match.group("msg")
            break
    age_seconds = None
    if last_ts is not None:
        age_seconds = max(0.0, (datetime.now(last_ts.tzinfo) - last_ts).total_seconds())
    running = age_seconds is not None and age_seconds <= 180
    has_error = any("HATA:" in line for line in logs[-20:])
    return {
        "strategy_name": config.get("strategy_name", "-"),
        "paper_only": bool(config.get("trading", {}).get("paper_only")),
        "live_trading_enabled": bool(config.get("trading", {}).get("live_trading_enabled")),
        "feed": config.get("trading", {}).get("data_feed"),
        "paper_base_url": config.get("trading", {}).get("paper_base_url"),
        "weighted_gross_leverage": sum(
            float(s.get("effective_capital_weight", 0.0)) * float(s.get("leverage", 0.0))
            for s in config.get("sleeves", [])
        ),
        "sleeve_count": len(config.get("sleeves", [])),
        "p50": config.get("paper_config_1y_mc_p50") or config.get("created_from_1y_mc_p50"),
        "p5": config.get("created_from_1y_mc_p5"),
        "p1": config.get("created_from_1y_mc_p1"),
        "last_log_at": last_ts.isoformat(timespec="seconds") if last_ts else None,
        "last_log_age_seconds": age_seconds,
        "last_log_line": last_line,
        "running": running,
        "has_recent_error": has_error,
        "paper_open_positions": len([p for p in paper_state.get("positions", []) if not p.get("closed")]),
        "dry_open_positions": len([p for p in dry_state.get("positions", []) if not p.get("closed")]),
    }


def read_equity(path: Path) -> list[dict[str, float | str]]:
    if not path.exists():
        return []
    rows: list[dict[str, float | str]] = []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                rows.append(
                    {
                        "date": row["date"],
                        "net_return": float(row["net_return"]),
                        "equity": float(row["equity"]),
                        "drawdown": float(row["drawdown"]),
                    }
                )
    except Exception:
        return []
    if len(rows) <= 900:
        return rows
    step = max(1, len(rows) // 900)
    sampled = rows[::step]
    if sampled[-1]["date"] != rows[-1]["date"]:
        sampled.append(rows[-1])
    return sampled


def portfolio_curve_from_fills(fills: list[dict], account: dict) -> list[dict[str, float | str]]:
    if not fills:
        return []
    try:
        current_equity = float(account.get("equity") or 0.0)
    except Exception:
        current_equity = 0.0
    daily: dict[str, float] = {}
    for fill in fills:
        date = str(fill.get("transaction_time") or fill.get("date") or "")[:10]
        if not date:
            continue
        qty = float(fill.get("qty") or 0.0)
        price = float(fill.get("price") or 0.0)
        side = str(fill.get("side") or "")
        signed = qty * price * (-1.0 if side == "buy" else 1.0)
        daily[date] = daily.get(date, 0.0) + signed
    rows = []
    running_cashflow = 0.0
    for date in sorted(daily):
        running_cashflow += daily[date]
        rows.append({"date": date, "cashflow": running_cashflow, "value": current_equity + running_cashflow})
    return rows


def parse_rule(rule: str) -> list[dict[str, str]]:
    pieces = []
    for raw in str(rule or "").split(" and "):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split()
        if len(parts) != 3:
            pieces.append({"raw": raw, "label": raw, "reason": "Kural ham haliyle uygulanir."})
            continue
        feature, op, value = parts
        name = FEATURES_TR.get(feature, feature)
        direction = {
            ">": "ustunde",
            ">=": "en az",
            "<": "altinda",
            "<=": "en fazla",
        }.get(op, op)
        reason = reason_for(feature, op)
        pieces.append({"raw": raw, "label": f"{name} {direction} {value}", "reason": reason})
    return pieces


def reason_for(feature: str, op: str) -> str:
    if feature in {"entry_low_dist", "entry_high_dist", "first_range"}:
        return "Fiyat gun ici araliktaki konumuna gore kirilim mi tepki mi ariyor."
    if feature in {"vwap_dist"}:
        return "VWAP kurumsal ortalama maliyet gibi okunur; uzaklik baski veya geri donus sinyali verir."
    if feature in {"qqq_early", "qqq_gap", "rel_early_qqq"}:
        return "QQQ piyasa rejimini temsil eder; hisse piyasanin tersine veya daha guclu hareket ediyorsa filtrelenir."
    if feature in {"prev_day_ret", "prev_5_ret"}:
        return "Onceki gunlerin hareketi momentum ve yorulma rejimini ayirmak icin kullanilir."
    if feature in {"gap", "early"}:
        return "Acilis boslugu ve ilk 5-15 dakikalik yon gun ici akisi belirlemek icin kullanilir."
    if feature == "rvol":
        return "Hacim hareketin tesadufi mi ciddi mi oldugunu ayirmaya yardim eder."
    return "Bu kosul tarihsel olarak daha iyi calisan alt evreni secmek icin kullanilir."


def enrich_sleeves(config: dict) -> list[dict]:
    enriched = []
    for sleeve in config.get("sleeves", []):
        item = dict(sleeve)
        item["rule_parts"] = parse_rule(str(sleeve.get("rule", "")))
        side = "LONG" if sleeve.get("side") == "long" else "SHORT"
        item["human_summary"] = (
            f"{side}: {int(sleeve.get('entry_bar', 0))}. 5 dakikalik bardan sonra girer, "
            f"{int(sleeve.get('exit_bar', 0))}. barda cikar. En iyi {int(sleeve.get('top_n', 1))} sembolu secer."
        )
        item["why"] = (
            "Sinyal puani hacim, erken aralik, QQQ'ya gore ayrisma, VWAP uzakligi, gap ve ilk hareketin "
            "buyuklugunu birlestirir; ayni gun cok aday varsa en guclu adaylari siralar."
        )
        enriched.append(item)
    return enriched


def process_status() -> list[dict[str, str | int]]:
    # Do not poll Windows process lists from the dashboard. The old version used
    # PowerShell every refresh and caused a visible flash. The server response
    # itself proves the integrated dashboard is alive; recent bot logs prove the
    # paper loop is alive.
    logs = tail(LOG, 8)
    bot_alive = any("Hesap equity=" in line or "PAPER order" in line or "DRY-RUN order" in line for line in logs)
    return [
        {"pid": 0, "command": "Dashboard aktif: bu panel entegre uygulama tarafindan servis ediliyor."},
        {
            "pid": 0,
            "command": "Paper bot aktif: son log akisi gorunuyor." if bot_alive else "Paper bot beklemede: henuz yeni log yok.",
        },
    ]


def snapshot() -> dict:
    config = read_json(CONFIG, {})
    mc = read_json(MC, {})
    paper_state = read_json(PAPER_STATE, {"positions": [], "entered": {}})
    dry_state = read_json(DRY_STATE, {"positions": [], "entered": {}})
    env_keys = []
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                env_keys.append(line.split("=", 1)[0])
    sleeves = enrich_sleeves(config)
    live = live_alpaca()
    logs = tail(LOG, 500)
    open_positions = [p for p in paper_state.get("positions", []) if not p.get("closed")]
    return {
        "generated_at": datetime.now(TR).isoformat(timespec="seconds"),
        "config": config,
        "mc": mc,
        "equity": read_equity(EQUITY),
        "logs": logs,
        "log_events": log_events(logs),
        "paper_state": paper_state,
        "dry_state": dry_state,
        "sleeves": sleeves,
        "open_positions": open_positions,
        "bot_status": bot_runtime_status(logs, config, paper_state, dry_state),
        "live": live,
        "live_portfolio_curve": portfolio_curve_from_fills(live.get("fills", []), live.get("account", {})),
        "checks": {
            "env_file": ENV.exists(),
            "env_keys": env_keys,
            "paper_state_file": PAPER_STATE.exists(),
            "dry_state_file": DRY_STATE.exists(),
            "log_file": LOG.exists(),
            "feed": config.get("trading", {}).get("data_feed"),
            "paper_base_url": config.get("trading", {}).get("paper_base_url"),
            "sizing_method": config.get("trading", {}).get("sizing_method"),
        },
        "processes": process_status(),
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/snapshot":
            return self.json(snapshot())
        if parsed.path == "/":
            return self.file(STATIC / "index.html", "text/html; charset=utf-8")
        target = STATIC / parsed.path.lstrip("/")
        if target.exists() and target.is_file() and target.resolve().is_relative_to(STATIC.resolve()):
            content_type = "text/plain"
            if target.suffix == ".css":
                content_type = "text/css; charset=utf-8"
            elif target.suffix == ".js":
                content_type = "application/javascript; charset=utf-8"
            elif target.suffix == ".html":
                content_type = "text/html; charset=utf-8"
            return self.file(target, content_type)
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/shutdown":
            if SHUTDOWN_EVENT is not None:
                SHUTDOWN_EVENT.set()
            return self.json({"ok": True})
        self.send_error(404)

    def json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Dashboard: http://127.0.0.1:8765")
    server.serve_forever()


if __name__ == "__main__":
    main()
