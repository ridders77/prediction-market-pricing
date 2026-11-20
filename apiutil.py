"""Small shared helpers for the two download scripts.

Standard library only.  Everything here is read-only HTTP GET against public
market-data endpoints: no accounts, no keys, no trading.

Politeness rules implemented here:
  * callers never run more than MAX_IN_FLIGHT (4) requests at once;
  * HTTP 429 and 5xx (and network errors) are retried with exponential back-off;
  * if a source keeps refusing (GIVE_UP_AFTER requests in a row fail even after
    their retries) the whole script stops with a clear message.
"""
import datetime as dt
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_IN_FLIGHT = 4          # hard cap on concurrent requests per script
RETRIES = 6                # attempts per request
GIVE_UP_AFTER = 25         # consecutive failed requests before we stop the source
HEADERS = {"User-Agent": "calibration-study/2.0 (student research; read-only)",
           "Accept": "application/json"}

_lock = threading.Lock()
_consecutive_failures = 0
_slot = threading.Semaphore(MAX_IN_FLIGHT)


def set_max_in_flight(n):
    """Change the cap on concurrent requests (call before any request is made)."""
    global _slot, MAX_IN_FLIGHT
    MAX_IN_FLIGHT = n
    _slot = threading.Semaphore(n)


class SourceRefusing(RuntimeError):
    """Raised when an API keeps refusing requests; the caller should stop."""


# Optional pacing: a minimum gap between request starts, adapted to the server.
# Every HTTP 429 widens the gap by half; every 200 successes narrow it by 5 %.
# This settles just under whatever rate the server allows without hammering it.
_pace = {"gap": 0.0, "floor": 0.0, "ceil": 0.0, "next": 0.0, "ok": 0}


def set_pace(gap, floor, ceil):
    """Turn pacing on: start with `gap` seconds between requests, kept within [floor, ceil]."""
    _pace.update(gap=gap, floor=floor, ceil=ceil)


def pace_gap():
    return _pace["gap"]


def _wait_turn():
    if _pace["gap"] <= 0:
        return
    with _lock:
        now = time.monotonic()
        start = max(now, _pace["next"])
        _pace["next"] = start + _pace["gap"]
    if start > now:
        time.sleep(start - now)


def _pace_feedback(throttled):
    if _pace["gap"] <= 0:
        return
    with _lock:
        if throttled:
            # widen at most once every 2 s: several in-flight requests usually get
            # their 429s together, and counting each one would over-correct
            now = time.monotonic()
            if now - _pace.get("last_widen", 0.0) > 2.0:
                _pace["last_widen"] = now
                _pace["gap"] = min(_pace["ceil"], _pace["gap"] * 1.3)
        else:
            _pace["ok"] += 1
            if _pace["ok"] % 100 == 0:
                _pace["gap"] = max(_pace["floor"], _pace["gap"] * 0.95)


def log(msg):
    """Timestamped line to stdout (the scripts are run with stdout sent to a log file)."""
    print(f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def get_json(url, params=None, body=None):
    """GET url?params and return the decoded JSON.

    If `body` is given it is sent as a JSON POST instead (used only for Polymarket's
    batch price-history query, which is still a read-only data request).

    Retries on 429 / 5xx / network errors with exponential back-off (2, 4, 8 ... 60 s).
    A 4xx other than 429 is a permanent error for that request: returns None
    (it is the caller's job to record that the item could not be fetched).
    """
    global _consecutive_failures
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(RETRIES):
        with _lock:
            if _consecutive_failures >= GIVE_UP_AFTER:
                raise SourceRefusing(f"{GIVE_UP_AFTER} requests in a row failed; stopping. Last: {last}")
        try:
            _wait_turn()
            with _slot:
                if body is None:
                    req = urllib.request.Request(url, headers=HEADERS)
                else:
                    req = urllib.request.Request(
                        url, data=json.dumps(body).encode(), method="POST",
                        headers=dict(HEADERS, **{"Content-Type": "application/json"}))
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = r.read()
            with _lock:
                _consecutive_failures = 0
            _pace_feedback(False)
            return json.loads(body)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {url[:150]}"
            if e.code == 429 or e.code >= 500:
                _pace_feedback(e.code == 429)
                time.sleep(min(60, 2 ** (attempt + 1)))
                continue
            # permanent client error (400, 404 ...): not the server refusing us
            with _lock:
                _consecutive_failures = 0
            return None
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, OSError) as e:
            last = f"{type(e).__name__} {url[:150]}"
            time.sleep(min(60, 2 ** (attempt + 1)))
    with _lock:
        _consecutive_failures += 1
    log(f"FAILED after {RETRIES} attempts: {last}")
    return None


def parse_time(s):
    """Parse the timestamp formats the two APIs use into Unix seconds (UTC).

    Handles '2024-11-06 15:02:11+00', '2024-11-06T15:02:11.123Z',
    '2025-03-17T18:37:25.725047Z' and plain dates.  Returns None if unparseable.
    """
    if not s:
        return None
    s = s.strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # '+00' -> '+00:00'
    if len(s) >= 3 and s[-3] in "+-" and s[-2:].isdigit():
        s = s + ":00"
    # trim fractional seconds to 6 digits (fromisoformat is strict)
    if "." in s:
        head, rest = s.split(".", 1)
        frac = ""
        for c in rest:
            if c.isdigit():
                frac += c
            else:
                break
        tz = rest[len(frac):]
        s = head + "." + (frac[:6].ljust(6, "0")) + tz
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())


def month_starts(first, last):
    """List of (year, month) from first to last inclusive."""
    y, m = first
    out = []
    while (y, m) <= last:
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def read_jsonl(path):
    """Yield records from a JSON-lines file, skipping a torn last line if any."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue   # half-written line from an interrupted run
    except FileNotFoundError:
        return
