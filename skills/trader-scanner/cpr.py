#!/usr/bin/env python3
"""Central Pivot Range (CPR) & Camarilla Pivots Engine for trader-scanner (Indian Equities - NSE).
Calculates Pivot (P), Bottom Central (BC), Top Central (TC), CPR Width %,
and Camarilla levels (H3, H4, L3, L4) from previous day's daily bar.
Standard library only.

    python3 cpr.py RELIANCE.NS                       # calculate CPR & Camarilla for Reliance
    python3 cpr.py --universe                        # scan all symbols for Narrow CPR (Trending setups)
    python3 cpr.py RELIANCE.NS TCS.NS --json
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.request

UA = "Mozilla/5.0 (compatible; day-trader-skill-india/1.0; +https://github.com/antigravity)"
DEFAULT_UNIVERSE = "trader/universe.txt"


def normalize_symbol(sym: str) -> str:
    s = sym.strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return s + ".NS"


def fetch_prev_daily_bar(sym):
    norm = normalize_symbol(sym)
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{norm}?range=5d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            chart = data["chart"]["result"][0]
            q = (chart.get("indicators", {}).get("quote") or [{}])[0]
            highs = [h for h in (q.get("high") or []) if h is not None]
            lows = [l for l in (q.get("low") or []) if l is not None]
            closes = [c for c in (q.get("close") or []) if c is not None]

            if len(closes) >= 2:
                # Use yesterday's completed bar (index -2 if market is open today, else -1)
                idx = -2 if len(closes) >= 2 else -1
                return {
                    "high": float(highs[idx]),
                    "low": float(lows[idx]),
                    "close": float(closes[idx])
                }
    except Exception:
        pass
    return None


def calculate_cpr_and_camarilla(high: float, low: float, close: float):
    """Calculate institutional Central Pivot Range (CPR) and Camarilla levels."""
    # 1. Central Pivot Range (CPR)
    pivot = round((high + low + close) / 3.0, 2)
    bc = round((high + low) / 2.0, 2)
    tc = round((pivot - bc) + pivot, 2)

    cpr_top = max(tc, bc)
    cpr_bot = min(tc, bc)
    cpr_width = round(abs(cpr_top - cpr_bot), 2)
    cpr_width_pct = round((cpr_width / pivot) * 100, 2) if pivot > 0 else 0.0

    # Narrow CPR < 0.25% indicates high trending probability
    cpr_classification = "NARROW (High Trend / Breakout Probability 🚀)" if cpr_width_pct <= 0.25 else \
                         "MEDIUM (Normal Day)" if cpr_width_pct <= 0.50 else \
                         "WIDE (Sideways / Mean Reversion Day ⚠️)"

    # 2. Camarilla Pivots (LODR / Intraday levels)
    rng = high - low
    h4 = round(close + (rng * 1.1 / 2.0), 2)  # Breakout Buy level
    h3 = round(close + (rng * 1.1 / 4.0), 2)  # Reversal Resistance
    l3 = round(close - (rng * 1.1 / 4.0), 2)  # Reversal Support
    l4 = round(close - (rng * 1.1 / 2.0), 2)  # Breakdown Short level

    return {
        "pivot": pivot,
        "tc": cpr_top,
        "bc": cpr_bot,
        "cpr_width": cpr_width,
        "cpr_width_pct": cpr_width_pct,
        "cpr_type": cpr_classification,
        "camarilla": {
            "h4_breakout": h4,
            "h3_resistance": h3,
            "l3_support": l3,
            "l4_breakdown": l4
        }
    }


def analyze_symbol(sym):
    norm = normalize_symbol(sym)
    bar = fetch_prev_daily_bar(norm)
    if not bar:
        return {"error": f"Could not fetch daily bar for {norm}"}
    res = calculate_cpr_and_camarilla(bar["high"], bar["low"], bar["close"])
    res["symbol"] = norm
    res["prev_high"] = round(bar["high"], 2)
    res["prev_low"] = round(bar["low"], 2)
    res["prev_close"] = round(bar["close"], 2)
    return res


def main():
    p = argparse.ArgumentParser(description="Central Pivot Range (CPR) & Camarilla Engine")
    p.add_argument("symbols", nargs="*", help="Stock ticker(s)")
    p.add_argument("--universe", action="store_true", help="Scan universe for Narrow CPR stocks")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    symbols = []
    if args.universe:
        if os.path.exists(DEFAULT_UNIVERSE):
            with open(DEFAULT_UNIVERSE, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("|")
                    if parts and parts[0]:
                        symbols.append(parts[0])
        else:
            symbols = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "TATAMOTORS.NS", "ICICIBANK.NS"]
    elif args.symbols:
        symbols = [normalize_symbol(s) for s in args.symbols]
    else:
        symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]

    results = []
    print(f"Calculating CPR & Camarilla Pivot Levels for {len(symbols)} symbol(s)...")
    for s in symbols:
        res = analyze_symbol(s)
        if "error" not in res:
            results.append(res)
            if not args.json:
                print("==================================================")
                print(f"CPR & CAMARILLA REPORT: {res['symbol']}")
                print("==================================================")
                print(f"Prev Day Range:      Rs {res['prev_low']:,.2f} - Rs {res['prev_high']:,.2f} (Close: Rs {res['prev_close']:,.2f})")
                print(f"Central Pivot (P):   Rs {res['pivot']:,.2f}")
                print(f"Top Central (TC):    Rs {res['tc']:,.2f}")
                print(f"Bottom Central (BC): Rs {res['bc']:,.2f}")
                print(f"CPR Width:           Rs {res['cpr_width']:.2f} ({res['cpr_width_pct']}%)")
                print(f"Day Setup Bias:      {res['cpr_type']}")
                print("--------------------------------------------------")
                print(f"Camarilla H4 (Breakout Buy):  Rs {res['camarilla']['h4_breakout']:,.2f}")
                print(f"Camarilla H3 (Resistance):    Rs {res['camarilla']['h3_resistance']:,.2f}")
                print(f"Camarilla L3 (Support):       Rs {res['camarilla']['l3_support']:,.2f}")
                print(f"Camarilla L4 (Breakdown):     Rs {res['camarilla']['l4_breakdown']:,.2f}")
                print("==================================================\n")
        time.sleep(0.3)

    if args.json:
        print(json.dumps(results, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()

