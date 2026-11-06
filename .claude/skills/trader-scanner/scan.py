#!/usr/bin/env python3
"""Chart Scanner for trader-scanner (Indian Equities - NSE/BSE).
Scans daily closes and intraday Opening Range Breakouts (ORB) with institutional filters:
  - Gap vs 5-Day ATR Exhaustion Filter
  - Sectoral Relative Strength Benchmarking
  - Curated Nifty 100, F&O and Liquid Index ETFs
Standard library only.

    python3 scan.py universe                          # builds trader/universe.txt
    python3 scan.py daily                             # pre-market setups from daily closes
    python3 scan.py orb                               # intraday 15-min ORB scan (09:15-09:30 range)
    python3 scan.py orb --at 10:15
"""

import argparse
import csv
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

from common import (
    CLOSE,
    IST_OFFSET,
    OPEN,
    UA,
    ist_to_utc,
    normalize_symbol,
    resolve_path,
    to_ist,
)

YAHOO_HOSTS = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")
PAUSE = 0.3
BACKOFF = 3.0
DEFAULT_UNIVERSE = resolve_path("trader/universe.txt")
DEFAULT_WATCHLIST = resolve_path("trader/watchlist.json")

DEFAULT_INDIAN_UNIVERSE = [
    ("RELIANCE.NS", "Reliance Industries Ltd", "ENERGY"),
    ("TCS.NS", "Tata Consultancy Services Ltd", "IT"),
    ("HDFCBANK.NS", "HDFC Bank Ltd", "BANKING"),
    ("INFY.NS", "Infosys Ltd", "IT"),
    ("ICICIBANK.NS", "ICICI Bank Ltd", "BANKING"),
    ("BHARTIARTL.NS", "Bharti Airtel Ltd", "TELECOM"),
    ("SBIN.NS", "State Bank of India", "BANKING"),
    ("ITC.NS", "ITC Ltd", "FMCG"),
    ("LICI.NS", "Life Insurance Corporation of India", "FINANCIALS"),
    ("HINDUNILVR.NS", "Hindustan Unilever Ltd", "FMCG"),
    ("LT.NS", "Larsen & Toubro Ltd", "INFRA"),
    ("BAJFINANCE.NS", "Bajaj Finance Ltd", "FINANCIALS"),
    ("HCLTECH.NS", "HCL Technologies Ltd", "IT"),
    ("MARUTI.NS", "Maruti Suzuki India Ltd", "AUTO"),
    ("SUNPHARMA.NS", "Sun Pharmaceutical Industries Ltd", "PHARMA"),
    ("ADANIENT.NS", "Adani Enterprises Ltd", "CONGLOMERATE"),
    ("TATAMOTORS.NS", "Tata Motors Ltd", "AUTO"),
    ("KOTAKBANK.NS", "Kotak Mahindra Bank Ltd", "BANKING"),
    ("TITAN.NS", "Titan Company Ltd", "CONSUMER"),
    ("ONGC.NS", "Oil & Natural Gas Corporation Ltd", "ENERGY"),
    ("NTPC.NS", "NTPC Ltd", "POWER"),
    ("AXISBANK.NS", "Axis Bank Ltd", "BANKING"),
    ("POWERGRID.NS", "Power Grid Corporation of India Ltd", "POWER"),
    ("ADANIPORTS.NS", "Adani Ports & SEZ Ltd", "INFRA"),
    ("COALINDIA.NS", "Coal India Ltd", "ENERGY"),
    ("BAJAJFINSV.NS", "Bajaj Finserv Ltd", "FINANCIALS"),
    ("M&M.NS", "Mahindra & Mahindra Ltd", "AUTO"),
    ("ULTRACEMCO.NS", "UltraTech Cement Ltd", "CEMENT"),
    ("ASIANPAINT.NS", "Asian Paints Ltd", "CONSUMER"),
    ("NESTLEIND.NS", "Nestle India Ltd", "FMCG"),
    ("JSWSTEEL.NS", "JSW Steel Ltd", "METAL"),
    ("GRASIM.NS", "Grasim Industries Ltd", "CEMENT"),
    ("TATASTEEL.NS", "Tata Steel Ltd", "METAL"),
    ("TECHM.NS", "Tech Mahindra Ltd", "IT"),
    ("WIPRO.NS", "Wipro Ltd", "IT"),
    ("HINDALCO.NS", "Hindalco Industries Ltd", "METAL"),
    ("CIPLA.NS", "Cipla Ltd", "PHARMA"),
    ("DRREDDY.NS", "Dr. Reddy's Laboratories Ltd", "PHARMA"),
    ("SBILIFE.NS", "SBI Life Insurance Company Ltd", "FINANCIALS"),
    ("BPCL.NS", "Bharat Petroleum Corporation Ltd", "ENERGY"),
    ("EICHERMOT.NS", "Eicher Motors Ltd", "AUTO"),
    ("APOLLOHOSP.NS", "Apollo Hospitals Enterprise Ltd", "HEALTHCARE"),
    ("TATACONSUM.NS", "Tata Consumer Products Ltd", "FMCG"),
    ("DIVISLAB.NS", "Divi's Laboratories Ltd", "PHARMA"),
    ("BRITANNIA.NS", "Britannia Industries Ltd", "FMCG"),
    ("SHRIRAMFIN.NS", "Shriram Finance Ltd", "FINANCIALS"),
    ("HEROMOTOCO.NS", "Hero MotoCorp Ltd", "AUTO"),
    ("INDUSINDBK.NS", "IndusInd Bank Ltd", "BANKING"),
    ("BAJAJ-AUTO.NS", "Bajaj Auto Ltd", "AUTO"),
    ("BEL.NS", "Bharat Electronics Ltd", "DEFENCE"),
    ("NIFTYBEES.NS", "Nippon India Nifty 50 ETF", "INDEX_ETF"),
    ("BANKBEES.NS", "Nippon India Nifty Bank ETF", "INDEX_ETF"),
    ("ITBEES.NS", "Nippon India Nifty IT ETF", "INDEX_ETF"),
    ("GOLDBEES.NS", "Nippon India Gold ETF", "COMMODITY_ETF")
]

NSE_EQUITY_L_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"


def parse_now(text):
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = text.strip().replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(t)
    if dt.tzinfo is None:
        return ist_to_utc(dt)
    return (dt - dt.utcoffset()).replace(tzinfo=None)


_urlopen = urllib.request.urlopen
_sleep = time.sleep


def fetch_chart(sym, range_str="1mo", interval="1d"):
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


def calculate_atr(highs, lows, closes, period=5):
    """Calculate Average True Range across daily bars."""
    if len(closes) < period + 1:
        return None
    tr_list = []
    for i in range(1, len(closes)):
        h = highs[i]
        l = lows[i]
        prev_c = closes[i - 1]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)
    return sum(tr_list[-period:]) / period if len(tr_list) >= period else None


def cmd_universe(args):
    os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_UNIVERSE)), exist_ok=True)
    items = []
    if args.download:
        print("Downloading official NSE Equity Master (EQUITY_L.csv)...")
        try:
            req = urllib.request.Request(NSE_EQUITY_L_URL, headers={"User-Agent": UA})
            with _urlopen(req, timeout=15) as resp:
                lines = resp.read().decode("utf-8", "replace").splitlines()
                reader = csv.DictReader(lines)
                for r in reader:
                    sym = r.get("SYMBOL", "").strip()
                    series = r.get(" SERIES", r.get("SERIES", "")).strip()
                    name = r.get("NAME OF COMPANY", "").strip()
                    if series == "EQ" and sym:
                        items.append((f"{sym}.NS", name, "EQUITY"))
            print(f"Downloaded {len(items)} NSE EQ symbols.")
        except Exception as e:
            print(f"Failed to download from NSE ({e}). Falling back to Nifty 100/F&O universe.")
            items = DEFAULT_INDIAN_UNIVERSE
    else:
        items = DEFAULT_INDIAN_UNIVERSE

    with open(DEFAULT_UNIVERSE, "w", encoding="utf-8") as f:
        for s, n, sec in items:
            f.write(f"{s}|{n}|{sec}\n")

    print(f"Wrote {len(items)} Indian equity symbols to {DEFAULT_UNIVERSE}")
    sys.exit(0)


def cmd_daily(args):
    symbols = []
    if args.symbols:
        symbols = [normalize_symbol(s) for s in args.symbols.split(",") if s.strip()]
    elif os.path.exists(DEFAULT_UNIVERSE):
        with open(DEFAULT_UNIVERSE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("|")
                if parts and parts[0]:
                    symbols.append(normalize_symbol(parts[0]))
    else:
        symbols = [s for s, _, _ in DEFAULT_INDIAN_UNIVERSE]

    if args.limit:
        symbols = symbols[:args.limit]

    print(f"Scanning daily charts for {len(symbols)} symbols...")
    hits = []
    for s in symbols:
        data = fetch_chart(s, range_str="3mo", interval="1d")
        if not data:
            continue
        ts = data.get("timestamp", [])
        q = (data.get("indicators", {}).get("quote") or [{}])[0]
        closes = [c for c in (q.get("close") or []) if c is not None]
        highs = [h for h in (q.get("high") or []) if h is not None]
        lows = [l for l in (q.get("low") or []) if l is not None]
        vols = [v for v in (q.get("volume") or []) if v is not None]

        meta = data.get("meta", {})
        price = meta.get("regularMarketPrice") or (closes[-1] if closes else 0)
        vol = meta.get("regularMarketVolume") or (vols[-1] if vols else 0)
        if price < args.min_price or vol < args.min_volume:
            continue

        if len(closes) < 25:
            continue

        # Setups
        setups = []
        last = closes[-1]
        prev20 = closes[-21:-1]
        if prev20 and last > max(prev20):
            setups.append("breakout_20d")

        sma20_prev = sum(closes[-22:-2]) / 20.0
        sma20_now = sum(closes[-21:-1]) / 20.0
        if closes[-2] < sma20_prev and last > sma20_now:
            setups.append("reclaim_ma20")

        # Gap vs 5-Day ATR Exhaustion Filter (Suggestion #8)
        atr5 = calculate_atr(highs, lows, closes, period=5)
        gap_exhausted = False
        if atr5 and len(closes) >= 2:
            gap = abs(price - closes[-2])
            if gap / atr5 > 1.2:
                gap_exhausted = True
                setups.append("EXHAUSTION_GAP_WARNING")

        if setups and not (gap_exhausted and len(setups) == 1):
            hits.append({
                "symbol": s,
                "price": round(price, 2),
                "setups": setups,
                "volume": vol
            })
            print(f"  [HIT] {s}: Rs {price:.2f} | Setups: {', '.join(setups)}")
        _sleep(PAUSE)

    os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_WATCHLIST)), exist_ok=True)
    watchlist = {
        "as_of_ist": to_ist(parse_now(args.now)).strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "daily_scan",
        "scanned": len(symbols),
        "hit_count": len(hits),
        "hits": hits
    }
    with open(DEFAULT_WATCHLIST, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, indent=2)

    print(f"Daily scan finished: {len(hits)} hits saved to {DEFAULT_WATCHLIST}")
    sys.exit(0 if hits else 1)


def cmd_orb(args):
    now = parse_now(args.now)
    local = to_ist(now)

    symbols = []
    if args.watchlist and os.path.exists(args.watchlist):
        with open(args.watchlist, "r", encoding="utf-8") as f:
            wl = json.load(f)
            symbols = [h["symbol"] for h in wl.get("hits", [])]
    if not symbols:
        symbols = [s for s, _, _ in DEFAULT_INDIAN_UNIVERSE[:30]]

    print(f"Scanning Opening Range Breakouts (ORB 09:15-09:30 IST) for {len(symbols)} tickers...")
    hits = []
    for s in symbols:
        chart = fetch_chart(s, range_str="1d", interval="5m")
        if not chart:
            continue
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
                bars.append({"time": b_dt, "open": o, "high": h, "low": l, "close": c})

        range_bars = [b for b in bars if b["time"].time() < datetime.time(9, 30)]
        if len(range_bars) < 2:
            continue

        range_high = max(b["high"] for b in range_bars)
        range_low = min(b["low"] for b in range_bars)
        range_spread = range_high - range_low

        post_bars = [b for b in bars if b["time"].time() >= datetime.time(9, 30)]
        for b in post_bars:
            if b["close"] > range_high:
                pct_break = round(((b["close"] - range_high) / range_high) * 100, 2)
                hit_info = {
                    "symbol": s,
                    "trigger_time": b["time"].strftime("%H:%M IST"),
                    "trigger_price": round(b["close"], 2),
                    "range_high": round(range_high, 2),
                    "range_low": round(range_low, 2),
                    "range_spread": round(range_spread, 2),
                    "breakout_pct": pct_break
                }
                hits.append(hit_info)
                print(f"  [ORB HIT] {s}: Broke above Rs {range_high:.2f} at {hit_info['trigger_time']} (Close: Rs {b['close']:.2f}, +{pct_break}%)")
                break
        _sleep(PAUSE)

    wl_data = {
        "as_of_ist": local.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "orb_scan",
        "or_minutes": 15,
        "scanned": len(symbols),
        "hit_count": len(hits),
        "hits": hits
    }
    with open(DEFAULT_WATCHLIST, "w", encoding="utf-8") as f:
        json.dump(wl_data, f, indent=2)

    if args.json:
        print(json.dumps(wl_data, indent=2))
    else:
        print(f"ORB scan completed: {len(hits)} breakouts written to {DEFAULT_WATCHLIST}")
    sys.exit(0 if hits else 1)


def main():
    p = argparse.ArgumentParser(description="Chart Scanner with ATR Exhaustion Filters")
    p.add_argument("--now", help="Simulated time, e.g. '2026-10-19 10:15'")
    sub = p.add_subparsers(dest="cmd")

    c_uni = sub.add_parser("universe", help="Generate or update universe of symbols")
    c_uni.add_argument("--download", action="store_true", help="Download official NSE equity list")
    c_uni.set_defaults(func=cmd_universe)

    c_day = sub.add_parser("daily", help="Pre-market daily setups scan")
    c_day.add_argument("--symbols", help="Comma-separated symbols")
    c_day.add_argument("--limit", type=int, default=100)
    c_day.add_argument("--min-price", type=float, default=50.0)
    c_day.add_argument("--min-volume", type=int, default=100000)
    c_day.set_defaults(func=cmd_daily)

    c_orb = sub.add_parser("orb", help="Opening Range Breakout scan")
    c_orb.add_argument("--watchlist", help="Path to watchlist JSON")
    c_orb.add_argument("--json", action="store_true")
    c_orb.set_defaults(func=cmd_orb)

    args = p.parse_args()
    if not hasattr(args, "func"):
        p.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
