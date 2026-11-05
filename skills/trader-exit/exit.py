#!/usr/bin/env python3
"""Exit Planner & Trailing Stop Engine for trader-exit (Indian Equities - NSE/BSE).
Calculates stop-loss, 1R/2R targets, and dynamic ATR Trailing Stops.
Standard library only. Writes trader/plan.json.

    python3 exit.py                                    # reads trader/entry.json
    python3 exit.py --entry 3000 --stop 2970 --r 2.0 --symbol RELIANCE.NS
    python3 exit.py --trailing atr --atr-mult 1.5      # enable ATR trailing stop mode
    python3 exit.py --write                            # writes trader/plan.json
"""

import argparse
import json
import os
import sys

DEFAULT_ENTRY_FILE = "trader/entry.json"
DEFAULT_PLAN_FILE = "trader/plan.json"
FLAT_BY_DEFAULT = "15:10"


def round_tick(val: float, tick: float = 0.05) -> float:
    return round(round(val / tick) * tick, 2)


def calculate_net_rr(entry: float, stop: float, target: float, qty: int = 100):
    risk_pts = entry - stop
    target_pts = target - entry
    if risk_pts <= 0:
        return 0.0, 0.0

    gross_rr = round(target_pts / risk_pts, 2)

    turnover_entry = entry * qty
    turnover_target = target * qty
    turnover_stop = stop * qty

    # Charges if target hits
    stt_win = turnover_target * 0.00025
    stamp_win = turnover_entry * 0.00003
    exch_win = (turnover_entry + turnover_target) * 0.0000297
    brokerage_win = 40.0
    gst_win = (brokerage_win + exch_win) * 0.18
    tot_charges_win = stt_win + stamp_win + exch_win + brokerage_win + gst_win
    net_win = (target_pts * qty) - tot_charges_win

    # Charges if stop hits
    stt_loss = turnover_stop * 0.00025
    stamp_loss = turnover_entry * 0.00003
    exch_loss = (turnover_entry + turnover_stop) * 0.0000297
    brokerage_loss = 40.0
    gst_loss = (brokerage_loss + exch_loss) * 0.18
    tot_charges_loss = stt_loss + stamp_loss + exch_loss + brokerage_loss + gst_loss
    net_loss = (risk_pts * qty) + tot_charges_loss

    net_rr = round(net_win / net_loss, 2) if net_loss > 0 else 0.0
    return gross_rr, net_rr


def plan_exit(entry_price, range_high, range_low, range_mid, stop_mode="midpoint",
              target_r=2.0, custom_stop=None, custom_target=None, trailing_mode=None, atr_mult=1.5):
    if custom_stop is not None:
        stop = round_tick(custom_stop)
    elif stop_mode == "low" and range_low:
        stop = round_tick(range_low - 0.10)
    elif range_mid:
        stop = round_tick(range_mid)
    else:
        stop = round_tick(entry_price * 0.99)

    risk_per_share = round_tick(entry_price - stop)
    if risk_per_share <= 0:
        raise ValueError(f"Invalid stop Rs {stop:.2f} must be strictly below entry Rs {entry_price:.2f}")

    if custom_target is not None:
        target = round_tick(custom_target)
    else:
        target = round_tick(entry_price + (risk_per_share * target_r))

    gross_rr, net_rr = calculate_net_rr(entry_price, stop, target)

    # Trailing Stop Calculation (Suggestion #7)
    trailing_spec = None
    if trailing_mode == "atr":
        trail_pts = round_tick(risk_per_share * atr_mult)
        trailing_spec = {
            "type": "ATR_TRAILING",
            "distance_pts": trail_pts,
            "rule": f"Trail stop behind highest price by Rs {trail_pts:.2f} (1.5x risk)"
        }

    return {
        "entry": round_tick(entry_price),
        "stop": stop,
        "target": target,
        "risk_per_share": risk_per_share,
        "target_per_share": round_tick(target - entry_price),
        "gross_reward_risk": gross_rr,
        "net_reward_risk": net_rr,
        "flat_by": FLAT_BY_DEFAULT,
        "trailing_stop": trailing_spec
    }


def main():
    p = argparse.ArgumentParser(description="Exit Planner & Trailing Stops for Indian Equities")
    p.add_argument("--symbol", help="Stock ticker (e.g. RELIANCE.NS)")
    p.add_argument("--entry", type=float, help="Entry price in Rs")
    p.add_argument("--stop", type=float, help="Explicit stop loss price in Rs")
    p.add_argument("--target", type=float, help="Explicit target price in Rs")
    p.add_argument("--stop-mode", choices=["midpoint", "low"], default="midpoint")
    p.add_argument("--r", type=float, default=2.0, help="Target multiple (e.g. 1.5, 2.0)")
    p.add_argument("--trailing", choices=["none", "atr"], default="atr", help="Trailing stop mechanism")
    p.add_argument("--atr-mult", type=float, default=1.5, help="Multiplier for ATR trailing stop")
    p.add_argument("--flat-by", default=FLAT_BY_DEFAULT, help="Mandatory squareoff time (IST)")
    p.add_argument("--write", action="store_true", help="Write to trader/plan.json")
    args = p.parse_args()

    sym = args.symbol
    entry_val = args.entry
    range_high = None
    range_low = None
    range_mid = None

    if not entry_val:
        if not os.path.exists(DEFAULT_ENTRY_FILE):
            print(f"ERROR: No --entry specified and {DEFAULT_ENTRY_FILE} not found. Run /trader-entry first.")
            sys.exit(1)
        with open(DEFAULT_ENTRY_FILE, "r", encoding="utf-8") as f:
            e = json.load(f)
        sym = sym or e.get("symbol")
        entry_val = e.get("entry_price")
        range_high = e.get("range_high")
        range_low = e.get("range_low")
        range_mid = e.get("range_mid")

    if not sym or not entry_val:
        print("ERROR: Symbol and entry price required.")
        sys.exit(1)

    try:
        plan = plan_exit(
            entry_price=entry_val,
            range_high=range_high,
            range_low=range_low,
            range_mid=range_mid,
            stop_mode=args.stop_mode,
            target_r=args.r,
            custom_stop=args.stop,
            custom_target=args.target,
            trailing_mode=args.trailing if args.trailing != "none" else None,
            atr_mult=args.atr_mult
        )
        plan["symbol"] = sym
        plan["flat_by"] = args.flat_by

        print(f"==================================================")
        print(f"TRADE EXIT PLAN: {sym}")
        print(f"==================================================")
        print(f"Entry Price:     Rs {plan['entry']:,.2f}")
        print(f"Initial Stop:    Rs {plan['stop']:,.2f}  (Risk: Rs {plan['risk_per_share']:.2f}/sh)")
        print(f"Target:          Rs {plan['target']:,.2f}  (Gain: Rs {plan['target_per_share']:.2f}/sh)")
        print(f"Gross R:R:       {plan['gross_reward_risk']}:1")
        print(f"Net R:R (Taxes): {plan['net_reward_risk']}:1 (Net of STT, GST, Stamp Duty & Brokerage)")
        if plan.get("trailing_stop"):
            print(f"Trailing Stop:   {plan['trailing_stop']['rule']}")
        print(f"Square-off Time: {plan['flat_by']} IST (Before broker auto-squareoff)")
        print(f"==================================================")

        if args.write:
            os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_PLAN_FILE)), exist_ok=True)
            with open(DEFAULT_PLAN_FILE, "w", encoding="utf-8") as f:
                json.dump(plan, f, indent=2)
            print(f"Wrote trade plan to {DEFAULT_PLAN_FILE}")
        sys.exit(0)

    except Exception as err:
        print(f"ERROR planning exit: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
