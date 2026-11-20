# Are prediction-market contracts mispriced?

**Question:** do Polymarket and Kalshi show a favourite-longshot bias
(cheap contracts overpriced), and has it shrunk since the 2026 papers
on it?

## Key findings
- 170,000+ resolved markets collected (99,778 Polymarket, 73,388 Kalshi)
- Overall, prices are well calibrated (7-day slope 1.00 Polymarket,
  1.03 Kalshi; 1 = perfectly priced)
- Low-volume markets show the bias (slopes 1.24 / 1.16); high-volume
  markets show the reverse (0.88 / 0.89)
- Kalshi contracts priced at 15p or less returned -35% before fees
  (n = 7,499), a pricing bias rather than a tradeable edge
- The bias has not shrunk since the papers

Full write-up: `results/report.md`. Every judgement call is in
`DECISIONS.md`.

**Note:** the data pipeline and analysis were built with an AI coding
assistant (Claude Code) from a brief I wrote (`claude_code_prompt.md`).

## What is here

| File | What it does |
|---|---|
| `download_polymarket.py` | Lists closed Polymarket markets, samples them, downloads reference prices |
| `download_kalshi.py` | Lists Kalshi events, samples them by month, downloads their markets and candles |
| `apiutil.py` | Shared HTTP helper: at most 4 requests in flight, back-off on 429/5xx, stops if a source keeps refusing |
| `analyse.py` | All tables, the power calculation, charts |
| `verify.py` | Independent re-computation of the headline numbers |
| `data/` | Not included (~1.5 GB); the download scripts recreate it |
| `results/` | `report.md` (the write-up), `tables.md` (every table), `results.json`, `csv/`, three charts |
| `claude_code_prompt.md` | The original brief |


## Requirements

Python 3.10 or later, plus:

```
python -m pip install numpy pandas matplotlib
```

No accounts or API keys are needed. Everything is read-only public market data.

## Rerunning from scratch

Run from this folder, in this order. Every download stage is resumable: if it is interrupted,
run the same command again and it carries on from where it stopped.

```
python download_polymarket.py markets
python download_polymarket.py prices
python download_kalshi.py series
python download_kalshi.py events
python download_kalshi.py markets
python download_kalshi.py candles
python analyse.py
python verify.py
```

Rough timings on a home connection: Polymarket listing 55 minutes, Polymarket prices 30 to 40
minutes (batch requests), Kalshi events listing 55 minutes, Kalshi markets 80 minutes, Kalshi
candles about 4 hours for everything (Kalshi allows only about four requests a second without a
key), analysis 35 minutes, verification 5 minutes.

The Kalshi candle stage fetches the 7-day horizon first, then 30, 90 and finally 1 day (a random
25,000 markets), so an interrupted run still has the horizons that matter most.

To send a long download to the background on Windows and keep a log:

```
Start-Process python -ArgumentList '-u','download_polymarket.py','prices' -RedirectStandardOutput logs\pm_prices.log -RedirectStandardError logs\pm_prices.err -WindowStyle Hidden
```

## Things to know before rerunning

- **A rerun will not reproduce the same numbers exactly.** New markets resolve every day, and the
  Kalshi boundary between "live" and "historical" data moves forward. The random samples use a
  fixed seed, but they are drawn from whatever the listing returns on the day.
- **To rerun only the analysis** on the saved data, run `python analyse.py`. It is deterministic.
- **To start a download again from nothing**, delete the relevant files in `data/` first
  (including the `*_state.json`, `polymarket_sample_ids.txt` and `kalshi_sampled_events.csv` files,
  which freeze the sample).
- `N_BOOT=200 python analyse.py` (or `$env:N_BOOT=200` in PowerShell) gives a quick test run with
  fewer bootstrap resamples. The reported results use 2,000.
