#!/usr/bin/env python3
"""Price Alerts & Push Notification Engine for trader-alerts (Indian Equities - NSE/BSE).
Watches prices, stop/targets, opening bells, and 15:10 IST square-off alerts.
Supports instant push notifications to Telegram Bot and Discord Webhook. Standard library only.

    python3 alerts.py clock                          # NSE open or closed, next open (IST)
    python3 alerts.py add --from-plan                # stop, target, flat by 15:10 from trader/plan.json
    python3 alerts.py add --opening-bell             # alert at 09:15 IST
    python3 alerts.py add --symbol RELIANCE.NS --stop 2950.00
    python3 alerts.py add --symbol RELIANCE.NS --target 3050.00
    python3 alerts.py check                          # check all alerts and dispatch notifications
    python3 alerts.py quote RELIANCE.NS --write      # write to trader/prices.json
    python3 alerts.py test-notify                    # test Telegram / Discord push notification
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
    CALENDAR_YEARS,
    CLOSE,
    FLAT_BY,
    IST_OFFSET,
    NSE_HOLIDAYS,
    OPEN,
    UA,
    ist_to_utc,
    normalize_symbol,
    resolve_path,
    to_ist,
)

PAUSE = 0.5
BACKOFF = 2.0
YAHOO_HOSTS = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")

DEFAULT_FILE = "trader/alerts.json"
PRICES_FILE = "trader/prices.json"
DEFAULT_CONFIG = "trader/config.json"


def parse_now(text):
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = text.strip().replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(t)
    if dt.tzinfo is None:
        return ist_to_utc(dt)
    return (dt - dt.utcoffset()).replace(tzinfo=None)


def trading_day(d):
    if d.weekday() >= 5:
        return False, "weekend"
    name = NSE_HOLIDAYS.get(d.isoformat())
    if name:
        return False, "NSE holiday: " + name
    return True, ""


def session(d):
    ok, _ = trading_day(d)
    if not ok:
        return None
    return OPEN, CLOSE


def market_status(now_utc):
    local = to_ist(now_utc)
    d = local.date()
    ok, reason = trading_day(d)
    st = {
        "now_ist": local.strftime("%Y-%m-%d %H:%M:%S"),
        "date": d.isoformat(),
        "weekday": local.strftime("%A"),
        "calendar_known": d.year in CALENDAR_YEARS,
        "open": False,
        "reason": reason,
        "flat_by": FLAT_BY.strftime("%H:%M")
    }
    s = session(d)
    if s:
        o, c = s
        st["opens"], st["closes"] = o.strftime("%H:%M"), c.strftime("%H:%M")
        if o <= local.time() < c:
            st["open"] = True
            st["reason"] = "regular trading session"
        elif local.time() < o:
            st["reason"] = "before the open"
        else:
            st["reason"] = "after the close"

    nd = d if (s and local.time() < s[0]) else d + datetime.timedelta(days=1)
    for _ in range(15):
        if session(nd):
            st["next_open"] = "%s 09:15 IST" % nd.isoformat()
            break
        nd += datetime.timedelta(days=1)
    return st


# ---------------------------------------------------------------- Push Notifications (Suggestion #17)

def dispatch_push_notification(title: str, message: str):
    """Sends webhook push notification to Telegram or Discord if configured."""
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID")
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")

    # Check config file if env vars not set
    if os.path.exists(DEFAULT_CONFIG):
        try:
            with open(DEFAULT_CONFIG, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                telegram_token = telegram_token or cfg.get("telegram_bot_token")
                telegram_chat = telegram_chat or cfg.get("telegram_chat_id")
                discord_webhook = discord_webhook or cfg.get("discord_webhook_url")
        except Exception:
            pass

    # 1. Telegram
    if telegram_token and telegram_chat:
        try:
            text = f"🚨 *{title}*\n{message}"
            tg_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            payload = json.dumps({"chat_id": telegram_chat, "text": text, "parse_mode": "Markdown"}).encode("utf-8")
            req = urllib.request.Request(tg_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5):
                print(f"  [PUSH] Telegram notification sent: {title}")
        except Exception as e:
            print(f"  [PUSH ERROR] Telegram failed: {e}")

    # 2. Discord
    if discord_webhook:
        try:
            payload = json.dumps({"content": f"**{title}**\n{message}"}).encode("utf-8")
            req = urllib.request.Request(discord_webhook, data=payload, headers={"Content-Type": "application/json", "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=5):
                print(f"  [PUSH] Discord webhook sent: {title}")
        except Exception as e:
            print(f"  [PUSH ERROR] Discord failed: {e}")


# ---------------------------------------------------------------- quotes

def yahoo_url(sym, host=YAHOO_HOSTS[0]):
    return f"https://{host}/v8/finance/chart/{normalize_symbol(sym)}?range=1d&interval=5m"


def parse_yahoo(text, sym):
    norm_sym = normalize_symbol(sym)
    try:
        data = json.loads(text)
        res = data["chart"]["result"]
    except Exception:
        raise AlertError("Yahoo returned unexpected response for %s" % norm_sym)
    if not res:
        err = (data.get("chart") or {}).get("error") or {}
        raise AlertError("Yahoo has no data for %s: %s" % (norm_sym, err.get("description", "unknown ticker")))
    m = res[0].get("meta", {})
    price = m.get("regularMarketPrice")
    if price is None:
        raise AlertError("Yahoo has no price for %s" % norm_sym)
    t = m.get("regularMarketTime")
    when = (datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t else "")
    return {
        "symbol": norm_sym,
        "price": float(price),
        "high": m.get("regularMarketDayHigh"),
        "low": m.get("regularMarketDayLow"),
        "prev_close": m.get("previousClose") or m.get("chartPreviousClose"),
        "time": when,
        "currency": m.get("currency", "INR"),
        "source": "yahoo"
    }


_urlopen = urllib.request.urlopen
_sleep = time.sleep


def fetch_quote(sym, offline=None):
    norm = normalize_symbol(sym)
    if offline:
        p = offline if os.path.isfile(offline) else os.path.join(offline, "%s.json" % norm)
        with open(p, "r", encoding="utf-8") as f:
            return parse_yahoo(f.read(), norm)

    last_err = None
    for host in YAHOO_HOSTS:
        url = yahoo_url(norm, host)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with _urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return parse_yahoo(raw, norm)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                _sleep(BACKOFF)
            continue
        except Exception as e:
            last_err = e
            continue
    raise AlertError("could not fetch quote for %s: %s" % (norm, last_err))


# ---------------------------------------------------------------- alert store

def load_alerts(path=DEFAULT_FILE):
    if not os.path.exists(path):
        return {"alerts": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"alerts": []}


def save_alerts(data, path=DEFAULT_FILE):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def add_alert(spec, path=DEFAULT_FILE):
    data = load_alerts(path)
    aid = spec.get("id") or ("alert-%d" % (len(data.get("alerts", [])) + 1))
    spec["id"] = aid
    spec["created_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    spec["rung"] = False
    data.setdefault("alerts", [])
    data["alerts"] = [a for a in data["alerts"] if a.get("id") != aid]
    data["alerts"].append(spec)
    save_alerts(data, path)
    return spec


def check_alerts(now_utc, offline=None, path=DEFAULT_FILE):
    data = load_alerts(path)
    alerts = data.get("alerts", [])
    if not alerts:
        return [], 0

    local = to_ist(now_utc)
    syms = set()
    for a in alerts:
        if not a.get("rung") and a.get("symbol"):
            syms.add(a["symbol"])

    quotes = {}
    for s in syms:
        try:
            quotes[s] = fetch_quote(s, offline=offline)
            _sleep(PAUSE)
        except Exception as e:
            quotes[s] = {"error": str(e)}

    rang = []
    for a in alerts:
        if a.get("rung"):
            continue
        hit = False
        reason = ""

        # Time-based
        if a.get("type") == "time":
            target_time = a.get("time")
            if target_time and local.strftime("%H:%M") >= target_time:
                hit = True
                reason = "hit scheduled time %s IST" % target_time
        elif a.get("type") == "opening_bell":
            if local.time() >= OPEN:
                hit = True
                reason = "NSE opening bell rang (09:15 IST)"
        elif a.get("type") == "flat_by":
            if local.time() >= FLAT_BY:
                hit = True
                reason = "intraday flat_by reached (15:10 IST - square off MIS positions)"

        # Price-based
        elif a.get("symbol"):
            sym = a["symbol"]
            q = quotes.get(sym, {})
            price = q.get("price")
            if price is not None:
                if "stop" in a and price <= a["stop"]:
                    hit = True
                    reason = f"price Rs {price:.2f} breached stop Rs {a['stop']:.2f}"
                elif "target" in a and price >= a["target"]:
                    hit = True
                    reason = f"price Rs {price:.2f} reached target Rs {a['target']:.2f}"
                elif "above" in a and price >= a["above"]:
                    hit = True
                    reason = f"price Rs {price:.2f} rose above Rs {a['above']:.2f}"
                elif "below" in a and price <= a["below"]:
                    hit = True
                    reason = f"price Rs {price:.2f} fell below Rs {a['below']:.2f}"

        if hit:
            a["rung"] = True
            a["rung_at"] = local.strftime("%Y-%m-%d %H:%M:%S IST")
            a["rung_reason"] = reason
            rang.append(a)
            # Dispatch push notification (Telegram / Discord)
            dispatch_push_notification(f"NSE Alert: {a.get('label', a.get('symbol'))}", reason)

    if rang:
        save_alerts(data, path)
    return rang, len(alerts)


def cmd_clock(args):
    now = parse_now(args.now)
    st = market_status(now)
    print("NSE Clock: %s" % st["now_ist"])
    print("Status: %s (%s)" % ("OPEN" if st["open"] else "CLOSED", st["reason"]))
    print("Session: %s - %s IST | Flat-by: %s IST" % (st.get("opens", "09:15"), st.get("closes", "15:30"), st["flat_by"]))
    if not st["open"] and "next_open" in st:
        print("Next Open: %s" % st["next_open"])
    sys.exit(0 if st["open"] else 1)


def cmd_quote(args):
    now = parse_now(args.now)
    syms = []
    if args.symbol:
        syms.append(normalize_symbol(args.symbol))
    syms = sorted(list(set(normalize_symbol(s) for s in syms if s)))
    quotes = {}
    for s in syms:
        try:
            q = fetch_quote(s, offline=args.offline)
            quotes[s] = q
            print(f"{s}: Rs {q['price']:.2f} (prev: Rs {q.get('prev_close', 0):.2f})")
            _sleep(PAUSE)
        except Exception as e:
            print(f"{s}: ERROR - {e}")

    if args.write and quotes:
        os.makedirs(os.path.dirname(os.path.abspath(PRICES_FILE)), exist_ok=True)
        with open(PRICES_FILE, "w", encoding="utf-8") as f:
            json.dump({"as_of_ist": to_ist(now).strftime("%Y-%m-%d %H:%M:%S"), "prices": quotes}, f, indent=2)
        print("Wrote quotes to %s" % PRICES_FILE)
    sys.exit(0)


def cmd_add(args):
    if args.from_plan:
        if not os.path.exists("trader/plan.json"):
            print("ERROR: trader/plan.json not found")
            sys.exit(1)
        with open("trader/plan.json", "r", encoding="utf-8") as f:
            p = json.load(f)
        sym = normalize_symbol(p["symbol"])
        add_alert({"id": f"{sym.lower()}-stop", "symbol": sym, "stop": p["stop"], "label": f"{sym} Stop Loss"})
        add_alert({"id": f"{sym.lower()}-target", "symbol": sym, "target": p["target"], "label": f"{sym} Target"})
        add_alert({"id": "intraday-flat-by", "type": "flat_by", "time": "15:10", "label": "Square off MIS positions"})
        print(f"Added alerts from plan for {sym}: Stop Rs {p['stop']:.2f}, Target Rs {p['target']:.2f}, Flat by 15:10 IST")
        sys.exit(0)

    if args.symbol:
        sym = normalize_symbol(args.symbol)
        if args.stop:
            add_alert({"id": f"{sym.lower()}-stop", "symbol": sym, "stop": float(args.stop), "label": f"{sym} Stop"})
            print(f"Added stop alert for {sym} at Rs {float(args.stop):.2f}")
        if args.target:
            add_alert({"id": f"{sym.lower()}-target", "symbol": sym, "target": float(args.target), "label": f"{sym} Target"})
            print(f"Added target alert for {sym} at Rs {float(args.target):.2f}")
        sys.exit(0)
    sys.exit(1)


def cmd_check(args):
    now = parse_now(args.now)
    rang, total = check_alerts(now, offline=args.offline)
    if rang:
        print(f"ALERTS RINGING ({len(rang)}):")
        for a in rang:
            print(f"  - [{a.get('id')}] {a.get('label')}: {a.get('rung_reason')}")
        sys.exit(0)
    else:
        print(f"No alerts triggered. Active alerts: {total}")
        sys.exit(1)


def cmd_test_notify(args):
    print("Testing push notification dispatch...")
    dispatch_push_notification("Vyapar AI Test Alert", "Test notification from Vyapar AI Trading Suite.")
    print("Test completed.")
    sys.exit(0)


def main():
    p = argparse.ArgumentParser(description="Price Alerts & Push Notification Engine")
    p.add_argument("--now", help="Simulate IST time, e.g. '2026-10-19 10:15'")
    p.add_argument("--offline")
    sub = p.add_subparsers(dest="cmd")

    c_clk = sub.add_parser("clock")
    c_clk.set_defaults(func=cmd_clock)

    c_add = sub.add_parser("add")
    c_add.add_argument("--from-plan", action="store_true")
    c_add.add_argument("--symbol")
    c_add.add_argument("--stop", type=float)
    c_add.add_argument("--target", type=float)
    c_add.set_defaults(func=cmd_add)

    c_chk = sub.add_parser("check")
    c_chk.set_defaults(func=cmd_check)

    c_quo = sub.add_parser("quote")
    c_quo.add_argument("symbol")
    c_quo.add_argument("--write", action="store_true")
    c_quo.set_defaults(func=cmd_quote)

    c_tst = sub.add_parser("test-notify")
    c_tst.set_defaults(func=cmd_test_notify)

    args = p.parse_args()
    if not hasattr(args, "func"):
        p.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
