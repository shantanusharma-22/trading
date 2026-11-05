#!/usr/bin/env python3
"""News Monitor for trader-news (Indian Equities - NSE/BSE).
Watches live breaking news and corporate headlines for Indian stocks from Yahoo Finance India
and Google News India RSS feeds. Standard library only.

    python3 news.py                                  # watches watchlist + plan tickers
    python3 news.py --tickers RELIANCE.NS TCS.NS
    python3 news.py --tickers INFY.NS --all          # show all news, seen or not
"""

import argparse
import datetime
import email.utils
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (compatible; day-trader-skill-india/1.0; +https://github.com/antigravity)"
DEFAULT_NEWS_STATE = "trader/state/news.json"
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)


def to_ist(utc):
    return utc.replace(tzinfo=None) + IST_OFFSET


def normalize_symbol(sym: str) -> str:
    s = sym.strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return s + ".NS"


_urlopen = urllib.request.urlopen


def clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def fetch_yahoo_rss(sym: str):
    norm = normalize_symbol(sym)
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={norm}&region=IN&lang=en-IN"
    items = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with _urlopen(req, timeout=10) as resp:
            root = ET.fromstring(resp.read())
            for item in root.findall(".//item"):
                title = clean_html(item.findtext("title", ""))
                link = item.findtext("link", "")
                pub_date_str = item.findtext("pubDate", "")
                if title:
                    dt = None
                    if pub_date_str:
                        try:
                            parsed_tuple = email.utils.parsedate_to_datetime(pub_date_str)
                            dt = to_ist(parsed_tuple)
                        except Exception:
                            pass
                    items.append({
                        "source": "Yahoo India",
                        "symbol": norm,
                        "title": title,
                        "link": link,
                        "time": dt.strftime("%Y-%m-%d %H:%M IST") if dt else "Recent"
                    })
    except Exception:
        pass
    return items


def fetch_google_news_rss(sym: str):
    clean_sym = sym.replace(".NS", "").replace(".BO", "")
    query = urllib.request.quote(f"{clean_sym} share price NSE")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    items = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with _urlopen(req, timeout=10) as resp:
            root = ET.fromstring(resp.read())
            for item in root.findall(".//item")[:5]:
                title = clean_html(item.findtext("title", ""))
                link = item.findtext("link", "")
                pub_date_str = item.findtext("pubDate", "")
                if title:
                    dt = None
                    if pub_date_str:
                        try:
                            parsed_tuple = email.utils.parsedate_to_datetime(pub_date_str)
                            dt = to_ist(parsed_tuple)
                        except Exception:
                            pass
                    items.append({
                        "source": "Google News India",
                        "symbol": normalize_symbol(sym),
                        "title": title,
                        "link": link,
                        "time": dt.strftime("%Y-%m-%d %H:%M IST") if dt else "Recent"
                    })
    except Exception:
        pass
    return items


def tag_news(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ["q1", "q2", "q3", "q4", "earnings", "profit", "revenue", "results"]):
        return "EARNINGS"
    if any(k in t for k in ["acquire", "merger", "stake", "buyout", "deal", "takeover"]):
        return "DEAL/M&A"
    if any(k in t for k in ["sebi", "rbi", "penalty", "order", "court", "tribunal", "nclt"]):
        return "REGULATORY"
    if any(k in t for k in ["dividend", "bonus", "split", "buyback"]):
        return "CORPORATE ACTION"
    if any(k in t for k in ["target", "upgrade", "downgrade", "brokerage", "rating"]):
        return "ANALYST"
    return "GENERAL"


def main():
    p = argparse.ArgumentParser(description="News Monitor for Indian Equities")
    p.add_argument("--tickers", nargs="*", help="Specific stock tickers")
    p.add_argument("--all", action="store_true", help="Display all headlines, ignoring seen state")
    args = p.parse_args()

    symbols = []
    if args.tickers:
        symbols = [normalize_symbol(s) for s in args.tickers]
    else:
        # Load from watchlist & plan
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

    # Seen cache
    seen = {}
    if not args.all and os.path.exists(DEFAULT_NEWS_STATE):
        try:
            with open(DEFAULT_NEWS_STATE, "r", encoding="utf-8") as f:
                seen = json.load(f)
        except Exception:
            pass

    print(f"Monitoring breaking news for {len(symbols)} Indian stock(s)...")
    all_news = []
    for s in symbols:
        news_items = fetch_yahoo_rss(s)
        if not news_items:
            news_items = fetch_google_news_rss(s)
        all_news.extend(news_items)

    new_count = 0
    for n in all_news:
        h = hashlib.md5((n["symbol"] + n["title"]).encode("utf-8")).hexdigest()
        if not args.all and h in seen:
            continue
        seen[h] = True
        new_count += 1
        tag = tag_news(n["title"])
        print(f"[{n['symbol']}] [{tag}] {n['title']} ({n['time']})")
        print(f"    Source: {n['source']} | Link: {n['link']}\n")

    if not args.all and new_count > 0:
        os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_NEWS_STATE)), exist_ok=True)
        with open(DEFAULT_NEWS_STATE, "w", encoding="utf-8") as f:
            json.dump(seen, f)

    if new_count == 0:
        print("No new breaking headlines since last check.")
    sys.exit(0)


if __name__ == "__main__":
    main()

