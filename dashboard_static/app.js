const $ = (id) => document.getElementById(id);
const fmtTL = (v) => Number.isFinite(+v) ? `${Math.round(+v).toLocaleString("tr-TR")} TL` : "-";
const shortId = (v) => v ? String(v).slice(0, 14) : "-";

let snapshot = null;

$("shutdownBtn").addEventListener("click", async () => {
  if (!confirm("Paper bot ve dashboard kapatılsın mı?")) return;
  await fetch("/api/shutdown", { method: "POST" });
  document.body.innerHTML = '<main class="shell"><section class="card"><h1>Bot kapatılıyor</h1><p>Paper bot ve panel birlikte durduruldu. Bu pencereyi kapatabilirsin.</p></section></main>';
});

async function load() {
  const response = await fetch("/api/snapshot", { cache: "no-store" });
  snapshot = await response.json();
  render(snapshot);
}

function render(data) {
  const live = data.live || {};
  const account = live.account || {};
  const positions = live.positions || [];
  const orders = live.orders || [];
  const fills = live.fills || [];

  $("updatedAt").textContent = data.generated_at || "-";
  renderStrategyStatus(data);
  $("liveEquity").textContent = fmtTL(account.equity);
  $("liveBuyingPower").textContent = fmtTL(account.buying_power);
  $("liveDailyPL").textContent = fmtTL(account.equity && account.last_equity ? (+account.equity - +account.last_equity) : NaN);
  $("livePositionCount").textContent = String(positions.length || 0);
  $("liveStatus").textContent = live.errors?.account
    ? "Bağlantı hatası"
    : live.cached
      ? `Canlı önbellek · ${Math.round(live.cache_age_seconds || 0)} sn`
      : "Canlı yenilendi";

  renderAccount(account);
  renderPositions(positions);
  renderOrders(orders);
  renderFills(fills);
  renderStatePositions(data.open_positions || []);
  renderBotOrderEvents(data.log_events || []);
  renderLogs(data.logs || []);
  renderChecks(data);
  drawLivePortfolio($("livePortfolioChart"), data);
}

function renderStrategyStatus(data) {
  const status = data.bot_status || {};
  const name = status.strategy_name || data.config?.strategy_name || "-";
  $("strategyName").textContent = compactStrategyName(name);
  $("strategyName").title = name;
  $("strategyMeta").textContent = `${status.sleeve_count ?? "-"} sleeve · ${status.feed || "-"} feed`;
  $("botRunning").textContent = status.has_recent_error ? "HATA" : (status.running ? "ÇALIŞIYOR" : "BEKLEMEDE");
  $("botRunning").className = status.has_recent_error ? "warn" : (status.running ? "ok" : "warn");
  const age = Number.isFinite(+status.last_log_age_seconds) ? `${Math.round(+status.last_log_age_seconds)} sn önce` : "log yok";
  $("botLastLog").textContent = `${age} · ${status.last_log_line || "-"}`;
  $("strategyP50").textContent = fmtTL(status.p50);
  $("strategyP5").textContent = `p5 ${fmtTL(status.p5)} · p1 ${fmtTL(status.p1)}`;
  $("strategyGross").textContent = Number.isFinite(+status.weighted_gross_leverage) ? (+status.weighted_gross_leverage).toFixed(3) : "-";
  $("strategyMode").textContent = status.paper_only && !status.live_trading_enabled
    ? "Paper only · live kapalı"
    : "Kontrol gerekli";
}

function compactStrategyName(name) {
  const text = String(name || "-");
  return text.length <= 34 ? text : `${text.slice(0, 31)}...`;
}

function renderAccount(account) {
  const rows = [
    ["Equity", fmtTL(account.equity)],
    ["Portfolio Value", fmtTL(account.portfolio_value)],
    ["Cash", fmtTL(account.cash)],
    ["Buying Power", fmtTL(account.buying_power)],
    ["Long Market Value", fmtTL(account.long_market_value)],
    ["Short Market Value", fmtTL(account.short_market_value)],
    ["Daytrade Count", account.daytrade_count ?? "-"],
    ["Pattern Day Trader", String(account.pattern_day_trader ?? "-")],
  ];
  $("accountTable").innerHTML = rows.map(([k, v]) => `<div class="rowline"><span>${k}</span><strong>${v}</strong></div>`).join("");

  const equity = +account.equity || 0;
  const items = [
    ["Nakit", +account.cash || 0, "#20e8ff"],
    ["Long Değer", +account.long_market_value || 0, "#37f29a"],
    ["Short Değer", Math.abs(+account.short_market_value || 0), "#ff4fd8"],
  ];
  $("accountBars").innerHTML = items.map(([name, value, color]) => {
    const pct = equity > 0 ? Math.min(100, Math.abs(value) / equity * 100) : 0;
    return `<div class="barrow"><span>${name}</span><div class="bar"><i style="width:${pct}%;background:${color}"></i></div><strong>${fmtTL(value)}</strong></div>`;
  }).join("");
}

function renderPositions(positions) {
  $("livePositions").innerHTML = positions.length ? positions.map((p) => `
    <tr>
      <td>${p.symbol}</td>
      <td>${Number(p.qty).toLocaleString("tr-TR")}</td>
      <td>${fmtTL(p.market_value)}</td>
      <td class="${+p.unrealized_pl >= 0 ? "ok" : "warn"}">${fmtTL(p.unrealized_pl)}</td>
    </tr>
  `).join("") : `<tr><td colspan="4">Alpaca'da açık pozisyon yok.</td></tr>`;
}

function renderOrders(orders) {
  $("openOrders").innerHTML = orders.length ? orders.map((o) => `
    <tr>
      <td>${o.submitted_at ? new Date(o.submitted_at).toLocaleTimeString("tr-TR") : "-"}</td>
      <td>${o.symbol || "-"}</td>
      <td>${o.side || "-"}</td>
      <td>${o.qty || "-"}</td>
      <td>${o.type || "-"}</td>
      <td>${o.status || "-"}</td>
      <td title="${escapeHtml(o.client_order_id || o.id || "")}">${shortId(o.client_order_id || o.id)}</td>
    </tr>
  `).join("") : `<tr><td colspan="7">Açık emir yok.</td></tr>`;
}

function renderFills(fills) {
  $("fills").innerHTML = fills.length ? fills.slice(0, 60).map((f) => `
    <tr>
      <td>${f.transaction_time ? new Date(f.transaction_time).toLocaleString("tr-TR") : "-"}</td>
      <td>${f.symbol || "-"}</td>
      <td>${f.side || "-"}</td>
      <td>${f.qty || "-"}</td>
      <td>${fmtTL(f.price)}</td>
      <td title="${escapeHtml(f.order_id || "")}">${shortId(f.order_id)}</td>
    </tr>
  `).join("") : `<tr><td colspan="6">Henüz fill yok.</td></tr>`;
}

function renderStatePositions(positions) {
  $("positions").innerHTML = positions.length ? positions.map((p) => `
    <tr><td>${p.symbol}</td><td>${p.side}</td><td>${p.qty}</td><td>${new Date(p.exit_at).toLocaleTimeString("tr-TR")}</td></tr>
  `).join("") : `<tr><td colspan="4">Bot state içinde açık pozisyon yok.</td></tr>`;
}

function renderBotOrderEvents(events) {
  $("botOrderEvents").innerHTML = events.length ? events.slice().reverse().map((e) => {
    const detail = e.type === "signal"
      ? `budget ${fmtTL(e.budget)} · per trade ${fmtTL(e.per_trade)} · ${e.count || 0} sinyal`
      : e.type === "order"
        ? `${e.mode || "-"} · ${e.client_id || e.order_id || "-"}`
        : e.raw || "-";
    return `
      <tr>
        <td>${e.timestamp ? new Date(e.timestamp).toLocaleTimeString("tr-TR") : "-"}</td>
        <td>${e.type || "-"}</td>
        <td>${e.sleeve || "-"}</td>
        <td>${e.symbol || "-"}</td>
        <td>${e.side || "-"}</td>
        <td>${e.qty || e.count || "-"}</td>
        <td title="${escapeHtml(e.raw || detail)}">${escapeHtml(detail)}</td>
      </tr>
    `;
  }).join("") : `<tr><td colspan="7">Henüz bot emir olayı yok.</td></tr>`;
}

function renderLogs(logs) {
  $("logs").textContent = logs.length ? logs.join("\n") : "Henüz bot logu yok.";
}

function renderChecks(data) {
  const c = data.checks || {};
  const checks = [
    ["Paper URL", c.paper_base_url === "https://paper-api.alpaca.markets", c.paper_base_url || "-"],
    ["IEX feed", c.feed === "iex", c.feed || "-"],
    [".env", !!c.env_file, c.env_file ? "var" : "yok"],
    ["Paper state", !!c.paper_state_file, c.paper_state_file ? "var" : "henüz oluşmadı"],
    ["Log", !!c.log_file, c.log_file ? "var" : "henüz oluşmadı"],
  ];
  $("checksList").innerHTML = checks.map(([name, ok, value]) => `
    <div class="check"><span>${name}</span><strong class="${ok ? "ok" : "warn"}">${value}</strong></div>
  `).join("");

  const procs = data.processes || [];
  $("processList").innerHTML = procs.length ? procs.map((p) => `
    <div class="rule-chip"><strong>PID ${p.pid}</strong><span>${escapeHtml(p.command)}</span></div>
  `).join("") : `<div class="rule-chip"><strong>Process bekleniyor</strong><span>Entegre uygulama botu başlatınca burada görünür.</span></div>`;
}

function drawLivePortfolio(canvas, data) {
  const account = data.live?.account || {};
  const curve = data.live_portfolio_curve || [];
  if (curve.length) {
    drawLine(canvas, curve, "value", "#37f29a", "Paper portföy");
    return;
  }
  const equity = +account.equity;
  const last = +account.last_equity;
  if (Number.isFinite(equity) && Number.isFinite(last) && last > 0) {
    drawLine(canvas, [
      { date: "önceki", value: last },
      { date: "şimdi", value: equity },
    ], "value", "#37f29a", "Paper equity");
    return;
  }
  const ctx = setup(canvas);
  grid(ctx, canvas);
  ctx.fillStyle = "#8ca2b7";
  ctx.font = "14px Inter, sans-serif";
  ctx.fillText("Paper hesap verisi bekleniyor.", 24, 48);
}

function drawLine(canvas, rows, key, color, label) {
  if (!canvas || !rows.length) return;
  const ctx = setup(canvas);
  const pad = 34;
  const values = rows.map((r) => +r[key]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const width = canvas._cssWidth || canvas.width;
  const height = canvas._cssHeight || canvas.height;
  grid(ctx, canvas);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  rows.forEach((row, i) => {
    const x = pad + (i / Math.max(rows.length - 1, 1)) * (width - pad * 2);
    const y = height - pad - ((+row[key] - min) / Math.max(max - min, 1)) * (height - pad * 2);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();
  labelText(ctx, label, color);
}

function setup(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const cssWidth = Math.max(320, Math.floor(rect.width));
  const cssHeight = +(canvas.getAttribute("height") || 240);
  canvas.width = Math.floor(cssWidth * dpr);
  canvas.height = Math.floor(cssHeight * dpr);
  canvas.style.height = `${cssHeight}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  canvas._cssWidth = cssWidth;
  canvas._cssHeight = cssHeight;
  return ctx;
}

function grid(ctx, canvas) {
  const width = canvas._cssWidth || canvas.width;
  const height = canvas._cssHeight || canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = "rgba(151,213,255,.10)";
  ctx.lineWidth = 1;
  for (let y = 28; y < height - 20; y += 42) {
    ctx.beginPath();
    ctx.moveTo(24, y);
    ctx.lineTo(width - 20, y);
    ctx.stroke();
  }
}

function labelText(ctx, text, color) {
  ctx.fillStyle = color;
  ctx.font = "12px Inter, sans-serif";
  ctx.fillText(text, 24, 20);
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[m]));
}

load().catch((err) => {
  console.error(err);
  $("logs").textContent = `Dashboard veri hatası: ${err}`;
});
setInterval(() => load().catch(console.error), 15000);
