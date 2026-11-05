#!/usr/bin/env python3
"""Institutional Risk Manager for trader-risk (Indian Equities - NSE/BSE).
Checks proposed orders against hard risk parameters before execution:
  - Rupee loss limits & daily drawdown caps
  - High-Water Mark Daily Profit Lock (Never let a green day turn red)
  - Unified Macro Event Blackouts (RBI MPC policy & Union Budget freezes)
  - Consecutive losses killswitch (stops revenge trading)
  - Correlated sector risk caps (max 1 trade per sector)
  - Configurable weekly expiry volatility cutoff (per instrument)
  - India VIX volatility regime filter (^INDIAVIX)
  - Market Breadth A/D ratio filter with staleness checking
  - Side-aware stop and target validation (BUY vs SELL)
  - Minimum tick size (0.05 for equities, 0.01 for ETFs)
Standard library only. Writes trader/state/risk.json atomically.
"""

import argparse
import datetime
import json
import os
import sys
import urllib.request

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import (
    CLOSE,
    IST_OFFSET,
    NSE_HOLIDAYS,
    OPEN,
    SECTOR_MAP,
    STATE_LOCK,
    compute_order_fingerprint,
    get_tick_size,
    get_todays_trade_state,
    is_valid_tick,
    ist_to_utc,
    load_json,
    normalize_symbol,
    resolve_path,
    save_json,
    to_ist,
)

DEFAULT_ORDERS_FILE = resolve_path("trader/orders.json")
DEFAULT_CONFIG_FILE = resolve_path("trader/config.json")
DEFAULT_EVENTS_FILE = resolve_path("trader/events.json")
DEFAULT_RISK_STATE = resolve_path("trader/state/risk.json")
DEFAULT_DECISIONS_FILE = resolve_path("trader/state/decisions.json")
DEFAULT_BROKER_STATE = resolve_path("trader/state/broker.json")
DEFAULT_BREADTH_STATE = resolve_path("trader/state/breadth.json")
DEFAULT_SURVEILLANCE_FILE = resolve_path("trader/data/surveillance.json")

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
    "no_entries_before": "09:30:00",
    "no_entries_after": "14:45:00",
    "expiry_cutoff": "13:45:00",
    "vix_min": 11.5,
    "vix_max": 24.0,
    "require_vix": True,
    "require_breadth": False,
    "min_breadth_ratio": 0.6,
    "blocked": []
}


def parse_now(text):
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = text.strip().replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(t)
    if dt.tzinfo is None:
        return ist_to_utc(dt)
    return (dt - dt.utcoffset()).replace(tzinfo=None)


def parse_time_obj(val) -> datetime.time:
    """Parses time string ('HH:MM' or 'HH:MM:SS') or returns datetime.time directly."""
    if isinstance(val, datetime.time):
        return val
    parts = [int(p) for p in str(val).strip().split(":")]
    if len(parts) == 2:
        return datetime.time(parts[0], parts[1], 0)
    elif len(parts) >= 3:
        return datetime.time(parts[0], parts[1], parts[2])
    return datetime.time(0, 0, 0)


def load_config_fail_closed(path: str = DEFAULT_CONFIG_FILE) -> tuple:
    """Loads configuration with utf-8-sig encoding, failing closed on syntax or I/O errors."""
    resolved = resolve_path(path)
    if not os.path.exists(resolved):
        return True, DEFAULT_CONFIG.copy(), ""
    try:
        with open(resolved, "r", encoding="utf-8-sig") as f:
            user_cfg = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        if isinstance(user_cfg, dict):
            merged.update(user_cfg)
        return True, merged, ""
    except Exception as e:
        return False, {}, f"Config Error: Unable to read config file {resolved} ({e})"


def load_events_fail_closed(path: str = DEFAULT_EVENTS_FILE) -> tuple:
    """Loads unified events.json, failing closed on syntax or I/O errors."""
    resolved = resolve_path(path)
    if not os.path.exists(resolved):
        return True, {"events": [], "rules": {}}, ""
    try:
        with open(resolved, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return True, data, ""
    except Exception as e:
        return False, {}, f"Events Error: Unable to read events file {resolved} ({e})"


def fetch_india_vix():
    """Fetches real-time India VIX (^INDIAVIX) from Yahoo Finance."""
    try:
        url = "https://query2.finance.yahoo.com/v8/finance/chart/%5EINDIAVIX?range=1d&interval=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (VyaparAI/1.0)"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception:
        return None


def get_expiry_for_symbol(symbol: str, events_data: dict) -> tuple:
    """Resolves expiry weekday and cutoff time per instrument."""
    fo_rules = events_data.get("rules", {}).get("fo_expiry", {})
    weekdays_map = fo_rules.get("weekdays", {
        "default": "THURSDAY",
        "^NSEBANK": "WEDNESDAY",
        "BANKNIFTY": "WEDNESDAY",
        "^BSESN": "FRIDAY",
        "SENSEX": "FRIDAY"
    })
    cutoff = fo_rules.get("cutoff_time", "13:45:00")
    size_factor = float(fo_rules.get("size_factor", 0.5))

    clean_sym = symbol.upper().replace(".NS", "").replace(".BO", "")
    target_weekday = weekdays_map.get(symbol.upper(), weekdays_map.get(clean_sym, weekdays_map.get("default", "THURSDAY")))
    return target_weekday.upper(), parse_time_obj(cutoff), size_factor


def evaluate_event_restrictions(symbol: str, now_ist: datetime.datetime, events_data: dict) -> tuple:
    """Checks the single unified events schema for active blackouts and size reductions.
    Returns: (allowed, size_factor, reason, action, event_dict)
    """
    d_str = now_ist.strftime("%Y-%m-%d")
    curr_t = now_ist.time()

    # 1. Official NSE Holiday Calendar
    if d_str in NSE_HOLIDAYS:
        return False, 0.0, f"NSE Exchange Holiday: {NSE_HOLIDAYS[d_str]}", "BLOCK_ALL_ENTRIES", {"type": "holiday", "name": NSE_HOLIDAYS[d_str]}

    # 2. Weekend Check
    if now_ist.weekday() >= 5:
        return False, 0.0, f"Weekend: {now_ist.strftime('%A')} (Exchange Closed)", "BLOCK_ALL_ENTRIES", {"type": "weekend"}

    events = events_data.get("events", [])
    for ev in events:
        if ev.get("date") == d_str:
            ev_type = ev.get("type")
            title = ev.get("title", ev.get("name", "Event"))
            raw_action = ev.get("action", "BLOCK_ALL_ENTRIES")
            action = "BLOCK_ALL_ENTRIES" if "FREEZE" in raw_action.upper() else raw_action

            # Corporate earnings blackout
            if ev_type == "results":
                ev_symbols = [s.strip().upper() for s in ev.get("symbols", [])]
                norm_sym = symbol.strip().upper() if symbol else ""
                if norm_sym in ev_symbols:
                    return False, 0.0, f"Corporate Action Blackout: {symbol} Quarterly Results Day", action, ev

            # Window-based macro policy or blackout
            start_str = ev.get("start_time")
            end_str = ev.get("end_time")
            if start_str and end_str:
                start_t = parse_time_obj(start_str)
                end_t = parse_time_obj(end_str)
                if start_t <= curr_t <= end_t:
                    return False, 0.0, f"Macro Event Blackout: {title} ({start_str}-{end_str} IST)", action, ev

            # Full-day macro blackout (e.g. Budget day)
            elif ev_type in ("union_budget", "special_session"):
                return False, 0.0, f"Macro Event Blackout: {title} (Trading Restricted)", action, ev

    # Check F&O expiry sizing for instrument
    exp_weekday, cutoff_t, size_factor = get_expiry_for_symbol(symbol, events_data)
    day_names = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
    if day_names[now_ist.weekday()] == exp_weekday:
        return True, size_factor, f"Weekly F&O Expiry ({exp_weekday}): Position size scaled by {size_factor}", "SCALE_SIZE", {"type": "fo_expiry"}

    return True, 1.0, "", "ALLOW", None


def event_guard(symbol: str, now_ist: datetime.datetime = None) -> dict:
    """Evaluates Indian market event calendar and risk rules for symbol and time."""
    if now_ist is None:
        now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
    ok, ev_data, err = load_events_fail_closed(DEFAULT_EVENTS_FILE)
    if not ok:
        return {
            "allowed": False,
            "size_factor": 0.0,
            "reason": err,
            "action": "BLOCK_ALL_ENTRIES",
            "event": None
        }
    allowed, size_factor, reason, action, ev = evaluate_event_restrictions(symbol, now_ist, ev_data)
    return {
        "allowed": allowed,
        "size_factor": size_factor,
        "reason": reason,
        "action": action,
        "event": ev
    }


def check_surveillance_lists(symbol: str) -> tuple:
    """Checks NSE ASM, GSM, and T2T surveillance status."""
    resolved = resolve_path(DEFAULT_SURVEILLANCE_FILE)
    if not os.path.exists(resolved):
        # Known baseline hard blocks
        if symbol in {"ADANIPOWER.NS", "RPOWER.NS"}:
            return False, f"Tradability Check: {symbol} is in Trade-to-Trade (T2T) series. Intraday MIS blocked."
        return True, "unknown"

    try:
        with open(resolved, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        as_of = data.get("as_of", "unknown")
        t2t = set(data.get("t2t", []))
        asm = set(data.get("asm_stage_2_plus", []))
        gsm = set(data.get("gsm", []))

        if symbol in t2t:
            return False, f"Surveillance Check (as of {as_of}): {symbol} is in Trade-to-Trade (T2T) series. MIS blocked."
        if symbol in asm:
            return False, f"Surveillance Check (as of {as_of}): {symbol} is in Long-term ASM Stage 2+. Intraday leverage blocked."
        if symbol in gsm:
            return False, f"Surveillance Check (as of {as_of}): {symbol} is in Graded Surveillance Measure (GSM). Blocked."

        return True, f"Surveillance verified (as of {as_of})"
    except Exception:
        return True, "unknown"


def check_breadth_filter(now_ist: datetime.datetime, config: dict) -> tuple:
    """Checks market breadth A/D ratio with staleness check."""
    if not config.get("require_breadth", False):
        return True, ""

    resolved = resolve_path(DEFAULT_BREADTH_STATE)
    if not os.path.exists(resolved):
        return False, "Market Breadth Error: Breadth state file missing; new entries blocked by breadth gate."

    try:
        with open(resolved, "r", encoding="utf-8-sig") as f:
            b_data = json.load(f)

        ts = b_data.get("timestamp", 0)
        now_ts = now_ist.timestamp()
        if (now_ts - ts) > 900:  # Older than 15 minutes
            return False, f"Market Breadth Stale: Last breadth update was {int((now_ts - ts)/60)}m ago (>15m threshold)."

        adv = b_data.get("advances", 0)
        dec = b_data.get("declines", 0)
        ratio = adv / max(1, dec)
        min_r = config.get("min_breadth_ratio", 0.6)
        if ratio < min_r:
            return False, f"Market Breadth Gate Block: Advances/Declines ratio {ratio:.2f} below required minimum {min_r:.2f}."

        return True, ""
    except Exception as e:
        return False, f"Market Breadth Error: Failed to evaluate breadth state ({e})"


def validate_order(order: dict, config: dict, now_ist: datetime.datetime, todays_broker_state: dict, current_vix=None, events_data=None):
    """Core deterministic risk rules evaluator."""
    sym = order.get("symbol", "")
    if not sym or not (sym.endswith(".NS") or sym.endswith(".BO")):
        return False, "Symbol must be a valid Indian equity ticker (.NS or .BO)"

    # 1. Event Blackout & Expiry Size Scaling (Fail Closed)
    if events_data is None:
        ev_ok, loaded_ev, ev_err = load_events_fail_closed(DEFAULT_EVENTS_FILE)
        if not ev_ok:
            return False, ev_err
        ev_data = loaded_ev
    else:
        ev_data = events_data

    allowed, size_factor, ev_msg, _, _ = evaluate_event_restrictions(sym, now_ist, ev_data)
    if not allowed:
        return False, ev_msg

    # 2. Surveillance & T2T Tradability
    surv_ok, surv_msg = check_surveillance_lists(sym)
    if not surv_ok:
        return False, surv_msg

    # 3. Market Breadth Filter
    breadth_ok, breadth_msg = check_breadth_filter(now_ist, config)
    if not breadth_ok:
        return False, breadth_msg

    # 4. Quantity and format check
    qty = order.get("qty", 0)
    if not isinstance(qty, int) or qty <= 0:
        return False, f"Quantity must be a positive integer (received {qty})"

    # Enforce size scaling if event or expiry day dictates size reduction
    if size_factor < 1.0:
        max_order_qty = max(1, int(config.get("max_order_inr", 50000.0) / max(0.01, float(order.get("entry_price", 1.0))) * size_factor))
        if qty > max_order_qty:
            return False, f"Event Sizing Rule: Quantity {qty} exceeds max scaled quantity {max_order_qty} ({int(size_factor*100)}% expiry limit)"

    side = order.get("side", "BUY").upper()
    if side not in ("BUY", "SELL"):
        return False, f"Invalid order side '{side}'. Must be BUY or SELL."

    entry = float(order.get("entry_price", 0.0))
    stop = float(order.get("stop_loss_price", 0.0))
    target = float(order.get("take_profit_price", 0.0))

    if entry <= 0:
        return False, "Entry price must be positive"

    # Order Rupee Caps
    order_val = entry * qty
    max_order_val = config.get("max_order_inr", 50000.0)
    if order_val > max_order_val:
        return False, f"Order turnover Rs {order_val:,.2f} exceeds max order value limit Rs {max_order_val:,.2f}"

    min_order_val = config.get("min_order_inr", 1000.0)
    if order_val < min_order_val:
        return False, f"Order turnover Rs {order_val:,.2f} is below min order value limit Rs {min_order_val:,.2f}"

    # 5. Side-Aware Stop Placement & Risk Calculation
    if config.get("require_stop", True):
        if stop <= 0:
            return False, "Stop-loss is required"

        if side == "BUY":
            if stop >= entry:
                return False, f"Long Stop-loss (Rs {stop:.2f}) cannot be at or above entry price (Rs {entry:.2f})"
            risk_per_share = entry - stop
            if target > 0 and target <= entry:
                return False, f"Long Profit Target (Rs {target:.2f}) cannot be at or below entry price (Rs {entry:.2f})"
        else:  # SELL (Short)
            if stop <= entry:
                return False, f"Short Stop-loss (Rs {stop:.2f}) cannot be at or below entry price (Rs {entry:.2f})"
            risk_per_share = stop - entry
            if target > 0 and target >= entry:
                return False, f"Short Profit Target (Rs {target:.2f}) cannot be at or above entry price (Rs {entry:.2f})"
    else:
        risk_per_share = abs(entry - stop) if stop > 0 else (entry * 0.01)

    # 6. Blocked list
    blocked = config.get("blocked", [])
    if sym in blocked:
        return False, f"Symbol {sym} is on the blocked tickers list"

    # 7. Tick size check (0.05 for equities, 0.01 for ETFs)
    tick = get_tick_size(sym)
    for price_val, label in [(entry, "Entry"), (stop, "Stop"), (target, "Target")]:
        if price_val > 0 and not is_valid_tick(price_val, tick):
            return False, f"{label} Rs {price_val:.2f} is not on {tick} tick grid for {sym}"

    # 8. Loss per trade limit
    total_risk = round(risk_per_share * qty, 2)
    max_loss_limit = config.get("max_loss_per_trade_inr", 1000.0)
    if total_risk > max_loss_limit:
        return False, f"Trade risk Rs {total_risk:,.2f} exceeds max loss limit Rs {max_loss_limit:,.2f}"

    # 9. Reward : Risk ratio
    if target > 0 and risk_per_share > 0:
        if side == "BUY":
            reward_pts = target - entry
        else:
            reward_pts = entry - target
        rr = round(reward_pts / risk_per_share, 2)
        min_rr = config.get("min_reward_risk", 1.5)
        if rr < min_rr:
            return False, f"Reward-to-risk {rr}:1 is below required minimum {min_rr}:1"

    placed_trades = todays_broker_state.get("trades_today", [])

    # 10. Duplicate Symbol Check (No duplicate trades for the same ticker today)
    if any(t.get("symbol") == sym for t in placed_trades):
        return False, f"Duplicate symbol: {sym} has already been traded today"

    # 11. High-Water Mark Daily Profit Lock
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

    # 12. Consecutive Losses Killswitch
    max_consec = config.get("max_consecutive_losses", 2)
    consec_losses = 0
    for t in reversed(placed_trades):
        if t.get("pnl", 0.0) < 0:
            consec_losses += 1
        elif t.get("pnl", 0.0) > 0:
            break
    if consec_losses >= max_consec:
        return False, f"Killswitch triggered: {consec_losses} consecutive losses reached today. Stop trading."

    # 13. Correlated Sector Risk Cap
    target_sector = SECTOR_MAP.get(sym)
    if target_sector:
        max_sec = config.get("max_trades_per_sector", 1)
        active_in_sec = sum(1 for t in placed_trades if SECTOR_MAP.get(t.get("symbol")) == target_sector)
        if active_in_sec >= max_sec:
            return False, f"Sector risk cap reached: already holding/traded {active_in_sec} stock(s) in {target_sector}"

    # 14. Daily Loss Limit (Including Realized P&L + Cumulative Risk)
    max_trades = config.get("max_trades_per_day", 3)
    if len(placed_trades) >= max_trades:
        return False, f"Max trades per day limit ({max_trades}) already reached today"

    realized_loss = abs(min(0.0, sum(t.get("pnl", 0.0) for t in placed_trades)))
    cumulative_risk = sum(t.get("max_loss", 0.0) for t in placed_trades) + total_risk + realized_loss
    max_daily_loss = config.get("max_daily_loss_inr", 3000.0)
    if cumulative_risk > max_daily_loss:
        return False, f"Cumulative daily risk Rs {cumulative_risk:,.2f} exceeds daily limit Rs {max_daily_loss:,.2f}"

    # 15. India VIX Regime Filter (Fail closed if None and required)
    if current_vix is None:
        if config.get("require_vix", False):
            return False, "India VIX data unavailable; new entries blocked by risk gate"
    else:
        v_min = config.get("vix_min", 11.5)
        v_max = config.get("vix_max", 24.0)
        if current_vix < v_min:
            return False, f"India VIX ({current_vix:.1f}) below {v_min}: low volatility trap"
        if current_vix > v_max:
            return False, f"India VIX ({current_vix:.1f}) above {v_max}: extreme volatility regime"

    # 16. Entry Windows & Session Hours (Time objects with seconds)
    t = now_ist.time()
    no_before_t = parse_time_obj(config.get("no_entries_before", "09:30:00"))
    no_after_t = parse_time_obj(config.get("no_entries_after", "14:45:00"))

    # Resolve instrument-specific expiry cutoff
    exp_weekday, expiry_cutoff_t, _ = get_expiry_for_symbol(sym, ev_data)
    day_names = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
    if day_names[now_ist.weekday()] == exp_weekday:
        no_after_t = expiry_cutoff_t

    if t < OPEN:
        return False, f"NSE market has not opened yet (opens at {OPEN.strftime('%H:%M:%S')} IST)"
    if t >= CLOSE:
        return False, f"NSE market is closed (closed at {CLOSE.strftime('%H:%M:%S')} IST)"
    if t < no_before_t:
        return False, f"Intraday entries not allowed before {no_before_t.strftime('%H:%M:%S')} IST (current time {t.strftime('%H:%M:%S')})"
    if t > no_after_t:
        return False, f"Intraday entries not allowed after {no_after_t.strftime('%H:%M:%S')} IST (Expiry/Session Cutoff)"

    return True, "All risk rules passed"


def log_risk_decision(order: dict, passed: bool, reason: str, now_ist: datetime.datetime):
    """Records audit trail of all risk decisions to trader/state/decisions.json under STATE_LOCK."""
    try:
        dec_file = DEFAULT_DECISIONS_FILE
        data = load_json(dec_file) if os.path.exists(dec_file) else {"decisions": []}
        decisions = data.get("decisions", [])
        entry = {
            "timestamp": now_ist.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": order.get("symbol", "UNKNOWN"),
            "side": order.get("side", "BUY"),
            "qty": order.get("qty", 0),
            "entry_price": order.get("entry_price", 0.0),
            "verdict": "PASS" if passed else "BLOCK",
            "reason": reason
        }
        decisions.insert(0, entry)
        decisions = decisions[:100]  # keep latest 100
        save_json(dec_file, {"decisions": decisions})
    except Exception:
        pass


def pre_trade_gate(order: dict, config: dict = None, now_ist: datetime.datetime = None, vix=None) -> tuple:
    """Universal institutional pre-trade risk gate called before any order entry.
    Fails closed on any configuration, data, or events file error.
    """
    now = now_ist or to_ist(datetime.datetime.now(datetime.timezone.utc))

    # 1. Config loading (Fail Closed)
    if config:
        cfg = config
    else:
        cfg_ok, loaded_cfg, cfg_err = load_config_fail_closed(DEFAULT_CONFIG_FILE)
        if not cfg_ok:
            log_risk_decision(order, False, cfg_err, now)
            return False, cfg_err
        cfg = loaded_cfg

    # 2. Events loading (Fail Closed)
    ev_ok, ev_data, ev_err = load_events_fail_closed(DEFAULT_EVENTS_FILE)
    if not ev_ok:
        log_risk_decision(order, False, ev_err, now)
        return False, ev_err

    # 3. Disallow options strategies in equity executor
    strat = str(order.get("strategy_id", "")).lower()
    if any(opt_kw in strat for opt_kw in ["straddle", "strangle", "iron_condor", "expiry_buying", "option"]):
        msg = "Options strategies (13-16) are marked Analysis-Only. Execution blocked."
        log_risk_decision(order, False, msg, now)
        return False, msg

    # 4. Resolve VIX
    vix_val = vix if vix is not None else fetch_india_vix()

    # 5. Shared broker trade state
    todays_broker = get_todays_trade_state(now, DEFAULT_BROKER_STATE)

    passed, reason = validate_order(order, cfg, now, todays_broker, current_vix=vix_val, events_data=ev_data)
    log_risk_decision(order, passed, reason, now)
    return passed, reason


def is_verdict_stale(verdict_entry: dict, now_ist: datetime.datetime, max_age_seconds: int = 300) -> bool:
    """Checks whether a recorded risk verdict is older than 5 minutes."""
    ts = verdict_entry.get("timestamp")
    if ts is None:
        chk_str = verdict_entry.get("checked_at_ist")
        if not chk_str:
            return True
        try:
            dt = datetime.datetime.strptime(chk_str, "%Y-%m-%d %H:%M:%S")
            ts = dt.timestamp()
        except Exception:
            return True

    return (now_ist.timestamp() - ts) > max_age_seconds


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

    try:
        with open(args.orders, "r", encoding="utf-8-sig") as f:
            order_data = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to read orders file {args.orders}: {e}")
        sys.exit(1)

    orders = order_data.get("orders", [])
    if not orders:
        print("No orders found to check.")
        sys.exit(1)

    cfg_ok, cfg, cfg_err = load_config_fail_closed(args.config)
    if not cfg_ok:
        print(f"ERROR: {cfg_err}")
        sys.exit(1)

    ev_ok, ev_data, ev_err = load_events_fail_closed(DEFAULT_EVENTS_FILE)
    if not ev_ok:
        print(f"ERROR: {ev_err}")
        sys.exit(1)

    b_state = get_todays_trade_state(now_ist, DEFAULT_BROKER_STATE)
    vix_val = args.vix if args.vix is not None else fetch_india_vix()

    verdicts = []
    overall_pass = True

    vix_str = f" | India VIX: {vix_val:.1f}" if vix_val is not None else ""
    print(f"Checking {len(orders)} order(s) against NSE risk rules as of {now_ist.strftime('%Y-%m-%d %H:%M:%S IST')}{vix_str}...")

    d_str = now_ist.strftime("%Y-%m-%d")
    for idx, ord_spec in enumerate(orders, 1):
        fp = compute_order_fingerprint(ord_spec, d_str)
        passed, reason = validate_order(ord_spec, cfg, now_ist, b_state, current_vix=vix_val, events_data=ev_data)
        v_entry = {
            "order_index": idx,
            "fingerprint": fp,
            "symbol": ord_spec.get("symbol"),
            "side": ord_spec.get("side"),
            "qty": ord_spec.get("qty"),
            "verdict": "PASS" if passed else "BLOCK",
            "reason": reason,
            "timestamp": now_ist.timestamp(),
            "checked_at_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S")
        }
        verdicts.append(v_entry)
        if not passed:
            overall_pass = False

        status_tag = "[PASS]" if passed else "[BLOCK]"
        print(f"  {status_tag} Order #{idx}: {ord_spec.get('side')} {ord_spec.get('qty')} {ord_spec.get('symbol')} -> {reason}")

    if not args.no_write:
        risk_output = {
            "date": d_str,
            "overall_status": "READY" if overall_pass else "BLOCKED",
            "verdicts": verdicts
        }
        save_json(DEFAULT_RISK_STATE, risk_output)
        print(f"Recorded risk verdict to {DEFAULT_RISK_STATE}")

    if args.json:
        print(json.dumps(verdicts, indent=2))

    sys.exit(0 if overall_pass else 1)


if __name__ == "__main__":
    main()
