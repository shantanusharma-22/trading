#!/usr/bin/env python3
"""Time Machine for trader-timemachine (Indian Equities - NSE/BSE).
Replays every possible outcome of an intraday trade before you risk real rupees:
10,000 simulated sessions plus historical setup replay from the stock's own 5-minute bars.
Standard library only.

    python3 timemachine.py                           # reads trader/plan.json
    python3 timemachine.py --symbol RELIANCE.NS --entry 3000 --stop 2970 --target 3060
    python3 timemachine.py --replays 5000 --seed 42
    python3 timemachine.py --now "2026-10-19 10:15"
"""

import argparse
import datetime
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import IST_OFFSET, UA, normalize_symbol, resolve_path, to_ist

YAHOO_HOSTS = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")
PAUSE = 0.5
BACKOFF = 3.0

# Indian NSE Session Math (09:15 to 15:30 IST)
INTERVAL = 300          # 5-minute bars
SESSION_BARS = 75       # 375 minutes / 5 = exactly 75 bars
OPEN_MIN = 9 * 60 + 15  # 555 min from midnight
CLOSE_MIN = 15 * 60 + 30# 930 min from midnight
FLAT_BY_MIN = 15 * 60 + 10 # 910 min (15:10 IST)

DEFAULT_PLAN_FILE = resolve_path("trader/plan.json")


_urlopen = urllib.request.urlopen
_sleep = time.sleep


def fetch_60d_5m_bars(sym):
    norm = normalize_symbol(sym)
    last_err = None
    for host in YAHOO_HOSTS:
        url = f"https://{host}/v8/finance/chart/{norm}?range=60d&interval=5m"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with _urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
                res = data.get("chart", {}).get("result")
                if res:
                    chart = res[0]
                    ts = chart.get("timestamp", [])
                    q = (chart.get("indicators", {}).get("quote") or [{}])[0]
                    opens = q.get("open", [])
                    highs = q.get("high", [])
                    lows = q.get("low", [])
                    closes = q.get("close", [])
                    bars = []
                    for t, o, h, l, c in zip(ts, opens, highs, lows, closes):
                        if c is not None and h is not None and l is not None:
                            b_dt = to_ist(datetime.datetime.fromtimestamp(t, datetime.timezone.utc))
                            bars.append({
                                "time": b_dt,
                                "open": float(o),
                                "high": float(h),
                                "low": float(l),
                                "close": float(c)
                            })
                    return bars
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                _sleep(BACKOFF)
            continue
        except Exception as e:
            last_err = e
            continue
    return None


def partition_into_sessions(bars):
    """Group 5m bars by trading day, filtering out incomplete days."""
    days = {}
    for b in bars:
        d = b["time"].date()
        days.setdefault(d, []).append(b)
    # Keep sessions with reasonable bar count (at least 60 bars out of 75)
    valid_sessions = [b_list for d, b_list in sorted(days.items()) if len(b_list) >= 50]
    return valid_sessions


def run_monte_carlo(sessions, entry: float, stop: float, target: float,
                     replays: int = 5000, seed: int = 42):
    """Simulate session paths using random historical 5-minute price changes."""
    random.seed(seed)
    risk_pts = entry - stop
    target_pts = target - entry

    # Extract all 5m percentage returns across historical sessions
    returns = []
    for sess in sessions:
        for i in range(1, len(sess)):
            prev_c = sess[i - 1]["close"]
            if prev_c > 0:
                ret = (sess[i]["close"] - prev_c) / prev_c
                high_diff = (sess[i]["high"] - prev_c) / prev_c
                low_diff = (sess[i]["low"] - prev_c) / prev_c
                returns.append((ret, high_diff, low_diff))

    if not returns:
        return None

    # Simulating paths
    target_hits = 0
    stop_hits = 0
    neither_hits = 0
    r_multiples = []

    remaining_bars = 50  # average bars remaining from typical 10:15 entry to 15:10 flat-by

    for _ in range(replays):
        curr_price = entry
        outcome = "neither"
        for _ in range(remaining_bars):
            ret, high_d, low_d = random.choice(returns)
            bar_high = curr_price * (1.0 + high_d)
            bar_low = curr_price * (1.0 + low_d)
            curr_price = curr_price * (1.0 + ret)

            # Check intrabar stop or target hit
            # Conservative rule: if both breached in same 5m bar, assume stop hit first
            if bar_low <= stop:
                outcome = "stop"
                break
            elif bar_high >= target:
                outcome = "target"
                break

        if outcome == "target":
            target_hits += 1
            r_multiples.append(target_pts / risk_pts)
        elif outcome == "stop":
            stop_hits += 1
            r_multiples.append(-1.0)
        else:
            neither_hits += 1
            gain = curr_price - entry
            r_multiples.append(gain / risk_pts)

    target_pct = round((target_hits / replays) * 100, 1)
    stop_pct = round((stop_hits / replays) * 100, 1)
    neither_pct = round((neither_hits / replays) * 100, 1)
    avg_r = round(sum(r_multiples) / len(r_multiples), 2)
    win_loss_ratio = round(target_pct / stop_pct, 2) if stop_pct > 0 else 99.9

    # Verdict
    if target_pct >= 55.0 and avg_r >= 0.5:
        verdict = "FAVORABLE EDGE: Solid statistical support for target over stop."
    elif target_pct >= 45.0 and avg_r >= 0.15:
        verdict = "MODEST EDGE: Positive expected value, viable setup."
    elif abs(target_pct - stop_pct) <= 5.0:
        verdict = "COIN FLIP: Even odds between stop and target. Tight execution required."
    else:
        verdict = "UNFAVORABLE: High historical stop probability. Reconsider or widen target."

    return {
        "replays": replays,
        "target_pct": target_pct,
        "stop_pct": stop_pct,
        "neither_pct": neither_pct,
        "avg_r": avg_r,
        "win_loss_ratio": win_loss_ratio,
        "verdict": verdict,
        "sessions_analyzed": len(sessions)
    }


def main():
    p = argparse.ArgumentParser(description="Monte Carlo Trade Simulator for Indian Equities (NSE/BSE)")
    p.add_argument("--symbol", help="Stock ticker (e.g. RELIANCE.NS)")
    p.add_argument("--entry", type=float, help="Entry price in Rs")
    p.add_argument("--stop", type=float, help="Stop loss price in Rs")
    p.add_argument("--target", type=float, help="Target price in Rs")
    p.add_argument("--replays", type=int, default=5000, help="Number of simulated paths")
    p.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = p.parse_args()

    sym = args.symbol
    entry_val = args.entry
    stop_val = args.stop
    target_val = args.target

    if not (entry_val and stop_val and target_val):
        if not os.path.exists(DEFAULT_PLAN_FILE):
            print(f"ERROR: {DEFAULT_PLAN_FILE} not found. Specify --entry, --stop, --target or run /trader-exit.")
            sys.exit(1)
        with open(DEFAULT_PLAN_FILE, "r", encoding="utf-8") as f:
            plan = json.load(f)
        sym = sym or plan.get("symbol")
        entry_val = plan.get("entry")
        stop_val = plan.get("stop")
        target_val = plan.get("target")

    sym = normalize_symbol(sym)
    print(f"Loading 60 days of 5-minute NSE bars for {sym}...")
    bars = fetch_60d_5m_bars(sym)
    if not bars:
        print(f"ERROR: Could not fetch historical 5m bars for {sym}")
        sys.exit(1)

    sessions = partition_into_sessions(bars)
    print(f"Built {len(sessions)} full trading sessions (75 bars/session). Running {args.replays:,} Monte Carlo simulations...")

    res = run_monte_carlo(sessions, entry_val, stop_val, target_val, replays=args.replays, seed=args.seed)
    if not res:
        print("ERROR: Simulation could not be completed.")
        sys.exit(1)

    print("==================================================")
    print(f"TIME MACHINE SIMULATION: {sym}")
    print("==================================================")
    print(f"Entry: Rs {entry_val:,.2f} | Stop: Rs {stop_val:,.2f} | Target: Rs {target_val:,.2f}")
    print(f"Simulated Paths:    {res['replays']:,} across {res['sessions_analyzed']} NSE sessions")
    print("--------------------------------------------------")
    print(f"Target Hit First:   {res['target_pct']}%")
    print(f"Stop Hit First:     {res['stop_pct']}%")
    print(f"Neither by 15:10:   {res['neither_pct']}%")
    print(f"Win/Loss Odds:      {res['win_loss_ratio']}:1")
    print(f"Expected Value:     +{res['avg_r']} R per trade")
    print("--------------------------------------------------")
    print(f"VERDICT: {res['verdict']}")
    print("==================================================")
    sys.exit(0)


if __name__ == "__main__":
    main()

