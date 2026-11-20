# Prediction-market calibration study, version 2

Run on 11 November 2026. All intervals are 95% bootstrap intervals from 2,000 resamples of whole
events. "n" is the number of markets. Every table behind this report is in `tables.md`.

## The answer in three sentences

**Replication:** taken as a whole, neither platform shows a favourite-longshot bias in the
calibration slope seven days before close (Polymarket 1.00, 0.97 to 1.03, n=27,255; Kalshi 1.03,
0.99 to 1.08, n=10,967), but that average hides a clear bias in low-volume markets (slopes of
1.24 and 1.16) and the reverse in high-volume markets (0.88 and 0.89).
**New question:** there is no evidence that the bias got smaller after the 2026 papers; the
slope went up, not down, on Polymarket (change +0.10, 0.03 to 0.18) and did not change
detectably on Kalshi (+0.07, -0.02 to 0.16).
The Polymarket rise looks like a change in which markets exist, not in how well they are priced:
inside groups of similar volume the change is about zero, and it disappears when the split date
is moved to September 2025.

## 1. Coverage

| | Polymarket | Kalshi |
|---|---|---|
| Listed | 1,176,675 closed markets with volume of $1,000+, January 2024 to November 2026 | 1,022,133 events (every event on the exchange) |
| Sampled | 99,778 clean binary markets open at least a day: all of them up to April 2025, a random 4,000 a month after | 13,858 events, stratified by month and type; 224,977 markets fetched |
| Collected (usable) | 99,778 markets in 66,762 events | 73,705 binary markets settled yes/no with 1,000+ contracts (73,388 of them closed in 2025 or later, in 9,987 events) |

Markets with a usable price, and in the slope sample (price 3% to 97%), by horizon:

| Platform | Horizon | Open that long | Priced | In slope sample | Events in slope sample |
|---|---|---|---|---|---|
| Polymarket | 1 day | 99,778 | 99,410 | 75,119 | 56,976 |
| Polymarket | 7 days | 37,099 | 36,538 | 27,255 | 17,512 |
| Polymarket | 30 days | 9,422 | 9,279 | 5,505 | 3,202 |
| Polymarket | 90 days | 3,509 | 3,449 | 2,182 | 1,213 |
| Kalshi | 1 day | 56,693 | 18,448 | 14,113 | 4,134 |
| Kalshi | 7 days | 23,176 | 13,651 | 10,967 | 2,651 |
| Kalshi | 30 days | 11,238 | 6,635 | 5,781 | 1,566 |
| Kalshi | 90 days | 3,437 | 1,921 | 1,739 | 579 |

Three things to know about this table:

- **Kalshi 1-day is a random subset.** A seeded random 25,000 of the 56,693 eligible markets had
  their 1-day price requested, because Kalshi limits clients without a key to about four
  requests a second and the 1-day horizon is secondary (see `DECISIONS.md`, item 18).
- **Many Kalshi markets have no price at a horizon.** About 40% of Kalshi markets that were open
  seven days before close had neither a trade nor a tight two-sided quote in the 12 hours before
  the horizon, so they drop out. Polymarket loses almost none, because its price feed carries a
  quote forward (which is its own problem, see section 8).
- **The split by half-year** is in `tables.md`. Early periods are thin: Polymarket has 945
  markets in the 7-day slope sample for the first half of 2024, and Kalshi 1,095 for the first
  half of 2025.

Sample for the before/after comparison at 7 days:

| Platform | Before (closed before 1 Feb 2026) | February 2026 (dropped) | After (closed from 1 Mar 2026) |
|---|---|---|---|
| Polymarket | 14,570 markets, 7,452 events | 1,191 | 11,494 markets, 9,108 events |
| Kalshi | 5,309 markets, 1,246 events | 664 | 4,994 markets, 1,260 events |

## 2. Power

Question: given this sample, how small a change in slope could the primary test detect with 80%
power (two-sided test at the 5% level)? Smallest detectable change = 2.80 x the standard error
of the change.

| Platform (7 days) | Standard error of the change | Smallest detectable change |
|---|---|---|
| Polymarket | 0.037 | **0.10** |
| Kalshi | 0.045 | **0.13** |

These use the event bootstrap, which allows for markets in the same event moving together.
A second calculation that simulates outcomes as if every market were independent and perfectly
priced gives slightly smaller figures (0.09 and 0.11); a check simulation confirmed the formula
(78% and 81% power achieved against a target of 80%).

In plain terms: if the papers had moved the slope by 0.10 or more on Polymarket, or 0.13 or more
on Kalshi, this study would probably have seen it. A smaller shift could be missed. For
secondary horizons the figures are much weaker (for example 0.23 for Polymarket at 30 days and
0.36 for Kalshi at 90 days; full table in `tables.md`).

## 3. Replication: is there a favourite-longshot bias?

A slope above 1 means favourites win more often than their price implies and longshots less
often. A slope of 1 is perfect calibration.

| Platform | Horizon | Slope (95% interval) | Markets | Events |
|---|---|---|---|---|
| Polymarket | 1 day | 1.01 (0.99 to 1.03) | 75,119 | 56,976 |
| Polymarket | 7 days | 1.00 (0.97 to 1.03) | 27,255 | 17,512 |
| Polymarket | 30 days | 1.06 (1.01 to 1.13) | 5,505 | 3,202 |
| Polymarket | 90 days | 1.06 (0.97 to 1.16) | 2,182 | 1,213 |
| Kalshi | 1 day | 1.03 (0.99 to 1.07) | 14,113 | 4,134 |
| Kalshi | 7 days | 1.03 (0.99 to 1.08) | 10,967 | 2,651 |
| Kalshi | 30 days | 1.01 (0.96 to 1.08) | 5,781 | 1,566 |
| Kalshi | 90 days | 1.01 (0.91 to 1.14) | 1,739 | 579 |

Seven of the eight intervals include 1. The exception is Polymarket at 30 days, a slope of 1.06
whose interval only just excludes 1. Eight intervals were examined, so one narrow miss is not
strong evidence. On the slope measure, the overall bias is at most small.

The reliability table at 7 days shows where prices and outcomes part company:

| Price band | Polymarket: mean price | Polymarket: won | n | Kalshi: mean price | Kalshi: won | n |
|---|---|---|---|---|---|---|
| 0-3% | 0.8% | 0.6% (0.4% to 0.8%) | 8,556 | 1.4% | 0.4% (0.1% to 0.6%) | 1,956 |
| 3-10% | 5.9% | 5.7% (5.0% to 6.4%) | 4,162 | 5.5% | 3.7% (2.9% to 4.5%) | 2,305 |
| 10-20% | 14.4% | 13.6% (12.5% to 14.7%) | 3,656 | 14.2% | 12.3% (10.5% to 14.1%) | 1,499 |
| 20-30% | 24.9% | 22.1% (20.8% to 23.5%) | 3,481 | 24.2% | 23.3% (20.7% to 26.2%) | 1,050 |
| 30-40% | 34.7% | 31.3% (29.4% to 33.0%) | 2,535 | 34.4% | 33.7% (30.5% to 37.1%) | 887 |
| 40-50% | 46.3% | 32.8% (31.4% to 34.2%) | 4,449 | 44.5% | 39.7% (35.8% to 43.7%) | 721 |
| 50-60% | 51.7% | 47.1% (45.6% to 48.5%) | 5,518 | 54.5% | 51.3% (47.3% to 55.1%) | 747 |
| 60-70% | 64.5% | 65.7% (62.9% to 68.5%) | 1,099 | 64.4% | 61.1% (57.2% to 64.8%) | 796 |
| 70-80% | 74.5% | 76.1% (73.3% to 78.9%) | 949 | 74.6% | 68.8% (65.5% to 72.3%) | 805 |
| 80-90% | 84.7% | 86.1% (83.5% to 88.7%) | 704 | 84.8% | 82.8% (80.1% to 85.6%) | 908 |
| 90-97% | 93.8% | 94.3% (92.4% to 96.1%) | 702 | 94.0% | 95.2% (93.8% to 96.4%) | 1,249 |
| 97-100% | 98.6% | 99.2% (98.5% to 99.7%) | 727 | 98.5% | 99.0% (98.1% to 99.7%) | 728 |

What this shows:

- **The main miscalibration is that "Yes" is overpriced across the lower and middle of the
  range, on both platforms.** Most bands below about 60% win less often than their price. This
  shows up in the regression as a negative intercept (-0.22 on Polymarket and -0.14 on Kalshi at
  7 days), not as a slope. It is a tilt towards "Yes", which is a different thing from a
  favourite-longshot bias.
- **Kalshi longshots do underperform.** Contracts priced 3% to 10% won 3.7% of the time against
  a mean price of 5.5%, and those under 3% won 0.4% against 1.4%.
- **The Polymarket 40-50% band is distorted by placeholder prices.** It wins 32.8% against a
  price of 46.3%. About 7% of Polymarket 7-day prices are exactly 50%: markets that had only
  just opened and had no real quotes yet. Section 7 shows that removing them does not change
  the conclusions.

Charts: `reliability_polymarket.png` and `reliability_kalshi.png` (all four horizons).

## 4. Primary test: did the slope change after the papers?

Fixed in advance: 7-day horizon, prices 3% to 97%, each platform separately, February 2026
dropped. A negative change would mean less bias afterwards.

| Platform | Slope before | n before | Slope after | n after | Change (after minus before) |
|---|---|---|---|---|---|
| Polymarket | 0.97 (0.93 to 1.01) | 14,570 | 1.07 (1.02 to 1.13) | 11,494 | **+0.10 (0.03 to 0.18)** |
| Kalshi | 1.00 (0.94 to 1.06) | 5,309 | 1.07 (1.00 to 1.14) | 4,994 | **+0.07 (-0.02 to 0.16)** |

- **Polymarket:** the slope rose by 0.10 and the interval excludes zero. That is the opposite
  direction to the hypothesis.
- **Kalshi:** the estimate is also positive, but the interval includes zero, so no change was
  detected.
- **Neither platform shows a fall.** Even the lower ends of the intervals (+0.03 and -0.02) rule
  out a meaningful reduction in bias.

A result pointing firmly the wrong way is a reason to look for a bug. None was found (section
10), but there is a good non-causal explanation for the Polymarket rise, in section 5.

## 5. Secondary results

Everything in this section is secondary. Nothing here was the pre-registered test.

### Other horizons

| Platform | Horizon | Slope before | n before | Slope after | n after | Change |
|---|---|---|---|---|---|---|
| Polymarket | 1 day | 1.06 (1.03 to 1.09) | 43,221 | 0.96 (0.93 to 0.99) | 28,622 | -0.10 (-0.14 to -0.06) |
| Polymarket | 30 days | 1.06 (0.99 to 1.13) | 4,155 | 1.08 (0.96 to 1.24) | 1,228 | +0.02 (-0.12 to 0.19) |
| Polymarket | 90 days | 1.04 (0.94 to 1.16) | 1,772 | 1.10 (0.92 to 1.35) | 375 | +0.06 (-0.15 to 0.33) |
| Kalshi | 1 day | 1.03 (0.97 to 1.09) | 6,519 | 1.02 (0.97 to 1.08) | 6,434 | -0.01 (-0.09 to 0.08) |
| Kalshi | 30 days | 1.07 (0.98 to 1.17) | 2,729 | 1.01 (0.92 to 1.10) | 2,676 | -0.07 (-0.20 to 0.07) |
| Kalshi | 90 days | 1.01 (0.85 to 1.22) | 944 | 1.04 (0.90 to 1.22) | 742 | +0.03 (-0.23 to 0.28) |

The one clear change, Polymarket at 1 day, goes the opposite way to Polymarket at 7 days. Two
confident results with opposite signs on the same platform are a warning that something other
than "traders read the papers" is moving the pooled slope.

### Slope by half-year (7 days)

| Half-year closed | Polymarket | n | Kalshi | n |
|---|---|---|---|---|
| 2024 H1 | 1.02 (0.87 to 1.19) | 945 | | |
| 2024 H2 | 1.03 (0.94 to 1.13) | 2,099 | | |
| 2025 H1 | 1.02 (0.95 to 1.09) | 4,656 | 1.01 (0.90 to 1.14) | 1,095 |
| 2025 H2 | 0.93 (0.87 to 1.00) | 5,836 | 0.99 (0.91 to 1.06) | 3,378 |
| 2026 H1 | 1.06 (0.99 to 1.14) | 6,111 | 1.06 (0.98 to 1.16) | 3,551 |
| 2026 H2 | 1.04 (0.97 to 1.12) | 7,608 | 1.07 (1.01 to 1.15) | 2,943 |

There is no downward trend. The Polymarket "before" figure is pulled down by one low half-year
(the second half of 2025), which is also why moving the split date changes the answer (section
7). Chart: `slope_by_halfyear.png`, all horizons.

### Volume terciles: the strongest pattern in the study

| Platform | Horizon | Low volume | Middle | High volume |
|---|---|---|---|---|
| Polymarket | 7 days | 1.24 (1.16 to 1.32), n=9,085 | 1.04 (0.99 to 1.09), n=9,085 | 0.88 (0.84 to 0.93), n=9,085 |
| Polymarket | 30 days | 1.14 (1.02 to 1.30), n=1,835 | 1.14 (1.04 to 1.26), n=1,835 | 0.96 (0.88 to 1.05), n=1,835 |
| Kalshi | 7 days | 1.16 (1.09 to 1.24), n=3,656 | 1.07 (0.99 to 1.15), n=3,655 | 0.89 (0.82 to 0.96), n=3,656 |
| Kalshi | 30 days | 1.20 (1.07 to 1.35), n=1,927 | 1.04 (0.94 to 1.15), n=1,927 | 0.84 (0.76 to 0.94), n=1,927 |

At 7 days the cut-points are $6,742 and $42,998 on Polymarket and 5,773 and 25,767 contracts on
Kalshi. On both platforms and at both horizons, thinly traded markets show a favourite-longshot
bias and heavily traded markets show the reverse (prices not extreme enough). The overall slope
of about 1 is an average of the two. The 1-day and 90-day rows are in `tables.md`; the same
pattern appears at 1 day on Kalshi (1.15, 1.08 to 1.23, n=4,705 in the low third; 0.86, 0.80
to 0.92, n=4,704 in the high third).

One caution: volume is measured at the end of a market's life, so it is partly a result of how
the market played out, not just a fixed property of it.

### Market type

| Platform | Group (7 days) | Slope | n |
|---|---|---|---|
| Polymarket | Yes/No questions | 0.97 (0.93 to 1.00) | 20,046 |
| Polymarket | Named outcomes (teams, Up/Down, Over/Under) | 1.15 (1.07 to 1.24) | 7,209 |
| Kalshi | Sports | 1.13 (1.01 to 1.27) | 1,446 |
| Kalshi | Economics and finance | 1.08 (0.99 to 1.20) | 1,978 |
| Kalshi | Politics and world | 1.07 (0.98 to 1.19) | 1,665 |
| Kalshi | Weather | 1.07 (0.91 to 1.31) | 447 |
| Kalshi | Culture and other | 1.00 (0.94 to 1.06) | 5,190 |
| Kalshi | Crypto | 1.35 (0.90 to 2.36) | 241 |

### Why the Polymarket slope rose: the mix of markets changed (exploratory)

This part was added after seeing the primary result. It was not pre-specified.

The markets in the two periods are very different:

| Platform | Period | Median volume | Share low-volume | Share high-volume | Type mix |
|---|---|---|---|---|---|
| Polymarket | Before | $35,334 | 18% | 46% | Yes/No 90%, named outcomes 10% |
| Polymarket | After | $6,034 | 52% | 17% | Yes/No 53%, named outcomes 47% |
| Kalshi | Before | 12,758 contracts | 31% | 36% | Culture and other 61%, sports 8% |
| Kalshi | After | 9,360 contracts | 38% | 29% | Culture and other 33%, sports 20% |

Polymarket listed about 2,000 to 5,000 qualifying markets a month in early 2025 and 60,000 to
100,000 a month in 2026, mostly small sports and price-level markets. Sampling 4,000 a month
therefore draws far more small markets after the split than before it. Since small markets have
higher slopes, the pooled slope rises even if no individual kind of market changed.

Repeating the before/after comparison inside groups of similar markets supports that reading:

| Platform | Group | Slope before | n | Slope after | n | Change |
|---|---|---|---|---|---|---|
| Polymarket | Low volume | 1.26 (1.14 to 1.40) | 2,692 | 1.23 (1.13 to 1.34) | 6,013 | -0.03 (-0.20 to 0.13) |
| Polymarket | Middle volume | 1.02 (0.95 to 1.09) | 5,123 | 1.05 (0.96 to 1.15) | 3,482 | +0.03 (-0.08 to 0.15) |
| Polymarket | High volume | 0.88 (0.84 to 0.94) | 6,755 | 0.89 (0.78 to 1.00) | 1,999 | 0.00 (-0.11 to 0.13) |
| Kalshi | Low volume | 1.13 (1.02 to 1.24) | 1,627 | 1.19 (1.08 to 1.31) | 1,897 | +0.06 (-0.09 to 0.23) |
| Kalshi | Middle volume | 1.06 (0.96 to 1.18) | 1,795 | 1.06 (0.96 to 1.17) | 1,662 | 0.00 (-0.16 to 0.15) |
| Kalshi | High volume | 0.85 (0.77 to 0.95) | 1,887 | 0.93 (0.83 to 1.06) | 1,435 | +0.08 (-0.06 to 0.23) |

Within every volume group on Polymarket the change is within 0.03 of zero. The honest summary is
that like-for-like markets were priced about the same before and after, and that this study
cannot separate "the papers had no effect" from "the papers had an effect smaller than about
0.1". The within-group intervals are wide, so this is a guide to interpretation and not a test.

## 6. Returns before fees

**These are not achievable trading returns. Fees, bid-ask spreads and the size actually tradable
at the reference price are all ignored.** Each market contributes two contracts, Yes at price p
and No at 1 - p, each classified by its own cost and held to resolution. The figure is the mean
return per pound with an equal stake on every contract. Contracts costing under 1p or over 99p
are left out. Prices are taken 7 days before close.

| Platform | Contract cost | All | Before | After |
|---|---|---|---|---|
| Polymarket | 15p or less | -12.6% (-21.8% to -2.6%), n=10,809 | -9.0% (-20.7% to +3.1%), n=7,943 | -22.2% (-36.6% to -7.7%), n=2,567 |
| Polymarket | 15p to 85p | -1.7% (-2.2% to -1.1%), n=39,714 | -0.6% (-1.5% to +0.3%), n=18,732 | -2.7% (-3.4% to -2.0%), n=19,003 |
| Polymarket | 85p or more | +0.5% (+0.0% to +1.0%), n=10,837 | +0.3% (-0.2% to +0.8%), n=7,959 | +0.9% (-0.1% to +1.9%), n=2,578 |
| Kalshi | 15p or less | -35.0% (-46.3% to -22.8%), n=7,499 | -38.6% (-50.1% to -26.4%), n=3,127 | -33.0% (-51.8% to -11.7%), n=3,933 |
| Kalshi | 15p to 85p | +0.9% (-0.6% to +2.4%), n=11,953 | +1.2% (-0.9% to +3.3%), n=6,163 | +1.2% (-0.9% to +3.5%), n=5,061 |
| Kalshi | 85p or more | +1.2% (+0.6% to +1.7%), n=7,574 | +0.6% (-0.4% to +1.5%), n=3,172 | +1.6% (+0.8% to +2.3%), n=3,958 |

n is the number of contracts. Other horizons are in `tables.md`.

- **Cheap contracts lose and dear contracts gain slightly, on both platforms.** That is the
  favourite-longshot pattern, and it is much stronger on Kalshi (-35.0%) than on Polymarket
  (-12.6%).
- **This does not contradict the slopes near 1.** The returns table includes contracts priced
  1p to 3p, which the slope sample excludes and where Kalshi is at its worst (0.4% won against
  a 1.4% price). A small gap in percentage points is a large percentage loss on a cheap
  contract: a 5p contract that wins 4% of the time loses 20%.
- **No sign of the cheap-contract loss shrinking.** The before and after intervals overlap
  heavily on both platforms.
- **The Polymarket middle band is affected by the placeholder 50% prices** described in
  section 3, so its -1.7% should not be read as a real loss.

## 7. Robustness of the primary test

| Variant | Platform | Slope before | n | Slope after | n | Change |
|---|---|---|---|---|---|---|
| Prices 5% to 95% (in brief) | Polymarket | 0.97 (0.93 to 1.02) | 13,275 | 1.07 (1.02 to 1.14) | 11,118 | +0.10 (0.02 to 0.18) |
| Prices 5% to 95% (in brief) | Kalshi | 0.98 (0.92 to 1.05) | 4,738 | 1.06 (1.00 to 1.14) | 4,287 | +0.09 (-0.01 to 0.18) |
| Split at 1 September 2025 (in brief) | Polymarket | 1.03 (0.97 to 1.08) | 8,813 | 1.01 (0.96 to 1.05) | 18,442 | -0.02 (-0.09 to 0.05) |
| Split at 1 September 2025 (in brief) | Kalshi | 1.01 (0.92 to 1.12) | 1,692 | 1.04 (0.99 to 1.09) | 9,275 | +0.02 (-0.09 to 0.13) |
| Horizon counted from the earlier of scheduled end and close (added) | Polymarket | 1.04 (1.00 to 1.09) | 11,117 | 1.11 (1.05 to 1.18) | 10,667 | +0.07 (-0.01 to 0.15) |
| Prices of exactly 50% removed (added) | Polymarket | 0.99 (0.95 to 1.03) | 13,407 | 1.08 (1.02 to 1.14) | 10,150 | +0.09 (0.02 to 0.16) |
| Traded prices only, no quote midpoints (added) | Kalshi | 1.01 (0.94 to 1.09) | 3,565 | 1.06 (0.98 to 1.14) | 3,144 | +0.04 (-0.07 to 0.17) |

- The 5% to 95% filter changes nothing.
- **Moving the split to 1 September 2025 removes the Polymarket effect entirely** (-0.02, -0.09
  to 0.05). The primary result depends on where the line is drawn, which fits the mix
  explanation and not a response to the papers.
- With the alternative Polymarket anchor the change is smaller and its interval includes zero.
- No variant on either platform shows a fall in the slope.

The overall 7-day slope is also stable under the added filters: Polymarket 1.01 (0.97 to 1.04,
n=24,633) without the 50% prices and 1.05 (1.01 to 1.08, n=22,679) with the alternative anchor;
Kalshi 1.04 (0.98 to 1.09, n=7,267) on traded prices only.

## 8. Limitations

- **The before/after comparison is not like-for-like.** Both exchanges grew enormously and
  changed what they list. This is the biggest weakness and it cannot be fixed by collecting
  more data of the same kind.
- **It is an observational comparison of two periods.** Even a clean fall in the slope would
  not show that the papers caused it; anything else that changed in early 2026 would be mixed
  in.
- **Results are unweighted and describe the sample.** Every sampled market counts once, however
  much money traded in it. Polymarket months from May 2025 are capped at 4,000 markets, and
  Kalshi strata were sampled at very different rates, so pooled figures are not estimates for
  "the average dollar traded".
- **Polymarket prices are not clean.** The price feed does not say whether a point is a trade
  or a quote, it carries values forward, and about 7% of 7-day prices are placeholder 50%
  values. Prices of 49.5% and 50.5% are also unusually common and are probably the same thing;
  only exactly 50% was removed in the robustness check.
- **Polymarket "close" can be after the result is known.** The close time is when the market
  was finally resolved, which can be a day or more after the event. The 1-day Polymarket
  results are the most exposed to this.
- **Kalshi drops illiquid markets at each horizon.** About 40% of eligible Kalshi markets had
  no usable price at 7 days, and about a third of the 7-day prices that were used are quote
  midpoints, not trades (26.5% across all horizons).
- **Kalshi 1-day results rest on a random 25,000 of the 56,693 eligible markets**, not all of
  them (14,113 markets in the slope sample).
- **Kalshi coverage is not even across months**, as the brief asked. Early 2025 has few
  long-lived events to sample.
- **Polymarket markets whose scheduled end date was before 2024** but which closed later are
  missing.
- **Many comparisons were made.** Outside the primary test, some intervals will exclude 1 or 0
  by chance. The volume pattern is trustworthy because it repeats across both platforms and
  several horizons, not because any single interval excludes 1.
- **Volume is measured after the fact**, so the volume pattern should not be read as "low
  liquidity causes bias".

## 9. Comparison with version 1 and with the published papers

**Version 1** found Polymarket 0.94 (0.82 to 1.08, n=1,353) and Kalshi 1.00 (0.89 to 1.12,
n=1,286), using only high-volume markets in the last week before close.

- Version 2's overall 7-day slopes (1.00 and 1.03) agree with version 1's conclusion of no
  overall bias, with intervals about four times narrower on Polymarket and about two and a
  half times narrower on Kalshi.
- The like-for-like comparison is version 2's high-volume tercile: 0.88 (0.84 to 0.93) on
  Polymarket and 0.89 (0.82 to 0.96) on Kalshi. Version 1's Polymarket estimate of 0.94 was
  pointing the same way but was too imprecise to show it.
- What version 1 could not see, because it only looked at high-volume markets, is that the
  bias is present in small markets.

**Published papers.** I found these by web search and read summaries and abstracts only, not
the full papers, so treat this comparison as provisional.

- *Bürgi, Deng and Whelan, "Makers and Takers: The Economics of the Kalshi Prediction Market"*
  (versions from July 2025 to February 2026) report a strong favourite-longshot pattern in
  Kalshi returns, with low-priced contracts losing heavily, and say the bias appears to be
  shrinking over time. This study agrees on the first point: Kalshi contracts costing 15p or
  less lost 35.0% before fees. It does not find the shrinkage: the Kalshi 7-day slope did not
  fall, and the cheap-contract loss was similar before and after. Their figures are after fees
  and are based on every traded contract, which gives far more weight to heavily traded
  markets than this study does, so the numbers are not directly comparable.
- *Le, "Decomposing Crowd Wisdom"* (arXiv 2602.19520, February 2026) reports that calibration
  varies by subject and by time to resolution on both platforms. This study also finds
  differences by category and horizon, though with wide intervals, and adds that volume
  matters at least as much.

Reconciling "slope near 1" with "cheap contracts lose heavily" is mostly a matter of where you
look: the losses are concentrated at the very cheap end and in thin markets, and a slope fitted
between 3% and 97% across all markets is not sensitive to either.

## 10. Checks

- **Three headline numbers recomputed by a second route.** `verify.py` shares no code with the
  analysis: it re-reads the raw files with its own parser, fits the regression with a different
  algorithm, and runs a separate 500-resample bootstrap. All match:

  | Number | Analysis | Second route |
  |---|---|---|
  | Polymarket 7-day slope | 0.9970 (0.966 to 1.028), n=27,255 | 0.9970 (0.965 to 1.028), n=27,255 |
  | Kalshi 7-day slope | 1.0330 (0.991 to 1.078), n=10,967 | 1.0330 (0.990 to 1.078), n=10,967 |
  | Polymarket change at 7 days | 0.1050 (0.034 to 0.179) | 0.1050 (0.036 to 0.185) |
  | Kalshi change at 7 days | 0.0680 (-0.017 to 0.159) | 0.0680 (-0.025 to 0.151) |

  Point estimates agree to four decimal places. Intervals differ slightly because the second
  route uses 500 resamples and a different random stream.
- **No market appears twice** (0 duplicate markets, 0 duplicate market-horizon rows, both
  platforms).
- **No price is from after the market closed** (0 prices dated after their horizon, 0 after
  close, 0 more than 12 hours before the horizon, both platforms).
- **Batch against single requests.** 240 Polymarket prices fetched both ways matched exactly.
- **Surprising result investigated.** The Polymarket rise was checked for a bug: the second
  route reproduces it, the period labels and sample sizes are as intended, and it survives the
  price-filter and 50%-price checks. The explanation found was the change in mix (section 5).

**What I did not verify:**

- That the Polymarket price feed returns trades or quotes; the API does not say, and I did not
  compare it against trade-level data.
- That Polymarket's `closedTime` or Kalshi's `close_time` is the true end of trading in every
  case, or that outcomes recorded by the exchanges are correct.
- That the Kalshi events list is truly complete. It ended normally at 1,022,133 events and
  reaches back before 2025, but there is no independent count to compare with.
- The Kalshi batch-candle route was compared with single requests on only a handful of markets
  (they agreed).
- The details of the published papers beyond abstracts and summaries.
- Whether results hold when weighted by money traded.
- A colour-blindness check on the charts was not run.
- A full rerun from scratch was not done; `analyse.py` and `verify.py` were run end to end on
  the saved data, and the download scripts were run in stages with restarts.
