#!/usr/bin/env python3
"""Order Tickets & Broker Execution for trader-broker (Indian Equities - NSE/BSE).
Renders plain-text approval tickets, generates copy-ready API payloads for
Zerodha Kite Connect, Angel One SmartAPI, and Shoonya (Finvasia), and provides
a built-in Paper Trading execution simulator. Standard library only.

    python3 ticket.py show                           # display tickets & broker payloads
    python3 ticket.py approve --index 1 --reply "yes" # record explicit yes
    python3 ticket.py fill --symbol RELIANCE.NS --side buy --qty 16 --price 3000.00
    python3 ticket.py flatten --symbol RELIANCE.NS --qty 16
    python3 ticket.py log                            # display day's trade ledger
"""

import argparse
import datetime
import hashlib
import json
import os
import sys

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import (
    IST_OFFSET,
    compute_order_fingerprint,
    load_json,
    record_placed_trade,
    resolve_path,
    save_json,
    to_ist,
)

DEFAULT_ORDERS_FILE = resolve_path("trader/orders.json")
DEFAULT_RISK_STATE = resolve_path("trader/state/risk.json")
DEFAULT_BROKER_STATE = resolve_path("trader/state/broker.json")
DEFAULT_PORTFOLIO_FILE = resolve_path("trader/portfolio.json")


def compute_fingerprint(order: dict, trade_date: str = None) -> str:
    return compute_order_fingerprint(order, trade_date)


def format_zerodha_payload(order: dict) -> str:
    sym = order.get("symbol", "").replace(".NS", "").replace(".BO", "")
    return f"""# Zerodha Kite Connect Python Snippet
kite.place_order(
    variety=kite.VARIETY_REGULAR,
    exchange=kite.EXCHANGE_NSE,
    tradingsymbol="{sym}",
    transaction_type=kite.TRANSACTION_TYPE_{order.get('side', 'BUY').upper()},
    quantity={order.get('qty', 1)},
    product=kite.PRODUCT_MIS,
    order_type=kite.ORDER_TYPE_LIMIT,
    price={order.get('entry_price', 0.0):.2f}
)"""


def format_angel_payload(order: dict) -> dict:
    sym = order.get("symbol", "").replace(".NS", "").replace(".BO", "")
    return {
        "variety": "NORMAL",
        "tradingsymbol": f"{sym}-EQ",
        "symboltoken": "3045",  # broker token
        "transactiontype": order.get("side", "BUY").upper(),
        "exchange": "NSE",
        "ordertype": "LIMIT",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "price": f"{order.get('entry_price', 0.0):.2f}",
        "quantity": str(order.get("qty", 1))
    }


def format_shoonya_payload(order: dict) -> dict:
    sym = order.get("symbol", "").replace(".NS", "").replace(".BO", "")
    return {
        "buy_or_sell": "B" if order.get("side", "BUY").upper() == "BUY" else "S",
        "product_type": "M",  # MIS
        "exchange": "NSE",
        "tradingsymbol": f"{sym}-EQ",
        "quantity": order.get("qty", 1),
        "price_type": "LMT",
        "price": order.get("entry_price", 0.0)
    }


def cmd_show(args):
    if not os.path.exists(DEFAULT_ORDERS_FILE):
        print(f"ERROR: {DEFAULT_ORDERS_FILE} not found. Run /trader-budget first.")
        sys.exit(1)

    with open(DEFAULT_ORDERS_FILE, "r", encoding="utf-8") as f:
        orders = json.load(f).get("orders", [])

    risk_verdicts = {}
    if os.path.exists(DEFAULT_RISK_STATE):
        try:
            with open(DEFAULT_RISK_STATE, "r", encoding="utf-8") as f:
                v_list = json.load(f).get("verdicts", [])
                for v in v_list:
                    risk_verdicts[v.get("fingerprint")] = v
        except Exception:
            pass

    print(f"Found {len(orders)} order proposal(s):\n")
    for idx, ord_spec in enumerate(orders, 1):
        fp = compute_fingerprint(ord_spec)
        rv = risk_verdicts.get(fp, {})
        passed = (rv.get("verdict") == "PASS")
        status_label = "READY TO EXECUTE" if passed else "BLOCKED BY RISK RULES"

        print("==================================================")
        print(f"ORDER TICKET #{idx} [{status_label}]")
        print("==================================================")
        print(f"Action:          {ord_spec.get('side')} {ord_spec.get('qty')} shares of {ord_spec.get('symbol')}")
        print(f"Exchange:        {ord_spec.get('exchange', 'NSE')} (Product: {ord_spec.get('product', 'MIS')})")
        print(f"Limit Price:     Rs {ord_spec.get('entry_price', 0.0):,.2f}")
        print(f"Stop-Loss:       Rs {ord_spec.get('stop_loss_price', 0.0):,.2f}")
        print(f"Target:          Rs {ord_spec.get('take_profit_price', 0.0):,.2f}")
        print(f"Total Value:     Rs {ord_spec.get('order_value', 0.0):,.2f}")
        print(f"Max Loss:        Rs {ord_spec.get('actual_loss_at_stop', 0.0):,.2f} (Net of taxes)")
        print(f"Net Gain:        Rs {ord_spec.get('actual_gain_at_target', 0.0):,.2f} (Net of taxes)")
        print(f"Square-off:      {ord_spec.get('flat_by', '15:10')} IST")
        print(f"Security Hash:   {fp} (Risk check: {rv.get('verdict', 'NOT_CHECKED')})")

        if args.broker == "zerodha":
            print("\n" + format_zerodha_payload(ord_spec))
        elif args.broker == "angel":
            print("\n# Angel One SmartAPI JSON:")
            print(json.dumps(format_angel_payload(ord_spec), indent=2))
        elif args.broker == "shoonya":
            print("\n# Shoonya (Finvasia) Order Payload:")
            print(json.dumps(format_shoonya_payload(ord_spec), indent=2))
        else:
            print("\n[Default: Paper Trading Mode active. Reply 'yes' to simulate paper execution.]")
        print("==================================================\n")
    sys.exit(0)


def cmd_approve(args):
    reply = (args.reply or "").strip().lower()
    if reply not in ("yes", "y", "approved"):
        print(f"ERROR: Explicit approval required. Received '{args.reply}'. No order placed.")
        sys.exit(1)

    if not os.path.exists(DEFAULT_ORDERS_FILE):
        print(f"ERROR: {DEFAULT_ORDERS_FILE} not found.")
        sys.exit(1)

    with open(DEFAULT_ORDERS_FILE, "r", encoding="utf-8") as f:
        orders = json.load(f).get("orders", [])

    idx = args.index - 1
    if idx < 0 or idx >= len(orders):
        print(f"ERROR: Invalid order index {args.index}")
        sys.exit(1)

    now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
    d_str = now_ist.strftime("%Y-%m-%d")

    ord_spec = orders[idx]
    fp = compute_fingerprint(ord_spec, d_str)

    # Check risk verdict
    if not os.path.exists(DEFAULT_RISK_STATE):
        print("ERROR: Orders must pass /trader-risk before approval.")
        sys.exit(1)

    with open(DEFAULT_RISK_STATE, "r", encoding="utf-8-sig") as f:
        v_list = json.load(f).get("verdicts", [])
        v_map = {v.get("fingerprint"): v for v in v_list}

    rv = v_map.get(fp)
    if rv is None:
        print(f"ERROR: No risk verdict found for Order #{args.index} (fingerprint: {fp}). Re-run /trader-risk.")
        sys.exit(1)

    if rv.get("verdict") != "PASS":
        print(f"ERROR: Order #{args.index} was BLOCKED by risk check: {rv.get('reason', 'no record')}")
        sys.exit(1)

    # Check for stale verdict (> 5 minutes / 300 seconds)
    v_ts = rv.get("timestamp")
    if v_ts and (now_ist.timestamp() - v_ts) > 300:
        print(f"ERROR: Risk verdict for Order #{args.index} is older than 5 minutes ({int((now_ist.timestamp() - v_ts)/60)}m old). Re-run /trader-risk.")
        sys.exit(1)

    # Check idempotency: refuse second approval of same order today
    b_data = load_json(DEFAULT_BROKER_STATE, {})
    day_entry = b_data.get(d_str, {})
    if any(o.get("fingerprint") == fp for o in day_entry.get("orders_placed", [])):
        print(f"ERROR: Order #{args.index} has already been approved and recorded.")
        sys.exit(1)

    # Record in shared broker state
    record_placed_trade(ord_spec, now_ist)

    print(f"===> [ORDER #{args.index} APPROVED & RECORDED]")
    print(f"     Placed order for {ord_spec['qty']} shares of {ord_spec['symbol']} at Rs {ord_spec['entry_price']:,.2f}")
    print(f"     Logged trade risk (Rs {ord_spec.get('actual_loss_at_stop', 0):,.2f}) to daily limits.")
    sys.exit(0)


def cmd_fill(args):
    now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
    p_data = {"cash": 100000.0, "holdings": {}}
    if os.path.exists(DEFAULT_PORTFOLIO_FILE):
        try:
            with open(DEFAULT_PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                p_data = json.load(f)
        except Exception:
            pass

    sym = args.symbol
    qty = args.qty
    price = args.price
    side = args.side.upper()
    turnover = round(price * qty, 2)

    holdings = p_data.setdefault("holdings", {})
    curr_qty = holdings.get(sym, 0)

    if side == "BUY":
        p_data["cash"] = round(p_data["cash"] - turnover, 2)
        holdings[sym] = curr_qty + qty
    else:
        p_data["cash"] = round(p_data["cash"] + turnover, 2)
        holdings[sym] = max(0, curr_qty - qty)
        if holdings[sym] == 0:
            holdings.pop(sym, None)

    os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_PORTFOLIO_FILE)), exist_ok=True)
    with open(DEFAULT_PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(p_data, f, indent=2)

    print(f"Recorded fill: {side} {qty} {sym} at Rs {price:,.2f}")
    print(f"Updated Cash Balance: Rs {p_data['cash']:,.2f}")
    print(f"Current Holdings: {holdings}")
    sys.exit(0)


def cmd_log(args):
    now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
    d_str = now_ist.strftime("%Y-%m-%d")
    if not os.path.exists(DEFAULT_BROKER_STATE):
        print("No trades executed yet.")
        sys.exit(0)

    with open(DEFAULT_BROKER_STATE, "r", encoding="utf-8") as f:
        b = json.load(f).get(d_str, {})

    orders = b.get("orders_placed", [])
    print(f"Trading Ledger for {d_str} (NSE/BSE):")
    if not orders:
        print("  No orders placed today.")
    for o in orders:
        ord_info = o.get("order", {})
        print(f"  [{o.get('approved_at_ist')}] {ord_info.get('side')} {ord_info.get('qty')} {ord_info.get('symbol')} @ Rs {ord_info.get('entry_price')}")
    sys.exit(0)


def main():
    p = argparse.ArgumentParser(description="Order Tickets & Broker Execution for Indian Equities")
    sub = p.add_subparsers(dest="cmd")

    c_sh = sub.add_parser("show", help="Display order tickets & broker payloads")
    c_sh.add_argument("--broker", choices=["paper", "zerodha", "angel", "shoonya"], default="paper")
    c_sh.set_defaults(func=cmd_show)

    c_ap = sub.add_parser("approve", help="Approve order for placement")
    c_ap.add_argument("--index", type=int, default=1, help="Order index number")
    c_ap.add_argument("--reply", help="Explicit approval confirmation (e.g. 'yes')")
    c_ap.set_defaults(func=cmd_approve)

    c_fl = sub.add_parser("fill", help="Record order fill into portfolio")
    c_fl.add_argument("--symbol", required=True)
    c_fl.add_argument("--side", choices=["buy", "sell"], required=True)
    c_fl.add_argument("--qty", type=int, required=True)
    c_fl.add_argument("--price", type=float, required=True)
    c_fl.set_defaults(func=cmd_fill)

    c_lg = sub.add_parser("log", help="Display today's order ledger")
    c_lg.set_defaults(func=cmd_log)

    args = p.parse_args()
    if not hasattr(args, "func"):
        p.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()

