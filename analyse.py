"""Calibration analysis of resolved Polymarket and Kalshi markets (version 2).

Run after the two download scripts:

    python analyse.py

Reads data/, writes results/tables.md (every table), results/csv/*.csv,
results/results.json (headline numbers) and results/*.png (charts).

Everything marked FIXED below was set in the brief before any data were seen.

Method in one paragraph.  For each market and each horizon (1, 7, 30, 90 days
before close) we have a reference price p for the "yes" side (Polymarket: the
first listed outcome) and the outcome y (1 if that side won).  The calibration
slope is the coefficient b in the logistic regression
        logit P(y = 1) = a + b * logit(p).
If prices are perfectly calibrated, a = 0 and b = 1.  b > 1 means favourites
win more often than their price says and longshots less often: the
favourite-longshot bias.  Uncertainty comes from a bootstrap that resamples
whole events (all markets in an event move together), 2,000 times.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import download_kalshi as dk
import download_polymarket as dp
from apiutil import parse_time, read_jsonl

# ----------------------------- FIXED settings -----------------------------
HORIZONS = (1, 7, 30, 90)
PMIN, PMAX = 0.03, 0.97               # slope sample
N_BOOT = 2000
BEFORE_END = parse_time("2026-02-01T00:00:00Z")    # "before": closed before this
AFTER_START = parse_time("2026-03-01T00:00:00Z")   # "after": closed on or after this
PRIMARY_H = 7
# ----------------------------- other settings -----------------------------
SEED = 20261111
ALT_SPLIT = parse_time("2025-09-01T00:00:00Z")     # robustness split date
KALSHI_MAX_SPREAD = 0.10              # quote fallback only if ask - bid <= 10c
N_SIM = 1000                          # simulations for the power calculation
Z_ALPHA, Z_POWER = 1.959964, 0.841621  # two-sided 5 % test, 80 % power
RESULTS = os.environ.get("RESULTS_DIR", "results")   # override only for test runs
BANDS = [(0.0, 0.03), (0.03, 0.10), (0.10, 0.20), (0.20, 0.30), (0.30, 0.40), (0.40, 0.50),
         (0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 0.97), (0.97, 1.0)]
N_BOOT_RUN = int(os.environ.get("N_BOOT", N_BOOT))  # override only for quick test runs

TABLES = []          # (title, note, DataFrame) in report order
HEADLINE = {}        # numbers saved to results.json


# ==========================================================================
# Loading
# ==========================================================================
def half_year(ts):
    t = pd.to_datetime(ts, unit="s", utc=True)
    return f"{t.year}H{1 if t.month <= 6 else 2}"


def load_polymarket():
    """Long table: one row per (market, horizon) with a price.  Also returns the market table."""
    with open(dp.SAMPLE_FILE, "r", encoding="utf-8") as f:
        sample = {x.strip() for x in f if x.strip()}
    prices = {}
    for r in read_jsonl(dp.PRICES_FILE):
        if not r.get("err"):
            prices[(r["id"], r["h"], r["anchor"])] = r
    markets, rows, alt_rows = [], [], []
    listed = 0
    for rec in dp.load_markets():
        listed += 1
        if rec["id"] not in sample:
            continue
        cb = dp.clean_binary(rec)
        if cb is None:
            continue
        _, y, open_ts, close_ts = cb
        outcomes = json.loads(rec["outcomes"])
        base = dict(platform="Polymarket", id=rec["id"],
                    cluster="pm-" + str(rec.get("event_id") or "m" + rec["id"]),
                    open_ts=open_ts, close_ts=close_ts, volume=float(rec.get("volumeNum") or 0),
                    group="Yes/No" if [o.strip().lower() for o in outcomes] == ["yes", "no"] else "Named outcomes",
                    y=y)
        markets.append(base)
        end_ts = parse_time(rec.get("endDate"))
        for h in HORIZONS:
            r = prices.get((rec["id"], h, "closed"))
            if r and r.get("p") is not None:
                rows.append(dict(base, h=h, p=float(r["p"]), pt=r["t"], T=r["T"], src="history"))
            # secondary sensitivity: horizon counted from min(endDate, closedTime)
            if h in (1, 7):
                if end_ts is not None and end_ts < close_ts - 3600:
                    r2 = prices.get((rec["id"], h, "end"))
                    if end_ts - open_ts < h * 86400:
                        r2 = None
                else:
                    r2 = r
                if r2 and r2.get("p") is not None:
                    alt_rows.append(dict(base, h=h, p=float(r2["p"]), pt=r2["t"], T=r2["T"], src="history"))
    return pd.DataFrame(markets), pd.DataFrame(rows), pd.DataFrame(alt_rows), listed


def kalshi_category(cat):
    if cat == "Sports":
        return "Sports"
    if cat in ("Politics", "Elections", "World"):
        return "Politics and world"
    if cat in ("Economics", "Financials", "Companies", "Commodities"):
        return "Economics and finance"
    if cat == "Crypto":
        return "Crypto"
    if cat == "Climate and Weather":
        return "Weather"
    return "Culture and other"


def load_kalshi():
    with open(dk.SERIES_FILE, "r", encoding="utf-8") as f:
        cat = {s["ticker"]: s.get("category") for s in json.load(f)["series"]}
    candles = {}
    for r in read_jsonl(dk.CANDLES_FILE):
        if not r.get("err"):
            candles[(r["ticker"], r["h"])] = r
    markets, rows, seen = [], [], set()
    fetched = 0
    for m in read_jsonl(dk.MARKETS_FILE):
        if m["ticker"] in seen:
            continue
        seen.add(m["ticker"])
        fetched += 1
        oc = dk.usable_market(m)
        if oc is None:
            continue
        open_ts, close_ts = oc
        base = dict(platform="Kalshi", id=m["ticker"], cluster="k-" + m["event_ticker"],
                    open_ts=open_ts, close_ts=close_ts, volume=float(m["volume_fp"]),
                    group=kalshi_category(cat.get(m["event_ticker"].split("-")[0])),
                    y=1 if m["result"] == "yes" else 0)
        markets.append(base)
        for h in HORIZONS:
            r = candles.get((m["ticker"], h))
            if not r:
                continue
            if r.get("trade_p") is not None:                       # last trade within 12 h
                p, pt, src = r["trade_p"], r["trade_t"], "trade"
            elif (r.get("bid") is not None and r.get("ask") is not None and r["bid"] > 0
                  and r["ask"] < 1 and r["ask"] - r["bid"] <= KALSHI_MAX_SPREAD + 1e-9):
                p, pt, src = (r["bid"] + r["ask"]) / 2, r["quote_t"], "quote"   # two-sided quote midpoint
            else:
                continue
            rows.append(dict(base, h=h, p=float(p), pt=pt, T=r["T"], src=src))
    return pd.DataFrame(markets), pd.DataFrame(rows), fetched


# ==========================================================================
# Statistics
# ==========================================================================
def logit(p):
    return np.log(p / (1 - p))


def newton(x, Y, W=None, iters=15):
    """Fit logit P(y=1) = a + s*x by Newton's method for a whole batch at once.

    x : (n,) predictor.  Y : (n,) or (b, n) outcomes.  W : (b, n) row weights or None.
    Returns (a, s), each of shape (b,).  Batches that cannot be fitted give NaN.
    """
    Y = np.atleast_2d(Y)
    b = W.shape[0] if W is not None else Y.shape[0]
    a, s = np.zeros(b), np.ones(b)
    bad = np.zeros(b, dtype=bool)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        for _ in range(iters):
            mu = 1.0 / (1.0 + np.exp(-(a[:, None] + s[:, None] * x)))
            r, v = Y - mu, mu * (1 - mu)
            if W is not None:
                r, v = W * r, W * v
            g0, g1 = r.sum(1), (r * x).sum(1)
            h00, h01, h11 = v.sum(1), (v * x).sum(1), (v * x * x).sum(1)
            det = h00 * h11 - h01 ** 2
            bad |= ~(det > 1e-9)
            det = np.where(det > 1e-9, det, 1.0)
            a += np.clip((h11 * g0 - h01 * g1) / det, -3, 3)
            s += np.clip((h00 * g1 - h01 * g0) / det, -3, 3)
    a[bad], s[bad] = np.nan, np.nan
    return a, s


def boot_slopes(d, masks, n_boot=None, seed=SEED):
    """Cluster bootstrap of the calibration slope for several subsets at once.

    d     : slope-sample rows (columns p, y, cluster)
    masks : dict name -> boolean array over the rows of d
    Every resample draws whole events with replacement from ALL events in d, then
    refits the slope inside each subset, so differences between subsets can be
    taken resample by resample.
    Returns (point, draws): point[name] = (intercept, slope, n, n_events);
    draws[name] = array of n_boot bootstrap slopes.
    """
    n_boot = n_boot or N_BOOT_RUN
    if len(d) == 0:                              # nothing collected for this cell
        return ({k: (np.nan, np.nan, 0, 0) for k in masks},
                {k: np.full(n_boot, np.nan) for k in masks})
    x, y = logit(d["p"].to_numpy()), d["y"].to_numpy(dtype=float)
    codes, uniq = pd.factorize(d["cluster"])
    nc = len(uniq)
    idx = {k: np.flatnonzero(m) for k, m in masks.items()}
    point = {}
    for k, ix in idx.items():
        if len(ix) < 20 or y[ix].min() == y[ix].max():
            point[k] = (np.nan, np.nan, len(ix), len(set(codes[ix])))
            continue
        a, s = newton(x[ix], y[ix])
        point[k] = (a[0], s[0], len(ix), len(set(codes[ix])))
    draws = {k: np.full(n_boot, np.nan) for k in masks}
    rng = np.random.default_rng(seed)
    batch = int(max(1, min(n_boot, 3e6 // max(len(d), 1))))
    done = 0
    while done < n_boot:
        b = min(batch, n_boot - done)
        counts = rng.multinomial(nc, np.full(nc, 1.0 / nc), size=b)     # times each event is drawn
        for k, ix in idx.items():
            if np.isnan(point[k][1]):
                continue
            W = counts[:, codes[ix]].astype(float)
            draws[k][done:done + b] = newton(x[ix], y[ix], W)[1]
        done += b
    return point, draws


def ci(draws):
    return tuple(np.nanpercentile(draws, [2.5, 97.5]))


def boot_mean(values, cluster, masks, seed=SEED):
    """Cluster-bootstrap interval for a mean of `values` inside each mask."""
    codes, uniq = pd.factorize(cluster)
    nc = len(uniq)
    if nc == 0:                                  # nothing collected for this cell
        return {k: (np.nan, np.nan, np.nan, 0, 0) for k in masks}
    rng = np.random.default_rng(seed)
    out = {}
    idx = {k: np.flatnonzero(m) for k, m in masks.items()}
    draws = {k: [] for k in masks}
    batch = int(max(1, min(N_BOOT_RUN, 3e6 // max(len(values), 1))))
    done = 0
    while done < N_BOOT_RUN:
        b = min(batch, N_BOOT_RUN - done)
        counts = rng.multinomial(nc, np.full(nc, 1.0 / nc), size=b)
        for k, ix in idx.items():
            if len(ix) == 0:
                continue
            W = counts[:, codes[ix]].astype(float)
            with np.errstate(invalid="ignore", divide="ignore"):
                draws[k].append((W * values[ix]).sum(1) / W.sum(1))
        done += b
    for k, ix in idx.items():
        if len(ix) == 0:
            out[k] = (np.nan, np.nan, np.nan, 0, 0)
            continue
        dr = np.concatenate(draws[k])
        lo, hi = np.nanpercentile(dr, [2.5, 97.5])
        out[k] = (values[ix].mean(), lo, hi, len(ix), len(set(codes[ix])))
    return out


# ==========================================================================
# Formatting helpers
# ==========================================================================
def f_est(est, lo, hi, d=2):
    if est is None or np.isnan(est):
        return "n/a"
    return f"{est:.{d}f} ({lo:.{d}f} to {hi:.{d}f})"


def f_pct(est, lo, hi):
    if est is None or np.isnan(est):
        return "n/a"
    return f"{100 * est:+.1f}% ({100 * lo:+.1f}% to {100 * hi:+.1f}%)"


def add_table(title, df, note=""):
    TABLES.append((title, note, df))
    os.makedirs(os.path.join(RESULTS, "csv"), exist_ok=True)
    name = "".join(c if c.isalnum() else "_" for c in title.lower())[:60]
    df.to_csv(os.path.join(RESULTS, "csv", name + ".csv"), index=False)
    print(f"\n## {title}\n{df.to_string(index=False)}", flush=True)


def md_table(df):
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def slope_sample(long, platform, h, pmin=PMIN, pmax=PMAX):
    d = long[(long.platform == platform) & (long.h == h) & (long.p >= pmin) & (long.p <= pmax)]
    return d.reset_index(drop=True)


def period_masks(d, split=None):
    """before / after masks.  Default: the FIXED split with February 2026 dropped."""
    c = d["close_ts"].to_numpy()
    if split is None:
        return {"before": c < BEFORE_END, "after": c >= AFTER_START}
    return {"before": c < split, "after": c >= split}


_period_cache = {}


def period_test(long, platform, h, pmin=PMIN, pmax=PMAX, split=None, tag="main"):
    """Slopes before and after, and the change (after minus before), with intervals.

    `tag` names the data set passed in, so that results for different subsets are
    cached separately.
    """
    key = (tag, platform, h, pmin, pmax, split)
    if key not in _period_cache:
        d = slope_sample(long, platform, h, pmin, pmax)
        point, draws = boot_slopes(d, period_masks(d, split))
        diff = draws["after"] - draws["before"]
        _period_cache[key] = dict(
            before=point["before"], after=point["after"],
            before_ci=ci(draws["before"]), after_ci=ci(draws["after"]),
            diff=point["after"][1] - point["before"][1], diff_ci=ci(diff), diff_se=np.nanstd(diff, ddof=1),
            p_boot=2 * min(np.nanmean(diff <= 0), np.nanmean(diff >= 0)), d=d)
    return _period_cache[key]


# ==========================================================================
# Sections
# ==========================================================================
def coverage(markets, long, extra):
    rows = []
    for platform in ("Polymarket", "Kalshi"):
        m = markets[markets.platform == platform].copy()
        m["half"] = m.close_ts.map(half_year)
        l = long[long.platform == platform].copy()
        l["half"] = l.close_ts.map(half_year)
        for half in sorted(m.half.unique()) + ["All"]:
            mm = m if half == "All" else m[m.half == half]
            ll = l if half == "All" else l[l.half == half]
            row = {"Platform": platform, "Half-year closed": half, "Markets collected": len(mm),
                   "Events": mm.cluster.nunique()}
            for h in HORIZONS:
                lh = ll[ll.h == h]
                row[f"Open {h}d+"] = int((mm.close_ts - mm.open_ts >= h * 86400).sum())
                row[f"Priced {h}d"] = len(lh)
                row[f"In 3-97% {h}d"] = int(((lh.p >= PMIN) & (lh.p <= PMAX)).sum())
            rows.append(row)
    add_table("Coverage", pd.DataFrame(rows),
              "Markets collected = clean binary markets above the volume floor whose prices were requested. "
              "Open Nd+ = had been open at least N days. Priced = a reference price was found within 12 hours "
              "before the horizon. In 3-97% = the slope sample. " + extra)
    rows = []
    for platform in ("Polymarket", "Kalshi"):
        for h in HORIZONS:
            d = slope_sample(long, platform, h)
            pm = period_masks(d)
            rows.append({"Platform": platform, "Horizon (days)": h,
                         "Before: markets": int(pm["before"].sum()),
                         "Before: events": d.cluster[pm["before"]].nunique(),
                         "Feb 2026 (dropped)": int((~pm["before"] & ~pm["after"]).sum()),
                         "After: markets": int(pm["after"].sum()),
                         "After: events": d.cluster[pm["after"]].nunique()})
    add_table("Slope sample by period", pd.DataFrame(rows),
              "Before = closed before 1 Feb 2026; after = closed on or after 1 Mar 2026.")


def power(long):
    """Smallest detectable change in slope with 80 % power, two-sided 5 % test.

    Two standard errors of the change are computed for the sample actually collected:
      (a) simulation, blind to outcomes: keep every market's price, draw outcomes as
          if prices were perfectly calibrated (independently), refit both slopes;
      (b) the event bootstrap of the real data, which also captures the fact that
          markets in the same event are not independent.
    Minimum detectable change = (1.96 + 0.84) x standard error.
    """
    rows = []
    rng = np.random.default_rng(SEED + 1)
    for platform in ("Polymarket", "Kalshi"):
        for h in HORIZONS:
            d = slope_sample(long, platform, h)
            pm = period_masks(d)
            nb, na = int(pm["before"].sum()), int(pm["after"].sum())
            if nb < 50 or na < 50:
                rows.append({"Platform": platform, "Horizon (days)": h, "n before": nb, "n after": na})
                continue
            x, p = logit(d.p.to_numpy()), d.p.to_numpy()
            sims = {}
            for k in ("before", "after"):
                xs, ps = x[pm[k]], p[pm[k]]
                out = []
                batch = int(max(1, 3e6 // len(xs)))
                for i in range(0, N_SIM, batch):
                    b = min(batch, N_SIM - i)
                    Y = (rng.random((b, len(xs))) < ps).astype(float)
                    out.append(newton(xs, Y)[1])
                sims[k] = np.concatenate(out)
            se_sim = np.nanstd(sims["after"] - sims["before"], ddof=1)
            se_boot = period_test(long, platform, h)["diff_se"]
            mde_sim, mde_boot = (Z_ALPHA + Z_POWER) * se_sim, (Z_ALPHA + Z_POWER) * se_boot
            # check the formula: simulate an after-period whose true slope is 1 + mde_sim
            xs = x[pm["after"]]
            pa = 1 / (1 + np.exp(-(1 + mde_sim) * xs))
            out = []
            batch = int(max(1, 3e6 // len(xs)))
            for i in range(0, N_SIM, batch):
                b = min(batch, N_SIM - i)
                out.append(newton(xs, (rng.random((b, len(xs))) < pa).astype(float))[1])
            alt = np.concatenate(out) - sims["before"]
            achieved = np.nanmean(np.abs(alt) / se_sim > Z_ALPHA)
            rows.append({"Platform": platform, "Horizon (days)": h, "n before": nb, "n after": na,
                         "SE of change, simulated (independent markets)": round(se_sim, 3),
                         "SE of change, event bootstrap": round(se_boot, 3),
                         "Design effect": round((se_boot / se_sim) ** 2, 2),
                         "Smallest detectable change, simulated": round(mde_sim, 3),
                         "Smallest detectable change, event bootstrap": round(mde_boot, 3),
                         "Power achieved in check simulation": round(achieved, 2)})
            if h == PRIMARY_H:
                HEADLINE[f"power_{platform}"] = dict(se_sim=se_sim, se_boot=se_boot, mde_sim=mde_sim,
                                                    mde_boot=mde_boot, n_before=nb, n_after=na)
    add_table("Power", pd.DataFrame(rows),
              "Smallest change in slope (after minus before) detectable with 80% power in a two-sided 5% test. "
              "The event-bootstrap column is the one to use: it allows for markets in the same event moving together. "
              "The 7-day rows are the primary test; other horizons are secondary.")


def replication(long):
    rows = []
    for platform in ("Polymarket", "Kalshi"):
        for h in HORIZONS:
            d = slope_sample(long, platform, h)
            point, draws = boot_slopes(d, {"all": np.ones(len(d), dtype=bool)})
            a, s, n, ne = point["all"]
            lo, hi = ci(draws["all"])
            rows.append({"Platform": platform, "Horizon (days)": h, "Slope (95% interval)": f_est(s, lo, hi),
                         "Intercept": round(a, 3), "Markets": n, "Events": ne})
            HEADLINE[f"slope_{platform}_{h}d"] = dict(slope=s, lo=lo, hi=hi, intercept=a, n=n, events=ne)
    add_table("Replication: calibration slope", pd.DataFrame(rows),
              "Slope above 1 = favourite-longshot bias; below 1 = the reverse. Prices 3% to 97%.")


def reliability(long):
    rows = []
    for platform in ("Polymarket", "Kalshi"):
        fig, axes = plt.subplots(2, 2, figsize=(9, 9), sharex=True, sharey=True)
        for ax, h in zip(axes.ravel(), HORIZONS):
            d = long[(long.platform == platform) & (long.h == h)].reset_index(drop=True)
            p = d.p.to_numpy()
            masks = {}
            for i, (lo, hi) in enumerate(BANDS):
                # bands are [lo, hi) except that 97% belongs to 90-97% and 100% to the top band
                if hi == 0.97:
                    masks[i] = (p >= lo) & (p <= hi)
                elif lo == 0.97:
                    masks[i] = p > lo
                else:
                    masks[i] = (p >= lo) & (p < hi)
            res = boot_mean(d.y.to_numpy(dtype=float), d.cluster, masks)
            xs, ys, los, his = [], [], [], []
            for i, (lo, hi) in enumerate(BANDS):
                win, wl, wh, n, ne = res[i]
                mp = p[masks[i]].mean() if n else np.nan
                rows.append({"Platform": platform, "Horizon (days)": h,
                             "Price band": f"{100 * lo:.0f}-{100 * hi:.0f}%", "Markets": n, "Events": ne,
                             "Mean price": "n/a" if not n else f"{100 * mp:.1f}%",
                             "Won (95% interval)": "n/a" if not n else
                             f"{100 * win:.1f}% ({100 * wl:.1f}% to {100 * wh:.1f}%)"})
                if n >= 20:
                    xs.append(mp); ys.append(win); los.append(win - wl); his.append(wh - win)
            ax.plot([0, 1], [0, 1], color="#9a9a9a", lw=1, ls="--", zorder=1)
            ax.errorbar(xs, ys, yerr=[los, his], fmt="o-", color="#2563a8", ms=5, lw=1.5,
                        elinewidth=1, capsize=2, zorder=2)
            ax.set_title(f"{h} day{'s' if h > 1 else ''} before close (n = {len(d):,})", fontsize=10)
            ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            ax.grid(color="#e6e6e6", lw=0.6)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
        for ax in axes[1]:
            ax.set_xlabel("Mean price in band")
        for ax in axes[:, 0]:
            ax.set_ylabel("Share that won")
        fig.suptitle(f"{platform}: price against actual win rate\n"
                     "Dashed line = perfect calibration; bars = 95% event-bootstrap intervals", fontsize=11)
        fig.tight_layout()
        fig.savefig(os.path.join(RESULTS, f"reliability_{platform.lower()}.png"), dpi=150)
        plt.close(fig)
    add_table("Reliability", pd.DataFrame(rows),
              "All priced markets, including those outside the 3-97% slope sample. "
              "If prices are calibrated, 'Won' should be close to 'Mean price'.")


def period_rows(long, combos, **kw):
    rows = []
    for platform, h in combos:
        r = period_test(long, platform, h, **kw)
        rows.append({"Platform": platform, "Horizon (days)": h,
                     "Slope before": f_est(r["before"][1], *r["before_ci"]), "n before": r["before"][2],
                     "Slope after": f_est(r["after"][1], *r["after_ci"]), "n after": r["after"][2],
                     "Change (after - before)": f_est(r["diff"], *r["diff_ci"]),
                     "Bootstrap p": round(r["p_boot"], 3)})
    return rows


def primary(long):
    add_table("PRIMARY TEST: change in slope at 7 days",
              pd.DataFrame(period_rows(long, [("Polymarket", 7), ("Kalshi", 7)])),
              "Before = closed before 1 Feb 2026; after = closed on or after 1 Mar 2026; February 2026 dropped. "
              "A negative change means less favourite-longshot bias after the papers. "
              "Bootstrap p = twice the smaller share of bootstrap changes on one side of zero.")
    for platform in ("Polymarket", "Kalshi"):
        r = period_test(long, platform, 7)
        HEADLINE[f"primary_{platform}"] = dict(
            before=r["before"][1], before_ci=r["before_ci"], n_before=r["before"][2], ev_before=r["before"][3],
            after=r["after"][1], after_ci=r["after_ci"], n_after=r["after"][2], ev_after=r["after"][3],
            diff=r["diff"], diff_ci=r["diff_ci"], p=r["p_boot"])


def secondary(long):
    add_table("Secondary: change in slope at 1, 30 and 90 days",
              pd.DataFrame(period_rows(long, [(p, h) for p in ("Polymarket", "Kalshi") for h in (1, 30, 90)])),
              "Secondary, not the primary test.")

    # ---- slope by half-year (table + chart)
    rows = []
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.5), sharey=True)
    colours = {"Polymarket": "#2563a8", "Kalshi": "#d9730d"}
    markers = {"Polymarket": "o", "Kalshi": "s"}
    for ax, h in zip(axes.ravel(), HORIZONS):
        halves_all = sorted({half_year(t) for t in long.close_ts.unique()})
        pos = {hy: i for i, hy in enumerate(halves_all)}
        for j, platform in enumerate(("Polymarket", "Kalshi")):
            d = slope_sample(long, platform, h)
            if d.empty:
                continue
            hy = d.close_ts.map(half_year).to_numpy()
            point, draws = boot_slopes(d, {k: hy == k for k in sorted(set(hy))})
            xs, ys, los, his = [], [], [], []
            for k in sorted(point):
                a, s, n, ne = point[k]
                lo, hi = ci(draws[k]) if not np.isnan(s) else (np.nan, np.nan)
                rows.append({"Platform": platform, "Horizon (days)": h, "Half-year closed": k,
                             "Slope (95% interval)": f_est(s, lo, hi), "Markets": n, "Events": ne})
                if not np.isnan(s) and n >= 100:
                    xs.append(pos[k] + (j - 0.5) * 0.16); ys.append(s); los.append(s - lo); his.append(hi - s)
            ax.errorbar(xs, ys, yerr=[los, his], fmt=markers[platform] + "-", color=colours[platform], ms=5,
                        lw=1.5, elinewidth=1, capsize=2, label=platform)
        ax.axhline(1, color="#9a9a9a", lw=1, ls="--")
        ax.set_xticks(range(len(halves_all)))
        ax.set_xticklabels(halves_all, fontsize=8)
        ax.set_title(f"{h} day{'s' if h > 1 else ''} before close", fontsize=10)
        ax.set_ylim(0.4, 1.8)
        ax.grid(color="#e6e6e6", lw=0.6)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    for ax in axes[:, 0]:
        ax.set_ylabel("Calibration slope")
    axes[0, 0].legend(frameon=False, fontsize=9)
    fig.suptitle("Calibration slope by half-year of market close\n"
                 "Above 1 = favourite-longshot bias; dashed line = perfect calibration; "
                 "bars = 95% intervals; half-years with under 100 markets not drawn", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "slope_by_halfyear.png"), dpi=150)
    plt.close(fig)
    add_table("Secondary: slope by half-year", pd.DataFrame(rows), "Secondary.")

    # ---- volume terciles
    rows = []
    for platform in ("Polymarket", "Kalshi"):
        for h in HORIZONS:
            d = slope_sample(long, platform, h)
            if len(d) < 300:
                continue
            q1, q2 = d.volume.quantile([1 / 3, 2 / 3])
            v = d.volume.to_numpy()
            masks = {f"Low (up to {q1:,.0f})": v <= q1,
                     f"Middle ({q1:,.0f} to {q2:,.0f})": (v > q1) & (v <= q2),
                     f"High (over {q2:,.0f})": v > q2}
            point, draws = boot_slopes(d, masks)
            for k in masks:
                a, s, n, ne = point[k]
                rows.append({"Platform": platform, "Horizon (days)": h, "Volume tercile": k,
                             "Slope (95% interval)": f_est(s, *ci(draws[k])), "Markets": n, "Events": ne})
    add_table("Secondary: slope by volume tercile", pd.DataFrame(rows),
              "Secondary. Volume is in dollars on Polymarket and contracts on Kalshi; terciles are "
              "computed within each platform and horizon.")

    # ---- market type / category
    rows = []
    for platform in ("Polymarket", "Kalshi"):
        for h in HORIZONS:
            d = slope_sample(long, platform, h)
            g = d.group.to_numpy()
            point, draws = boot_slopes(d, {k: g == k for k in sorted(set(g))})
            for k in sorted(point):
                a, s, n, ne = point[k]
                rows.append({"Platform": platform, "Horizon (days)": h, "Group": k,
                             "Slope (95% interval)": f_est(s, *ci(draws[k])) if not np.isnan(s) else "n/a (too few)",
                             "Markets": n, "Events": ne})
    add_table("Secondary: slope by market type", pd.DataFrame(rows),
              "Secondary. Polymarket: Yes/No questions against markets with named outcomes (teams, Up/Down, "
              "Over/Under). Kalshi: broad category of the series.")


def returns(long):
    """Return per pound staked, before fees, holding to resolution.

    Every market offers two contracts: YES costing p and NO costing 1 - p.  Both are
    included, each classified by its own cost.  Return = (payout - cost) / cost, averaged
    with an equal stake on every contract.  Contracts costing under 1p or over 99p are
    left out (a return on a cost of zero is undefined).
    """
    rows = []
    for platform in ("Polymarket", "Kalshi"):
        for h in HORIZONS:
            d = long[(long.platform == platform) & (long.h == h) & (long.p >= 0.01) & (long.p <= 0.99)]
            both = pd.concat([
                pd.DataFrame({"cost": d.p, "pay": d.y, "cluster": d.cluster, "close_ts": d.close_ts}),
                pd.DataFrame({"cost": 1 - d.p, "pay": 1 - d.y, "cluster": d.cluster, "close_ts": d.close_ts}),
            ], ignore_index=True)
            ret = ((both.pay - both.cost) / both.cost).to_numpy()
            cost, c = both.cost.to_numpy(), both.close_ts.to_numpy()
            bands = {"15p or less": cost <= 0.15, "15p to 85p": (cost > 0.15) & (cost < 0.85),
                     "85p or more": cost >= 0.85}
            periods = {"All": np.ones(len(both), dtype=bool), "Before": c < BEFORE_END, "After": c >= AFTER_START}
            masks = {(bk, pk): bm & pmk for bk, bm in bands.items() for pk, pmk in periods.items()}
            res = boot_mean(ret, both.cluster, masks)
            for (bk, pk), (m, lo, hi, n, ne) in res.items():
                rows.append({"Platform": platform, "Horizon (days)": h, "Contract cost": bk, "Period": pk,
                             "Mean return (95% interval)": f_pct(m, lo, hi), "Contracts": n, "Events": ne})
                if h == PRIMARY_H:
                    HEADLINE[f"return_{platform}_{bk}_{pk}"] = dict(mean=m, lo=lo, hi=hi, n=n, events=ne)
    add_table("Returns before fees", pd.DataFrame(rows),
              "Mean return per pound staked, equal stake on each contract, bought at the reference price and "
              "held to resolution. Fees, bid-ask spreads and the size actually tradable at that price are IGNORED, "
              "so these are not achievable trading returns. Both the YES and the NO contract of each market are "
              "included, classified by their own cost; costs under 1p or over 99p are excluded.")


def robustness(long, alt_long):
    rows = period_rows(long, [("Polymarket", 7), ("Kalshi", 7)], pmin=0.05, pmax=0.95)
    for r in rows:
        r["Variant"] = "Prices 5% to 95%"
    rows2 = period_rows(long, [("Polymarket", 7), ("Kalshi", 7)], split=ALT_SPLIT)
    for r in rows2:
        r["Variant"] = "Split at 1 Sep 2025 (no gap)"
    rows3 = period_rows(alt_long, [("Polymarket", 7), ("Polymarket", 1)], tag="alt") if len(alt_long) else []
    for r in rows3:
        r["Variant"] = "Polymarket: horizon counted from the earlier of scheduled end and close"
    # Polymarket shows a spike of prices at exactly 0.50: markets that have only just
    # opened and have no real quotes yet.  Drop them and repeat.
    rows4 = period_rows(long[long.p != 0.5], [("Polymarket", 7)], tag="no50")
    for r in rows4:
        r["Variant"] = "Polymarket: prices of exactly 50% removed (placeholder quotes)"
    # Kalshi: use only prices that come from an actual trade in the 12-hour window.
    rows5 = period_rows(long[long.src != "quote"], [("Kalshi", 7)], tag="trade")
    for r in rows5:
        r["Variant"] = "Kalshi: traded prices only (no quote midpoints)"
    df = pd.DataFrame(rows + rows2 + rows3 + rows4 + rows5)
    df = df[["Variant"] + [c for c in df.columns if c != "Variant"]]
    add_table("Robustness of the primary test", df,
              "The first two variants were specified in the brief. The others are extra sensitivity checks added "
              "in this study (see DECISIONS.md).")
    rows = []
    for name, sub, platform in (("Polymarket: prices of exactly 50% removed", long[long.p != 0.5], "Polymarket"),
                                ("Kalshi: traded prices only", long[long.src != "quote"], "Kalshi")):
        d = slope_sample(sub, platform, 7)
        point, draws = boot_slopes(d, {"all": np.ones(len(d), dtype=bool)})
        a, s, n, ne = point["all"]
        rows.append({"Variant": name, "Horizon (days)": 7, "Slope (95% interval)": f_est(s, *ci(draws["all"])),
                     "Markets": n, "Events": ne})
    add_table("Sensitivity: overall 7-day slope under the extra filters", pd.DataFrame(rows), "Secondary.")
    if len(alt_long):
        rows = []
        for h in (1, 7):
            d = slope_sample(alt_long, "Polymarket", h)
            point, draws = boot_slopes(d, {"all": np.ones(len(d), dtype=bool)})
            a, s, n, ne = point["all"]
            rows.append({"Platform": "Polymarket", "Horizon (days)": h,
                         "Slope (95% interval)": f_est(s, *ci(draws["all"])), "Markets": n, "Events": ne})
            HEADLINE[f"altslope_Polymarket_{h}d"] = dict(slope=s, ci=ci(draws["all"]), n=n, events=ne)
        add_table("Sensitivity: Polymarket slope with the alternative anchor", pd.DataFrame(rows),
                  "Secondary. Horizon counted back from the earlier of the scheduled end date and the actual close.")


def composition(long):
    """EXPLORATORY (added after seeing the results, not pre-specified).

    The mix of markets changed a great deal between the two periods, and the slope
    differs strongly by volume and by market type.  So a change in the pooled slope
    could be a change in mix rather than a change in how well any given kind of market
    is priced.  This section shows the mix in each period and repeats the 7-day
    before/after comparison inside groups of similar markets.
    """
    rows, rows2 = [], []
    for platform in ("Polymarket", "Kalshi"):
        d = slope_sample(long, platform, PRIMARY_H)
        if d.empty:
            continue
        pm = period_masks(d)
        q1, q2 = d.volume.quantile([1 / 3, 2 / 3])
        vol = np.where(d.volume <= q1, "Volume: low", np.where(d.volume <= q2, "Volume: middle", "Volume: high"))
        for k in ("before", "after"):
            dd = d[pm[k]]
            row = {"Platform": platform, "Period": k, "Markets": len(dd),
                   "Median volume": f"{dd.volume.median():,.0f}",
                   "Low-volume share": f"{100 * (vol[pm[k]] == 'Volume: low').mean():.0f}%",
                   "High-volume share": f"{100 * (vol[pm[k]] == 'Volume: high').mean():.0f}%"}
            row["Mix by type"] = ", ".join(f"{g} {100 * share:.0f}%"
                                           for g, share in dd.group.value_counts(normalize=True).items())
            rows.append(row)
        subsets = [(f"Volume: low (up to {q1:,.0f})", vol == "Volume: low"),
                   (f"Volume: middle ({q1:,.0f} to {q2:,.0f})", vol == "Volume: middle"),
                   (f"Volume: high (over {q2:,.0f})", vol == "Volume: high")]
        subsets += [(f"Type: {g}", (d.group == g).to_numpy()) for g in sorted(d.group.unique())]
        for name, mask in subsets:
            sub = d[mask]
            r = period_test(sub, platform, PRIMARY_H, tag=f"comp-{platform}-{name}")
            rows2.append({"Platform": platform, "Group": name,
                          "Slope before": f_est(r["before"][1], *r["before_ci"]), "n before": r["before"][2],
                          "Slope after": f_est(r["after"][1], *r["after_ci"]), "n after": r["after"][2],
                          "Change (after - before)": f_est(r["diff"], *r["diff_ci"])})
    add_table("Exploratory: mix of markets in each period (7-day slope sample)", pd.DataFrame(rows),
              "Not pre-specified. Volume groups are terciles of the whole 7-day slope sample for that platform.")
    add_table("Exploratory: change in 7-day slope within groups of similar markets", pd.DataFrame(rows2),
              "Not pre-specified; added after seeing the primary result, to see whether it reflects a change in the "
              "mix of markets. Treat as a guide to interpretation, not as a test.")


def checks(markets, long, alt_long):
    lines = []
    for platform in ("Polymarket", "Kalshi"):
        m = markets[markets.platform == platform]
        l = long[long.platform == platform]
        lines.append({"Check": f"{platform}: duplicate markets", "Result": int(m.id.duplicated().sum())})
        lines.append({"Check": f"{platform}: duplicate (market, horizon) rows",
                      "Result": int(l.duplicated(["id", "h"]).sum())})
        lines.append({"Check": f"{platform}: prices dated after their horizon", "Result": int((l.pt > l["T"]).sum())})
        lines.append({"Check": f"{platform}: prices dated after market close",
                      "Result": int((l.pt > l.close_ts).sum())})
        lines.append({"Check": f"{platform}: prices more than 12h before horizon",
                      "Result": int((l.pt < l["T"] - 12 * 3600).sum())})
        lines.append({"Check": f"{platform}: horizon not equal to close minus h days",
                      "Result": int((l["T"] != l.close_ts - l.h * 86400).sum())})
        lines.append({"Check": f"{platform}: rows where market was open less than the horizon",
                      "Result": int((l.close_ts - l.open_ts < l.h * 86400).sum())})
        lines.append({"Check": f"{platform}: outcomes not 0/1", "Result": int((~l.y.isin([0, 1])).sum())})
    k = long[long.platform == "Kalshi"]
    lines.append({"Check": "Kalshi: share of prices from a quote midpoint rather than a trade",
                  "Result": f"{100 * (k.src == 'quote').mean():.1f}%"})
    add_table("Checks", pd.DataFrame(lines), "All counts should be 0.")
    return all(r["Result"] == 0 for r in lines if isinstance(r["Result"], int))


def main():
    os.makedirs(RESULTS, exist_ok=True)
    pm_m, pm_l, pm_alt, pm_listed = load_polymarket()
    k_m, k_l, k_fetched = load_kalshi()
    markets = pd.concat([pm_m, k_m], ignore_index=True)
    long = pd.concat([pm_l, k_l], ignore_index=True)
    # keep only markets that closed inside the study window
    lo_ts = {"Polymarket": parse_time("2024-01-01T00:00:00Z"), "Kalshi": parse_time("2025-01-01T00:00:00Z")}
    markets = markets[markets.close_ts >= markets.platform.map(lo_ts)].reset_index(drop=True)
    long = long[long.close_ts >= long.platform.map(lo_ts)].reset_index(drop=True)
    HEADLINE["counts"] = dict(pm_listed=pm_listed, pm_sampled=len(pm_m), kalshi_fetched=k_fetched,
                              kalshi_usable=len(k_m))
    extra = (f"Polymarket: {pm_listed:,} closed markets listed above the $1,000 floor, {len(pm_m):,} clean binary "
             f"markets in the price sample. Kalshi: {k_fetched:,} markets fetched from sampled events, "
             f"{len(k_m):,} binary, settled yes/no, with 1,000+ contracts.")
    coverage(markets, long, extra)
    power(long)                 # reported before the main analysis
    replication(long)
    reliability(long)
    primary(long)
    secondary(long)
    returns(long)
    robustness(long, pm_alt)
    composition(long)
    ok = checks(markets, long, pm_alt)

    with open(os.path.join(RESULTS, "tables.md"), "w", encoding="utf-8") as f:
        f.write("# All tables (generated by analyse.py)\n\nIntervals are 95% event-bootstrap intervals "
                f"({N_BOOT_RUN:,} resamples of whole events).\n")
        for title, note, df in TABLES:
            f.write(f"\n## {title}\n\n{note}\n\n{md_table(df)}\n")
    with open(os.path.join(RESULTS, "results.json"), "w", encoding="utf-8") as f:
        json.dump(HEADLINE, f, indent=1, default=lambda o: float(o) if isinstance(o, np.floating) else
                  (int(o) if isinstance(o, np.integer) else list(o)))
    print("\nchecks passed" if ok else "\nCHECKS FAILED - see the Checks table", flush=True)


if __name__ == "__main__":
    main()
