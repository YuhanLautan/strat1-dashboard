# Strat 1 Dashboard

Static dashboard for the "Causal Consolidation-Gated RSI/MA Reversal" BTCUSDT
strategy (5x leverage, 10% daily-loss limit, 3-day pause on breach). Shows
current position/pending-signal status, the last 10 closed trades, and the
full parameter set — meant as a reference for manual trade execution, not a
live feed.

`index.html` is self-contained (all data embedded, generated from a
point-in-time backtest run). It does **not** update itself.

## Regenerating

This repo only holds the generator scripts and the last-exported
`status.json` — the actual backtest run needs the full project (data file,
`backtest.py`, `fast_backtest.py`, `causal_consolidation.py`), which lives
outside this repo. From the full project:

```
py -3 "Strat 1/export_status.py"
py -3 "Strat 1/generate_dashboard.py"
```

Then copy the refreshed `status.json` and `dashboard.html` (as `index.html`)
into this repo, commit, and push — Vercel redeploys automatically on push.
