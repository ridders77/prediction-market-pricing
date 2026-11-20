# Task: prediction-market calibration study, version 2 (run unattended)

Work in this folder. Do the whole task without asking me questions. If something is ambiguous, make the most reasonable choice, write it in `DECISIONS.md`, and carry on. I am a first-year statistics student and will read the results afterwards.

## Goal

Test two things on resolved Polymarket and Kalshi markets:

1. Replication: is there a favourite-longshot bias (longshots overpriced, favourites underpriced)?
2. New question: is the bias smaller for markets that closed after the 2026 papers on it were published than for markets that closed before?

A small first version found no bias (Polymarket slope 0.94, interval 0.82 to 1.08, n=1,353; Kalshi 1.00, 0.89 to 1.12, n=1,286) but it was too small, used only high-volume markets, and only looked at the last week before close. This version fixes that.

## Rules

- Read-only use of public market-data APIs. No accounts, no API keys, no trading, no VPNs.
- Be polite to the APIs: at most 4 requests in flight, back off on HTTP 429 and 5xx, and stop a source if it keeps refusing.
- Python standard library plus numpy, pandas and matplotlib only. Install what is missing with pip.
- Every download step must be resumable: append results to files as they arrive and skip what is already saved on restart.
- Run long downloads as background processes that write a log file, and check the log occasionally instead of watching it. Do not burn usage polling.
- Do not delete or modify anything outside this folder.

## Fixed in advance (do not change after seeing results)

- Outcome: binary markets with a clean yes/no resolution only. Drop voided or 50/50 resolutions.
- Reference price: the last traded or quoted price at or before each horizon, taken no more than 12 hours earlier than the horizon. Horizons: 1, 7, 30 and 90 days before the market closed. A market contributes to a horizon only if it had been open that long.
- Slope sample: prices between 3% and 97%.
- Calibration slope: logistic regression of outcome on the log-odds of price. Slope above 1 is favourite-longshot bias.
- Uncertainty: 95% bootstrap intervals, 2,000 resamples, resampling whole events (all markets in one event move together).
- Before/after split: "before" is markets closing before 1 February 2026; "after" is markets closing on or after 1 March 2026; February 2026 is dropped.
- Primary test: change in slope (after minus before) at the 7-day horizon, Polymarket and Kalshi separately. Everything else is secondary and must be labelled as such.
- Before running the main analysis, do a power calculation: given the sample you actually collected, what is the smallest change in slope you could detect with 80% power? Report it.

## Data to collect

### Polymarket
- Markets: `GET https://gamma-api.polymarket.com/markets` with `closed=true`, `limit=100`, `offset`, `end_date_min`, `end_date_max`, `order=volumeNum`, `ascending=false`, optional `volume_num_min`. The response is a JSON list. Check the current docs at docs.polymarket.com for a keyset-pagination variant and use it if offsets are capped.
- Cover January 2024 to today, every month, with no "top 300" cap this time. Use a volume floor of $1,000 to drop dead markets. Target 50,000 or more markets. If the full set is far larger, take a random sample stratified by month and record the sampling rule.
- Fields that mattered last time: `id`, `outcomes` and `outcomePrices` (both JSON-encoded strings; resolved markets are `["1","0"]` or `["0","1"]`), `clobTokenIds` (JSON string; first token is the first outcome), `closedTime` (format like `2024-11-06 15:02:11+00`), `endDate`, `startDate`, `volumeNum`, `negRisk`, `events[0].id` (use as the event cluster).
- Prices: `GET https://clob.polymarket.com/prices-history` with `market=<token id>`, `startTs`, `endTs`, `fidelity=60`. This worked for 7-day windows on all 2,500 markets last time. For 30 and 90 day horizons you only need the price near each horizon, so request a short window (for example 24 hours) ending at each horizon instead of the whole history. Test on 20 markets first and adjust if windows come back empty.

### Kalshi
- Base URL `https://api.elections.kalshi.com/trade-api/v2`. Read docs.kalshi.com (start from `https://docs.kalshi.com/llms.txt`) before writing code.
- Live and historical data are split. `GET /historical/cutoff` gives the boundary. Settled markets older than the cutoff are at `GET /historical/markets` (`limit` up to 1000, `cursor`, `tickers`, `event_ticker`, `mve_filter=exclude`). Newer ones are at `GET /markets?status=settled`.
- Problem found last time: paging `/historical/markets` from the start returned 111,000 markets that all closed within about three days, so paging the whole feed back to 2025 is not practical. Find a time-stratified route instead. The likely one: list events across time (the events endpoint is documented as reaching events older than the cutoff), sample events evenly by month from January 2025 to today, then fetch each sampled event's markets with `/historical/markets?event_ticker=...`. Verify this against the docs and a small test before committing to it.
- Target 30,000 or more markets, spread evenly across months, volume of 1,000 contracts or more. Most Kalshi markets last under a day (hourly crypto, weather, sports props). Keep them for the 1-day analysis where valid, and make sure the sample also includes enough longer-lived markets (politics, economics, season-long sports) for the 7, 30 and 90 day horizons. Record how you did that.
- Fields: `ticker`, `event_ticker` (cluster), `market_type` (keep `binary`), `result` (`yes`/`no`), `open_time`, `close_time`, `volume_fp`.
- Candles: historical markets use `GET /historical/markets/{ticker}/candlesticks`; live ones use `GET /series/{series_ticker}/markets/{ticker}/candlesticks`, where the series ticker is the part of `event_ticker` before the first hyphen. Both need `start_ts`, `end_ts`, `period_interval` (1, 60 or 1440 minutes). The two feeds name fields differently: historical candles have `price.close`, live candles have `price.close_dollars`. Handle both. Use daily candles for the 30 and 90 day horizons.

## Analysis

1. Coverage table: markets collected, usable at each horizon, by platform and by half-year.
2. Power calculation (see above).
3. Replication: slope with interval at each horizon and platform; a reliability table and chart (price band against actual win rate) at each horizon.
4. Primary test: before/after change in slope at 7 days, with interval.
5. Secondary: the same at 1, 30 and 90 days; slope by half-year; split by volume (terciles); for Polymarket split Yes/No questions from named-outcome markets; for Kalshi split by broad category from the series ticker.
6. Returns before fees for contracts costing 15p or less, 15p to 85p, and 85p or more, holding to resolution, with intervals, before and after. State clearly that fees, spreads and tradable size are ignored.
7. Robustness: repeat the primary test with a 5% to 95% price filter and with the split date moved to 1 September 2025.

## Deliverables (all in this folder)

- `download_polymarket.py`, `download_kalshi.py`, `analyse.py`: clean, commented, runnable end to end.
- `data/`: the raw downloads.
- `results/report.md`: the write-up. Lead with the answer to both questions in three sentences. Then coverage, power, replication, primary test, secondary results, returns, robustness, limitations, and how it compares with the first version and with the published papers. Plain English, British spelling, every number with its interval and sample size.
- `results/*.png`: reliability charts and a slope-by-half-year chart.
- `DECISIONS.md`: every judgement call and anything in this brief you could not do as written.
- `README.md`: how to rerun everything.

## Checks before you finish

- Recompute three headline numbers by a second route (for example a hand-rolled check on a subsample) and confirm they match.
- Confirm no market appears twice and no price used is from after the market closed.
- If a result looks surprisingly strong, look for a bug before reporting it.
- Say plainly what you did not verify.
