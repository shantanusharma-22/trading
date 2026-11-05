#!/usr/bin/env python3
"""Institutional Risk Manager for trader-risk (Indian Equities - NSE/BSE).
Checks proposed orders against hard risk parameters before execution:
  - Rupee loss limits & daily drawdown caps
  - High-Water Mark Daily Profit Lock (Never let a green day turn red)
  - Macro Event Blackouts (RBI MPC policy & Union Budget freezes)
  - Consecutive losses killswitch (stops revenge trading)
  - Correlated sector risk caps (max 1 trade per sector)
  - Thursday weekly expiry volatility cutoff (13:45 IST)
  - India VIX volatility regime filter (^INDIAVIX)
  - Market Breadth A/D ratio filter
Standard library only. Writes trader/state/risk.json.

    python3 check.py                                 # checks trader/orders.json
    python3 check.py --json                          # print verdict as JSON
    python3 check.py --now "2026-10-19 10:15"        # pin the clock (IST)
    python3 check.py --vix 16.5                      # explicit VIX level
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
import urllib.request

NSE_HOLIDAYS = {
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-20": "Id-Ul-Fitr",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-27": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-08-15": "Independence Day",
    "2026-09-16": "Milad-un-Nabi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan",
    "2026-11-24": "Gurunanak Jayanti",
    "2026-12-25": "Christmas Day",
    "2027-01-26": "Republic Day",
    "2027-03-10": "Id-Ul-Fitr",
    "2027-03-22": "Holi",
    "2027-03-26": "Good Friday",
    "2027-04-14": "Dr. Ambedkar Jayanti",
    "2027-05-01": "Maharashtra Day",
    "2027-05-17": "Bakri Id",
    "2027-06-16": "Muharram",
    "2027-08-15": "Independence Day",
    "2027-10-02": "Mahatma Gandhi Jayanti",
    "2027-10-09": "Dussehra",
    "2027-10-29": "Diwali Laxmi Pujan",
    "2027-11-14": "Gurunanak Jayanti",
    "2027-12-25": "Christmas Day",
}

SECTOR_MAP = {
    "HDFCBANK.NS": "BANKING", "ICICIBANK.NS": "BANKING", "SBIN.NS": "BANKING",
    "KOTAKBANK.NS": "BANKING", "AXISBANK.NS": "BANKING", "INDUSINDBK.NS": "BANKING",
    "TCS.NS": "IT", "INFY.NS": "IT", "HCLTECH.NS": "IT", "WIPRO.NS": "IT", "TECHM.NS": "IT",
    "TATAMOTORS.NS": "AUTO", "MARUTI.NS": "AUTO", "M&M.NS": "AUTO", "BAJAJ-AUTO.NS": "AUTO", "EICHERMOT.NS": "AUTO",
    "SUNPHARMA.NS": "PHARMA", "CIPLA.NS": "PHARMA", "DRREDDY.NS": "PHARMA", "DIVISLAB.NS": "PHARMA",
    "TATASTEEL.NS": "METAL", "JSWSTEEL.NS": "METAL", "HINDALCO.NS": "METAL",
    "RELIANCE.NS": "ENERGY", "ONGC.NS": "ENERGY", "BPCL.NS": "ENERGY", "COALINDIA.NS": "ENERGY"
}

IST_OFFSET = datetime.timedelta(hours=5, minutes=30)
OPEN = datetime.time(9, 15)
CLOSE = datetime.time(15, 30)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def resolve_path(rel_path: str) -> str:
    p = os.path.join(BASE_DIR, rel_path)
    return p if os.path.exists(p) else rel_path

DEFAULT_ORDERS_FILE = resolve_path("trader/orders.json")
DEFAULT_CONFIG_FILE = resolve_path("trader/config.json")
DEFAULT_EVENTS_FILE = resolve_path("trader/events.json")
DEFAULT_RISK_STATE = resolve_path("trader/state/risk.json")
DEFAULT_BROKER_STATE = resolve_path("trader/state/broker.json")
DEFAULT_BREADTH_STATE = resolve_path("trader/state/breadth.json")

DEFAULT_CONFIG = {
    "budget": 100000.0,
    "max_order_inr": 50000.0,
    "min_order_inr": 1000.0,
    "max_loss_per_trade_inr": 1000.0,
    "max_daily_loss_inr": 3000.0,
    "max_trades_per_day": 3,
    "max_consecutive_losses": 2,
    "max_trades_per_sector": 1,
    "profit_lock_trigger_inr": 2500.0,
    "profit_lock_floor_inr": 1500.0,
    "min_reward_risk": 1.5,
    "require_stop": True,
    "no_entries_before": "09:30",
    "no_entries_after": "14:45",
    "expiry_cutoff": "13:45",
    "vix_min": 11.5,
    "vix_max": 24.0,
    "blocked": []
}


def to_ist(utc):
    return utc.replace(tzinfo=None) + IST_OFFSET


def ist_to_utc(local):
    return local.replace(tzinfo=None) - IST_OFFSET


def parse_now(text):
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = text.strip().replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(t)
    if dt.tzinfo is None:
        return ist_to_utc(dt)
    return (dt - dt.utcoffset()).replace(tzinfo=None)


def compute_order_fingerprint(order: dict) -> str:
    raw = f"{order.get('symbol')}:{order.get('side')}:{order.get('qty')}:{order.get('entry_price')}:{order.get('stop_loss_price')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def fetch_india_vix():
    try:
        url = "https://query2.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX?range=1d&interval=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception:
        return None


def event_guard(symbol: str, now_ist: datetime.datetime = None) -> dict:
    """Evaluates Indian market event calendar and risk rules for symbol and time.
    Returns: {"allowed": bool, "size_factor": float, "reason": str, "event": dict or None}
    """
    if now_ist is None:
        now_ist = datetime.datetime.now(datetime.timezone.utc) + IST_OFFSET

    d_str = now_ist.strftime("%Y-%m-%d")
    t_str = now_ist.strftime("%H:%M")

    # 1. Exchange Holiday Check
    if d_str in NSE_HOLIDAYS:
        return {
            "allowed": False,
            "size_factor": 0.0,
            "reason": f"NSE Exchange Holiday: {NSE_HOLIDAYS[d_str]}",
            "event": {"type": "holiday", "title": NSE_HOLIDAYS[d_str]}
        }

    # 2. Weekend Check
    if now_ist.weekday() >= 5:
        return {
            "allowed": False,
            "size_factor": 0.0,
            "reason": f"Weekend: {now_ist.strftime('%A')} (Exchange Closed)",
            "event": {"type": "weekend"}
        }

    events_file = DEFAULT_EVENTS_FILE
    if os.path.exists(events_file):
        try:
            with open(events_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            events = data.get("events", [])
            rules = data.get("rules", {})

            # Check individual scheduled events
            for ev in events:
                if ev.get("date") == d_str:
                    ev_type = ev.get("type")
                    if ev_type == "rbi_policy":
                        ann_time = ev.get("time", "10:00")
                        b_min = ev.get("before_min", 15)
                        a_min = ev.get("after_min", 30)
                        try:
                            ann_dt = datetime.datetime.strptime(f"{d_str} {ann_time}", "%Y-%m-%d %H:%M")
                            start_window = ann_dt - datetime.timedelta(minutes=b_min)
                            end_window = ann_dt + datetime.timedelta(minutes=a_min)
                            if start_window <= now_ist <= end_window:
                                return {
                                    "allowed": False,
                                    "size_factor": 0.0,
                                    "action": ev.get("action", "FREEZE_ALL_ENTRIES"),
                                    "reason": f"Macro Blackout: {ev.get('title')} ({start_window.strftime('%H:%M')}-{end_window.strftime('%H:%M')} IST)",
                                    "event": ev
                                }
                        except Exception:
                            pass

                    elif ev_type == "results":
                        ev_symbols = [s.strip().upper() for s in ev.get("symbols", [])]
                        norm_sym = symbol.strip().upper() if symbol else ""
                        if norm_sym in ev_symbols:
                            return {
                                "allowed": False,
                                "size_factor": 0.0,
                                "action": ev.get("action", "BLOCK_SYMBOL_TODAY"),
                                "reason": f"Corporate Action Blackout: {symbol} Quarterly Results Day",
                                "event": ev
                            }

                    elif ev_type == "union_budget":
                        return {
                            "allowed": False,
                            "size_factor": 0.0,
                            "reason": f"Macro Blackout: {ev.get('title')} (Extreme Budget Volatility)",
                            "event": ev
                        }

                    elif ev_type == "special_session":
                        return {
                            "allowed": False,
                            "size_factor": 0.0,
                            "reason": f"Special Session restriction: {ev.get('title')}",
                            "event": ev
                        }

            # Check general rules (e.g. F&O Expiry risk reduction)
            fo_rule = rules.get("fo_expiry", {})
            if fo_rule.get("enabled", True):
                exp_day = fo_rule.get("weekday", "THURSDAY").upper()
                day_names = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
                if day_names[now_ist.weekday()] == exp_day:
                    return {
                        "allowed": True,
                        "size_factor": float(fo_rule.get("size_factor", 0.5)),
                        "reason": f"Weekly F&O Expiry ({exp_day}): Position size scaled to {int(float(fo_rule.get('size_factor', 0.5))*100)}%",
                        "event": {"type": "fo_expiry", "title": f"F&O Expiry ({exp_day})"}
                    }

        except Exception:
            pass

    return {
        "allowed": True,
        "size_factor": 1.0,
        "reason": "No active event restrictions",
        "event": None
    }


def check_macro_blackout(now_ist: datetime.datetime):
    """Check if current time is within RBI policy or Union Budget blackout window (Suggestion #3)."""
    if not os.path.exists(DEFAULT_EVENTS_FILE):
        return False, ""
    try:
        with open(DEFAULT_EVENTS_FILE, "r", encoding="utf-8") as f:
            events = json.load(f).get("macro_blackouts", [])
        d_str = now_ist.strftime("%Y-%m-%d")
        t_str = now_ist.strftime("%H:%M")
        for ev in events:
            if ev.get("date") == d_str:
                if ev.get("start_time", "00:00") <= t_str <= ev.get("end_time", "23:59"):
                    return True, f"Macro Event Blackout: {ev.get('name')} ({ev.get('start_time')} - {ev.get('end_time')} IST)"
    except Exception:
        pass
    return False, ""


def validate_order(order: dict, config: dict, now_ist: datetime.datetime, todays_broker_state: dict, current_vix=None):
    # 1. Macro Event Blackout
    in_blackout, ev_msg = check_macro_blackout(now_ist)
    if in_blackout:
        return False, ev_msg

    # 2. Format check
    sym = order.get("symbol", "")
    if not sym or not (sym.endswith(".NS") or sym.endswith(".BO")):
        return False, "Symbol must be a valid Indian equity ticker (.NS or .BO)"

    qty = order.get("qty", 0)
    if not isinstance(qty, int) or qty <= 0:
        return False, f"Quantity must be a positive integer (received {qty})"

    entry = order.get("entry_price", 0.0)
    stop = order.get("stop_loss_price", 0.0)
    target = order.get("take_profit_price", 0.0)

    if entry <= 0:
        return False, "Entry price must be positive"

    # 3. Stop placement
    if config.get("require_stop", True):
        if stop <= 0:
            return False, "Stop-loss is required"
        if order.get("side", "BUY") == "BUY" and stop >= entry:
            return False, f"Stop-loss (Rs {stop:.2f}) cannot be at or above entry price (Rs {entry:.2f})"

    # 4. Blocked list
    blocked = config.get("blocked", [])
    if sym in blocked:
        return False, f"Symbol {sym} is on the blocked tickers list"

    # 5. Tick size (0.05 paise)
    for price_val, label in [(entry, "Entry"), (stop, "Stop"), (target, "Target")]:
        if price_val > 0:
            cents = round(price_val * 100)
            if cents % 5 != 0:
                return False, f"{label} Rs {price_val:.2f} is not on 0.05 NSE tick grid"

    # 6. Loss per trade limit
    risk_per_share = entry - stop
    total_risk = round(risk_per_share * qty, 2)
    max_loss_limit = config.get("max_loss_per_trade_inr", 1000.0)
    if total_risk > max_loss_limit:
        return False, f"Trade risk Rs {total_risk:,.2f} exceeds max loss limit Rs {max_loss_limit:,.2f}"

    # 7. Reward : Risk ratio
    if target > entry and risk_per_share > 0:
        rr = round((target - entry) / risk_per_share, 2)
        min_rr = config.get("min_reward_risk", 1.5)
        if rr < min_rr:
            return False, f"Reward-to-risk {rr}:1 is below required minimum {min_rr}:1"

    # 8. High-Water Mark Daily Profit Lock (Suggestion #4)
    placed_trades = todays_broker_state.get("trades_today", [])
    net_pnls = [t.get("pnl", 0.0) for t in placed_trades if "pnl" in t]
    if net_pnls:
        cum_pnl = 0.0
        peak_pnl = 0.0
        for pnl in net_pnls:
            cum_pnl += pnl
            if cum_pnl > peak_pnl:
                peak_pnl = cum_pnl
        running_pnl = cum_pnl
        trigger = config.get("profit_lock_trigger_inr", 2500.0)
        floor = config.get("profit_lock_floor_inr", 1500.0)
        if peak_pnl >= trigger and running_pnl <= floor:
            return False, f"Daily Profit High-Water Mark Lockout: Peak was Rs {peak_pnl:,.2f}, current profit Rs {running_pnl:,.2f} reached floor Rs {floor:,.2f}. Capital locked for today."

    # 9. Consecutive Losses Killswitch
    max_consec = config.get("max_consecutive_losses", 2)
    consec_losses = 0
    for t in reversed(placed_trades):
        if t.get("pnl", 0.0) < 0:
            consec_losses += 1
        else:
            break
    if consec_losses >= max_consec:
        return False, f"Killswitch triggered: {consec_losses} consecutive losses reached today. Stop trading."

    # 10. Correlated Sector Risk Cap
    target_sector = SECTOR_MAP.get(sym)
    if target_sector:
        max_sec = config.get("max_trades_per_sector", 1)
        active_in_sec = sum(1 for t in placed_trades if SECTOR_MAP.get(t.get("symbol")) == target_sector)
        if active_in_sec >= max_sec:
            return False, f"Sector risk cap reached: already holding/traded {active_in_sec} stock(s) in {target_sector}"

    # 11. Daily Loss Limit & Trade Counts
    max_trades = config.get("max_trades_per_day", 3)
    if len(placed_trades) >= max_trades:
        return False, f"Max trades per day limit ({max_trades}) already reached today"

    cumulative_risk = sum(t.get("max_loss", 0.0) for t in placed_trades) + total_risk
    max_daily_loss = config.get("max_daily_loss_inr", 3000.0)
    if cumulative_risk > max_daily_loss:
        return False, f"Cumulative daily risk Rs {cumulative_risk:,.2f} exceeds daily limit Rs {max_daily_loss:,.2f}"

    # 12. India VIX Regime Filter
    if current_vix is not None:
        v_min = config.get("vix_min", 11.5)
        v_max = config.get("vix_max", 24.0)
        if current_vix < v_min:
            return False, f"India VIX ({current_vix:.1f}) below {v_min}: low volatility trap"
        if current_vix > v_max:
            return False, f"India VIX ({current_vix:.1f}) above {v_max}: extreme volatility regime"

    # 13. Market Window, Calendar & Expiry Shield
    d_str = now_ist.strftime("%Y-%m-%d")
    if now_ist.weekday() >= 5:
        return False, f"Market is closed today (Weekend: {now_ist.strftime('%A')})"
    if d_str in NSE_HOLIDAYS:
        return False, f"Market is closed today (NSE Holiday: {NSE_HOLIDAYS[d_str]})"

    t = now_ist.time()
    t_str = t.strftime("%H:%M")
    no_before = config.get("no_entries_before", "09:30")
    no_after = config.get("no_entries_after", "14:45")

    is_thursday = (now_ist.weekday() == 3)
    if is_thursday:
        no_after = config.get("expiry_cutoff", "13:45")

    if t < OPEN:
        return False, f"NSE market has not opened yet (opens at 09:15 IST)"
    if t >= CLOSE:
        return False, f"NSE market is closed (closed at 15:30 IST)"
    if t_str < no_before:
        return False, f"Intraday entries not allowed before {no_before} IST (current time {t_str})"
    if t_str > no_after:
        return False, f"Intraday entries not allowed after {no_after} IST ({'Thursday Expiry Shield' if is_thursday else 'Normal Cutoff'})"

    return True, "All risk rules passed"


def pre_trade_gate(order: dict, config: dict = None, now_ist: datetime.datetime = None) -> tuple:
    """Universal institutional pre-trade risk gate called before any order entry.
    Used by cockpit, autopilot, and REST APIs.
    """
    if config:
        cfg = config
    elif os.path.exists(DEFAULT_CONFIG_FILE):
        try:
            with open(DEFAULT_CONFIG_FILE, "r", encoding="utf-8-sig") as f:
                cfg = json.load(f)
        except Exception:
            cfg = DEFAULT_CONFIG
    else:
        cfg = DEFAULT_CONFIG
    now = now_ist or to_ist(datetime.datetime.now(datetime.timezone.utc))

    sym = order.get("symbol", "")
    
    # 1. Event Guard check
    guard = event_guard(sym, now)
    if not guard.get("allowed", True):
        return False, f"Event Guard Block: {guard.get('reason')}"

    # 2. Options strategies restriction (C9)
    strat = str(order.get("strategy_id", "")).lower()
    if any(opt_kw in strat for opt_kw in ["straddle", "strangle", "iron_condor", "expiry_buying", "option"]):
        return False, "C9 Restriction: Options strategies (13-16) are marked Analysis-Only. Execution blocked."

    # 3. Tradability check (3.9-C)
    t2t_blocked = {"ADANIPOWER.NS", "RPOWER.NS"}
    if sym in t2t_blocked:
        return False, f"Tradability Check: {sym} is in Trade-to-Trade (T2T) series. Intraday MIS blocked."

    # 4. Load today's broker state
    todays_broker = {}
    if os.path.exists(DEFAULT_BROKER_STATE):
        try:
            with open(DEFAULT_BROKER_STATE, "r", encoding="utf-8") as f:
                b_data = json.load(f)
            d_key = now.strftime("%Y-%m-%d")
            todays_broker = b_data.get(d_key, {})
        except Exception:
            pass

    return validate_order(order, cfg, now, todays_broker)


def main():
    p = argparse.ArgumentParser(description="Institutional Risk Manager for Indian Equities")
    p.add_argument("--orders", default=DEFAULT_ORDERS_FILE)
    p.add_argument("--config", default=DEFAULT_CONFIG_FILE)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-write", action="store_true")
    p.add_argument("--now", help="Simulate IST time, e.g. '2026-10-19 10:15'")
    p.add_argument("--vix", type=float, help="Explicit India VIX level")
    args = p.parse_args()

    now = parse_now(args.now)
    now_ist = to_ist(now)

    if not os.path.exists(args.orders):
        print(f"ERROR: {args.orders} not found. Run /trader-budget first.")
        sys.exit(1)

    with open(args.orders, "r", encoding="utf-8") as f:
        order_data = json.load(f)

    orders = order_data.get("orders", [])
    if not orders:
        print("No orders found to check.")
        sys.exit(1)

    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(args.config):
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass

    b_state = {}
    if os.path.exists(DEFAULT_BROKER_STATE):
        try:
            with open(DEFAULT_BROKER_STATE, "r", encoding="utf-8") as f:
                b_state = json.load(f).get(now_ist.strftime("%Y-%m-%d"), {})
        except Exception:
            pass

    vix_val = args.vix or fetch_india_vix()

    verdicts = []
    overall_pass = True

    vix_str = f" | India VIX: {vix_val:.1f}" if vix_val else ""
    print(f"Checking {len(orders)} order(s) against NSE risk rules as of {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}{vix_str}...")
    for idx, ord_spec in enumerate(orders, 1):
        fp = compute_order_fingerprint(ord_spec)
        passed, reason = validate_order(ord_spec, cfg, now_ist, b_state, current_vix=vix_val)
        v_entry = {
            "order_index": idx,
            "fingerprint": fp,
            "symbol": ord_spec.get("symbol"),
            "side": ord_spec.get("side"),
            "qty": ord_spec.get("qty"),
            "verdict": "PASS" if passed else "BLOCK",
            "reason": reason,
            "checked_at_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S")
        }
        verdicts.append(v_entry)
        if not passed:
            overall_pass = False

        status_tag = "[PASS]" if passed else "[BLOCK]"
        print(f"  {status_tag} Order #{idx}: {ord_spec.get('side')} {ord_spec.get('qty')} {ord_spec.get('symbol')} -> {reason}")

    if not args.no_write:
        os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_RISK_STATE)), exist_ok=True)
        risk_output = {
            "date": now_ist.strftime("%Y-%m-%d"),
            "overall_status": "READY" if overall_pass else "BLOCKED",
            "verdicts": verdicts
        }
        with open(DEFAULT_RISK_STATE, "w", encoding="utf-8") as f:
            json.dump(risk_output, f, indent=2)
        print(f"Recorded risk verdict to {DEFAULT_RISK_STATE}")

    if args.json:
        print(json.dumps(verdicts, indent=2))

    sys.exit(0 if overall_pass else 1)


if __name__ == "__main__":
    main()
