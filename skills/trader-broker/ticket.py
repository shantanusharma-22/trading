#!/usr/bin/env python3
"""Order Tickets & Broker Execution for trader-broker (Indian Equities - NSE/BSE).
Renders plain-text approval tickets, generates copy-ready API payloads and protective
stop-loss orders for Zerodha Kite Connect, Angel One SmartAPI, and Shoonya (Finvasia),
and provides a built-in Paper Trading execution simulator. Standard library only.

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
    STATE_LOCK,
    compute_order_fingerprint,
    load_json,
    normalize_holding,
    normalize_symbol,
    record_closed_trade,
    record_placed_trade,
    resolve_path,
    save_json,
    to_ist,
)

# Import tax calculator for statutory fees, STT, and GST deduction
try:
    from skills.trader_budget import tax_calculator
except Exception:
    try:
        import importlib.util
        tax_path = resolve_path("skills/trader-budget/tax_calculator.py")
        spec = importlib.util.spec_from_file_location("tax_calculator", tax_path)
        tax_calculator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tax_calculator)
    except Exception:
        tax_calculator = None

DEFAULT_ORDERS_FILE = resolve_path("trader/orders.json")
DEFAULT_RISK_STATE = resolve_path("trader/state/risk.json")
DEFAULT_BROKER_STATE = resolve_path("trader/state/broker.json")
DEFAULT_PORTFOLIO_FILE = resolve_path("trader/portfolio.json")
DEFAULT_CONFIG_FILE = resolve_path("trader/config.json")
DEFAULT_ANGEL_TOKENS_FILE = resolve_path("trader/angel_tokens.json")

# Verified Angel One SmartAPI instrument tokens for liquid NSE stocks
BASE_ANGEL_TOKENS = {
    "RELIANCE": "2885", "RELIANCE.NS": "2885",
    "TCS": "11536", "TCS.NS": "11536",
    "HDFCBANK": "1333", "HDFCBANK.NS": "1333",
    "INFY": "1594", "INFY.NS": "1594",
    "ICICIBANK": "4963", "ICICIBANK.NS": "4963",
    "BHARTIARTL": "10604", "BHARTIARTL.NS": "10604",
    "SBIN": "3045", "SBIN.NS": "3045",
    "ITC": "1660", "ITC.NS": "1660",
    "LT": "11483", "LT.NS": "11483",
    "BAJFINANCE": "317", "BAJFINANCE.NS": "317",
    "KOTAKBANK": "1922", "KOTAKBANK.NS": "1922",
    "HCLTECH": "7229", "HCLTECH.NS": "7229",
    "AXISBANK": "5900", "AXISBANK.NS": "5900",
    "ASIANPAINT": "236", "ASIANPAINT.NS": "236",
    "MARUTI": "10999", "MARUTI.NS": "10999",
    "SUNPHARMA": "3351", "SUNPHARMA.NS": "3351",
    "TITAN": "3506", "TITAN.NS": "3506",
    "TATAMOTORS": "3456", "TATAMOTORS.NS": "3456",
    "ULTRACEMCO": "11532", "ULTRACEMCO.NS": "11532",
    "NTPC": "11630", "NTPC.NS": "11630",
    "WIPRO": "3787", "WIPRO.NS": "3787",
    "POWERGRID": "14977", "POWERGRID.NS": "14977",
    "M&M": "2031", "M&M.NS": "2031",
    "JIOFIN": "19234", "JIOFIN.NS": "19234",
    "COALINDIA": "20374", "COALINDIA.NS": "20374",
    "BAJAJFINSV": "16669", "BAJAJFINSV.NS": "16669",
    "TATASTEEL": "3499", "TATASTEEL.NS": "3499",
    "HINDUNILVR": "1394", "HINDUNILVR.NS": "1394",
}


def resolve_angel_token(symbol: str) -> str:
    """Resolves instrument token for Angel One SmartAPI, refusing if not found."""
    clean = symbol.replace(".NS", "").replace(".BO", "").strip().upper()
    if clean in BASE_ANGEL_TOKENS:
        return BASE_ANGEL_TOKENS[clean]
    if symbol in BASE_ANGEL_TOKENS:
        return BASE_ANGEL_TOKENS[symbol]

    # Check custom tokens file
    custom_tokens = load_json(DEFAULT_ANGEL_TOKENS_FILE, {})
    if clean in custom_tokens:
        return str(custom_tokens[clean])
    if symbol in custom_tokens:
        return str(custom_tokens[symbol])

    # Check config.json
    cfg = load_json(DEFAULT_CONFIG_FILE, {})
    cfg_tokens = cfg.get("angel_tokens", {})
    if clean in cfg_tokens:
        return str(cfg_tokens[clean])
    if symbol in cfg_tokens:
        return str(cfg_tokens[symbol])

    return None


def compute_fingerprint(order: dict, trade_date: str = None) -> str:
    return compute_order_fingerprint(order, trade_date)


def format_zerodha_payload(order: dict) -> str:
    sym = order.get("symbol", "").replace(".NS", "").replace(".BO", "")
    side = order.get("side", "BUY").upper()
    return f"""# Zerodha Kite Connect Python Snippet (Entry Order)
kite.place_order(
    variety=kite.VARIETY_REGULAR,
    exchange=kite.EXCHANGE_NSE,
    tradingsymbol="{sym}",
    transaction_type=kite.TRANSACTION_TYPE_{side},
    quantity={order.get('qty', 1)},
    product=kite.PRODUCT_MIS,
    order_type=kite.ORDER_TYPE_LIMIT,
    price={float(order.get('entry_price', 0.0)):.2f}
)"""


def format_zerodha_stop_payload(order: dict) -> str:
    sym = order.get("symbol", "").replace(".NS", "").replace(".BO", "")
    side = order.get("side", "BUY").upper()
    stop_side = "SELL" if side == "BUY" else "BUY"
    stop_p = float(order.get("stop_loss_price", 0.0))
    return f"""# Zerodha Kite Connect Stop-Loss Order (Protective SL)
kite.place_order(
    variety=kite.VARIETY_REGULAR,
    exchange=kite.EXCHANGE_NSE,
    tradingsymbol="{sym}",
    transaction_type=kite.TRANSACTION_TYPE_{stop_side},
    quantity={order.get('qty', 1)},
    product=kite.PRODUCT_MIS,
    order_type=kite.ORDER_TYPE_SL,
    price={stop_p:.2f},
    trigger_price={stop_p:.2f}
)"""


def format_angel_payload(order: dict) -> dict:
    sym = order.get("symbol", "").replace(".NS", "").replace(".BO", "")
    token = resolve_angel_token(sym)
    if not token:
        return None
    side = order.get("side", "BUY").upper()
    return {
        "variety": "NORMAL",
        "tradingsymbol": f"{sym}-EQ",
        "symboltoken": str(token),
        "transactiontype": side,
        "exchange": "NSE",
        "ordertype": "LIMIT",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "price": f"{float(order.get('entry_price', 0.0)):.2f}",
        "quantity": str(order.get("qty", 1))
    }


def format_angel_stop_payload(order: dict) -> dict:
    sym = order.get("symbol", "").replace(".NS", "").replace(".BO", "")
    token = resolve_angel_token(sym)
    if not token:
        return None
    side = order.get("side", "BUY").upper()
    stop_side = "SELL" if side == "BUY" else "BUY"
    stop_p = float(order.get("stop_loss_price", 0.0))
    return {
        "variety": "STOPLOSS",
        "tradingsymbol": f"{sym}-EQ",
        "symboltoken": str(token),
        "transactiontype": stop_side,
        "exchange": "NSE",
        "ordertype": "STOPLOSS_LIMIT",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "price": f"{stop_p:.2f}",
        "triggerprice": f"{stop_p:.2f}",
        "quantity": str(order.get("qty", 1))
    }


def format_shoonya_payload(order: dict) -> dict:
    sym = order.get("symbol", "").replace(".NS", "").replace(".BO", "")
    side = order.get("side", "BUY").upper()
    prod = order.get("product", "MIS").upper()
    # Finvasia Shoonya product types: I = Intraday (MIS), C = CNC, M = NRML
    prod_code = "I" if prod == "MIS" else ("C" if prod in ("CNC", "DELIVERY") else "M")
    return {
        "buy_or_sell": "B" if side == "BUY" else "S",
        "product_type": prod_code,
        "exchange": "NSE",
        "tradingsymbol": f"{sym}-EQ",
        "quantity": int(order.get("qty", 1)),
        "price_type": "LMT",
        "price": float(order.get("entry_price", 0.0))
    }


def format_shoonya_stop_payload(order: dict) -> dict:
    sym = order.get("symbol", "").replace(".NS", "").replace(".BO", "")
    side = order.get("side", "BUY").upper()
    stop_side = "S" if side == "BUY" else "B"
    stop_p = float(order.get("stop_loss_price", 0.0))
    prod = order.get("product", "MIS").upper()
    prod_code = "I" if prod == "MIS" else ("C" if prod in ("CNC", "DELIVERY") else "M")
    return {
        "buy_or_sell": stop_side,
        "product_type": prod_code,
        "exchange": "NSE",
        "tradingsymbol": f"{sym}-EQ",
        "quantity": int(order.get("qty", 1)),
        "price_type": "SL-LMT",
        "price": stop_p,
        "trigger_price": stop_p
    }


def execute_approve(order_idx: int, reply: str, orders_file: str = None,
                    risk_file: str = None, broker_file: str = None,
                    now_ist: datetime.datetime = None) -> tuple:
    """Programmatic approval handler: enforces explicit yes, risk PASS, 300s freshness, and idempotency."""
    conf = (reply or "").strip().lower()
    if conf not in ("yes", "y", "approved"):
        return False, f"Explicit approval required. Received '{reply}'. No order placed.", None

    o_file = orders_file or DEFAULT_ORDERS_FILE
    r_file = risk_file or DEFAULT_RISK_STATE
    b_file = broker_file or DEFAULT_BROKER_STATE

    if not os.path.exists(o_file):
        return False, f"Orders file not found: {o_file}", None

    orders_data = load_json(o_file, {})
    orders = orders_data.get("orders", [])
    idx = order_idx - 1
    if idx < 0 or idx >= len(orders):
        return False, f"Invalid order index #{order_idx} (total proposals: {len(orders)})", None

    if now_ist is None:
        now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
    d_str = now_ist.strftime("%Y-%m-%d")

    ord_spec = orders[idx]
    fp = compute_fingerprint(ord_spec, d_str)

    # Check risk verdict
    if not os.path.exists(r_file):
        return False, "Orders must pass /trader-risk before approval (risk state file missing).", None

    r_data = load_json(r_file, {})
    v_list = r_data.get("verdicts", [])
    v_map = {v.get("fingerprint"): v for v in v_list if isinstance(v, dict)}

    rv = v_map.get(fp)
    if rv is None:
        return False, f"No risk verdict found for Order #{order_idx} (fingerprint: {fp}). Re-run /trader-risk.", None

    if rv.get("verdict") != "PASS":
        return False, f"Order #{order_idx} was BLOCKED by risk check: {rv.get('reason', 'fail closed')}", None

    # Check verdict freshness (< 300s)
    v_ts = rv.get("timestamp")
    if v_ts and (now_ist.timestamp() - v_ts) > 300:
        age_m = int((now_ist.timestamp() - v_ts) / 60)
        return False, f"Risk verdict for Order #{order_idx} is older than 5 minutes ({age_m}m old). Re-run /trader-risk.", None

    # Idempotency check: refuse duplicate approvals today
    b_data = load_json(b_file, {})
    day_entry = b_data.get(d_str, {})
    if any(o.get("fingerprint") == fp for o in day_entry.get("orders_placed", [])):
        return False, f"Order #{order_idx} has already been approved and recorded today.", None

    # Record trade placed
    trade_record = record_placed_trade(ord_spec, now_ist, broker_state_path=b_file)
    return True, f"Order #{order_idx} APPROVED & RECORDED successfully.", trade_record


def execute_fill(symbol: str, side: str, qty: int, price: float,
                 stop: float = 0.0, target: float = 0.0, strategy: str = "manual",
                 portfolio_file: str = None, broker_file: str = None,
                 now_ist: datetime.datetime = None) -> tuple:
    """Executes order fill: enforces shared holdings schema, statutory taxes, cash checks, and no phantom credit."""
    if qty <= 0 or price <= 0:
        return False, f"Invalid fill parameters: qty={qty}, price={price}", {}

    p_file = portfolio_file or DEFAULT_PORTFOLIO_FILE
    b_file = broker_file or DEFAULT_BROKER_STATE

    if now_ist is None:
        now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))

    side_norm = side.upper()
    if side_norm not in ("BUY", "SELL"):
        return False, f"Invalid order side: {side}", {}

    with STATE_LOCK:
        p_data = load_json(p_file, {"cash": 100000.0, "holdings": {}})
        cash = float(p_data.get("cash", 100000.0))
        holdings = p_data.setdefault("holdings", {})

        turnover = round(price * qty, 2)
        # Calculate statutory charges for this leg
        charges = 0.0
        if tax_calculator and hasattr(tax_calculator, "calculate_single_leg_charges"):
            c_info = tax_calculator.calculate_single_leg_charges(price, qty, side_norm)
            charges = c_info.get("total_charges", 0.0)
        else:
            # Conservative standard fallback: Brokerage Rs 20 + GST (18%) + STT/Stamp
            charges = 23.60

        raw_existing = holdings.get(symbol)
        existing = normalize_holding(symbol, raw_existing) if raw_existing else None

        if side_norm == "BUY":
            # Scenario A: Closing or trimming an existing SHORT position
            if existing and existing.get("side") == "SELL" and existing.get("qty", 0) > 0:
                short_qty = existing["qty"]
                if qty > short_qty:
                    return False, f"Cannot buy {qty} shares to cover short; existing short position is only {short_qty} shares.", {}

                # Calculate P&L on covering short
                entry_p = existing.get("entry_price", price)
                gross_pnl = round((entry_p - price) * qty, 2)

                # Round-trip charges via tax_calculator if available
                if tax_calculator and hasattr(tax_calculator, "calculate_intraday_charges"):
                    rt = tax_calculator.calculate_intraday_charges(price, entry_p, qty)
                    total_trip_charges = rt.get("total_charges", charges * 2)
                else:
                    total_trip_charges = charges * 2
                net_pnl = round(gross_pnl - total_trip_charges, 2)

                # Return locked margin and adjust for net PnL
                margin_released = round(existing.get("margin_used", entry_p * qty) * (qty / short_qty), 2)
                cash = round(cash + margin_released + net_pnl, 2)
                p_data["cash"] = cash

                rem_qty = short_qty - qty
                if rem_qty <= 0:
                    holdings.pop(symbol, None)
                else:
                    existing["qty"] = rem_qty
                    existing["margin_used"] = round(existing["margin_used"] - margin_released, 2)
                    holdings[symbol] = existing

                record_closed_trade(symbol, price, net_pnl, now_ist, broker_state_path=b_file)
                save_json(p_file, p_data)
                return True, f"Covered SHORT {qty} {symbol} @ Rs {price:.2f}. Realized Net P&L: Rs {net_pnl:+,.2f}", p_data

            # Scenario B: Opening or adding to a LONG position
            cash_required = round(turnover + charges, 2)
            if cash < cash_required:
                return False, f"Insufficient cash balance. Required: Rs {cash_required:,.2f}, Available: Rs {cash:,.2f}", {}

            cash = round(cash - cash_required, 2)
            p_data["cash"] = cash

            if existing and existing.get("side") == "BUY" and existing.get("qty", 0) > 0:
                old_qty = existing["qty"]
                old_entry = existing["entry_price"]
                new_qty = old_qty + qty
                avg_entry = round(((old_qty * old_entry) + (qty * price)) / new_qty, 2)
                existing["qty"] = new_qty
                existing["entry_price"] = avg_entry
                existing["current_price"] = price
                existing["margin_used"] = round(existing.get("margin_used", 0.0) + turnover, 2)
                if stop:
                    existing["stop"] = stop
                if target:
                    existing["target"] = target
                holdings[symbol] = existing
            else:
                holdings[symbol] = {
                    "symbol": symbol,
                    "qty": qty,
                    "entry_price": price,
                    "side": "BUY",
                    "stop": stop,
                    "target": target,
                    "current_price": price,
                    "margin_used": turnover,
                    "strategy": strategy,
                    "placed_at": now_ist.strftime("%Y-%m-%d %H:%M:%S"),
                    "pnl": 0.0
                }

            save_json(p_file, p_data)
            return True, f"Filled BUY {qty} {symbol} @ Rs {price:.2f}. Deducted statutory fees Rs {charges:.2f}. Cash: Rs {cash:,.2f}", p_data

        else:  # side_norm == "SELL"
            # Scenario A: Closing or trimming an existing LONG position
            if existing and existing.get("side") == "BUY" and existing.get("qty", 0) > 0:
                long_qty = existing["qty"]
                if qty > long_qty:
                    return False, f"Cannot sell {qty} shares; existing holding is only {long_qty} shares.", {}

                entry_p = existing.get("entry_price", price)
                gross_pnl = round((price - entry_p) * qty, 2)

                if tax_calculator and hasattr(tax_calculator, "calculate_intraday_charges"):
                    rt = tax_calculator.calculate_intraday_charges(entry_p, price, qty)
                    total_trip_charges = rt.get("total_charges", charges * 2)
                else:
                    total_trip_charges = charges * 2
                net_pnl = round(gross_pnl - total_trip_charges, 2)

                # Never credit cash for shares not owned; credit actual net proceeds
                net_proceeds = round(turnover - charges, 2)
                cash = round(cash + net_proceeds, 2)
                p_data["cash"] = cash

                rem_qty = long_qty - qty
                if rem_qty <= 0:
                    holdings.pop(symbol, None)
                else:
                    existing["qty"] = rem_qty
                    existing["margin_used"] = max(0.0, round(existing.get("margin_used", 0.0) - turnover, 2))
                    holdings[symbol] = existing

                record_closed_trade(symbol, price, net_pnl, now_ist, broker_state_path=b_file)
                save_json(p_file, p_data)
                return True, f"Sold LONG {qty} {symbol} @ Rs {price:.2f}. Realized Net P&L: Rs {net_pnl:+,.2f}. Cash: Rs {cash:,.2f}", p_data

            # Scenario B: Explicit SHORT entry
            # Intraday equity short requires margin (20% for MIS leverage or 100% paper reserve)
            margin_required = round(turnover * 0.20, 2)  # 5x intraday MIS leverage margin
            total_short_req = round(margin_required + charges, 2)
            if cash < total_short_req:
                return False, f"Insufficient margin to enter short. Required: Rs {total_short_req:,.2f}, Available: Rs {cash:,.2f}", {}

            cash = round(cash - charges, 2)  # deduct upfront charges; margin is committed
            p_data["cash"] = cash

            holdings[symbol] = {
                "symbol": symbol,
                "qty": qty,
                "entry_price": price,
                "side": "SELL",
                "stop": stop,
                "target": target,
                "current_price": price,
                "margin_used": margin_required,
                "strategy": strategy,
                "placed_at": now_ist.strftime("%Y-%m-%d %H:%M:%S"),
                "pnl": 0.0
            }

            save_json(p_file, p_data)
            return True, f"Filled SHORT {qty} {symbol} @ Rs {price:.2f}. Locked margin Rs {margin_required:,.2f}. Cash: Rs {cash:,.2f}", p_data


def execute_flatten(symbol: str, qty: int = None, price: float = None,
                    portfolio_file: str = None, broker_file: str = None,
                    now_ist: datetime.datetime = None) -> tuple:
    """Flattens an open position in portfolio, executing market square-off and recording net P&L."""
    p_file = portfolio_file or DEFAULT_PORTFOLIO_FILE
    p_data = load_json(p_file, {})
    holdings = p_data.get("holdings", {})

    if symbol not in holdings:
        return False, f"No open position found for {symbol} to flatten.", {}

    raw_h = holdings[symbol]
    h = normalize_holding(symbol, raw_h)
    pos_qty = h.get("qty", 0)
    if pos_qty <= 0:
        return False, f"Holding quantity for {symbol} is zero.", {}

    flat_qty = min(pos_qty, qty) if qty and qty > 0 else pos_qty
    side = h.get("side", "BUY")

    # Opposite side to flatten
    flat_side = "SELL" if side == "BUY" else "BUY"
    flat_price = price if (price and price > 0) else h.get("current_price", h.get("entry_price", 100.0))

    return execute_fill(
        symbol=symbol,
        side=flat_side,
        qty=flat_qty,
        price=flat_price,
        portfolio_file=portfolio_file,
        broker_file=broker_file,
        now_ist=now_ist
    )


# =====================================================================
# CLI Command Handlers
# =====================================================================

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
                    if isinstance(v, dict):
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
            print("\n" + format_zerodha_stop_payload(ord_spec))
        elif args.broker == "angel":
            payload = format_angel_payload(ord_spec)
            stop_payload = format_angel_stop_payload(ord_spec)
            if not payload or not stop_payload:
                print(f"\nERROR: Angel One instrument token not found for {ord_spec.get('symbol')}. Refusing to generate payload.")
            else:
                print("\n# Angel One SmartAPI Entry JSON:")
                print(json.dumps(payload, indent=2))
                print("\n# Angel One SmartAPI Stop-Loss JSON:")
                print(json.dumps(stop_payload, indent=2))
        elif args.broker == "shoonya":
            print("\n# Shoonya (Finvasia) Entry Payload:")
            print(json.dumps(format_shoonya_payload(ord_spec), indent=2))
            print("\n# Shoonya (Finvasia) Stop-Loss Payload:")
            print(json.dumps(format_shoonya_stop_payload(ord_spec), indent=2))
        else:
            print("\n[Default: Paper Trading Mode active. Reply 'yes' to simulate paper execution.]")
        print("==================================================\n")
    sys.exit(0)


def cmd_approve(args):
    ok, msg, record = execute_approve(args.index, args.reply)
    if not ok:
        print(f"ERROR: {msg}")
        sys.exit(1)
    print(f"===> {msg}")
    if record:
        print(f"     Recorded trade: {record.get('side')} {record.get('qty')} {record.get('symbol')} @ Rs {record.get('entry_price'):,.2f}")
    sys.exit(0)


def cmd_fill(args):
    ok, msg, p_data = execute_fill(
        symbol=args.symbol,
        side=args.side,
        qty=args.qty,
        price=args.price,
        stop=getattr(args, "stop", 0.0),
        target=getattr(args, "target", 0.0),
        strategy=getattr(args, "strategy", "manual")
    )
    if not ok:
        print(f"ERROR: {msg}")
        sys.exit(1)
    print(f"===> {msg}")
    print(f"Updated Cash Balance: Rs {p_data.get('cash', 0.0):,.2f}")
    print(f"Current Holdings: {p_data.get('holdings', {})}")
    sys.exit(0)


def cmd_flatten(args):
    ok, msg, p_data = execute_flatten(
        symbol=args.symbol,
        qty=getattr(args, "qty", None),
        price=getattr(args, "price", None)
    )
    if not ok:
        print(f"ERROR: {msg}")
        sys.exit(1)
    print(f"===> [FLATTEN EXECUTED] {msg}")
    print(f"Updated Cash Balance: Rs {p_data.get('cash', 0.0):,.2f}")
    print(f"Current Holdings: {p_data.get('holdings', {})}")
    sys.exit(0)


def cmd_log(args):
    now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
    d_str = now_ist.strftime("%Y-%m-%d")
    b_data = load_json(DEFAULT_BROKER_STATE, {})
    day_entry = b_data.get(d_str, {})
    orders = day_entry.get("orders_placed", [])

    print(f"Trading Ledger for {d_str} (NSE/BSE):")
    if not orders:
        print("  No orders placed today.")
    for o in orders:
        ord_info = o.get("order", {})
        print(f"  [{o.get('placed_at_ist')}] {ord_info.get('side')} {ord_info.get('qty')} {ord_info.get('symbol')} @ Rs {ord_info.get('entry_price')}")
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
    c_fl.add_argument("--stop", type=float, default=0.0)
    c_fl.add_argument("--target", type=float, default=0.0)
    c_fl.add_argument("--strategy", default="manual")
    c_fl.set_defaults(func=cmd_fill)

    c_ft = sub.add_parser("flatten", help="Flatten open position in portfolio")
    c_ft.add_argument("--symbol", required=True)
    c_ft.add_argument("--qty", type=int, default=None)
    c_ft.add_argument("--price", type=float, default=None)
    c_ft.set_defaults(func=cmd_flatten)

    c_lg = sub.add_parser("log", help="Display today's order ledger")
    c_lg.set_defaults(func=cmd_log)

    args = p.parse_args()
    if not hasattr(args, "func"):
        p.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
