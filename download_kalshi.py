"""Download settled Kalshi markets, sampled evenly over time, and their prices.

Usage (each stage is resumable: rerun the same command after an interruption):

    python download_kalshi.py series     # 1. list of all series (category, frequency)
    python download_kalshi.py events     # 2. list of ALL events (the time-stratified route)
    python download_kalshi.py markets    # 3. markets of a stratified random sample of events
    python download_kalshi.py candles    # 4. hourly candles around each horizon
    python download_kalshi.py all

Why this route: /historical/markets has no time filter and pages newest-first
through ~37,000 markets a day, so it cannot be paged back to 2025.  The /events
endpoint lists every event ever (including those older than the historical
cutoff), and most event tickers carry their date (e.g. KXHIGHNY-25MAR05).  So we
list all events, group them by month and by how long-lived their series is,
draw a random sample from every month, and fetch each sampled event's markets
by event ticker.

Outputs (all in data/):
    kalshi_series.json          raw series list
    kalshi_events.jsonl         one slimmed event per line; kalshi_events_state.json holds the cursor
    kalshi_sampled_events.csv   the sampled events with their stratum
    kalshi_markets.jsonl        one slimmed market per line (every market of every sampled event)
    kalshi_events_done.txt      events whose markets have been fetched
    kalshi_candles.jsonl        one line per (market, horizon) candle request
"""
import csv
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from apiutil import MAX_IN_FLIGHT, get_json, log, pace_gap, parse_time, read_jsonl, set_pace

# Kalshi answers HTTP 429 above a few requests a second: start at ~6 a second and adapt.
set_pace(gap=0.16, floor=0.05, ceil=1.0)

BASE = "https://api.elections.kalshi.com/trade-api/v2"
DATA = "data"
SERIES_FILE = os.path.join(DATA, "kalshi_series.json")
EVENTS_FILE = os.path.join(DATA, "kalshi_events.jsonl")
EVENTS_STATE = os.path.join(DATA, "kalshi_events_state.json")
SAMPLED_FILE = os.path.join(DATA, "kalshi_sampled_events.csv")
MARKETS_FILE = os.path.join(DATA, "kalshi_markets.jsonl")
EVENTS_DONE = os.path.join(DATA, "kalshi_events_done.txt")
CANDLES_FILE = os.path.join(DATA, "kalshi_candles.jsonl")

FIRST_MONTH = "2025-01"
LAST_MONTH = "2026-11"
VOLUME_FLOOR = 1000              # contracts
HORIZONS = (1, 7, 30, 90)
WINDOW = 12 * 3600
DAY = 86400
SEED = 20261111

# Events sampled per month in each stratum (set after a pilot on October 2026; see DECISIONS.md).
# 'short'  = series that Kalshi labels fifteen_min / hourly / daily (crypto, indices, weather):
#            ~30,000 events a month, almost none open for a day
# 'sports' = other series in the Sports category (single games): ~36,000 events a month,
#            mostly open 1-7 days
# 'other'  = everything else with a date (politics, economics, entertainment ...):
#            ~1,000 events a month, the main source of long-lived markets, so we take them all
#
# Kalshi throttles unauthenticated clients to a few requests a second, so the whole
# download has to fit in roughly 75,000 requests.  The quotas below spend that budget
# where the 7, 30 and 90 day horizons get their data ('other' and undated events), and
# take every 'other' event up to February 2026 because the "before" period is the
# scarce side of the before/after comparison.
PER_MONTH = {"short": 60, "sports": 100, "other": 300}
OTHER_TAKE_ALL_UNTIL = "2026-02"  # every 'other' event dated up to and including this month
UNDATED_EVENTS = 4000            # random sample of events whose ticker carries no date (one-offs, long-lived)
ONE_DAY_CAP = 25000              # 1-day candles are fetched for a random sample of this many markets

MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
DATE_TOKEN = re.compile(r"-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})?")

KEEP_EVENT = ["event_ticker", "series_ticker", "category", "strike_date", "title", "sub_title",
              "mutually_exclusive"]
KEEP_MARKET = ["ticker", "event_ticker", "market_type", "result", "status", "open_time", "close_time",
               "settlement_ts", "expected_expiration_time", "volume_fp", "open_interest_fp",
               "last_price_dollars", "settlement_value_dollars", "yes_sub_title", "title",
               "can_close_early", "strike_type", "mve_collection_ticker"]


# --------------------------------------------------------------------------
# Stage 1 and 2: series and events
# --------------------------------------------------------------------------
def stage_series():
    os.makedirs(DATA, exist_ok=True)
    if os.path.exists(SERIES_FILE):
        log("series list already saved")
        return
    res = get_json(BASE + "/series")
    if res is None:
        raise SystemExit("could not fetch the series list")
    with open(SERIES_FILE, "w", encoding="utf-8") as f:
        json.dump(res, f)
    log(f"saved {len(res.get('series') or [])} series")


def stage_events():
    """Page GET /events (200 per page) to the end, appending as we go."""
    os.makedirs(DATA, exist_ok=True)
    try:
        with open(EVENTS_STATE, "r", encoding="utf-8") as f:
            st = json.load(f)
    except FileNotFoundError:
        st = {"cursor": None, "done": False, "n": 0}
    if st["done"]:
        log(f"events list already complete ({st['n']} events)")
        return
    with open(EVENTS_FILE, "a", encoding="utf-8") as out:
        while True:
            params = {"limit": 200}
            if st["cursor"]:
                params["cursor"] = st["cursor"]
            page = get_json(BASE + "/events", params)
            if page is None:
                raise SystemExit("events listing failed; rerun to resume")
            events = page.get("events") or []
            for e in events:
                out.write(json.dumps({k: e.get(k) for k in KEEP_EVENT}) + "\n")
            out.flush()
            st["n"] += len(events)
            st["cursor"] = page.get("cursor")
            st["done"] = not st["cursor"] or not events
            tmp = EVENTS_STATE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(st, f)
            os.replace(tmp, EVENTS_STATE)
            if st["done"]:
                break
            if st["n"] % 50000 == 0:
                log(f"events: {st['n']}")
    log(f"events stage finished: {st['n']} events")


# --------------------------------------------------------------------------
# Sampling events
# --------------------------------------------------------------------------
def event_month(ticker):
    """'YYYY-MM' from the date token in an event ticker, or None."""
    m = DATE_TOKEN.search(ticker)
    if not m:
        return None
    return f"20{m.group(1)}-{MONTHS[m.group(2)]:02d}"


def choose_events():
    """Stratified random sample of events: by ticker month and short/long series.

    Nothing about prices or outcomes is used.  Events dated outside the study
    months are ignored; undated events form their own stratum.
    """
    with open(SERIES_FILE, "r", encoding="utf-8") as f:
        series = json.load(f)["series"]
    freq = {s["ticker"]: s.get("frequency") for s in series}
    cat = {s["ticker"]: s.get("category") for s in series}
    strata = {}
    seen = set()
    for e in read_jsonl(EVENTS_FILE):
        t = e["event_ticker"]
        if t in seen:
            continue
        seen.add(t)
        month = event_month(t)
        if freq.get(e["series_ticker"]) in ("fifteen_min", "hourly", "daily"):
            kind = "short"
        elif cat.get(e["series_ticker"]) == "Sports":
            kind = "sports"
        else:
            kind = "other"
        if month is None:
            key = ("undated", "undated")
        elif FIRST_MONTH <= month <= LAST_MONTH:
            key = (month, kind)
        else:
            continue
        strata.setdefault(key, []).append(t)
    rng = random.Random(SEED)
    rows = []
    for key in sorted(strata):
        tickers = sorted(strata[key])
        if key[0] == "undated":
            quota = UNDATED_EVENTS
        elif key[1] == "other" and key[0] <= OTHER_TAKE_ALL_UNTIL:
            quota = len(tickers)
        else:
            quota = PER_MONTH[key[1]]
        take = tickers if len(tickers) <= quota else rng.sample(tickers, quota)
        log(f"stratum {key}: {len(take)} of {len(tickers)} events")
        rows += [(t, key[0], key[1], len(tickers)) for t in take]
    with open(SAMPLED_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["event_ticker", "month", "stratum", "stratum_size"])
        w.writerows(rows)
    return rows


# --------------------------------------------------------------------------
# Stage 3: markets of the sampled events
# --------------------------------------------------------------------------
def fetch_event_markets(event_ticker):
    """All markets of one event, from the historical feed and/or the live feed.

    Markets settled before the cutoff are only on /historical/markets, newer ones
    only on /markets.  We ask the historical feed first and the live feed only if
    that is empty (an event normally lives entirely on one side).
    """
    out = {}
    for path in ("/historical/markets", "/markets"):
        cursor = None
        while True:
            params = {"event_ticker": event_ticker, "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            page = get_json(BASE + path, params)
            if page is None:
                return event_ticker, None
            for m in page.get("markets") or []:
                rec = {k: m.get(k) for k in KEEP_MARKET}
                rec["feed"] = "historical" if path.startswith("/hist") else "live"
                out[rec["ticker"]] = rec
            cursor = page.get("cursor")
            if not cursor or not page.get("markets"):
                break
        if out and path == "/historical/markets" and all(m["result"] in ("yes", "no") for m in out.values()):
            break
    return event_ticker, list(out.values())


def stage_markets(limit=None):
    if os.path.exists(SAMPLED_FILE):
        with open(SAMPLED_FILE, "r", encoding="utf-8") as f:
            sampled = [r["event_ticker"] for r in csv.DictReader(f)]
        log(f"using existing sample of {len(sampled)} events")
    else:
        sampled = [r[0] for r in choose_events()]
    done = set()
    if os.path.exists(EVENTS_DONE):
        with open(EVENTS_DONE, "r", encoding="utf-8") as f:
            done = {x.strip() for x in f if x.strip()}
    todo = [t for t in sampled if t not in done]
    random.Random(SEED).shuffle(todo)        # so a partial run is still spread over all months
    if limit:
        todo = todo[:limit]
    log(f"{len(todo)} events to fetch")
    with open(MARKETS_FILE, "a", encoding="utf-8") as out, open(EVENTS_DONE, "a", encoding="utf-8") as dn, \
            ThreadPoolExecutor(MAX_IN_FLIGHT) as ex:
        for i in range(0, len(todo), 200):
            for ticker, markets in ex.map(fetch_event_markets, todo[i:i + 200]):
                if markets is None:
                    continue                  # failed: not marked done, retried on rerun
                for m in markets:
                    out.write(json.dumps(m) + "\n")
                dn.write(ticker + "\n")
            out.flush()
            dn.flush()
            if (i // 200) % 5 == 0:
                log(f"markets: {i + 200}/{len(todo)} events (gap {pace_gap():.3f}s)")
    log("markets stage finished")


# --------------------------------------------------------------------------
# Stage 4: candles
# --------------------------------------------------------------------------
def usable_market(m):
    """(open_ts, close_ts) if the market is binary, cleanly settled yes/no and has
    traded at least VOLUME_FLOOR contracts; else None."""
    if m.get("market_type") != "binary" or m.get("result") not in ("yes", "no"):
        return None
    if m.get("mve_collection_ticker"):
        return None                           # multivariate combo markets are excluded
    try:
        if float(m.get("volume_fp") or 0) < VOLUME_FLOOR:
            return None
    except ValueError:
        return None
    o, c = parse_time(m.get("open_time")), parse_time(m.get("close_time"))
    if o is None or c is None:
        return None
    return o, c


def _num(d, key):
    """Read a price that may be named 'close' (historical feed) or 'close_dollars' (live feed)."""
    if not isinstance(d, dict):
        return None
    v = d.get(key)
    if v is None:
        v = d.get(key + "_dollars")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def summarise(ticker, h, T, candles, src):
    """Reduce the candles in [T-12h, T] to the last trade and the last quote."""
    rec = {"ticker": ticker, "h": h, "T": T, "trade_p": None, "trade_t": None,
           "bid": None, "ask": None, "quote_t": None, "n": 0, "src": src}
    candles = [c for c in candles or [] if T - WINDOW <= c.get("end_period_ts", 0) <= T]
    rec["n"] = len(candles)
    for c in sorted(candles, key=lambda c: c["end_period_ts"]):
        p = _num(c.get("price"), "close")
        if p is not None:                     # a trade happened in this hour
            rec["trade_p"], rec["trade_t"] = p, c["end_period_ts"]
        b, a = _num(c.get("yes_bid"), "close"), _num(c.get("yes_ask"), "close")
        if b is not None and a is not None:
            rec["bid"], rec["ask"], rec["quote_t"] = b, a, c["end_period_ts"]
    return rec


def fetch_candles(task):
    """Hourly candles in [T-12h, T] for one market; keep the last trade and the last quote."""
    ticker, event_ticker, feed, h, T = task
    series = event_ticker.split("-")[0]
    paths = [f"/historical/markets/{ticker}/candlesticks", f"/series/{series}/markets/{ticker}/candlesticks"]
    if feed == "live":
        paths.reverse()
    for path in paths:
        res = get_json(BASE + path, {"start_ts": T - WINDOW, "end_ts": T, "period_interval": 60})
        if res is None:
            continue                          # e.g. 404 on the wrong feed: try the other
        return summarise(ticker, h, T, res.get("candlesticks"), "historical" if path.startswith("/hist") else "live")
    return {"ticker": ticker, "h": h, "T": T, "err": True}


def fetch_candles_batch(tasks):
    """Candles for up to 100 LIVE markets in one request (GET /markets/candlesticks).

    Only markets newer than the historical cutoff are served by this endpoint (tested:
    it returns nothing for older ones), so it is used for the 'live' feed only.  Tasks
    share a horizon and a UTC day of T, so one window of at most 36 hours covers them.
    A market that comes back with no candles is retried on its own with fetch_candles,
    which also tries the historical feed.
    """
    lo = min(t[4] for t in tasks) - WINDOW
    hi = max(t[4] for t in tasks)
    res = get_json(BASE + "/markets/candlesticks",
                   {"market_tickers": ",".join(t[0] for t in tasks), "start_ts": lo, "end_ts": hi,
                    "period_interval": 60})
    got = {m["market_ticker"]: m.get("candlesticks") for m in (res or {}).get("markets") or []}
    out = []
    for task in tasks:
        ticker, _, _, h, T = task
        if got.get(ticker):
            rec = summarise(ticker, h, T, got[ticker], "live-batch")
            out.append(rec)
        else:
            out.append(fetch_candles(task))
    return out


def fetch_job(job):
    """A job is either one single-market task or a list of live tasks for a batch."""
    return fetch_candles_batch(job) if isinstance(job, list) else [fetch_candles(job)]


def candle_tasks():
    """Every (market, horizon) request still to do, in priority order.

    Order: 7 days (the primary test), then 30, 90, then 1 day.  Within a horizon the
    order is a seeded shuffle, so an interrupted run is still a random subset.  The
    1-day horizon has far more eligible markets than the request budget allows, so
    it is limited to a seeded random sample of ONE_DAY_CAP markets.
    """
    done = {(r["ticker"], r["h"]) for r in read_jsonl(CANDLES_FILE) if not r.get("err")}
    with open(SAMPLED_FILE, "r", encoding="utf-8") as f:
        sampled = {r["event_ticker"] for r in csv.DictReader(f)}
    seen = set()
    by_h = {h: [] for h in HORIZONS}
    for m in read_jsonl(MARKETS_FILE):
        if m["ticker"] in seen or m["event_ticker"] not in sampled:
            continue
        seen.add(m["ticker"])
        oc = usable_market(m)
        if oc is None:
            continue
        o, c = oc
        for h in HORIZONS:
            if c - o >= h * DAY:
                by_h[h].append((m["ticker"], m["event_ticker"], m.get("feed"), h, c - h * DAY))
    rng = random.Random(SEED)
    for h in (7, 30, 90, 1):
        tasks = sorted(by_h[h])
        rng.shuffle(tasks)
        if h == 1:
            tasks = tasks[:ONE_DAY_CAP]
        for t in tasks:
            if (t[0], h) not in done:
                yield t


def stage_candles(limit=None):
    tasks = list(candle_tasks())
    if limit:
        tasks = tasks[:limit]
    # Build jobs in priority order (tasks arrive ordered 7, 30, 90, 1 days).  Within a
    # horizon, live markets are grouped into batch requests; historical ones go singly.
    jobs = []
    for h in (7, 30, 90, 1):
        th = [t for t in tasks if t[3] == h]
        groups = {}
        for t in th:
            if t[2] == "live":
                groups.setdefault(t[4] // DAY, []).append(t)
        for day in sorted(groups):
            g = groups[day]
            jobs += [g[i:i + 100] for i in range(0, len(g), 100)]
        jobs += [t for t in th if t[2] != "live"]
    log(f"{len(tasks)} candle lookups to do in {len(jobs)} requests")
    n = 0
    with open(CANDLES_FILE, "a", encoding="utf-8") as out, ThreadPoolExecutor(MAX_IN_FLIGHT) as ex:
        out.write("\n")      # in case an interrupted run left a half-written last line
        for i in range(0, len(jobs), 200):
            for recs in ex.map(fetch_job, jobs[i:i + 200]):
                for rec in recs:
                    out.write(json.dumps(rec) + "\n")
                n += len(recs)
            out.flush()
            if (i // 200) % 10 == 0:
                log(f"candles: {n}/{len(tasks)} lookups, {i + 200}/{len(jobs)} requests (gap {pace_gap():.3f}s)")
    log("candles stage finished")


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if stage in ("series", "all"):
        stage_series()
    if stage in ("events", "all"):
        stage_events()
    if stage == "sample":
        choose_events()
    if stage in ("markets", "all"):
        stage_markets(lim)
    if stage in ("candles", "all"):
        stage_candles(lim)
