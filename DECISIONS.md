# Decisions and deviations from the brief

Everything in the "Fixed in advance" section of the brief was applied as written and was not
changed after seeing results. This file lists every judgement call, and every place where the
brief could not be followed literally. Items marked **DEVIATION** depart from the brief.

## A. Changes made during the run at your request

1. **Concurrency cap on Polymarket.** The brief said at most 4 requests in flight. Part-way
   through you asked for more speed, so the Polymarket price download was restarted at 12 in
   flight. It was no faster (about 18 requests a second either way: Polymarket queues requests
   per client), so the cap went back to 4. Kalshi stayed at 4 throughout.
2. **Polymarket batch endpoint.** The speed-up that worked was `POST /batch-prices-history`
   (20 tokens per request) instead of one `GET /prices-history` per price. It is still a
   read-only data query. Before switching, 240 prices already fetched one at a time were
   re-fetched through the batch route: all 240 matched exactly (price and timestamp). About
   70,000 prices came from single requests and the rest from batch requests; each record in
   `data/polymarket_prices.jsonl` says which (`"via": "batch"` or absent).

## A2. Things added after seeing preview results (all labelled as such in the report)

2a. **Placeholder prices of exactly 50% on Polymarket.** About 7% of Polymarket 7-day prices
    are exactly 0.50, and those markets win only about 40% of the time. They are markets that
    had only just opened and had no real quotes yet (an empty order book has a midpoint of
    0.50). The pre-registered rule counts them as quoted prices, so they stay in the main
    analysis; a robustness row removes them.
2b. **Kalshi quote midpoints.** About a quarter of Kalshi reference prices (a third at 7 days)
    come from a quote midpoint, not a trade. A robustness row uses traded prices only.
2c. **Exploratory mix analysis.** The primary result pointed the opposite way to the
    hypothesis, which the brief says to treat as a prompt to look for a bug. No bug was found,
    but the mix of markets differs sharply between the periods (on Polymarket the median
    volume in the 7-day slope sample fell from about $35,000 to $6,000, and the share of
    Yes/No questions from 90% to 53%), and the slope depends strongly on volume. Two
    exploratory tables were added: the mix in each period, and the before/after change inside
    volume terciles and market types. They were not pre-specified and are not tests.

## B. Polymarket

3. **Paging.** The offset endpoint rejects deep offsets ("offset too large"), so the keyset
   variant `GET /markets/keyset` is used, as the brief suggested. It ignores `order`, which does
   not matter because every market in each window is taken.
4. **Month windows are on the scheduled `endDate`**, the only date filter the API has. An extra
   window (end dates from December 2026 to 2040) catches markets that resolved early. Markets
   whose scheduled end was before 2024 but which closed in 2024 or later are missed.
5. **The full set is far larger than the target**: 1,176,675 closed markets with volume of
   $1,000 or more. Monthly counts run from about 200 in early 2024 to over 100,000 in 2026.
   Early 2024 really is that thin in the API: January 2024 has only 231 closed markets even
   without the volume floor.
6. **Sampling rule.** Eligible = two outcomes, resolved exactly 1/0, closed on or after
   1 January 2024, and open for at least one day (a market open for less than a day cannot
   contribute to any horizon). For each closing month: take all eligible markets if there are
   4,000 or fewer, otherwise a simple random sample of 4,000 (seed 20261111). Result: 99,778
   markets. All months up to April 2025 are complete; later months are sampled. The rule never
   looks at prices or outcomes. Consequence: pooled results weight every month from May 2025
   equally, not in proportion to how many markets there were.
7. **Raw data is slimmed.** `data/polymarket_markets.jsonl` keeps the fields the analysis uses
   plus question, slug and event title, with the API's values untouched. The full records
   (about 5 kB each, mostly description text) would have been about 6 GB.
8. **"Open" time** is `startDate`, falling back to `createdAt`. **"Close" time** is `closedTime`.
9. **Outcome and price side.** The price analysed is that of the first listed outcome (for
   Yes/No questions, "Yes"), and the outcome is whether that side won.
10. **Price windows.** One window from 12 hours before the horizon to the horizon, hourly points
    (`fidelity=60`), last point at or before the horizon. If that is empty the request is
    repeated with one-minute points. `prices-history` rejects a 91-day window, so whole
    histories were never an option. The 20-market test in the brief was run: 27 of 27 lookups
    returned a price.
11. **What a Polymarket "price" is.** The API does not say whether a history point is a last
    trade or a quote midpoint. The series returns a point every period even when nothing
    changes, so it behaves like a carried-forward quote, and a price that has been stale for
    more than 12 hours cannot be detected. This is a limitation of the source.
12. **Extra sensitivity check (not in the brief, labelled secondary).** `closedTime` can be a day
    or more after the real-world outcome was known, so the "1 day before close" price can
    already reflect the result. For the 1-day and 7-day horizons, prices were also fetched
    counting back from the earlier of the scheduled `endDate` and `closedTime`. The
    pre-registered anchor (`closedTime`) remains the main analysis.

## C. Kalshi

13. **Time-stratified route.** Confirmed by test that `/historical/markets` ignores
    `min_close_ts`/`max_close_ts` and pages newest-first, so it cannot be stratified by time.
    `GET /events` does list every event, including those older than the historical cutoff
    (12 September 2026 on the day of the run), and `/historical/markets?event_ticker=...`
    returns their markets. So: all 1,022,133 events were listed, each was assigned a month from
    the date in its ticker (for example `KXHIGHNY-25MAR05`), and events were sampled by month.
14. **Strata and quotas** (seed 20261111, nothing about prices or outcomes used):
    - *short*: series Kalshi labels fifteen-minute, hourly or daily (crypto, indices, weather).
      60 events a month.
    - *sports*: other series in the Sports category (mostly single games). 100 events a month.
    - *other*: every other dated event (politics, economics, entertainment, companies). Every
      event dated up to February 2026; 300 a month from March 2026.
    - *undated*: events whose ticker has no date (one-off, long-lived questions). A random 4,000
      of 25,618.
    Total 13,858 events. This is how longer-lived markets were secured: the "other" and
    "undated" strata supply nearly all markets open 7, 30 or 90 days, and they were sampled far
    more heavily than the short-lived strata.
15. **Why the quotas are what they are.** Kalshi throttles clients without a key to roughly 3 to
    4 requests a second (it answers HTTP 429 above that), so the whole download had to fit in
    about 70,000 requests. A pilot of 1,000 events measured how many usable markets each
    stratum yields per event, and the quotas spend the budget on the strata that feed the
    primary test. The pilot looked only at volume and how long markets were open. A first,
    larger sample (45,000 events) was abandoned for this reason, and its partial download was
    deleted.
16. **DEVIATION: not spread evenly across months.** The brief asked for markets spread evenly by
    month. Kalshi had very few non-sports, non-crypto events in early 2025 (about 90 a month,
    against 1,600 a month in late 2026), so even taking all of them leaves early months thin.
    The coverage table shows the result by half-year.
17. **DEVIATION: hourly candles at every horizon, not daily at 30 and 90 days.** A daily
    candle's last trade can be up to 24 hours before the horizon, which would break the fixed
    rule that a price is at most 12 hours old. Hourly candles over a 12-hour window satisfy the
    rule and cost the same single request.
18. **DEVIATION: 1-day prices for a random subset.** 57,007 collected markets had been open at
    least a day, more than the request budget allowed. The 1-day horizon is secondary, so it
    was fetched last, for a seeded random 25,000 of those markets. The first version of the
    results (finished 19:30) used only the 6,332 lookups done by then; at your request the
    remaining 18,668 were fetched afterwards (finished 20:57) and the analysis was rerun. All
    25,000 lookups are now in, so the 1-day Kalshi sample is a uniform random subset. The
    Kalshi 7, 30 and 90-day results did not change in the rerun.
18a. **Wifi outage.** The connection dropped at 17:33 and the Kalshi candle download stopped
    itself after repeated failures, as designed. It was restarted at 18:15 and resumed from the
    saved file. No data were lost; the 7, 30 and 90-day horizons are complete.
19. **Reference price.** The last trade in the 12-hour window (`price.close` in a candle whose
    period ends at or before the horizon). If no trade happened in the window, the midpoint of
    the last bid and ask in the window, but only when both sides were quoted (bid above 0, ask
    below 1) and the spread was 10 cents or less. Otherwise the market has no price at that
    horizon. The 10-cent limit is a judgement call.
20. **Batch candles for recent markets.** `GET /markets/candlesticks` (up to 100 markets per
    request) only serves markets newer than the cutoff (tested), so it is used for those; older
    markets use one request each.
21. **Usable market** = `market_type` binary, `result` yes or no, at least 1,000 contracts
    traded, not a multivariate combo. Scalar and voided markets are dropped.
22. **Pacing.** A minimum gap between requests that widens by half on every HTTP 429 and narrows
    slowly on success, so the download settles just under the rate Kalshi allows.

## D. Analysis

23. **Bootstrap.** 2,000 resamples of whole events; percentile intervals. For before/after
    changes, each resample draws events from the whole sample and refits both periods, and the
    interval is taken over the 2,000 differences.
24. **Regression includes an intercept.** The slope is reported; intercepts are in the table.
25. **Unweighted.** Every sampled market counts once. Because strata were sampled at different
    rates, pooled figures describe the sample, not a volume-weighted or population-weighted
    market. See limitations in the report.
26. **Power calculation.** Smallest detectable change = (1.96 + 0.84) x standard error of the
    change. Two standard errors are reported: one from simulating outcomes as if prices were
    perfectly calibrated (blind to real outcomes), one from the event bootstrap of the real data
    (which allows for markets in one event moving together). The bootstrap one uses real
    outcomes, but only their variability, and is the more honest of the two. It was computed
    before any slope estimates were looked at.
27. **Reliability bands**: 0-3%, 3-10%, 10-20%, ... 80-90%, 90-97%, 97-100%, so the two outer
    bands are exactly the prices excluded from the slope sample.
28. **Returns.** Each market contributes two contracts: Yes at price p and No at 1 - p, each
    classified by its own cost. Return = (payout - cost) / cost, averaged with an equal stake
    per contract. Contracts costing under 1p or over 99p are excluded (a return on a zero cost
    is undefined). Reported at all horizons; the 7-day figures are the ones quoted.
29. **Robustness split at 1 September 2025** has no dropped month: before = closed before that
    date, after = on or after.
30. **Kalshi categories** come from the category of the series: Sports; Politics and world
    (Politics, Elections, World); Economics and finance (Economics, Financials, Companies,
    Commodities); Crypto; Weather; Culture and other (everything else).
31. **Polymarket market type.** "Yes/No" if the outcomes are exactly Yes and No; otherwise
    "Named outcomes" (team names, Up/Down, Over/Under).
32. **Charts** are static matplotlib PNGs. A colour-palette validator was not run; the one
    two-series chart uses blue circles and orange squares so it does not rely on colour alone.
33. **Study window.** Polymarket: closed 1 January 2024 or later. Kalshi: closed 1 January 2025
    or later.
