"""Download resolved Polymarket markets and their prices at fixed horizons.

Usage (each stage is resumable: rerun the same command after an interruption):

    python download_polymarket.py markets     # 1. list every closed market, month by month
    python download_polymarket.py prices      # 2. reference prices for the sampled markets
    python download_polymarket.py all         # both, in order

Outputs (all in data/):
    polymarket_markets.jsonl        one slimmed market record per line (raw API values kept as-is)
    polymarket_markets_state.json   paging cursor per month window (for resuming)
    polymarket_sample_ids.txt       ids of the markets chosen for price download
    polymarket_prices.jsonl         one line per (market, horizon, anchor) price request

Read-only public endpoints, no key:
    https://gamma-api.polymarket.com/markets/keyset   (market metadata, cursor paging)
    https://clob.polymarket.com/prices-history         (price series for one outcome token)
"""
import json
import os
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from apiutil import get_json, log, month_starts, parse_time, read_jsonl, set_max_in_flight

MAX_IN_FLIGHT = 4            # the brief's cap (12 was tried and was no faster: the server queues)
set_max_in_flight(MAX_IN_FLIGHT)
BATCH = "https://clob.polymarket.com/batch-prices-history"   # up to 20 tokens per request

GAMMA = "https://gamma-api.polymarket.com/markets/keyset"
CLOB = "https://clob.polymarket.com/prices-history"
DATA = "data"
MARKETS_FILE = os.path.join(DATA, "polymarket_markets.jsonl")
STATE_FILE = os.path.join(DATA, "polymarket_markets_state.json")
SAMPLE_FILE = os.path.join(DATA, "polymarket_sample_ids.txt")
PRICES_FILE = os.path.join(DATA, "polymarket_prices.jsonl")

FIRST_MONTH = (2024, 1)
LAST_MONTH = (2026, 11)          # month in which this study was run
VOLUME_FLOOR = 1000              # dollars; drops dead markets
HORIZONS = (1, 7, 30, 90)        # days before close
WINDOW = 12 * 3600               # a price may be at most 12 h older than the horizon
DAY = 86400
SEED = 20261111
CAP_PER_MONTH = 4000             # max sampled markets per closing month (see DECISIONS.md)

# Fields kept from each market record.  The full record is ~5 kB of mostly
# descriptive text; keeping every field for hundreds of thousands of markets
# would be several GB, so we keep what the analysis (and a human checking it) needs.
KEEP = ["id", "question", "slug", "conditionId", "outcomes", "outcomePrices", "clobTokenIds",
        "closedTime", "endDate", "startDate", "createdAt", "volumeNum", "negRisk",
        "umaResolutionStatus", "groupItemTitle", "sportsMarketType", "feesEnabled"]

_write_lock = threading.Lock()


# --------------------------------------------------------------------------
# Stage 1: list markets
# --------------------------------------------------------------------------
def windows():
    """Month windows on endDate, plus one catch-all 'future' window.

    The API can only filter on the *scheduled* end date.  A market scheduled to
    end in 2027 that resolved early in 2025 would be missed by month windows
    alone, so a final window covers scheduled end dates after the study month.
    """
    out = []
    months = month_starts(FIRST_MONTH, LAST_MONTH)
    for (y, m) in months:
        ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
        out.append((f"{y}-{m:02d}", f"{y}-{m:02d}-01T00:00:00Z", f"{ny}-{nm:02d}-01T00:00:00Z"))
    y, m = LAST_MONTH
    ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
    out.append(("future", f"{ny}-{nm:02d}-01T00:00:00Z", "2040-01-01T00:00:00Z"))
    return out


def slim(m):
    rec = {k: m.get(k) for k in KEEP}
    ev = (m.get("events") or [{}])[0]
    rec["event_id"] = ev.get("id")
    rec["event_slug"] = ev.get("slug")
    rec["event_title"] = ev.get("title")
    return rec


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


def list_window(win, state, out):
    """Page one endDate window to exhaustion, appending records as they arrive."""
    name, lo, hi = win
    st = state.get(name, {"cursor": None, "done": False, "n": 0})
    if st["done"]:
        return
    while True:
        params = {"closed": "true", "limit": 100, "end_date_min": lo, "end_date_max": hi,
                  "volume_num_min": VOLUME_FLOOR}
        if st["cursor"]:
            params["after_cursor"] = st["cursor"]
        page = get_json(GAMMA, params)
        if page is None:
            log(f"window {name}: request failed permanently; leaving for a rerun")
            return
        markets = page.get("markets") or []
        with _write_lock:
            # write the page first, then the cursor: a crash in between can only
            # cause duplicates (removed later by id), never a gap
            for m in markets:
                out.write(json.dumps(slim(m)) + "\n")
            out.flush()
            st["n"] += len(markets)
            st["cursor"] = page.get("next_cursor")
            st["done"] = not st["cursor"]
            state[name] = st
            save_state(state)
        if st["done"]:
            log(f"window {name}: done, {st['n']} markets")
            return
        if st["n"] % 5000 < 100:
            log(f"window {name}: {st['n']} so far")


def stage_markets():
    os.makedirs(DATA, exist_ok=True)
    state = load_state()
    with open(MARKETS_FILE, "a", encoding="utf-8") as out:
        with ThreadPoolExecutor(MAX_IN_FLIGHT) as ex:
            list(ex.map(lambda w: list_window(w, state, out), windows()))
    done = sum(1 for w in windows() if state.get(w[0], {}).get("done"))
    log(f"markets stage finished: {done}/{len(windows())} windows complete, "
        f"{sum(s['n'] for s in state.values())} records written")


# --------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------
def load_markets():
    """All listed markets, de-duplicated by id."""
    seen = {}
    for rec in read_jsonl(MARKETS_FILE):
        seen[rec["id"]] = rec
    return list(seen.values())


def clean_binary(rec):
    """Return (yes_token, outcome, open_ts, close_ts) for a cleanly resolved two-outcome
    market, else None.  'outcome' is 1 if the FIRST listed outcome won."""
    try:
        outcomes = json.loads(rec.get("outcomes") or "[]")
        prices = json.loads(rec.get("outcomePrices") or "[]")
        tokens = json.loads(rec.get("clobTokenIds") or "[]")
    except (json.JSONDecodeError, TypeError):
        return None
    if len(outcomes) != 2 or len(prices) != 2 or len(tokens) != 2:
        return None
    try:
        p0, p1 = float(prices[0]), float(prices[1])
    except (TypeError, ValueError):
        return None
    if (p0, p1) == (1.0, 0.0):
        y = 1
    elif (p0, p1) == (0.0, 1.0):
        y = 0
    else:
        return None                      # voided, 50/50 or not finally resolved
    close_ts = parse_time(rec.get("closedTime"))
    open_ts = parse_time(rec.get("startDate")) or parse_time(rec.get("createdAt"))
    if close_ts is None or open_ts is None or not tokens[0]:
        return None
    return tokens[0], y, open_ts, close_ts


def choose_sample():
    """Pick the markets whose prices we download.

    Eligible: clean binary resolution, closed on/after 1 Jan 2024, open for at
    least one day (a market open for less than a day cannot contribute to any
    horizon, so excluding it loses nothing).  If a closing month has more than
    CAP_PER_MONTH eligible markets, take a simple random sample of CAP_PER_MONTH
    from that month (fixed seed).  Selection never looks at the outcome or price.
    """
    by_month = {}
    start = parse_time("2024-01-01T00:00:00Z")
    for rec in load_markets():
        cb = clean_binary(rec)
        if cb is None:
            continue
        _, _, open_ts, close_ts = cb
        if close_ts < start or close_ts - open_ts < DAY:
            continue
        month = rec["closedTime"][:7]
        by_month.setdefault(month, []).append(rec["id"])
    rng = random.Random(SEED)
    chosen = []
    for month in sorted(by_month):
        ids = sorted(by_month[month], key=int)
        take = ids if len(ids) <= CAP_PER_MONTH else rng.sample(ids, CAP_PER_MONTH)
        log(f"sample {month}: {len(take)} of {len(ids)} eligible")
        chosen.extend(take)
    with open(SAMPLE_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(chosen) + "\n")
    return set(chosen)


# --------------------------------------------------------------------------
# Stage 2: prices at each horizon
# --------------------------------------------------------------------------
def fetch_price(task):
    """One reference price: the last point at or before T inside [T-12h, T]."""
    mid, token, h, anchor, T = task
    rec = {"id": mid, "h": h, "anchor": anchor, "T": T, "t": None, "p": None, "n": 0}
    for fidelity in (60, 1):                 # hourly points first; 1-minute points if that is empty
        res = get_json(CLOB, {"market": token, "startTs": T - WINDOW, "endTs": T, "fidelity": fidelity})
        if res is None:
            rec["err"] = True
            return rec
        pts = [x for x in (res.get("history") or []) if T - WINDOW <= x["t"] <= T]
        if pts:
            last = max(pts, key=lambda x: x["t"])
            rec.update(t=last["t"], p=last["p"], n=len(pts), fid=fidelity)
            rec.pop("err", None)
            return rec
    return rec                                # no price in the window: recorded so we do not retry


def price_tasks(sample_ids):
    """Yield every (market, horizon, anchor) request still to do.

    anchor 'closed' : horizon counted back from closedTime (the pre-registered rule).
    anchor 'end'    : secondary sensitivity check, counted back from the earlier of the
                      scheduled endDate and closedTime; only fetched for 1 and 7 days and
                      only when it differs from closedTime by more than an hour.
    """
    done = {(r["id"], r["h"], r["anchor"]) for r in read_jsonl(PRICES_FILE) if not r.get("err")}
    for rec in load_markets():
        if rec["id"] not in sample_ids:
            continue
        cb = clean_binary(rec)
        if cb is None:
            continue
        token, _, open_ts, close_ts = cb
        end_ts = parse_time(rec.get("endDate"))
        for h in HORIZONS:
            if close_ts - open_ts >= h * DAY and (rec["id"], h, "closed") not in done:
                yield (rec["id"], token, h, "closed", close_ts - h * DAY)
            if h in (1, 7) and end_ts is not None and end_ts < close_ts - 3600 \
                    and end_ts - open_ts >= h * DAY and (rec["id"], h, "end") not in done:
                yield (rec["id"], token, h, "end", end_ts - h * DAY)


def fetch_batch(tasks):
    """Reference prices for up to 20 tasks in ONE request.

    All tasks in a batch share a horizon and have their horizon time T on the same UTC
    day, so one window [earliest T - 12h, latest T] (at most 36 hours) covers them all.
    Each task still only uses points inside its own [T - 12h, T].  Checked against 240
    single-market requests: identical prices and timestamps.  Tasks that come back
    empty are retried one at a time with fetch_price (which also tries 1-minute points).
    """
    lo = min(t[4] for t in tasks) - WINDOW
    hi = max(t[4] for t in tasks)
    res = get_json(BATCH, body={"markets": [t[1] for t in tasks], "start_ts": lo, "end_ts": hi, "fidelity": 60})
    hist = (res or {}).get("history") or {}
    out = []
    for task in tasks:
        mid, token, h, anchor, T = task
        pts = [x for x in hist.get(token) or [] if T - WINDOW <= x["t"] <= T]
        if pts:
            last = max(pts, key=lambda x: x["t"])
            out.append({"id": mid, "h": h, "anchor": anchor, "T": T, "t": last["t"], "p": last["p"],
                        "n": len(pts), "fid": 60, "via": "batch"})
        else:
            out.append(fetch_price(task))
    return out


def make_batches(tasks):
    groups = {}
    for t in tasks:
        groups.setdefault((t[2], t[3], t[4] // DAY), []).append(t)
    batches = []
    for key in sorted(groups):
        g = groups[key]
        batches += [g[i:i + 20] for i in range(0, len(g), 20)]
    return batches


def stage_prices(limit=None):
    if os.path.exists(SAMPLE_FILE):
        with open(SAMPLE_FILE, "r", encoding="utf-8") as f:
            sample_ids = {x.strip() for x in f if x.strip()}
        log(f"using existing sample of {len(sample_ids)} markets")
    else:
        sample_ids = choose_sample()
    tasks = list(price_tasks(sample_ids))
    if limit:
        tasks = tasks[:limit]
    batches = make_batches(tasks)
    log(f"{len(tasks)} prices to fetch in {len(batches)} batch requests")
    n = 0
    with open(PRICES_FILE, "a", encoding="utf-8") as out, ThreadPoolExecutor(MAX_IN_FLIGHT) as ex:
        out.write("\n")      # in case an interrupted run left a half-written last line
        for i in range(0, len(batches), 40):
            for recs in ex.map(fetch_batch, batches[i:i + 40]):
                for rec in recs:
                    out.write(json.dumps(rec) + "\n")
                n += len(recs)
            out.flush()
            if (i // 40) % 10 == 0:
                log(f"prices: {n}/{len(tasks)}")
    log("prices stage finished")


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("markets", "all"):
        stage_markets()
    if stage == "sample":
        choose_sample()
    if stage in ("prices", "all"):
        stage_prices(int(sys.argv[2]) if len(sys.argv) > 2 else None)
