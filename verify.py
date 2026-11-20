"""Independent re-computation of headline numbers (a 'second route').

Deliberately shares NO code with analyse.py or the download scripts: it re-reads
the raw files with its own parsing, rebuilds the 7-day slope samples, fits the
logistic regression with a textbook matrix IRLS, and runs a plain row-copying
event bootstrap (500 resamples, so intervals will differ slightly from the
2,000-resample ones).  It then compares against results/results.json.

    python verify.py
"""
import datetime as dt
import json
import math
import random

import numpy as np

H = 7
DAY = 86400


def ts(s):
    """Timestamp string -> Unix seconds, written independently of apiutil.parse_time."""
    s = s.strip().replace(" ", "T").replace("Z", "+00:00")
    if s[-3] in "+-":
        s += ":00"
    if "." in s:
        head, rest = s.split(".", 1)
        i = 0
        while i < len(rest) and rest[i].isdigit():
            i += 1
        s = head + rest[i:]                      # drop fractional seconds
    return int(dt.datetime.fromisoformat(s).timestamp())


def lines(path):
    with open(path, encoding="utf-8") as f:
        for ln in f:
            try:
                yield json.loads(ln)
            except json.JSONDecodeError:
                pass


def irls(x, y):
    """Logistic regression y ~ 1 + x by iteratively reweighted least squares."""
    X = np.column_stack([np.ones(len(x)), x])
    beta = np.array([0.0, 1.0])
    for _ in range(50):
        mu = 1 / (1 + np.exp(-X @ beta))
        w = mu * (1 - mu)
        step = np.linalg.solve(X.T @ (X * w[:, None]), X.T @ (y - mu))
        beta = beta + step
        if np.abs(step).max() < 1e-10:
            break
    return beta


def polymarket_rows():
    sample = {x.strip() for x in open("data/polymarket_sample_ids.txt", encoding="utf-8") if x.strip()}
    price = {}
    for r in lines("data/polymarket_prices.jsonl"):
        if r["h"] == H and r["anchor"] == "closed" and r.get("p") is not None and not r.get("err"):
            price[r["id"]] = r
    rows, seen = [], set()
    for m in lines("data/polymarket_markets.jsonl"):
        if m["id"] in seen or m["id"] not in sample or m["id"] not in price:
            continue
        seen.add(m["id"])
        op = json.loads(m["outcomePrices"])
        if op == ["1", "0"]:
            y = 1
        elif op == ["0", "1"]:
            y = 0
        else:
            continue
        close = ts(m["closedTime"])
        r = price[m["id"]]
        assert r["T"] == close - H * DAY and r["t"] <= r["T"] <= close
        if close < ts("2024-01-01T00:00:00Z"):
            continue
        rows.append((float(r["p"]), y, "e" + str(m.get("event_id") or "m" + m["id"]), close))
    return rows


def kalshi_rows():
    candle = {}
    for r in lines("data/kalshi_candles.jsonl"):
        if r["h"] == H and not r.get("err"):
            candle[r["ticker"]] = r
    rows, seen = [], set()
    for m in lines("data/kalshi_markets.jsonl"):
        t = m["ticker"]
        if t in seen or t not in candle:
            continue
        seen.add(t)
        if m["market_type"] != "binary" or m["result"] not in ("yes", "no") or m.get("mve_collection_ticker"):
            continue
        if float(m["volume_fp"]) < 1000:
            continue
        close = ts(m["close_time"])
        r = candle[t]
        if r["trade_p"] is not None:
            p, pt = r["trade_p"], r["trade_t"]
        elif r["bid"] is not None and r["ask"] is not None and r["bid"] > 0 and r["ask"] < 1 \
                and r["ask"] - r["bid"] <= 0.10 + 1e-9:
            p, pt = (r["bid"] + r["ask"]) / 2, r["quote_t"]
        else:
            continue
        assert pt <= r["T"] == close - H * DAY
        if close < ts("2025-01-01T00:00:00Z"):
            continue
        rows.append((p, 1 if m["result"] == "yes" else 0, m["event_ticker"], close))
    return rows


def slope(rows):
    x = np.array([math.log(p / (1 - p)) for p, _, _, _ in rows])
    y = np.array([float(v) for _, v, _, _ in rows])
    return irls(x, y)[1]


def report(name, rows, expected):
    rows = [r for r in rows if 0.03 <= r[0] <= 0.97]
    before = [r for r in rows if r[3] < ts("2026-02-01T00:00:00Z")]
    after = [r for r in rows if r[3] >= ts("2026-03-01T00:00:00Z")]
    s_all, s_b, s_a = slope(rows), slope(before), slope(after)
    # plain bootstrap: draw events with replacement and physically copy their rows
    by_event = {}
    for r in rows:
        by_event.setdefault(r[2], []).append(r)
    events = sorted(by_event)
    rng = random.Random(7)
    diffs, alls = [], []
    for _ in range(500):
        res = [r for e in rng.choices(events, k=len(events)) for r in by_event[e]]
        b = [r for r in res if r[3] < ts("2026-02-01T00:00:00Z")]
        a = [r for r in res if r[3] >= ts("2026-03-01T00:00:00Z")]
        diffs.append(slope(a) - slope(b))
        alls.append(slope(res))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    alo, ahi = np.percentile(alls, [2.5, 97.5])
    print(f"\n{name}, {H}-day horizon, prices 3-97%")
    print(f"  overall slope  verify {s_all:.4f} [{alo:.3f}, {ahi:.3f}] n={len(rows)}"
          f"   analyse {expected['slope']['slope']:.4f} [{expected['slope']['lo']:.3f}, {expected['slope']['hi']:.3f}]"
          f" n={expected['slope']['n']}")
    e = expected["primary"]
    print(f"  slope before   verify {s_b:.4f} n={len(before)}   analyse {e['before']:.4f} n={e['n_before']}")
    print(f"  slope after    verify {s_a:.4f} n={len(after)}   analyse {e['after']:.4f} n={e['n_after']}")
    print(f"  change         verify {s_a - s_b:.4f} [{lo:.3f}, {hi:.3f}]"
          f"   analyse {e['diff']:.4f} [{e['diff_ci'][0]:.3f}, {e['diff_ci'][1]:.3f}]")
    ok = (abs(s_all - expected["slope"]["slope"]) < 1e-3 and abs(s_b - e["before"]) < 1e-3
          and abs(s_a - e["after"]) < 1e-3 and len(rows) == expected["slope"]["n"]
          and abs(lo - e["diff_ci"][0]) < 0.05 and abs(hi - e["diff_ci"][1]) < 0.05)
    print("  MATCH" if ok else "  MISMATCH")
    return ok


if __name__ == "__main__":
    res = json.load(open("results/results.json", encoding="utf-8"))
    ok1 = report("Polymarket", polymarket_rows(),
                 {"slope": res["slope_Polymarket_7d"], "primary": res["primary_Polymarket"]})
    ok2 = report("Kalshi", kalshi_rows(), {"slope": res["slope_Kalshi_7d"], "primary": res["primary_Kalshi"]})
    print("\nALL MATCH" if ok1 and ok2 else "\nSOME MISMATCH")
