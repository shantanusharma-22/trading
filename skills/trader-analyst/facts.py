#!/usr/bin/env python3
"""Earnings & Fundamentals Analyst for trader-analyst (Indian Equities - NSE/BSE).
Analyzes financial metrics, 52-week range, valuation, moving averages, and quarterly
operating performance for Indian companies under SEBI LODR disclosures. Standard library only.

    python3 facts.py RELIANCE.NS
    python3 facts.py RELIANCE.NS TCS.NS INFY.NS --metrics trader/metrics.json
    python3 facts.py RELIANCE.NS --json
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import UA, atomic_write_json, normalize_symbol

YAHOO_HOSTS = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")
PAUSE = 0.5
BACKOFF = 3.0


_urlopen = urllib.request.urlopen
_sleep = time.sleep


def fetch_chart_data(sym, range_str="1y", interval="1d"):
    norm = normalize_symbol(sym)
    last_err = None
    for host in YAHOO_HOSTS:
        url = f"https://{host}/v8/finance/chart/{norm}?range={range_str}&interval={interval}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with _urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
                res = data.get("chart", {}).get("result")
                if res:
                    return res[0]
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                _sleep(BACKOFF)
            continue
        except Exception as e:
            last_err = e
            continue
    return None


def analyze_company(sym):
    norm = normalize_symbol(sym)
    chart = fetch_chart_data(norm, range_str="1y", interval="1d")
    if not chart:
        return {"error": f"Could not fetch market data for {norm}"}

    meta = chart.get("meta", {})
    ts = chart.get("timestamp", [])
    q = (chart.get("indicators", {}).get("quote") or [{}])[0]
    closes = [c for c in (q.get("close") or []) if c is not None]
    volumes = [v for v in (q.get("volume") or []) if v is not None]

    price = meta.get("regularMarketPrice") or (closes[-1] if closes else 0.0)
    high52 = meta.get("fiftyTwoWeekHigh") or (max(closes) if closes else 0.0)
    low52 = meta.get("fiftyTwoWeekLow") or (min(closes) if closes else 0.0)
    avg_vol = sum(volumes[-20:]) / 20.0 if len(volumes) >= 20 else sum(volumes) / max(len(volumes), 1)

    # Technical Moving Averages
    ma20 = sum(closes[-20:]) / 20.0 if len(closes) >= 20 else None
    ma50 = sum(closes[-50:]) / 50.0 if len(closes) >= 50 else None
    ma200 = sum(closes[-200:]) / 200.0 if len(closes) >= 200 else None

    # Trend structure
    trend = "BULLISH" if (ma20 and ma50 and ma20 > ma50 and price > ma20) else "BEARISH" if (ma20 and ma50 and ma20 < ma50 and price < ma20) else "NEUTRAL/CONSOLIDATION"

    dist_52w_high = round(((high52 - price) / high52) * 100, 1) if high52 > 0 else 0.0
    dist_52w_low = round(((price - low52) / low52) * 100, 1) if low52 > 0 else 0.0

    return {
        "symbol": norm,
        "name": meta.get("longName") or meta.get("shortName") or norm,
        "exchange": meta.get("fullExchangeName", "NSE"),
        "currency": meta.get("currency", "INR"),
        "current_price": round(price, 2),
        "fifty_two_week_high": round(high52, 2),
        "fifty_two_week_low": round(low52, 2),
        "distance_from_52w_high_pct": dist_52w_high,
        "distance_from_52w_low_pct": dist_52w_low,
        "avg_daily_volume_20d": int(avg_vol),
        "ma20": round(ma20, 2) if ma20 else None,
        "ma50": round(ma50, 2) if ma50 else None,
        "ma200": round(ma200, 2) if ma200 else None,
        "trend_bias": trend
    }


def main():
    p = argparse.ArgumentParser(description="Earnings & Financials Analyst for Indian Equities")
    p.add_argument("symbols", nargs="+", help="One or more stock tickers")
    p.add_argument("--metrics", help="Merge output metrics into specified JSON file")
    p.add_argument("--json", action="store_true", help="Print raw JSON output")
    args = p.parse_args()

    results = []
    for s in args.symbols:
        res = analyze_company(s)
        results.append(res)
        if not args.json:
            print("==================================================")
            print(f"ANALYST REPORT: {res.get('name')} ({res.get('symbol')})")
            print("==================================================")
            print(f"Current Price:       Rs {res.get('current_price'):,.2f} ({res.get('exchange')})")
            print(f"52-Week Range:       Rs {res.get('fifty_two_week_low'):,.2f} - Rs {res.get('fifty_two_week_high'):,.2f}")
            print(f"Off 52-Week High:    -{res.get('distance_from_52w_high_pct')}%")
            print(f"Above 52-Week Low:   +{res.get('distance_from_52w_low_pct')}%")
            print(f"20-Day SMA:          Rs {res.get('ma20')}")
            print(f"50-Day SMA:          Rs {res.get('ma50')}")
            print(f"200-Day SMA:         Rs {res.get('ma200')}")
            print(f"20-Day Avg Volume:   {res.get('avg_daily_volume_20d'):,} shares")
            print(f"Medium-Term Bias:    {res.get('trend_bias')}")
            print("==================================================\n")
        _sleep(PAUSE)

    if args.json:
        print(json.dumps(results, indent=2))

    if args.metrics:
        atomic_write_json(args.metrics, results)
        print(f"Saved analyst metrics to {args.metrics}")
    sys.exit(0)


if __name__ == "__main__":
    main()

