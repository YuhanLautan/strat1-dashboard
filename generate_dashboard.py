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


def build_html(data):
    cfg = data["config"]
    live = data["live_state"]
    summary = data["summary"]
    trades = data["last_10_trades"]

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
          <div><span class="lbl">Entry time</span><span class="val">{live['entry_time']}</span></div>
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
          <div><span class="lbl">Signal candle</span><span class="val">{live['signal_time']}</span></div>
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

    rows_trades = ""
    for t in reversed(trades):
        d = t["direction"]
        reason = t["reason"]
        pnl = t["balance_after_usd"]
        dir_class = "up" if d == "LONG" else "down"
        reason_class = "up" if reason == "TAKE_PROFIT" else ("down" if reason == "STOP_LOSS" else "")
        rows_trades += f"""
        <tr>
          <td>{t['entry_time']}</td>
          <td>{t['exit_time']}</td>
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
</style>
</head>
<body>
<div class="wrap">
  <h1>Strat 1 — Causal Consolidation-Gated RSI/MA Reversal (15m BTCUSDT)</h1>
  <div class="subtitle">5x leverage · 10% daily-loss limit · 3-day pause on breach — the adopted config</div>

  <div class="banner">
    ⚠ This is a <b>backtest snapshot</b>, not a live feed. Status below reflects the last candle in the
    local dataset (<b>{live['as_of']}</b>). Re-run <code>export_status.py</code> after refreshing
    <code>BTCUSDT_15m_history.csv</code> to bring this current before using it to place a real trade.
  </div>

  <div class="card">
    <h2>Current status</h2>
    <span class="status-badge {status_class}">{status_labels[status]}</span>
    <div class="mini-badges">
      <span class="mini-badge">Consolidation gate: {gate_badge}</span>
      <span class="mini-badge">Daily-loss pause: {pause_badge}</span>
      <span class="mini-badge">RSI({live['rsi_period']}): {live['current_rsi']:.1f}</span>
      <span class="mini-badge">MA({live['ma_period']}): ${fmt_num(live['current_ma'])}</span>
    </div>
    {live_body}
  </div>

  <div class="card">
    <h2>Last 10 closed trades</h2>
    <div class="table-scroll">
    <table>
      <thead><tr>
        <th>Entry time</th><th>Exit time</th><th>Dir</th><th>Exit reason</th>
        <th>Entry px</th><th>Exit px</th><th>Margin</th><th>Balance after</th>
      </tr></thead>
      <tbody>{rows_trades}
      </tbody>
    </table>
    </div>
  </div>

  <div class="card">
    <h2>Backtest track record (full history, this config)</h2>
    <div class="summary-row">
      <div><span class="lbl">Return</span><span class="val up">{fmt_pct(summary['return_pct'])}</span></div>
      <div><span class="lbl">Max drawdown</span><span class="val down">{fmt_pct(summary['max_drawdown_pct'])}</span></div>
      <div><span class="lbl">Trades (closed)</span><span class="val">{summary['num_trades']}</span></div>
      <div><span class="lbl">Win rate</span><span class="val">{fmt_num(summary['win_rate_pct'],1)}%</span></div>
    </div>
    <p class="manual-note">Dollar figures compound off a hypothetical $10k start at 100% position size / 5x
    leverage over ~9 years — not a realistic deployable size. The % return/drawdown/win-rate are the
    meaningful numbers here.</p>
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
    Generated from data as of {data['generated_at_data_timestamp']}.
  </footer>
</div>
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
