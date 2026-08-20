"""
Reads status.json (produced by export_status.py) and writes dashboard.html
-- a self-contained, no-server-needed local page (all data embedded inline,
so file:// double-click works, no fetch/CORS issues).

Run from the project root, after export_status.py:
    py -3 "Strat 1/export_status.py"
    py -3 "Strat 1/generate_dashboard.py"
"""

import json
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATUS_PATH = os.path.join(HERE, "status.json")
OUT_PATH = os.path.join(HERE, "dashboard.html")

PARAM_LABELS = [
    ("RSI_PERIOD", "RSI period", ""),
    ("RSI_OVERSOLD", "RSI long threshold (RSI ≤ this + price > MA → long)", ""),
    ("RSI_OVERBOUGHT", "RSI short threshold (RSI ≥ this + price < MA → short)", ""),
    ("USE_MA_FILTER", "MA filter enabled", ""),
    ("MA_PERIOD", "MA period", "candles"),
    ("ALLOW_SHORTS", "Shorts allowed", ""),
    ("CLOSE_ON_RSI_FLIP", "Close early on RSI flip", ""),
    ("STOP_LOSS_PCT", "Stop loss", "%"),
    ("TAKE_PROFIT_PCT", "Take profit", "%"),
    ("LEVERAGE", "Leverage", "x"),
    ("POSITION_SIZE_PCT", "Position size (of balance)", "%"),
    ("DAILY_LOSS_LIMIT_PCT", "Daily loss limit (margin-relative)", "%"),
    ("DAILY_LOSS_PAUSE_DAYS", "Pause after daily-loss breach", "days"),
    ("ALLOW_MULTIPLE_POSITIONS", "Multiple concurrent positions allowed", ""),
    ("FEE_PCT_EACH_WAY", "Taker fee (stop-loss exits)", "%"),
    ("CAUSAL_DETECTOR_LOOKBACK_DAYS", "Consolidation gate: lookback", "days"),
    ("CAUSAL_DETECTOR_THRESHOLD_PCT", "Consolidation gate: range threshold", "%"),
    ("CAUSAL_DETECTOR_PERSISTENCE_DAYS", "Consolidation gate: persistence", "days"),
]


def fmt_num(x, decimals=2):
    return f"{x:,.{decimals}f}"


def fmt_pct(x, decimals=2):
    sign = "+" if x > 0 else ""
    return f"{sign}{x:,.{decimals}f}%"


def fmt_time_my(ts):
    """Malaysia has no DST, so a fixed UTC+8 offset is exact year-round --
    no zoneinfo/tz-database dependency needed."""
    if ts is None:
        return None
    dt = pd.to_datetime(ts, utc=True) + pd.Timedelta(hours=8)
    return dt.strftime("%Y-%m-%d %H:%M") + " MYT"


def build_html(data):
    cfg = data["config"]
    live = data["live_state"]
    summary = data["recent_summary"]
    trades = data["last_20_trades"]

    status = live["status"]
    status_labels = {
        "IN_POSITION": "IN POSITION",
        "PENDING_ENTRY": "PENDING ENTRY (order resting, not filled)",
        "FLAT_NO_SIGNAL": "FLAT — no signal",
    }
    status_class = {
        "IN_POSITION": "long" if live.get("direction") == "LONG" else "short",
        "PENDING_ENTRY": "pending",
        "FLAT_NO_SIGNAL": "flat",
    }[status]

    # ---- live status card body ----
    if status == "IN_POSITION":
        direction = live["direction"]
        live_body = f"""
        <div class="status-grid">
          <div><span class="lbl">Direction</span><span class="val {'up' if direction=='LONG' else 'down'}">{direction}</span></div>
          <div><span class="lbl">Entry time</span><span class="val">{fmt_time_my(live['entry_time'])}</span></div>
          <div><span class="lbl">Entry price</span><span class="val">${fmt_num(live['entry_price'])}</span></div>
          <div><span class="lbl">Stop loss</span><span class="val down">${fmt_num(live['stop_loss_price'])}</span></div>
          <div><span class="lbl">Take profit</span><span class="val up">${fmt_num(live['take_profit_price'])}</span></div>
          <div><span class="lbl">Last known price</span><span class="val">${fmt_num(live['last_close'])}</span></div>
          <div><span class="lbl">Unrealized P&L (of margin, {cfg['LEVERAGE']}x)</span><span class="val {'up' if live['unrealized_pnl_pct_of_margin']>=0 else 'down'}">{fmt_pct(live['unrealized_pnl_pct_of_margin'])}</span></div>
        </div>
        <p class="manual-note">Manual trade reference: to mirror this position, go <b>{direction}</b> at/near
        <b>${fmt_num(live['entry_price'])}</b>, stop-loss at <b>${fmt_num(live['stop_loss_price'])}</b>,
        take-profit at <b>${fmt_num(live['take_profit_price'])}</b>. Position was already open as of the
        data timestamp below — if price has since moved past either level, that trade would already be closed;
        re-run the exporter against fresh data to check.</p>
        """
    elif status == "PENDING_ENTRY":
        direction = live["direction"]
        live_body = f"""
        <div class="status-grid">
          <div><span class="lbl">Direction</span><span class="val {'up' if direction=='LONG' else 'down'}">{direction}</span></div>
          <div><span class="lbl">Signal candle</span><span class="val">{fmt_time_my(live['signal_time'])}</span></div>
          <div><span class="lbl">Trigger price</span><span class="val">${fmt_num(live['trigger_price'])}</span></div>
          <div><span class="lbl">Last known price</span><span class="val">${fmt_num(live['last_close'])}</span></div>
        </div>
        <p class="manual-note">Manual trade reference: a resting limit-style entry is waiting to be
        touched at <b>${fmt_num(live['trigger_price'])}</b> ({direction}). It only becomes a real position
        once price actually trades back through that level on the following candle — it hadn't as of the
        data timestamp below.</p>
        """
    else:
        live_body = f"""
        <div class="status-grid">
          <div><span class="lbl">Last known price</span><span class="val">${fmt_num(live['last_close'])}</span></div>
          <div><span class="lbl">Consolidation gate</span><span class="val">{'OPEN' if live['gate_open'] else 'CLOSED'}</span></div>
        </div>
        <p class="manual-note">No open position and no resting entry signal as of the data timestamp below.
        The strategy is waiting for RSI + MA conditions to line up while the consolidation gate is open.</p>
        """

    gate_badge = "OPEN" if live["gate_open"] else "CLOSED"
    pause_badge = "PAUSED" if live["blocked_by_daily_loss_pause"] else "ACTIVE"

    live_price_js_data = json.dumps({
        "status": status,
        "direction": live.get("direction"),
        "entry_price": live.get("entry_price"),
        "stop_loss_price": live.get("stop_loss_price"),
        "take_profit_price": live.get("take_profit_price"),
        "trigger_price": live.get("trigger_price"),
    })

    checkpoint_js_data = json.dumps(data["engine_checkpoint"])
    static_trades_js_data = json.dumps(trades)
    all_static_trades_js_data = json.dumps(data["all_trades"])
    engine_cfg_js_data = json.dumps({
        "RSI_PERIOD": cfg["RSI_PERIOD"], "RSI_OVERSOLD": cfg["RSI_OVERSOLD"], "RSI_OVERBOUGHT": cfg["RSI_OVERBOUGHT"],
        "USE_MA_FILTER": cfg["USE_MA_FILTER"], "MA_PERIOD": cfg["MA_PERIOD"], "ALLOW_SHORTS": cfg.get("ALLOW_SHORTS", False),
        "STOP_LOSS_PCT": cfg["STOP_LOSS_PCT"], "TAKE_PROFIT_PCT": cfg["TAKE_PROFIT_PCT"], "LEVERAGE": cfg["LEVERAGE"],
        "DAILY_LOSS_LIMIT_PCT": cfg["DAILY_LOSS_LIMIT_PCT"], "DAILY_LOSS_PAUSE_DAYS": cfg["DAILY_LOSS_PAUSE_DAYS"],
        "CAUSAL_DETECTOR_LOOKBACK_DAYS": cfg["CAUSAL_DETECTOR_LOOKBACK_DAYS"],
        "CAUSAL_DETECTOR_THRESHOLD_PCT": cfg["CAUSAL_DETECTOR_THRESHOLD_PCT"],
        "CAUSAL_DETECTOR_PERSISTENCE_DAYS": cfg["CAUSAL_DETECTOR_PERSISTENCE_DAYS"],
    })

    rows_trades = ""
    for t in reversed(trades):
        d = t["direction"]
        reason = t["reason"]
        pnl = t["balance_after_usd"]
        dir_class = "up" if d == "LONG" else "down"
        reason_class = "up" if reason == "TAKE_PROFIT" else ("down" if reason == "STOP_LOSS" else "")
        rows_trades += f"""
        <tr>
          <td>{fmt_time_my(t['entry_time'])}</td>
          <td>{fmt_time_my(t['exit_time'])}</td>
          <td class="{dir_class}">{d}</td>
          <td class="{reason_class}">{reason.replace('_',' ')}</td>
          <td>${fmt_num(t['entry_price'])}</td>
          <td>${fmt_num(t['exit_price'])}</td>
          <td>${fmt_num(t['margin_usd'], 0)}</td>
          <td>${fmt_num(t['balance_after_usd'], 0)}</td>
        </tr>"""

    rows_params = ""
    for key, label, unit in PARAM_LABELS:
        v = cfg.get(key)
        if isinstance(v, bool):
            v_str = "Yes" if v else "No"
        elif isinstance(v, float):
            v_str = f"{v:g}{unit}"
        else:
            v_str = f"{v}{unit}"
        rows_params += f"<tr><td>{label}</td><td>{v_str}</td></tr>"

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Strat 1 — Live Status</title>
<style>
  :root {{
    --bg: #0b0f14; --panel: #131a22; --panel2: #182029; --border: #253140;
    --text: #e6edf3; --muted: #8b98a5; --up: #3fb950; --down: #f85149;
    --accent: #58a6ff; --pending: #d29922;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--text); margin: 0; padding: 32px 20px 60px;
    font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  }}
  .wrap {{ max-width: 980px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 4px; }}
  .subtitle {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 24px; }}
  .banner {{
    background: #3b2c00; border: 1px solid #6b4e00; color: #ffd97a;
    padding: 10px 14px; border-radius: 8px; font-size: 0.85rem; margin-bottom: 24px;
  }}
  .card {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px 22px; margin-bottom: 22px;
  }}
  .card h2 {{ font-size: 1.05rem; margin: 0 0 14px; }}
  .status-badge {{
    display: inline-block; padding: 4px 12px; border-radius: 999px; font-weight: 600;
    font-size: 0.8rem; letter-spacing: 0.03em; margin-bottom: 14px;
  }}
  .status-badge.long {{ background: rgba(63,185,80,0.15); color: var(--up); border: 1px solid rgba(63,185,80,0.4); }}
  .status-badge.short {{ background: rgba(248,81,73,0.15); color: var(--down); border: 1px solid rgba(248,81,73,0.4); }}
  .status-badge.pending {{ background: rgba(210,153,34,0.15); color: var(--pending); border: 1px solid rgba(210,153,34,0.4); }}
  .status-badge.flat {{ background: rgba(139,148,165,0.15); color: var(--muted); border: 1px solid rgba(139,148,165,0.4); }}
  .mini-badges {{ display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }}
  .mini-badge {{ font-size: 0.75rem; color: var(--muted); background: var(--panel2); border: 1px solid var(--border); padding: 3px 10px; border-radius: 6px; }}
  .status-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px 22px; margin-bottom: 14px;
  }}
  .status-grid > div {{ display: flex; flex-direction: column; gap: 2px; }}
  .lbl {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }}
  .val {{ font-size: 1.05rem; font-weight: 600; }}
  .val.up {{ color: var(--up); }}
  .val.down {{ color: var(--down); }}
  .manual-note {{
    background: var(--panel2); border: 1px solid var(--border); border-left: 3px solid var(--accent);
    padding: 10px 14px; border-radius: 6px; font-size: 0.85rem; color: var(--text); line-height: 1.5;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  th {{ color: var(--muted); font-weight: 500; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em; }}
  td.up {{ color: var(--up); }}
  td.down {{ color: var(--down); }}
  .table-scroll {{ overflow-x: auto; }}
  .summary-row {{ display: flex; gap: 28px; flex-wrap: wrap; margin-bottom: 6px; }}
  .summary-row div {{ display: flex; flex-direction: column; gap: 2px; }}
  .params-table td:first-child {{ color: var(--muted); }}
  .params-table td:last-child {{ font-weight: 600; text-align: right; }}
  footer {{ color: var(--muted); font-size: 0.78rem; line-height: 1.6; margin-top: 30px; }}
  code {{ background: var(--panel2); padding: 1px 5px; border-radius: 4px; font-size: 0.85em; }}
  .live-price-card {{ display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }}
  .live-price {{ font-size: 2.2rem; font-weight: 700; font-variant-numeric: tabular-nums; }}
  .live-change {{ font-size: 1rem; font-weight: 600; }}
  .live-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--muted); margin-right: 6px; }}
  .live-dot.ok {{ background: var(--up); box-shadow: 0 0 6px var(--up); }}
  .live-dot.err {{ background: var(--down); }}
  .live-meta {{ color: var(--muted); font-size: 0.78rem; }}
  .live-distances {{ display: flex; gap: 22px; flex-wrap: wrap; margin-top: 12px; font-size: 0.85rem; }}
  .live-distances span.lbl {{ display: block; }}
  .gate-card {{ padding: 14px 18px; }}
  .gate-card h2 {{ font-size: 0.9rem; margin-bottom: 8px; }}
  .gate-card .manual-note {{ padding: 7px 10px; font-size: 0.78rem; }}
  .gate-timeline {{ display: flex; gap: 2px; margin: 8px 0; flex-wrap: wrap; }}
  .gate-day {{ width: 9px; height: 16px; border-radius: 2px; background: var(--panel2); border: 1px solid var(--border); cursor: default; }}
  .gate-day.open {{ background: var(--up); border-color: var(--up); }}
  .gate-day.closed {{ background: var(--down); border-color: var(--down); opacity: 0.75; }}
  .gate-day.unknown {{ background: var(--panel2); }}
  .gate-table-scroll {{ max-height: 220px; overflow-y: auto; margin-top: 8px; }}
  .gate-card table {{ font-size: 0.78rem; }}
  .gate-card th, .gate-card td {{ padding: 5px 8px; }}
  .gate-card thead th {{ position: sticky; top: 0; background: var(--panel); }}
  .gate-periods-label {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; margin: 10px 0 6px; }}
  .gate-period {{ background: var(--panel2); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 6px; padding: 8px 10px; }}
  .gate-period summary {{
    cursor: pointer; display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
    font-size: 0.82rem; list-style: none;
  }}
  .gate-period summary::-webkit-details-marker {{ display: none; }}
  .gate-period summary::before {{ content: "▸"; color: var(--muted); margin-right: 2px; }}
  .gate-period[open] summary::before {{ content: "▾"; }}
  td.pass {{ color: var(--up); }}
  td.fail {{ color: var(--down); }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Strat 1 — Causal Consolidation-Gated RSI/MA Reversal (15m BTCUSDT)</h1>
  <div class="subtitle">5x leverage · 10% daily-loss limit · 3-day pause on breach — the adopted config</div>

  <div id="staleness-banner" class="banner">
    ⚠ Showing a <b>backtest snapshot</b> from <b>{fmt_time_my(live['as_of'])}</b> while the live engine computes (or as a
    fallback if it fails to reach Binance). Re-run <code>export_status.py</code> against a refreshed
    <code>BTCUSDT_15m_history.csv</code> any time to move this checkpoint forward.
  </div>

  <div class="card">
    <h2><span id="live-dot" class="live-dot"></span>Live BTC/USDT price</h2>
    <div class="live-price-card">
      <span id="live-price" class="live-price">—</span>
      <span id="live-change" class="live-change"></span>
    </div>
    <div id="live-pnl" class="live-distances"></div>
    <div id="live-distances" class="live-distances"></div>
    <div id="live-meta" class="live-meta" style="margin-top:10px;">Fetching from Binance…</div>
  </div>

  <div class="card">
    <h2>Current status <span id="engine-live-tag" class="mini-badge" style="margin-left:8px;">computing…</span></h2>
    <div id="status-card-inner">
    <span class="status-badge {status_class}">{status_labels[status]}</span>
    <div class="mini-badges">
      <span class="mini-badge">Consolidation gate: {gate_badge}</span>
      <span class="mini-badge">Daily-loss pause: {pause_badge}</span>
      <span class="mini-badge">RSI({live['rsi_period']}): {live['current_rsi']:.1f}</span>
      <span class="mini-badge">MA({live['ma_period']}): ${fmt_num(live['current_ma'])}</span>
    </div>
    {live_body}
    </div>
  </div>

  <div class="card gate-card">
    <h2>Consolidation gate <span id="gate-live-tag" class="mini-badge" style="margin-left:8px;">computing…</span></h2>
    <div id="gate-current"><p class="manual-note">Loading gate history…</p></div>
    <div id="gate-timeline" class="gate-timeline"></div>
    <div class="gate-periods-label">Last 10 consolidation periods (most recent first) — click to see daily data</div>
    <div id="gate-periods"></div>
  </div>

  <div class="card">
    <h2>Last 20 closed trades <span id="trades-live-tag" class="mini-badge" style="margin-left:8px;">computing…</span></h2>
    <div class="table-scroll">
    <table>
      <thead><tr>
        <th>Entry time</th><th>Exit time</th><th>Dir</th><th>Exit reason</th>
        <th>Entry px</th><th>Exit px</th><th>Margin</th><th>Balance after</th>
      </tr></thead>
      <tbody id="trades-tbody">{rows_trades}
      </tbody>
    </table>
    </div>
  </div>

  <div class="card">
    <h2>Track record — last 20 closed trades <span id="track-live-tag" class="mini-badge" style="margin-left:8px;">computing…</span></h2>
    <div id="track-summary" class="summary-row">
      <div><span class="lbl">Return</span><span class="val {'up' if summary['return_pct']>=0 else 'down'}">{fmt_pct(summary['return_pct'])}</span></div>
      <div><span class="lbl">Max drawdown</span><span class="val down">{fmt_pct(summary['max_drawdown_pct'])}</span></div>
      <div><span class="lbl">Trades (closed)</span><span class="val">{summary['num_trades']}</span></div>
      <div><span class="lbl">Win rate</span><span class="val">{fmt_num(summary['win_rate_pct'],1)}%</span></div>
    </div>
    <p class="manual-note">Compounds a hypothetical $10k restart at the first of these 20 trades, {cfg['LEVERAGE']}x
    leverage / 100% position size each trade — matches the trades table above exactly, not the full 9-year
    backtest. Dollar amounts aren't shown here since they'd depend on real position sizing; the %
    figures are what matter for gauging recent performance.</p>
  </div>

  <div class="card">
    <h2>All parameters</h2>
    <table class="params-table">
      <tbody>{rows_params}
      </tbody>
    </table>
  </div>

  <footer>
    Strategy logic: RSI({cfg['RSI_PERIOD']}) + MA({cfg['MA_PERIOD']}) filter decide direction while a causal
    consolidation gate is open (trailing {cfg['CAUSAL_DETECTOR_LOOKBACK_DAYS']}-day range must stay within
    {cfg['CAUSAL_DETECTOR_THRESHOLD_PCT']}% of its low for ≥{cfg['CAUSAL_DETECTOR_PERSISTENCE_DAYS']} consecutive
    days, one-day-shifted so nothing leaks). Entries are pending-limit style — a signal only becomes a position
    once the next candle's high/low actually touches the signal price. Exit is a fixed SL/TP bracket
    ({cfg['STOP_LOSS_PCT']}% / {cfg['TAKE_PROFIT_PCT']}%), whichever hits first. A daily-loss breach of
    {cfg['DAILY_LOSS_LIMIT_PCT']}% (margin-relative) pauses new entries for {cfg['DAILY_LOSS_PAUSE_DAYS']} days.
    See <code>Strat 1/README.md</code> for full derivation, validation, and caveats.
    Generated from data as of {fmt_time_my(data['generated_at_data_timestamp'])}. All times on this page are
    Malaysia time (UTC+8).
  </footer>
</div>

<script>
let LIVE_STATE = {live_price_js_data};
const CHECKPOINT = {checkpoint_js_data};
const STATIC_TRADES = {static_trades_js_data};
const ALL_STATIC_TRADES = {all_static_trades_js_data};
const CFG = {engine_cfg_js_data};
let prevPrice = null;

function fmtUsd(x) {{
  return "$" + x.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
}}
function dateStr(isoOrMs) {{
  const d = new Date(isoOrMs);
  return d.toISOString().slice(0, 10);
}}
function addDaysStr(ds, n) {{
  const d = new Date(ds + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}}

// Malaysia has no DST, so UTC+8 is exact year-round -- shown explicitly
// rather than the viewer's own device timezone, since a manual-trade
// reference is only useful if the times mean the same thing to everyone
// reading it.
const MY_OFFSET_MS = 8 * 3600 * 1000;
function fmtTimeMY(isoOrDate) {{
  if (!isoOrDate) return "";
  const d = new Date(new Date(isoOrDate).getTime() + MY_OFFSET_MS);
  const pad = (n) => String(n).padStart(2, "0");
  return `${{d.getUTCFullYear()}}-${{pad(d.getUTCMonth() + 1)}}-${{pad(d.getUTCDate())}} `
       + `${{pad(d.getUTCHours())}}:${{pad(d.getUTCMinutes())}} MYT`;
}}
function nowMY() {{ return fmtTimeMY(new Date()); }}
function nowTimeOnlyMY() {{
  const d = new Date(Date.now() + MY_OFFSET_MS);
  const pad = (n) => String(n).padStart(2, "0");
  return `${{pad(d.getUTCHours())}}:${{pad(d.getUTCMinutes())}}:${{pad(d.getUTCSeconds())}} MYT`;
}}

function renderDistances(price) {{
  const el = document.getElementById("live-distances");
  const parts = [];
  if (LIVE_STATE.status === "IN_POSITION") {{
    const toSl = (price - LIVE_STATE.stop_loss_price) / price * 100;
    const toTp = (price - LIVE_STATE.take_profit_price) / price * 100;
    parts.push(`<div><span class="lbl">To stop-loss (${{fmtUsd(LIVE_STATE.stop_loss_price)}})</span><b>${{toSl.toFixed(2)}}%</b></div>`);
    parts.push(`<div><span class="lbl">To take-profit (${{fmtUsd(LIVE_STATE.take_profit_price)}})</span><b>${{toTp.toFixed(2)}}%</b></div>`);
  }} else if (LIVE_STATE.status === "PENDING_ENTRY") {{
    const toTrigger = (price - LIVE_STATE.trigger_price) / price * 100;
    parts.push(`<div><span class="lbl">To entry trigger (${{fmtUsd(LIVE_STATE.trigger_price)}})</span><b>${{toTrigger.toFixed(2)}}%</b></div>`);
  }}
  el.innerHTML = parts.join("");
}}

function renderUnrealizedPnl(price) {{
  const el = document.getElementById("live-pnl");
  if (LIVE_STATE.status !== "IN_POSITION") {{ el.innerHTML = ""; return; }}
  const dir = LIVE_STATE.direction === "LONG" ? 1 : -1;
  const movePct = (price - LIVE_STATE.entry_price) / LIVE_STATE.entry_price * dir * 100;
  const levPct = movePct * CFG.LEVERAGE;
  const cls = (x) => "val " + (x >= 0 ? "up" : "down");
  const sign = (x) => (x >= 0 ? "+" : "") + x.toFixed(2) + "%";
  el.innerHTML = `
    <div><span class="lbl">Unrealized P&amp;L — unleveraged (spot)</span><b class="${{cls(movePct)}}">${{sign(movePct)}}</b></div>
    <div><span class="lbl">Unrealized P&amp;L — ${{CFG.LEVERAGE}}x leveraged (of margin)</span><b class="${{cls(levPct)}}">${{sign(levPct)}}</b></div>`;
}}

// Binance serves market data from a couple of different hosts. api.binance.com
// geo-blocks US-origin traffic (HTTP 451) and is a common ad-blocker target;
// data-api.binance.vision is Binance's dedicated public-market-data mirror,
// meant for exactly this kind of anonymous read-only access, and isn't
// geo-restricted -- tried first, with the other as a fallback in case either
// one has a transient outage.
const BINANCE_HOSTS = ["https://data-api.binance.vision", "https://api.binance.com"];

async function fetchJson(path) {{
  let lastErr;
  for (const host of BINANCE_HOSTS) {{
    try {{
      const res = await fetch(host + path, {{cache: "no-store"}});
      if (!res.ok) throw new Error("HTTP " + res.status);
      return await res.json();
    }} catch (e) {{ lastErr = e; }}
  }}
  throw lastErr;
}}

async function refreshPrice() {{
  const dot = document.getElementById("live-dot");
  const priceEl = document.getElementById("live-price");
  const changeEl = document.getElementById("live-change");
  const metaEl = document.getElementById("live-meta");
  try {{
    const data = await fetchJson("/api/v3/ticker/price?symbol=BTCUSDT");
    const price = parseFloat(data.price);
    priceEl.textContent = fmtUsd(price);
    if (prevPrice !== null) {{
      const diff = price - prevPrice;
      changeEl.textContent = (diff >= 0 ? "▲ " : "▼ ") + Math.abs(diff).toFixed(2) + " since last check";
      changeEl.style.color = diff >= 0 ? "var(--up)" : "var(--down)";
    }}
    prevPrice = price;
    dot.className = "live-dot ok";
    metaEl.textContent = "Live from Binance · updated " + nowTimeOnlyMY();
    renderDistances(price);
    renderUnrealizedPnl(price);
  }} catch (e) {{
    dot.className = "live-dot err";
    metaEl.textContent = "Couldn't fetch live price (" + e.message + "). Retrying…";
  }}
}}

// ---------------------------------------------------------------------
// Live strategy engine: replays RSI/MA signals, the consolidation gate,
// and the SL/TP/pause state machine forward from the checkpoint baked
// into this page (computed by export_status.py from the local backtest)
// using fresh candles pulled straight from Binance. Mirrors run_variant.py
// / export_status.py's simulate loop as closely as practical client-side.
// ---------------------------------------------------------------------

async function fetchKlines(interval, startTime, endTime, limit) {{
  const out = [];
  let cursor = startTime;
  while (cursor < endTime) {{
    const path = `/api/v3/klines?symbol=BTCUSDT&interval=${{interval}}&startTime=${{cursor}}&endTime=${{endTime}}&limit=${{limit}}`;
    const batch = await fetchJson(path);
    if (!batch.length) break;
    for (const k of batch) {{
      out.push({{
        openTime: k[0], open: parseFloat(k[1]), high: parseFloat(k[2]),
        low: parseFloat(k[3]), close: parseFloat(k[4]), closeTime: k[6],
      }});
    }}
    if (batch.length < limit) break;
    cursor = batch[batch.length - 1][6] + 1; // batch is raw Binance rows here, not yet the {{...}} objects pushed to out -- index 6 is closeTime
  }}
  return out;
}}

// Full daily history, cached across ticks: past days never change, so after
// the one-time full fetch (needed to find the last ~10 consolidation
// periods, which can span months) each subsequent tick only asks Binance
// for whatever's new since the last cached day instead of re-fetching years
// of candles every 60s.
const HISTORY_START_MS = Date.UTC(2017, 7, 17);
let DAILY_HISTORY_CACHE = null;

async function getDailyHistory(now) {{
  if (!DAILY_HISTORY_CACHE) {{
    const raw = await fetchKlines("1d", HISTORY_START_MS, now, 1000);
    DAILY_HISTORY_CACHE = raw.filter(k => k.closeTime <= now)
      .map(k => ({{date: dateStr(k.openTime), high: k.high, low: k.low, close: k.close}}));
  }} else {{
    const lastDate = DAILY_HISTORY_CACHE[DAILY_HISTORY_CACHE.length - 1].date;
    const fetchFrom = new Date(lastDate + "T00:00:00Z").getTime() + 86400000;
    if (fetchFrom < now) {{
      const raw = await fetchKlines("1d", fetchFrom, now, 1000);
      const known = new Set(DAILY_HISTORY_CACHE.map(d => d.date));
      for (const k of raw) {{
        if (k.closeTime > now) continue;
        const d = dateStr(k.openTime);
        if (!known.has(d)) {{ DAILY_HISTORY_CACHE.push({{date: d, high: k.high, low: k.low, close: k.close}}); known.add(d); }}
      }}
    }}
  }}
  return DAILY_HISTORY_CACHE;
}}

function computeRSIWilder(closes, period) {{
  const n = closes.length;
  const rsi = new Array(n).fill(null);
  const alpha = 1 / period;
  let avgGain = null, avgLoss = null;
  for (let i = 1; i < n; i++) {{
    const delta = closes[i] - closes[i - 1];
    const gain = Math.max(delta, 0), loss = Math.max(-delta, 0);
    if (avgGain === null) {{ avgGain = gain; avgLoss = loss; }}
    else {{ avgGain = alpha * gain + (1 - alpha) * avgGain; avgLoss = alpha * loss + (1 - alpha) * avgLoss; }}
    if (avgLoss === 0) rsi[i] = avgGain === 0 ? 50 : 100;
    else {{ const rs = avgGain / avgLoss; rsi[i] = 100 - 100 / (1 + rs); }}
  }}
  return rsi;
}}

function computeMA(closes, period) {{
  const n = closes.length;
  const ma = new Array(n).fill(null);
  let sum = 0;
  for (let i = 0; i < n; i++) {{
    sum += closes[i];
    if (i >= period) sum -= closes[i - period];
    if (i >= period - 1) ma[i] = sum / period;
  }}
  return ma;
}}

function computeDailyFlags(days, lookback, thresholdPct, persistence) {{
  const n = days.length;
  const rawHit = new Array(n).fill(false);
  const rangePct = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {{
    const start = Math.max(0, i - lookback + 1);
    if (i - start + 1 < lookback) continue;
    let hi = -Infinity, lo = Infinity;
    for (let j = start; j <= i; j++) {{ hi = Math.max(hi, days[j].high); lo = Math.min(lo, days[j].low); }}
    rangePct[i] = (hi - lo) / lo * 100;
    rawHit[i] = rangePct[i] <= thresholdPct;
  }}
  let flag;
  if (persistence <= 1) {{ flag = rawHit; }}
  else {{
    flag = new Array(n).fill(false);
    let run = 0;
    for (let i = 0; i < n; i++) {{ run = rawHit[i] ? run + 1 : 0; flag[i] = run >= persistence; }}
  }}
  return {{ rawHit, flag, rangePct }};
}}

function tradesInRange(startMs, endMs, newTrades) {{
  // ALL_STATIC_TRADES covers the full 9-year backtest (embedded once at
  // export time); newTrades is whatever the live engine has closed since
  // the checkpoint. Together they cover every period, however old.
  const inRange = (t) => {{
    const tMs = new Date(t.entry_time.replace(" ", "T")).getTime();
    return tMs >= startMs && tMs < endMs;
  }};
  const fromStatic = ALL_STATIC_TRADES.filter(inRange).map(t => ({{...t, live: false}}));
  const fromLive = newTrades.filter(inRange).map(t => ({{...t, live: true}}));
  return fromStatic.concat(fromLive).sort((a, b) => new Date(a.entry_time.replace(" ", "T")) - new Date(b.entry_time.replace(" ", "T")));
}}

function renderGateHistory(days, rawHit, flag, rangePct, gateMap, newTrades) {{
  const n = days.length;
  const todayEffective = dateStr(Date.now());
  const currentGateOpen = gateMap.get(todayEffective) || false;

  // how many more consecutive tight days are needed before it reopens, if closed
  let currentRun = 0;
  for (let i = n - 1; i >= 0; i--) {{ if (rawHit[i]) currentRun++; else break; }}

  const currentEl = document.getElementById("gate-current");
  if (currentGateOpen) {{
    currentEl.innerHTML = `<p class="manual-note">Gate is currently <b class="val up">OPEN</b> as of ${{todayEffective}} (UTC).
      New entries are allowed if RSI/MA also line up.</p>`;
  }} else {{
    const need = Math.max(0, CFG.CAUSAL_DETECTOR_PERSISTENCE_DAYS - currentRun);
    const needText = need > 0
      ? `needs ${{need}} more consecutive day${{need > 1 ? "s" : ""}} with a ≤${{CFG.CAUSAL_DETECTOR_THRESHOLD_PCT}}% rolling ${{CFG.CAUSAL_DETECTOR_LOOKBACK_DAYS}}-day range before it reopens`
      : "should reopen at the next daily close if today stays tight";
    currentEl.innerHTML = `<p class="manual-note">Gate is currently <b class="val down">CLOSED</b> as of ${{todayEffective}} (UTC).
      No new entries regardless of RSI/MA until it reopens — ${{needText}}. Existing open positions are unaffected.</p>`;
  }}

  const timelineEl = document.getElementById("gate-timeline");
  const recent = [];
  for (let i = Math.max(0, n - 30); i < n; i++) {{
    const eff = addDaysStr(days[i].date, 1);
    const open = gateMap.get(eff) || false;
    recent.push({{i, open}});
  }}
  timelineEl.innerHTML = recent.map(r =>
    `<div class="gate-day ${{r.open ? 'open' : 'closed'}}" title="${{days[r.i].date}}: gate ${{r.open ? 'OPEN' : 'CLOSED'}}"></div>`
  ).join("");

  // Group the effective (shifted) daily flags into contiguous OPEN runs --
  // each run is one actual consolidation episode, not just a single day.
  const eff = days.map((d, i) => ({{
    effDate: addDaysStr(d.date, 1), open: flag[i], rangePct: rangePct[i], rawHit: rawHit[i],
    sourceDate: d.date, high: d.high, low: d.low, close: d.close,
  }}));
  const periods = [];
  let cur = null;
  for (let i = 0; i < eff.length; i++) {{
    if (eff[i].open) {{
      if (!cur) cur = {{ days: [] }};
      cur.days.push(eff[i]);
    }} else if (cur) {{
      cur.closedAtDay = eff[i]; // the first FAIL day right after the period ended
      periods.push(cur);
      cur = null;
    }}
  }}
  if (cur) {{ cur.ongoing = true; periods.push(cur); }}

  const last10 = periods.slice(-10).reverse();
  const periodsEl = document.getElementById("gate-periods");
  if (!last10.length) {{
    periodsEl.innerHTML = `<p class="manual-note">No consolidation periods found yet in the fetched history.</p>`;
  }} else {{
    periodsEl.innerHTML = last10.map(p => {{
      const startDate = p.days[0].effDate;
      const endDate = p.ongoing ? null : p.days[p.days.length - 1].effDate;
      const durationDays = p.days.length;
      const openPrice = p.days[0].close;
      const closePrice = p.days[p.days.length - 1].close;
      const priceChangePct = (closePrice - openPrice) / openPrice * 100;
      let lo = Infinity, hi = -Infinity, tightest = Infinity;
      for (const d of p.days) {{
        lo = Math.min(lo, d.low); hi = Math.max(hi, d.high);
        if (d.rangePct !== null) tightest = Math.min(tightest, d.rangePct);
      }}
      const statusLabel = p.ongoing ? `ONGOING (${{durationDays}} days so far)` : `CLOSED after ${{durationDays}} days`;
      const statusClass = p.ongoing ? "up" : "down";
      const closeInfo = p.closedAtDay
        ? ` · closed when range expanded to ${{p.closedAtDay.rangePct.toFixed(2)}}% on ${{p.closedAtDay.sourceDate}}`
        : "";

      const startMs = new Date(p.days[0].effDate + "T00:00:00Z").getTime();
      const endMs = p.ongoing ? Date.now() : new Date(p.days[p.days.length - 1].effDate + "T00:00:00Z").getTime() + 86400000;
      const periodTrades = tradesInRange(startMs, endMs, newTrades);
      const tradesInfo = periodTrades.length
        ? `${{periodTrades.length}} trade${{periodTrades.length > 1 ? "s" : ""}}, ${{periodTrades.filter(t => t.reason === "TAKE_PROFIT").length}} TP / ${{periodTrades.filter(t => t.reason === "STOP_LOSS").length}} SL`
        : "no trades fired during this period";

      const tradeRows = periodTrades.length
        ? periodTrades.map(tradeRowHtml).join("")
        : `<tr><td colspan="8" style="color:var(--muted);">No trades fired while this gate was open (RSI/MA conditions never lined up).</td></tr>`;

      return `<details class="gate-period">
        <summary>
          <span class="val ${{statusClass}}">${{startDate}} → ${{endDate || "now"}}</span>
          <span class="mini-badge">${{statusLabel}}</span>
          <span class="mini-badge">BTC ${{fmtUsd(lo)}}–${{fmtUsd(hi)}} (${{priceChangePct >= 0 ? "+" : ""}}${{priceChangePct.toFixed(1)}}%)</span>
          <span class="mini-badge">tightest ${{tightest === Infinity ? "—" : tightest.toFixed(2) + "%"}}</span>
          <span class="mini-badge">${{tradesInfo}}</span>
        </summary>
        <p class="manual-note" style="margin:8px 0;">${{p.ongoing ? "Still open as of the latest daily close" : "Closed"}}${{closeInfo}}.</p>
        <div class="table-scroll gate-table-scroll">
        <table>
          <thead><tr>
            <th>Entry time</th><th>Exit time</th><th>Dir</th><th>Exit reason</th>
            <th>Entry px</th><th>Exit px</th><th>Margin</th><th>Balance after</th>
          </tr></thead>
          <tbody>${{tradeRows}}</tbody>
        </table>
        </div>
      </details>`;
    }}).join("");
  }}

  const tag = document.getElementById("gate-live-tag");
  tag.textContent = "live · computed " + nowTimeOnlyMY();
  tag.style.color = "var(--up)";
}}

function statusLabel(s) {{
  return {{IN_POSITION: "IN POSITION", PENDING_ENTRY: "PENDING ENTRY (order resting, not filled)", FLAT_NO_SIGNAL: "FLAT — no signal"}}[s];
}}
function statusClass(s, direction) {{
  if (s === "IN_POSITION") return direction === "LONG" ? "long" : "short";
  if (s === "PENDING_ENTRY") return "pending";
  return "flat";
}}

function renderStatusCard(st) {{
  const badgeClass = statusClass(st.status, st.direction);
  let body = "";
  if (st.status === "IN_POSITION") {{
    const dirClass = st.direction === "LONG" ? "up" : "down";
    body = `
      <div class="status-grid">
        <div><span class="lbl">Direction</span><span class="val ${{dirClass}}">${{st.direction}}</span></div>
        <div><span class="lbl">Entry time</span><span class="val">${{fmtTimeMY(st.entry_time)}}</span></div>
        <div><span class="lbl">Entry price</span><span class="val">${{fmtUsd(st.entry_price)}}</span></div>
        <div><span class="lbl">Stop loss</span><span class="val down">${{fmtUsd(st.stop_loss_price)}}</span></div>
        <div><span class="lbl">Take profit</span><span class="val up">${{fmtUsd(st.take_profit_price)}}</span></div>
      </div>
      <p class="manual-note">Manual trade reference: to mirror this position, go <b>${{st.direction}}</b> at/near
      <b>${{fmtUsd(st.entry_price)}}</b>, stop-loss at <b>${{fmtUsd(st.stop_loss_price)}}</b>,
      take-profit at <b>${{fmtUsd(st.take_profit_price)}}</b>.</p>`;
  }} else if (st.status === "PENDING_ENTRY") {{
    const dirClass = st.direction === "LONG" ? "up" : "down";
    body = `
      <div class="status-grid">
        <div><span class="lbl">Direction</span><span class="val ${{dirClass}}">${{st.direction}}</span></div>
        <div><span class="lbl">Signal candle</span><span class="val">${{fmtTimeMY(st.signal_time)}}</span></div>
        <div><span class="lbl">Trigger price</span><span class="val">${{fmtUsd(st.trigger_price)}}</span></div>
      </div>
      <p class="manual-note">Manual trade reference: a resting limit-style entry is waiting to be touched at
      <b>${{fmtUsd(st.trigger_price)}}</b> (${{st.direction}}). It only becomes a real position once price
      actually trades back through that level.</p>`;
  }} else {{
    body = `<p class="manual-note">No open position and no resting entry signal right now. The strategy is
    waiting for RSI + MA conditions to line up while the consolidation gate is open.</p>`;
  }}
  document.getElementById("status-card-inner").innerHTML = `
    <span class="status-badge ${{badgeClass}}">${{statusLabel(st.status)}}</span>
    <div class="mini-badges">
      <span class="mini-badge">Consolidation gate: ${{st.gate_open ? "OPEN" : "CLOSED"}}</span>
      <span class="mini-badge">Daily-loss pause: ${{st.blocked ? "PAUSED" : "ACTIVE"}}</span>
      <span class="mini-badge">RSI(${{CFG.RSI_PERIOD}}): ${{st.rsi.toFixed(1)}}</span>
      <span class="mini-badge">MA(${{CFG.MA_PERIOD}}): ${{fmtUsd(st.ma)}}</span>
    </div>
    ${{body}}`;
}}

function fmtPct(x) {{ return (x >= 0 ? "+" : "") + x.toFixed(2) + "%"; }}

function computeWindowSummary(tradesOldestFirst) {{
  // Mirrors export_status.py's compute_window_summary exactly: a fresh
  // hypothetical $10k restart at the first trade in the window, so this
  // card's numbers always match whatever's actually listed in the table.
  const makerFee = 0.02 / 100, takerFee = 0.05 / 100;
  let equity = 1.0, peak = 1.0, maxDd = 0.0, wins = 0;
  for (const t of tradesOldestFirst) {{
    const dir = t.direction === "LONG" ? 1 : -1;
    const movePct = (t.exit_price - t.entry_price) / t.entry_price * dir;
    const exitFeeFrac = (t.reason === "TAKE_PROFIT" ? makerFee : takerFee) * CFG.LEVERAGE;
    const entryFeeFrac = makerFee * CFG.LEVERAGE;
    const multiplier = 1 + movePct * CFG.LEVERAGE - entryFeeFrac - exitFeeFrac;
    equity *= Math.max(multiplier, 0);
    if (movePct > 0) wins++;
    if (equity > peak) peak = equity;
    const dd = (equity - peak) / peak * 100;
    if (dd < maxDd) maxDd = dd;
  }}
  const n = tradesOldestFirst.length;
  return {{
    return_pct: (equity - 1) * 100, max_drawdown_pct: maxDd,
    num_trades: n, win_rate_pct: n ? (wins / n * 100) : 0,
  }};
}}

function renderTrackRecord(tradesOldestFirst) {{
  const s = computeWindowSummary(tradesOldestFirst);
  document.getElementById("track-summary").innerHTML = `
    <div><span class="lbl">Return</span><span class="val ${{s.return_pct >= 0 ? 'up' : 'down'}}">${{fmtPct(s.return_pct)}}</span></div>
    <div><span class="lbl">Max drawdown</span><span class="val down">${{fmtPct(s.max_drawdown_pct)}}</span></div>
    <div><span class="lbl">Trades (closed)</span><span class="val">${{s.num_trades}}</span></div>
    <div><span class="lbl">Win rate</span><span class="val">${{s.win_rate_pct.toFixed(1)}}%</span></div>`;
  const tag = document.getElementById("track-live-tag");
  tag.textContent = "live · computed " + nowTimeOnlyMY();
  tag.style.color = "var(--up)";
}}

function tradeRowHtml(t) {{
  const dirClass = t.direction === "LONG" ? "up" : "down";
  const reasonClass = t.reason === "TAKE_PROFIT" ? "up" : (t.reason === "STOP_LOSS" ? "down" : "");
  const margin = t.live ? "—" : fmtUsd(t.margin_usd);
  const bal = t.live ? "—" : fmtUsd(t.balance_after_usd);
  return `<tr>
      <td>${{fmtTimeMY(t.entry_time)}}</td>
      <td>${{fmtTimeMY(t.exit_time)}}</td>
      <td class="${{dirClass}}">${{t.direction}}</td>
      <td class="${{reasonClass}}">${{t.reason.replace(/_/g, " ")}}</td>
      <td>${{fmtUsd(t.entry_price)}}</td>
      <td>${{fmtUsd(t.exit_price)}}</td>
      <td>${{margin}}</td>
      <td>${{bal}}</td>
    </tr>`;
}}

function renderTradesTable(newTrades) {{
  // newTrades (live-computed, no $ balance tracked) + STATIC_TRADES (from the
  // backtest checkpoint, which do have $ balance) -- newest first, capped at 20.
  const merged = newTrades.slice().reverse().map(t => ({{...t, live: true}}))
    .concat(STATIC_TRADES.slice().reverse().map(t => ({{...t, live: false}})))
    .slice(0, 20);
  renderTrackRecord(merged.slice().reverse());
  document.getElementById("trades-tbody").innerHTML = merged.map(tradeRowHtml).join("");
}}

async function runLiveEngine() {{
  const tag = document.getElementById("engine-live-tag");
  try {{
    const checkpointMs = new Date(CHECKPOINT.as_of_time).getTime();
    const now = Date.now();

    const warmupCloses = CHECKPOINT.warmup_closes.map(w => w.c);
    const newCandles = await fetchKlines("15m", checkpointMs + 1, now, 1000);
    const closedNew = newCandles.filter(k => k.closeTime <= now);
    if (!closedNew.length) {{ tag.textContent = "live (no new candles yet)"; tag.style.color = "var(--up)"; return; }}

    const allCloses = warmupCloses.concat(closedNew.map(k => k.close));
    const rsiArr = computeRSIWilder(allCloses, CFG.RSI_PERIOD);
    const maArr = computeMA(allCloses, CFG.MA_PERIOD);
    const offset = warmupCloses.length;

    const days = await getDailyHistory(now);
    const {{rawHit, flag: dayFlags, rangePct}} = computeDailyFlags(days, CFG.CAUSAL_DETECTOR_LOOKBACK_DAYS, CFG.CAUSAL_DETECTOR_THRESHOLD_PCT, CFG.CAUSAL_DETECTOR_PERSISTENCE_DAYS);
    const gateMap = new Map();
    for (let i = 0; i < days.length; i++) gateMap.set(addDaysStr(days[i].date, 1), dayFlags[i]);

    let hasPosition = CHECKPOINT.has_position;
    let direction = CHECKPOINT.direction === "LONG" ? 1 : (CHECKPOINT.direction === "SHORT" ? -1 : null);
    let entryPrice = CHECKPOINT.entry_price;
    let entryTime = CHECKPOINT.entry_time;
    let pending = CHECKPOINT.pending;
    let pendingDir = direction;
    let pendingTrigger = CHECKPOINT.trigger_price;
    let signalTime = CHECKPOINT.signal_time;
    let pausedUntilDate = CHECKPOINT.paused_until_date;
    let curDay = dateStr(CHECKPOINT.as_of_time);
    let dailyPnlPct = 0;
    const newTrades = [];

    const slPct = CFG.STOP_LOSS_PCT / 100, tpPct = CFG.TAKE_PROFIT_PCT / 100;
    let lastRsi = rsiArr[offset - 1], lastMa = maArr[offset - 1], lastGateOpen = gateMap.get(curDay) || false;

    for (let idx = 0; idx < closedNew.length; idx++) {{
      const k = closedNew[idx];
      const i = offset + idx;
      const price = k.close, lo = k.low, hi = k.high, d = dateStr(k.openTime);
      if (d !== curDay) {{ curDay = d; dailyPnlPct = 0; }}

      if (hasPosition) {{
        let hitSl, hitTp;
        if (direction === 1) {{ hitSl = price <= entryPrice * (1 - slPct); hitTp = price >= entryPrice * (1 + tpPct); }}
        else {{ hitSl = price >= entryPrice * (1 + slPct); hitTp = price <= entryPrice * (1 - tpPct); }}
        if (hitSl || hitTp) {{
          const movePct = hitTp ? tpPct : ((price - entryPrice) / entryPrice * direction);
          dailyPnlPct += movePct * CFG.LEVERAGE * 100; // approximation: ignores fees' small effect on the exact pause threshold
          const exitPrice = hitTp ? entryPrice * (1 + tpPct * direction) : price;
          newTrades.push({{
            entry_time: entryTime, exit_time: new Date(k.openTime).toISOString(),
            direction: direction === 1 ? "LONG" : "SHORT", reason: hitTp ? "TAKE_PROFIT" : "STOP_LOSS",
            entry_price: entryPrice, exit_price: exitPrice,
          }});
          hasPosition = false;
          if (dailyPnlPct <= -CFG.DAILY_LOSS_LIMIT_PCT) pausedUntilDate = addDaysStr(d, CFG.DAILY_LOSS_PAUSE_DAYS - 1);
        }}
      }}

      const blocked = pausedUntilDate !== null && d <= pausedUntilDate;
      const gateOk = gateMap.get(d) || false;
      const rsiVal = rsiArr[i], maVal = maArr[i];
      let entrySignal = 0;
      if (CFG.USE_MA_FILTER) {{
        if (rsiVal <= CFG.RSI_OVERSOLD && price > maVal) entrySignal = 1;
        else if (CFG.ALLOW_SHORTS && rsiVal >= CFG.RSI_OVERBOUGHT && price < maVal) entrySignal = -1;
      }} else {{
        if (rsiVal <= CFG.RSI_OVERSOLD) entrySignal = 1;
        else if (CFG.ALLOW_SHORTS && rsiVal >= CFG.RSI_OVERBOUGHT) entrySignal = -1;
      }}

      if (pending) {{
        const touched = pendingDir === 1 ? (lo <= pendingTrigger) : (hi >= pendingTrigger);
        if (touched && !hasPosition) {{
          hasPosition = true; direction = pendingDir; entryPrice = pendingTrigger; entryTime = new Date(k.openTime).toISOString();
        }}
        pending = false;
      }} else if (!hasPosition && !blocked && gateOk && entrySignal !== 0) {{
        pending = true; pendingDir = entrySignal; pendingTrigger = price; signalTime = new Date(k.openTime).toISOString();
      }}

      lastRsi = rsiVal; lastMa = maVal; lastGateOpen = gateOk;
    }}

    let status;
    if (hasPosition) status = "IN_POSITION";
    else if (pending) status = "PENDING_ENTRY";
    else status = "FLAT_NO_SIGNAL";

    const st = {{
      status, gate_open: lastGateOpen, blocked: pausedUntilDate !== null && curDay <= pausedUntilDate,
      rsi: lastRsi, ma: lastMa,
      direction: direction === 1 ? "LONG" : (direction === -1 ? "SHORT" : null),
      entry_time: entryTime, entry_price: entryPrice,
      stop_loss_price: hasPosition ? (direction === 1 ? entryPrice * (1 - slPct) : entryPrice * (1 + slPct)) : null,
      take_profit_price: hasPosition ? (direction === 1 ? entryPrice * (1 + tpPct) : entryPrice * (1 - tpPct)) : null,
      trigger_price: pendingTrigger, signal_time: signalTime,
    }};

    renderStatusCard(st);
    renderTradesTable(newTrades);
    renderGateHistory(days, rawHit, dayFlags, rangePct, gateMap, newTrades);
    LIVE_STATE = {{
      status: st.status, direction: st.direction, entry_price: st.entry_price,
      stop_loss_price: st.stop_loss_price, take_profit_price: st.take_profit_price, trigger_price: st.trigger_price,
    }};
    document.getElementById("staleness-banner").style.display = "none";
    const nowStr = nowTimeOnlyMY();
    tag.textContent = "live · computed " + nowStr;
    tag.style.color = "var(--up)";
    const tradesTag = document.getElementById("trades-live-tag");
    tradesTag.textContent = newTrades.length
      ? `live · ${{newTrades.length}} new trade${{newTrades.length > 1 ? "s" : ""}} since snapshot`
      : "live · none closed since snapshot";
    tradesTag.style.color = "var(--up)";
  }} catch (e) {{
    tag.textContent = "live engine unavailable (" + e.message + ") — showing backtest snapshot";
    tag.style.color = "var(--down)";
    document.getElementById("trades-live-tag").textContent = "showing backtest snapshot";
    document.getElementById("track-live-tag").textContent = "showing backtest snapshot";
    document.getElementById("gate-live-tag").textContent = "unavailable";
    document.getElementById("gate-current").innerHTML = `<p class="manual-note">Couldn't reach Binance to compute gate history right now.</p>`;
  }}
}}

refreshPrice();
setInterval(refreshPrice, 10000);
runLiveEngine();
setInterval(runLiveEngine, 60000);
</script>
</body>
</html>
"""
    return html


def main():
    with open(STATUS_PATH) as f:
        data = json.load(f)
    html = build_html(data)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
