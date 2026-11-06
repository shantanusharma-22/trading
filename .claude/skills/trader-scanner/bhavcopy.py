#!/usr/bin/env python3
"""EOD Bhavcopy Downloader & Delivery Ranker for trader-scanner (Indian Equities - NSE).
Downloads and analyzes NSE Bhavcopy to identify institutional accumulation (high delivery %).
Standard library only.

    python3 bhavcopy.py --download                   # download today's/latest Bhavcopy
    python3 bhavcopy.py --rank --min-delivery 60     # find stocks with >60% delivery
"""

import argparse
import csv
import datetime
import io
import json
import os
import sys
import urllib.request
import zipfile

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import UA, resolve_path

BHAV_DIR = resolve_path("trader/data/bhavcopy")


def get_latest_bhav_url(date_obj):
    # Form: https://archives.nseindia.com/products/content/sec_bhavdata_full_03112026.csv
    d_str = date_obj.strftime("%d%m%Y")
    return f"https://archives.nseindia.com/products/content/sec_bhavdata_full_{d_str}.csv"


def download_bhavcopy(target_date):
    os.makedirs(BHAV_DIR, exist_ok=True)
    d = target_date
    for _ in range(5):
        if d.weekday() < 5:  # skip weekends
            url = get_latest_bhav_url(d)
            dest = os.path.join(BHAV_DIR, f"sec_bhavdata_{d.strftime('%Y%m%d')}.csv")
            try:
                print(f"Checking Bhavcopy for {d.strftime('%d-%b-%Y')} at {url}...")
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    with open(dest, "wb") as f:
                        f.write(resp.read())
                    print(f"Downloaded Bhavcopy: {dest}")
                    return dest
            except Exception:
                pass
        d -= datetime.timedelta(days=1)
    return None


def parse_bhavcopy(file_path, min_delivery=50.0):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return []

    results = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            series = r.get(" SERIES", r.get("SERIES", "")).strip()
            if series == "EQ":
                sym = r.get("SYMBOL", "").strip()
                close_p = float(r.get(" CLOSE_PRICE", r.get("CLOSE_PRICE", 0)) or 0)
                tot_qty = int(r.get(" TTL_TRD_QNTY", r.get("TTL_TRD_QNTY", 0)) or 0)
                del_qty = int(r.get(" DELIV_QTY", r.get("DELIV_QTY", 0)) or 0)
                del_pct = float(r.get(" DELIV_PER", r.get("DELIV_PER", 0)) or 0)

                if del_pct >= min_delivery and tot_qty >= 100000:
                    results.append({
                        "symbol": f"{sym}.NS",
                        "close": close_p,
                        "volume": tot_qty,
                        "delivery_qty": del_qty,
                        "delivery_pct": del_pct
                    })

    results.sort(key=lambda x: x["delivery_pct"], reverse=True)
    return results


def main():
    p = argparse.ArgumentParser(description="NSE EOD Bhavcopy & Delivery Analyzer")
    p.add_argument("--download", action="store_true", help="Download latest official Bhavcopy")
    p.add_argument("--min-delivery", type=float, default=50.0, help="Min delivery percentage")
    args = p.parse_args()

    today = datetime.date.today()
    target_file = None

    if args.download:
        target_file = download_bhavcopy(today)

    if not target_file:
        if os.path.exists(BHAV_DIR):
            files = sorted([os.path.join(BHAV_DIR, f) for f in os.listdir(BHAV_DIR) if f.endswith(".csv")])
            if files:
                target_file = files[-1]

    if target_file and os.path.exists(target_file):
        items = parse_bhavcopy(target_file, min_delivery=args.min_delivery)
        print(f"\nTop Institutional Accumulation Stocks (>={args.min_delivery}% Delivery):")
        for it in items[:15]:
            print(f"  {it['symbol']:<15} Close: Rs {it['close']:<9.2f} Delivery: {it['delivery_pct']:>5.1f}% (Vol: {it['volume']:,})")
    else:
        print("No local Bhavcopy found. Run with --download around 18:30 IST on trading days.")
    sys.exit(0)


if __name__ == "__main__":
    main()

