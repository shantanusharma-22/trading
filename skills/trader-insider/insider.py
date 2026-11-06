#!/usr/bin/env python3
"""SEBI Insider Trading & SAST Tracker for trader-insider (Indian Equities - NSE/BSE).
Tracks market-moving insider transactions (Promoter, Director, and Key Management buys/sells)
filed under SEBI (Prohibition of Insider Trading) Regulations and SAST disclosures.
Standard library only.

    python3 insider.py                               # checks watchlist + plan tickers
    python3 insider.py --symbol RELIANCE.NS
    python3 insider.py --min-val 1000000             # min trade value Rs 10 Lakhs
    python3 insider.py --offline sample_pit.json
"""

import argparse
import datetime
import email.utils
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import (
    IST_OFFSET,
    UA,
    create_nse_session_opener,
    normalize_symbol,
    resolve_path,
    to_ist,
)

DEFAULT_STATE = resolve_path("trader/state/insider.json")


_urlopen = urllib.request.urlopen


def fetch_insider_news_rss(sym: str):
    """Fallback intelligence: fetches promoter buying/selling filings via Google News RSS."""
    clean_sym = sym.replace(".NS", "").replace(".BO", "")
    query = urllib.request.quote(f'"{clean_sym}" (promoter OR "insider trading" OR "SAST" OR "bulk deal") NSE')
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    items = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with _urlopen(req, timeout=10) as resp:
            root = ET.fromstring(resp.read())
            for item in root.findall(".//item")[:5]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                if title:
                    items.append({
                        "symbol": normalize_symbol(sym),
                        "source": "SEBI/NSE Corporate Disclosure News",
                        "headline": title,
                        "link": link,
                        "date": pub_date
                    })
    except Exception:
        pass
    return items


def fetch_nse_pit_api():
    """Attempt direct query to NSE PIT endpoint with primed cookie session."""
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading"
    }
    try:
        opener = create_nse_session_opener()
        api_url = "https://www.nseindia.com/api/corporates-pit?index=equities"
        resp = opener.open(urllib.request.Request(api_url, headers=headers), timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("data", [])
    except Exception:
        return []


def main():
    p = argparse.ArgumentParser(description="SEBI Insider Trading & Promoter Activity Tracker")
    p.add_argument("--symbol", help="Filter by specific Indian ticker")
    p.add_argument("--min-val", type=float, default=1000000.0, help="Minimum transaction value in Rs (default 10L)")
    p.add_argument("--offline", help="Path to local cached disclosures JSON")
    args = p.parse_args()

    symbols = []
    if args.symbol:
        symbols.append(normalize_symbol(args.symbol))
    else:
        if os.path.exists("trader/plan.json"):
            try:
                with open("trader/plan.json", "r", encoding="utf-8") as f:
                    symbols.append(json.load(f).get("symbol"))
            except Exception:
                pass
        if os.path.exists("trader/watchlist.json"):
            try:
                with open("trader/watchlist.json", "r", encoding="utf-8") as f:
                    for h in json.load(f).get("hits", []):
                        symbols.append(h.get("symbol"))
            except Exception:
                pass

    symbols = sorted(list(set(normalize_symbol(s) for s in symbols if s)))
    if not symbols:
        symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"]

    print(f"Tracking SEBI PIT & Insider Disclosures for {len(symbols)} symbol(s)...")

    # 1. Check direct NSE PIT API or offline file
    pit_records = []
    if args.offline and os.path.exists(args.offline):
        with open(args.offline, "r", encoding="utf-8") as f:
            pit_records = json.load(f)
    else:
        pit_records = fetch_nse_pit_api()

    matched_records = []
    if pit_records:
        for r in pit_records:
            sec_sym = normalize_symbol(r.get("symbol", ""))
            if sec_sym in symbols:
                val = float(r.get("val", 0) or 0)
                if val >= args.min_val:
                    matched_records.append(r)

    if matched_records:
        print(f"\nFound {len(matched_records)} official SEBI PIT disclosure(s):")
        for r in matched_records:
            print("==================================================")
            print(f"INSIDER TRADE: {r.get('symbol')} | {r.get('acqName', 'Unknown')}")
            print(f"Category:     {r.get('personCategory', 'Promoter/Director')}")
            print(f"Action:       {r.get('tdpTransactionType', 'Market Trade')}")
            print(f"Quantity:     {r.get('secAcq', 0):,} shares (Value: Rs {float(r.get('val', 0)):,.2f})")
            print(f"Date:         {r.get('date', 'Recent')}")
            print("==================================================")
    else:
        # Fallback to corporate action news
        print("No immediate raw PIT filings; checking corporate disclosure feed...")
        for s in symbols:
            news = fetch_insider_news_rss(s)
            for n in news:
                print(f"[{n['symbol']}] {n['headline']}")
                print(f"    Source: {n['source']} | Date: {n['date']}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()

