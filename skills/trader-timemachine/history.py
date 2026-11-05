#!/usr/bin/env python3
"""Local SQLite Bar Cache for trader-timemachine (Indian Equities - NSE).
Stores and retrieves historical 5-minute and daily bars locally to prevent
network latency and rate-limiting during Monte Carlo simulations. Standard library only.

    python3 history.py sync RELIANCE.NS TCS.NS       # sync 60d bars into local database
    python3 history.py stats                         # show database stats and cached symbols
"""

import argparse
import datetime
import json
import os
import sqlite3
import sys
import time
import urllib.request

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import IST_OFFSET, UA, resolve_path, to_ist

DB_PATH = resolve_path("trader/data/history.db")


def get_connection():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bars_5m (
            symbol TEXT,
            timestamp INTEGER,
            time_ist TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            PRIMARY KEY(symbol, timestamp)
        )
    """)
    conn.commit()
    return conn


def sync_symbol(sym):
    conn = get_connection()
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?range=60d&interval=5m"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            chart = data["chart"]["result"][0]
            ts = chart.get("timestamp", [])
            q = (chart.get("indicators", {}).get("quote") or [{}])[0]
            opens = q.get("open", [])
            highs = q.get("high", [])
            lows = q.get("low", [])
            closes = q.get("close", [])
            vols = q.get("volume", [])

            rows = []
            for t, o, h, l, c, v in zip(ts, opens, highs, lows, closes, vols):
                if c is not None and h is not None and l is not None:
                    b_dt = to_ist(datetime.datetime.fromtimestamp(t, datetime.timezone.utc))
                    rows.append((sym, t, b_dt.strftime("%Y-%m-%d %H:%M:%S"), float(o), float(h), float(l), float(c), int(v or 0)))

            conn.executemany("""
                INSERT OR REPLACE INTO bars_5m (symbol, timestamp, time_ist, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            conn.commit()
            print(f"Synced {len(rows)} 5m bars for {sym} into local SQLite database.")
            return len(rows)
    except Exception as e:
        print(f"Error syncing {sym}: {e}")
        return 0
    finally:
        conn.close()


def get_cached_bars(sym):
    if not os.path.exists(DB_PATH):
        return []
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT time_ist, open, high, low, close, volume FROM bars_5m
        WHERE symbol = ? ORDER BY timestamp ASC
    """, (sym,))
    rows = cursor.fetchall()
    conn.close()
    return [{
        "time": datetime.datetime.fromisoformat(r[0]),
        "open": r[1], "high": r[2], "low": r[3], "close": r[4], "vol": r[5]
    } for r in rows]


def main():
    p = argparse.ArgumentParser(description="Local SQLite Bar Cache")
    sub = p.add_subparsers(dest="cmd")

    c_sy = sub.add_parser("sync", help="Sync bars for symbols")
    c_sy.add_argument("symbols", nargs="+")

    c_st = sub.add_parser("stats", help="Show database cache statistics")
    args = p.parse_args()

    if args.cmd == "sync":
        for s in args.symbols:
            norm = s.strip().upper()
            if not norm.endswith(".NS") and not norm.endswith(".BO"):
                norm += ".NS"
            sync_symbol(norm)
            time.sleep(0.5)
        sys.exit(0)

    if args.cmd == "stats":
        if not os.path.exists(DB_PATH):
            print("Database empty. Run sync first.")
            sys.exit(0)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, COUNT(*), MIN(time_ist), MAX(time_ist) FROM bars_5m GROUP BY symbol")
        rows = cursor.fetchall()
        print("Cached Symbols in SQLite Database:")
        for r in rows:
            print(f"  {r[0]:<15} {r[1]:>5} bars ({r[2]} to {r[3]})")
        conn.close()
        sys.exit(0)


if __name__ == "__main__":
    main()

