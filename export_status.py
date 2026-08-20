"""
Exports the current strategy status + last 10 trades + full parameter set
to status.json, for dashboard.html to render as a static page.

Run from the project root:
    py -3 "Strat 1/export_status.py"

This reuses run_variant.py's simulate() logic exactly (same engine, same
config), just adds a bit of introspection at the final bar so the dashboard
can show whether the strategy is currently flat, pending an entry, or
holding an open position -- info a backtest's trade list alone doesn't
expose (the engine only records a trade once it's closed, or as
"OPEN_AT_END" if a position was still open at the last available candle).
"""

import json
import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_variant import load_data, load_config, prepare, DATA_PATH
from backtest import compute_rsi, MAKER_FEE_PCT, TAKER_FEE_PCT

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "status.json")


def simulate_with_live_state(prepared, cfg, leverage, daily_limit_pct, pause_days):
    close, low, high = prepared["close"], prepared["low"], prepared["high"]
    day_idx, open_time = prepared["day_idx"], prepared["open_time"]
    entry_signal, valid_mask, causal_mask = prepared["entry_signal"], prepared["valid_mask"], prepared["causal_mask"]

    n = len(close)
    sl_pct = cfg["STOP_LOSS_PCT"] / 100.0
    tp_pct = cfg["TAKE_PROFIT_PCT"] / 100.0
    pos_pct = cfg["POSITION_SIZE_PCT"] / 100.0
    maker_fee = MAKER_FEE_PCT / 100.0
    taker_fee = TAKER_FEE_PCT / 100.0
    liquidation_move = 1.0 / leverage

    starting_balance = 10_000.0
    balance = starting_balance
    has_position = False
    direction = 1
    entry_price = 0.0
    margin = 0.0
    notional = 0.0
    entry_i = 0
    pending = False
    pending_dir = 1
    pending_trigger = 0.0
    pending_since_i = None
    cur_day = -1
    daily_pnl_pct = 0.0
    paused_until_day = -1
    num_trades = 0
    num_wins = 0
    equity_peak = starting_balance
    max_dd = 0.0
    trades = []

    for i in range(n):
        if not valid_mask[i]:
            continue
        price = close[i]
        lo = low[i]
        hi = high[i]
        d = day_idx[i]

        if d != cur_day:
            cur_day = d
            daily_pnl_pct = 0.0

        if has_position:
            if direction == 1:
                hit_sl = price <= entry_price * (1 - sl_pct)
                hit_tp = price >= entry_price * (1 + tp_pct)
            else:
                hit_sl = price >= entry_price * (1 + sl_pct)
                hit_tp = price <= entry_price * (1 - tp_pct)
            if hit_sl or hit_tp:
                exit_fee_pct = maker_fee if hit_tp else taker_fee
                move_pct = tp_pct if hit_tp else (price - entry_price) / entry_price * direction
                if move_pct <= -liquidation_move:
                    move_pct = -liquidation_move
                gross_pnl = notional * move_pct
                exit_fee = notional * exit_fee_pct
                proceeds = max(margin + gross_pnl - exit_fee, 0.0)
                balance += proceeds
                if margin:
                    daily_pnl_pct += (proceeds - margin) / margin * 100
                num_trades += 1
                if proceeds > margin:
                    num_wins += 1
                exit_price = entry_price * (1 + tp_pct * direction) if hit_tp else price
                trades.append({
                    "entry_time": str(open_time.iloc[entry_i]), "exit_time": str(open_time.iloc[i]),
                    "direction": "LONG" if direction == 1 else "SHORT",
                    "reason": "TAKE_PROFIT" if hit_tp else "STOP_LOSS",
                    "entry_price": entry_price, "exit_price": exit_price,
                    "margin_usd": margin, "notional_usd": notional, "balance_after_usd": balance,
                })
                has_position = False
                if daily_pnl_pct <= -daily_limit_pct:
                    paused_until_day = cur_day + pause_days - 1

        blocked = cur_day <= paused_until_day
        con_ok = causal_mask[i]

        if pending:
            touched = (lo <= pending_trigger) if pending_dir == 1 else (hi >= pending_trigger)
            if touched and not has_position:
                m = balance * pos_pct
                if m > 0:
                    notl = m * leverage
                    entry_fee = notl * maker_fee
                    balance -= m
                    has_position = True
                    direction = pending_dir
                    entry_price = pending_trigger
                    entry_i = i
                    margin = m - entry_fee
                    notional = notl
                pending = False
                pending_since_i = None
        elif (not has_position) and (not blocked) and con_ok and entry_signal[i] != 0:
            pending = True
            pending_dir = int(entry_signal[i])
            pending_trigger = price
            pending_since_i = i

        open_value = 0.0
        if has_position:
            move_pct = (price - entry_price) / entry_price * direction
            open_value = max(margin + notional * move_pct, 0.0)
        equity = balance + open_value
        if equity > equity_peak:
            equity_peak = equity
        dd = (equity - equity_peak) / equity_peak * 100
        if dd < max_dd:
            max_dd = dd

    # `equity` here is mark-to-market as of the last bar (balance + open
    # position's current value if one is still held) -- unlike balance
    # alone, this matches what run_variant.py reports (it force-closes any
    # still-open position at the last close to compute final_balance).
    final_equity = equity
    return_pct = (final_equity - starting_balance) / starting_balance * 100
    win_rate = (num_wins / num_trades * 100) if num_trades else 0.0

    dataset_start_date = open_time.iloc[0].normalize()
    paused_until_date = (dataset_start_date + pd.Timedelta(days=int(paused_until_day))) if paused_until_day >= 0 else None

    live_state = {
        "as_of": str(open_time.iloc[n - 1]),
        "last_close": float(close[n - 1]),
        "gate_open": bool(causal_mask[n - 1]),
        "blocked_by_daily_loss_pause": bool(cur_day <= paused_until_day),
        "paused_until_date": str(paused_until_date.date()) if paused_until_date is not None else None,
    }
    if has_position:
        sl_price = entry_price * (1 - sl_pct) if direction == 1 else entry_price * (1 + sl_pct)
        tp_price = entry_price * (1 + tp_pct) if direction == 1 else entry_price * (1 - tp_pct)
        unrealized_pct = (close[n - 1] - entry_price) / entry_price * direction * leverage * 100
        live_state.update({
            "status": "IN_POSITION",
            "direction": "LONG" if direction == 1 else "SHORT",
            "entry_time": str(open_time.iloc[entry_i]),
            "entry_price": float(entry_price),
            "stop_loss_price": float(sl_price),
            "take_profit_price": float(tp_price),
            "margin_usd": float(margin),
            "notional_usd": float(notional),
            "unrealized_pnl_pct_of_margin": float(unrealized_pct),
        })
    elif pending:
        live_state.update({
            "status": "PENDING_ENTRY",
            "direction": "LONG" if pending_dir == 1 else "SHORT",
            "trigger_price": float(pending_trigger),
            "signal_time": str(open_time.iloc[pending_since_i]),
        })
    else:
        live_state["status"] = "FLAT_NO_SIGNAL"

    result = {
        "final_balance": final_equity, "return_pct": return_pct, "max_drawdown_pct": max_dd,
        "num_trades": num_trades, "win_rate_pct": win_rate,
        "trades": trades, "live_state": live_state,
    }
    return result


def compute_window_summary(trades, cfg, leverage=None):
    """Return/max-drawdown/win-rate computed fresh from just this slice of
    trades (a hypothetical $10k restart at the first trade in the window).
    Per-trade compounding uses leverage-on-margin math (mirrors simulate()'s
    proceeds = margin + gross_pnl - exit_fee, expressed as a fraction of
    margin so it doesn't need the trade's actual dollar margin/notional --
    works the same whether a trade came from the static backtest or the
    live client-side engine, which doesn't track dollar balance at all).
    leverage defaults to cfg's configured leverage; pass 1 for the
    unleveraged/spot equivalent of the same trade sequence."""
    leverage = cfg["LEVERAGE"] if leverage is None else leverage
    maker_fee = MAKER_FEE_PCT / 100.0
    taker_fee = TAKER_FEE_PCT / 100.0

    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    wins = 0
    for t in trades:
        direction = 1 if t["direction"] == "LONG" else -1
        move_pct = (t["exit_price"] - t["entry_price"]) / t["entry_price"] * direction
        exit_fee_frac = (maker_fee if t["reason"] == "TAKE_PROFIT" else taker_fee) * leverage
        entry_fee_frac = maker_fee * leverage
        multiplier = 1 + move_pct * leverage - entry_fee_frac - exit_fee_frac
        equity *= max(multiplier, 0.0)
        if move_pct > 0:
            wins += 1
        if equity > peak:
            peak = equity
        dd = (equity - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    n = len(trades)
    return {
        "return_pct": (equity - 1.0) * 100,
        "max_drawdown_pct": max_dd,
        "num_trades": n,
        "win_rate_pct": (wins / n * 100) if n else 0.0,
    }


def main():
    cfg = load_config()
    df = load_data()
    prepared = prepare(df, cfg)

    leverage = cfg["LEVERAGE"]
    pause_days = cfg["DAILY_LOSS_PAUSE_DAYS"]
    r = simulate_with_live_state(prepared, cfg, leverage=leverage,
                                  daily_limit_pct=cfg["DAILY_LOSS_LIMIT_PCT"], pause_days=pause_days)

    # current RSI/MA reading, for manual cross-check against a live chart
    rsi = compute_rsi(df["close"], cfg["RSI_PERIOD"]).to_numpy()
    ma = df["close"].rolling(cfg["MA_PERIOD"]).mean().to_numpy()
    r["live_state"]["current_rsi"] = float(rsi[-1])
    r["live_state"]["current_ma"] = float(ma[-1])
    r["live_state"]["rsi_period"] = cfg["RSI_PERIOD"]
    r["live_state"]["ma_period"] = cfg["MA_PERIOD"]

    # Warmup buffer so a browser can continue the RSI/MA recursion forward
    # from this checkpoint using only new candles fetched from Binance --
    # 200 15m closes is far more than RSI(5)'s EWM needs to converge
    # (alpha=0.2, so (1-alpha)^200 is effectively zero) and MA(50) only
    # ever needs its own trailing 50 anyway.
    WARMUP_N = 200
    warmup_closes = [
        {"t": str(t), "c": float(c)}
        for t, c in zip(df["open_time"].iloc[-WARMUP_N:], df["close"].iloc[-WARMUP_N:])
    ]

    recent_trades = r["trades"][-20:]
    full_summary_1x = compute_window_summary(r["trades"], cfg, leverage=1)
    full_summary_lev = compute_window_summary(r["trades"], cfg, leverage=cfg["LEVERAGE"])

    out = {
        "config": cfg,
        "summary": {
            "final_balance": r["final_balance"],
            "return_pct": r["return_pct"],
            "max_drawdown_pct": r["max_drawdown_pct"],
            "num_trades": r["num_trades"],
            "win_rate_pct": r["win_rate_pct"],
        }, # from the real dollar-tracking engine -- kept for reference, but
           # full_history_summary below (same compute_window_summary formula
           # used everywhere else on the dashboard) is what's actually shown
        "full_history_summary": {
            "return_pct_1x": full_summary_1x["return_pct"],
            "return_pct_leveraged": full_summary_lev["return_pct"],
            "max_drawdown_pct": full_summary_lev["max_drawdown_pct"],
            "num_trades": full_summary_lev["num_trades"],
            "win_rate_pct": full_summary_lev["win_rate_pct"],
        },
        "recent_summary": compute_window_summary(recent_trades, cfg),
        "live_state": r["live_state"],
        "last_20_trades": recent_trades,
        "all_trades": r["trades"],
        "generated_at_data_timestamp": r["live_state"]["as_of"],
        "engine_checkpoint": {
            "as_of_time": r["live_state"]["as_of"],
            "has_position": r["live_state"]["status"] == "IN_POSITION",
            "direction": r["live_state"].get("direction"),
            "entry_time": r["live_state"].get("entry_time"),
            "entry_price": r["live_state"].get("entry_price"),
            "pending": r["live_state"]["status"] == "PENDING_ENTRY",
            "trigger_price": r["live_state"].get("trigger_price"),
            "signal_time": r["live_state"].get("signal_time"),
            "paused_until_date": r["live_state"]["paused_until_date"],
            "warmup_closes": warmup_closes,
        },
    }
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Wrote {OUT_PATH}")
    print(json.dumps(out["live_state"], indent=2))
    print(json.dumps(out["summary"], indent=2))


if __name__ == "__main__":
    main()
