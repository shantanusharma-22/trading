#!/usr/bin/env python3
"""Live Nifty 50 Advance-Decline (A/D) Market Breadth Barometer for trader-scanner (NSE).
Measures real-time institutional participation across Nifty 50 constituents.
Blocks or warns against taking long breakouts when the broader market breadth is negative.
Standard library only. Writes trader/state/breadth.json.

    python3 breadth.py                               # evaluate current Nifty 50 breadth
    python3 breadth.py --json                        # export breadth JSON
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.request

UA = "Mozilla/5.0 (compatible; day-trader-skill-india/1.0; +https://github.com/antigravity)"
DEFAULT_BREADTH_STATE = "trader/state/breadth.json"
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)

NIFTY_50_CORE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "BHARTIARTL.NS", "SBIN.NS", "ITC.NS", "HINDUNILVR.NS", "LT.NS",
    "BAJFINANCE.NS", "HCLTECH.NS", "MARUTI.NS", "SUNPHARMA.NS", "ADANIENT.NS",
    "TATAMOTORS.NS", "KOTAKBANK.NS", "TITAN.NS", "ONGC.NS", "NTPC.NS",
    "AXISBANK.NS", "POWERGRID.NS", "ADANIPORTS.NS", "COALINDIA.NS", "BAJAJFINSV.NS",
    "M&M.NS", "ULTRACEMCO.NS", "ASIANPAINT.NS", "NESTLEIND.NS", "JSWSTEEL.NS",
    "TATASTEEL.NS", "TECHM.NS", "WIPRO.NS", "HINDALCO.NS", "CIPLA.NS"
]


def to_ist(utc):
    return utc.replace(tzinfo=None) + IST_OFFSET


def fetch_quote_change(sym):
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            meta = data["chart"]["result"][0]["meta"]
            curr = meta.get("regularMarketPrice", 0.0)
            prev = meta.get("previousClose") or meta.get("chartPreviousClose", 0.0)
            if prev > 0:
                pct = round(((curr - prev) / prev) * 100, 2)
                return {"symbol": sym, "price": curr, "change_pct": pct}
    except Exception:
        pass
    return None


def calculate_breadth(symbols=None):
    if not symbols:
        symbols = NIFTY_50_CORE

    advances = []
    declines = []
    unchanged = []

    for s in symbols:
        res = fetch_quote_change(s)
        if res:
            pct = res["change_pct"]
            if pct > 0.05:
                advances.append(res)
            elif pct < -0.05:
                declines.append(res)
            else:
                unchanged.append(res)
        time.sleep(0.15)

    tot = len(advances) + len(declines) + len(unchanged)
    if tot == 0:
        return None

    ad_ratio = round(len(advances) / max(len(declines), 1), 2)

    # Classification
    if len(advances) >= 25 and ad_ratio >= 2.0:
        bias = "STRONG_BULLISH (Aggressive Long Breakouts Approved 🟢)"
    elif len(advances) >= 20 and ad_ratio >= 1.2:
        bias = "MILD_BULLISH (Normal Breakouts Approved 🟢)"
    elif len(declines) >= 25 and ad_ratio <= 0.6:
        bias = "HEAVY_BEARISH (Long Breakouts High Failure Risk 🔴)"
    else:
        bias = "NEUTRAL / MIXED CHOP (Selective Trading Only ⚪)"

    now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
    return {
        "as_of_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S"),
        "total_monitored": tot,
        "advances": len(advances),
        "declines": len(declines),
        "unchanged": len(unchanged),
        "ad_ratio": ad_ratio,
        "market_breadth_bias": bias,
        "top_gainers": sorted(advances, key=lambda x: x["change_pct"], reverse=True)[:5],
        "top_losers": sorted(declines, key=lambda x: x["change_pct"])[:5]
    }


def main():
    p = argparse.ArgumentParser(description="Nifty 50 Advance-Decline Market Breadth Barometer")
    p.add_argument("--json", action="store_true")
    p.add_argument("--limit", type=int, default=35, help="Number of constituents to check")
    args = p.parse_args()

    print(f"Sampling real-time Nifty 50 Advance/Decline breadth...")
    res = calculate_breadth(NIFTY_50_CORE[:args.limit])
    if not res:
        print("ERROR: Could not compute market breadth.")
        sys.exit(1)

    print("==================================================")
    print("NIFTY 50 MARKET BREADTH BAROMETER (NSE)")
    print("==================================================")
    print(f"Timestamp:       {res['as_of_ist']} IST")
    print(f"Monitored:       {res['total_monitored']} Large-Caps")
    print(f"Advances:        {res['advances']} 🟢 | Declines: {res['declines']} 🔴 | Unchanged: {res['unchanged']}")
    print(f"A/D Ratio:       {res['ad_ratio']}:1")
    print(f"Market Regime:   {res['market_breadth_bias']}")
    print("--------------------------------------------------")
    if res.get("top_gainers"):
        print("Leading Gainers: " + ", ".join(f"{g['symbol']} (+{g['change_pct']}%)" for g in res['top_gainers']))
    if res.get("top_losers"):
        print("Leading Draggers:" + ", ".join(f"{l['symbol']} ({l['change_pct']}%)" for l in res['top_losers']))
    print("==================================================")

    os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_BREADTH_STATE)), exist_ok=True)
    with open(DEFAULT_BREADTH_STATE, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)

    if args.json:
        print(json.dumps(res, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()

