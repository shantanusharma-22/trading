#!/usr/bin/env python3
"""FII & DII Institutional Flow Tracker for trader-news (Indian Equities - NSE).
Tracks Foreign Institutional Investors (FII) and Domestic Institutional Investors (DII)
daily net cash market activity published by the National Stock Exchange.
Standard library only.

    python3 fiidii.py                                # fetch latest FII / DII net figures
"""

import datetime
import json
import os
import sys
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)


def to_ist(utc):
    return utc.replace(tzinfo=None) + IST_OFFSET


def fetch_fii_dii():
    url = "https://www.nseindia.com/api/fiidiiTradeReact"
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Referer": "https://www.nseindia.com/reports/fii-dii"
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def main():
    now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
    print(f"==================================================")
    print(f"FII & DII INSTITUTIONAL FLOW REPORT ({now_ist.strftime('%d-%b-%Y')})")
    print(f"==================================================")

    data = fetch_fii_dii()
    if data and isinstance(data, list):
        for item in data:
            cat = item.get("category", "")
            buy = float(item.get("buyValue", 0.0))
            sell = float(item.get("sellValue", 0.0))
            net = float(item.get("netValue", 0.0))
            date_str = item.get("date", "")
            action = "NET BUYER 🟢" if net > 0 else "NET SELLER 🔴"
            print(f"[{date_str}] {cat:<8}: Buy: Rs {buy:>9,.2f} Cr | Sell: Rs {sell:>9,.2f} Cr | Net: Rs {net:>+9,.2f} Cr ({action})")
    else:
        print("Note: Live NSE FII/DII API is updated each evening around 18:30 IST.")
        print("Market Sentiment Guidance:")
        print("  - FII Net Buy > Rs +1,000 Cr: Strong institutional bull bias for Nifty 50.")
        print("  - FII Net Sell > Rs -1,000 Cr: Headwinds for large-cap momentum; tight stops advised.")
    print(f"==================================================")
    sys.exit(0)


if __name__ == "__main__":
    main()

