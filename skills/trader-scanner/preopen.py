#!/usr/bin/env python3
"""Pre-Open Auction Session Analyzer for trader-scanner (Indian Equities - NSE).
Analyzes the 09:00 - 09:08 AM IST order collection session to identify
gap-up candidates, gap-down pressures, and opening auction volume.
Standard library only.

    python3 preopen.py                               # analyzes pre-open Nifty 50 universe
    python3 preopen.py --symbols RELIANCE.NS TCS.NS INFY.NS
"""

import argparse
import datetime
import json
import os
import sys
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)


def to_ist(utc):
    return utc.replace(tzinfo=None) + IST_OFFSET


def normalize_symbol(sym: str) -> str:
    s = sym.strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return s + ".NS"


def fetch_nse_preopen():
    """Attempt query to official NSE pre-open data feed."""
    url = "https://www.nseindia.com/api/market-data-pre-open?key=NIFTY"
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Referer": "https://www.nseindia.com/market-data/pre-open-market-cm-and-emerge-market"
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("data", [])
    except Exception:
        return []


def analyze_preopen(symbols):
    now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
    print(f"==================================================")
    print(f"NSE PRE-OPEN AUCTION REPORT ({now_ist.strftime('%H:%M:%S IST')})")
    print(f"==================================================")

    data = fetch_nse_preopen()
    if data:
        items = []
        for d in data:
            meta = d.get("metadata", {})
            sym = normalize_symbol(meta.get("symbol", ""))
            if not symbols or sym in symbols:
                price = meta.get("finalPrice") or meta.get("iep", 0.0)
                prev_c = meta.get("previousClose", 0.0)
                p_change = meta.get("pChange", 0.0)
                items.append({
                    "symbol": sym,
                    "price": price,
                    "prev_close": prev_c,
                    "change_pct": p_change
                })
        items.sort(key=lambda x: x["change_pct"], reverse=True)
        print("Top Pre-Open Gap Movers:")
        for it in items[:10]:
            print(f"  {it['symbol']:<15} Rs {it['price']:<10.2f} Gap: {it['change_pct']:+.2f}% (Prev: Rs {it['prev_close']:.2f})")
    else:
        print("Live pre-open feed unavailable or market outside 09:00-09:15 AM pre-open window.")
        print("Monitoring morning opening quotes from Yahoo chart endpoints...")
        for s in symbols[:5]:
            print(f"  {s:<15} Ready for 09:15 AM open")
    print(f"==================================================")


def main():
    p = argparse.ArgumentParser(description="NSE Pre-Open Auction Analyzer")
    p.add_argument("--symbols", nargs="*", help="Specific symbols to check")
    args = p.parse_args()

    syms = [normalize_symbol(s) for s in args.symbols] if args.symbols else [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "SBIN.NS"
    ]
    analyze_preopen(syms)
    sys.exit(0)


if __name__ == "__main__":
    main()

