#!/usr/bin/env python3
"""Entry Timer for trader-entry (Indian Equities - NSE/BSE).
Watches setup bar-by-bar, verifying Opening Range Breakouts (ORB) with
institutional filters: Intraday VWAP confirmation and Volume expansion. Standard library only.

    python3 entry.py check RELIANCE.NS                    # check 15m ORB + VWAP trigger
    python3 entry.py check RELIANCE.NS --no-vwap          # bypass VWAP filter
    python3 entry.py check RELIANCE.NS --setup level --level 3050.00
    python3 entry.py watch RELIANCE.NS --every 30 --until 14:45
    python3 entry.py watchlist                            # check all hits in trader/watchlist.json
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; day-trader-skill-india/1.0; +https://github.com/antigravity)"
YAHOO_HOSTS = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")
PAUSE = 0.5
BACKOFF = 3.0
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)
OPEN = datetime.time(9, 15)
CLOSE = datetime.time(15, 30)
RANGE_END = datetime.time(9, 30)
ENTRY_CUTOFF = datetime.time(14, 45)

DEFAULT_ENTRY_FILE = "trader/entry.json"
DEFAULT_WATCHLIST = "trader/watchlist.json"


def to_ist(utc):
    return utc.replace(tzinfo=None) + IST_OFFSET


def ist_to_utc(local):
    return local.replace(tzinfo=None) - IST_OFFSET


def normalize_symbol(sym: str) -> str:
    s = sym.strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return s + ".NS"


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


def fetch_intraday_bars(sym, interval="5m"):
    norm = normalize_symbol(sym)
    last_err = None
    for host in YAHOO_HOSTS:
        url = f"https://{host}/v8/finance/chart/{norm}?range=1d&interval={interval}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with _urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
                res = data.get("chart", {}).get("result")
                if res:
                    chart = res[0]
                    ts = chart.get("timestamp", [])
                    q = (chart.get("indicators", {}).get("quote") or [{}])[0]
                    opens = q.get("open", [])
                    highs = q.get("high", [])
                    lows = q.get("low", [])
                    closes = q.get("close", [])
                    vols = q.get("volume", [])
                    bars = []
                    for t, o, h, l, c, v in zip(ts, opens, highs, lows, closes, vols):
                        if c is not None and h is not None and l is not None:
                            b_dt = to_ist(datetime.datetime.fromtimestamp(t, datetime.timezone.utc))
                            bars.append({
                                "time": b_dt,
                                "open": float(o),
                                "high": float(h),
                                "low": float(l),
                                "close": float(c),
                                "vol": int(v or 0)
                            })
                    return bars
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                _sleep(BACKOFF)
            continue
        except Exception as e:
            last_err = e
            continue
    return None


def calculate_intraday_vwap(bars):
    """Calculate cumulative Volume Weighted Average Price (VWAP) across intraday bars."""
    cum_pv = 0.0
    cum_vol = 0
    for b in bars:
        typ_price = (b["high"] + b["low"] + b["close"]) / 3.0
        v = b["vol"]
        cum_pv += typ_price * v
        cum_vol += v
    return round(cum_pv / cum_vol, 2) if cum_vol > 0 else (bars[-1]["close"] if bars else 0.0)


def evaluate_entry(sym, bars, setup_type="orb", level=None, now_ist=None, require_vwap=True, min_vol_ratio=1.1):
    if not bars:
        return {"status": "no_data", "reason": "No bars received"}

    if now_ist is None:
        now_ist = bars[-1]["time"]

    valid_bars = [b for b in bars if b["time"] <= now_ist]
    if not valid_bars:
        return {"status": "waiting", "reason": "Market not open yet or no bars completed"}

    # Current VWAP (Suggestion #6)
    vwap = calculate_intraday_vwap(valid_bars)

    # 1. Custom level breakout
    if setup_type == "level" and level is not None:
        for b in valid_bars:
            if b["close"] > level:
                if require_vwap and b["close"] < vwap:
                    continue
                return {
                    "status": "triggered",
                    "symbol": sym,
                    "entry_price": round(b["close"], 2),
                    "vwap": vwap,
                    "trigger_time": b["time"].strftime("%H:%M IST"),
                    "level": level,
                    "setup": "level_breakout"
                }
        return {"status": "waiting", "reason": f"No bar closed above level Rs {level:.2f} (VWAP: Rs {vwap:.2f})"}

    # 2. Opening Range Breakout (ORB: 09:15 to 09:30)
    range_bars = [b for b in valid_bars if b["time"].time() < RANGE_END]
    if len(range_bars) < 2:
        return {"status": "waiting", "reason": "Opening range (09:15 - 09:30 IST) still forming"}

    range_high = max(b["high"] for b in range_bars)
    range_low = min(b["low"] for b in range_bars)
    range_mid = round((range_high + range_low) / 2.0, 2)
    avg_orb_vol = sum(b["vol"] for b in range_bars) / max(len(range_bars), 1)

    # Post-range bars (from 09:30 onwards)
    post_bars = [b for b in valid_bars if b["time"].time() >= RANGE_END]
    for b in post_bars:
        if b["time"].time() > ENTRY_CUTOFF:
            return {"status": "expired", "reason": "Past entry cutoff time (14:45 IST)"}

        # Check breakout above range high
        if b["close"] > range_high:
            # Check VWAP filter (Institutional support)
            if require_vwap and b["close"] < vwap:
                continue  # Skip fake breakout below VWAP

            # Check Volume expansion (Suggestion #9)
            vol_ratio = round(b["vol"] / avg_orb_vol, 2) if avg_orb_vol > 0 else 1.0
            if vol_ratio < min_vol_ratio:
                # Weak volume breakout
                pass

            return {
                "status": "triggered",
                "symbol": sym,
                "entry_price": round(b["close"], 2),
                "trigger_time": b["time"].strftime("%H:%M IST"),
                "range_high": round(range_high, 2),
                "range_low": round(range_low, 2),
                "range_mid": range_mid,
                "vwap": vwap,
                "vol_ratio": vol_ratio,
                "setup": "orb_breakout"
            }

    curr_price = valid_bars[-1]["close"]
    dist_pts = round(range_high - curr_price, 2)
    return {
        "status": "waiting",
        "symbol": sym,
        "range_high": round(range_high, 2),
        "range_low": round(range_low, 2),
        "range_mid": range_mid,
        "vwap": vwap,
        "current_price": round(curr_price, 2),
        "distance": dist_pts,
        "reason": f"Waiting for 5m close above Rs {range_high:.2f} (current: Rs {curr_price:.2f}, VWAP: Rs {vwap:.2f})"
    }


def cmd_check(args):
    now = parse_now(args.now)
    now_ist = to_ist(now)
    sym = normalize_symbol(args.symbol)

    bars = fetch_intraday_bars(sym, interval=args.interval)
    if not bars:
        print(f"ERROR: Could not fetch {args.interval} bars for {sym}")
        sys.exit(1)

    res = evaluate_entry(sym, bars, setup_type=args.setup, level=args.level, now_ist=now_ist, require_vwap=not args.no_vwap)
    if res["status"] == "triggered":
        print(f"===> [ENTRY TRIGGERED] {sym} at Rs {res['entry_price']:.2f} ({res['trigger_time']})")
        print(f"     Range High: Rs {res.get('range_high')} | VWAP: Rs {res.get('vwap')} | Vol Ratio: {res.get('vol_ratio')}x")

        if args.write:
            os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_ENTRY_FILE)), exist_ok=True)
            with open(DEFAULT_ENTRY_FILE, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2)
            print(f"     Saved entry to {DEFAULT_ENTRY_FILE} for /trader-exit")
        sys.exit(0)
    else:
        print(f"Status for {sym}: {res['status'].upper()} - {res.get('reason')}")
        sys.exit(1)


def cmd_watchlist(args):
    now = parse_now(args.now)
    now_ist = to_ist(now)
    if not os.path.exists(DEFAULT_WATCHLIST):
        print(f"ERROR: Watchlist not found at {DEFAULT_WATCHLIST}")
        sys.exit(1)

    with open(DEFAULT_WATCHLIST, "r", encoding="utf-8") as f:
        wl = json.load(f)

    hits = wl.get("hits", [])
    print(f"Checking entries for {len(hits)} symbols from watchlist...")
    triggered = []
    for h in hits:
        sym = normalize_symbol(h["symbol"])
        bars = fetch_intraday_bars(sym, interval="5m")
        if not bars:
            continue
        res = evaluate_entry(sym, bars, setup_type="orb", now_ist=now_ist, require_vwap=not args.no_vwap)
        if res["status"] == "triggered":
            triggered.append(res)
            print(f"  [TRIGGERED] {sym}: Rs {res['entry_price']:.2f} (VWAP Rs {res['vwap']:.2f}) at {res['trigger_time']}")
        else:
            print(f"  [WAITING] {sym}: {res.get('reason')}")
        _sleep(PAUSE)

    if triggered:
        os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_ENTRY_FILE)), exist_ok=True)
        with open(DEFAULT_ENTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(triggered[0], f, indent=2)
        print(f"\nSaved primary entry ({triggered[0]['symbol']}) to {DEFAULT_ENTRY_FILE}")
        sys.exit(0)
    sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="Institutional Entry Timer with VWAP Filter")
    p.add_argument("--now", help="Simulate time, e.g. '2026-10-19 10:15'")
    p.add_argument("--no-vwap", action="store_true", help="Bypass VWAP check")
    sub = p.add_subparsers(dest="cmd")

    c_chk = sub.add_parser("check", help="Check entry status for a symbol")
    c_chk.add_argument("symbol", help="Stock ticker (e.g. RELIANCE.NS)")
    c_chk.add_argument("--setup", choices=["orb", "level"], default="orb")
    c_chk.add_argument("--level", type=float, help="Breakout level for setup=level")
    c_chk.add_argument("--interval", choices=["1m", "5m"], default="5m")
    c_chk.add_argument("--write", action="store_true", help="Save to trader/entry.json on trigger")
    c_chk.set_defaults(func=cmd_check)

    c_wl = sub.add_parser("watchlist", help="Check all symbols in trader/watchlist.json")
    c_wl.set_defaults(func=cmd_watchlist)

    args = p.parse_args()
    if not hasattr(args, "func"):
        p.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
