#!/usr/bin/env python3
"""Position Sizing & Dynamic Risk Manager for trader-budget (Indian Equities - NSE/BSE).
Sizes an intraday trade to rupee limits, whole shares, and dynamic drawdown rules (Half-Kelly scaling).
Calculates exact statutory taxes and execution slippage. Writes trader/orders.json.

    python3 size.py                                  # reads trader/plan.json + trader/config.json
    python3 size.py --write                          # writes trader/orders.json
    python3 size.py --budget 100000 --max-loss 1000  # override parameters
    python3 size.py --dynamic-risk                   # scale risk down if account is in drawdown
    python3 size.py --charges                        # print detailed tax & slippage breakdown
"""

import argparse
import json
import math
import os
import sys

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import resolve_path

try:
    from tax_calculator import calculate_intraday_charges, format_charges_summary
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from tax_calculator import calculate_intraday_charges, format_charges_summary

DEFAULT_PLAN_FILE = resolve_path("trader/plan.json")
DEFAULT_CONFIG_FILE = resolve_path("trader/config.json")
DEFAULT_ORDERS_FILE = resolve_path("trader/orders.json")
DEFAULT_PORTFOLIO_FILE = resolve_path("trader/portfolio.json")

DEFAULT_CONFIG = {
    "budget": 100000.0,
    "cash_buffer_pct": 10.0,
    "max_position_pct": 50.0,
    "max_order_inr": 50000.0,
    "min_order_inr": 1000.0,
    "max_loss_per_trade_inr": 1000.0,
    "max_daily_loss_inr": 3000.0,
    "max_trades_per_day": 3,
    "max_orders_per_day": 10,
    "min_reward_risk": 1.5,
    "require_stop": True,
    "no_entries_before": "09:30",
    "no_entries_after": "14:45",
    "flat_by": "15:10",
    "broker": "paper",
    "exchange": "NSE",
    "product": "MIS",
    "brokerage_per_order": 20.0,
    "slippage_pct": 0.05,
    "dynamic_drawdown_scaling": True
}


def load_config():
    if os.path.exists(DEFAULT_CONFIG_FILE):
        try:
            with open(DEFAULT_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                res = DEFAULT_CONFIG.copy()
                res.update(cfg)
                return res
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def get_drawdown_multiplier(starting_capital: float) -> float:
    """Calculate Half-Kelly scaling: reduce risk per trade if current cash is below starting capital."""
    if not os.path.exists(DEFAULT_PORTFOLIO_FILE):
        return 1.0
    try:
        with open(DEFAULT_PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            p = json.load(f)
            cash = float(p.get("cash", starting_capital))
            if cash < starting_capital:
                drawdown_pct = (starting_capital - cash) / starting_capital
                if drawdown_pct >= 0.05:  # >= 5% drawdown
                    return 0.5            # cut risk by 50%
                elif drawdown_pct >= 0.02: # >= 2% drawdown
                    return 0.75           # cut risk by 25%
    except Exception:
        pass
    return 1.0


def size_trade(plan, config, apply_dynamic=False):
    sym = plan["symbol"]
    entry = plan["entry"]
    stop = plan["stop"]
    target = plan["target"]
    side = plan.get("side", "BUY").upper()

    if side == "SELL":
        risk_per_share = stop - entry
        if risk_per_share <= 0:
            raise ValueError(f"Stop loss (Rs {stop:.2f}) must be strictly above entry (Rs {entry:.2f}) for SELL order")
    else:
        risk_per_share = entry - stop
        if risk_per_share <= 0:
            raise ValueError(f"Stop loss (Rs {stop:.2f}) must be strictly below entry (Rs {entry:.2f}) for BUY order")

    budget = config.get("budget", 100000.0)
    base_max_loss = config.get("max_loss_per_trade_inr", 1000.0)

    # Dynamic drawdown risk scaling (Suggestion #13)
    multiplier = get_drawdown_multiplier(budget) if apply_dynamic else 1.0
    effective_max_loss = round(base_max_loss * multiplier, 2)

    # 1. Limit by Max Loss Per Trade
    qty_by_risk = math.floor(effective_max_loss / risk_per_share)

    # 2. Limit by Max Order Rupee Cap
    max_order_val = config.get("max_order_inr", 50000.0)
    qty_by_max_order = math.floor(max_order_val / entry)

    # 3. Limit by Position % of Budget
    max_pos_pct = config.get("max_position_pct", 50.0)
    qty_by_pos_cap = math.floor((budget * (max_pos_pct / 100.0)) / entry)

    # 4. Limit by Available Cash after Buffer
    buffer_pct = config.get("cash_buffer_pct", 10.0)
    investable_cash = budget * (1.0 - (buffer_pct / 100.0))
    qty_by_cash = math.floor(investable_cash / entry)

    # Take strict minimum
    qty = min(qty_by_risk, qty_by_max_order, qty_by_pos_cap, qty_by_cash)

    deciding_limit = f"Max Loss Limit (Rs {effective_max_loss:,.2f})"
    if qty == qty_by_max_order:
        deciding_limit = f"Max Order Cap (Rs {max_order_val:,.0f})"
    elif qty == qty_by_pos_cap:
        deciding_limit = f"Position Cap ({max_pos_pct}% of budget)"
    elif qty == qty_by_cash:
        deciding_limit = f"Available Cash (after {buffer_pct}% buffer)"

    if qty <= 0:
        raise ValueError(
            f"Cannot size position for {sym}: Risk per share Rs {risk_per_share:.2f} exceeds loss limit Rs {effective_max_loss:,.2f}"
        )

    order_value = round(entry * qty, 2)
    min_order = config.get("min_order_inr", 1000.0)
    if order_value < min_order:
        raise ValueError(f"Order value Rs {order_value:,.2f} is under min order Rs {min_order:,.2f}")

    # Calculate Charges & Net Returns with Slippage Modeling (Suggestion #12)
    brk_fee = config.get("brokerage_per_order", 20.0)
    slip_pct = config.get("slippage_pct", 0.05)

    win_charges = calculate_intraday_charges(entry, target, qty, brk_fee, slip_pct)
    loss_charges = calculate_intraday_charges(entry, stop, qty, brk_fee, slip_pct)

    actual_loss_at_stop = round((risk_per_share * qty) + loss_charges["total_charges"], 2)
    if side == "SELL":
        actual_gain_at_target = round(((entry - target) * qty) - win_charges["total_charges"], 2)
    else:
        actual_gain_at_target = round(((target - entry) * qty) - win_charges["total_charges"], 2)

    order_spec = {
        "symbol": sym,
        "exchange": config.get("exchange", "NSE"),
        "product": config.get("product", "MIS"),
        "side": side,
        "qty": qty,
        "entry_price": entry,
        "stop_loss_price": stop,
        "take_profit_price": target,
        "order_value": order_value,
        "effective_max_loss": effective_max_loss,
        "drawdown_multiplier": multiplier,
        "actual_loss_at_stop": actual_loss_at_stop,
        "actual_gain_at_target": actual_gain_at_target,
        "breakeven_move_pts": win_charges["breakeven_points"],
        "deciding_limit": deciding_limit,
        "flat_by": plan.get("flat_by", "15:10"),
        "broker": config.get("broker", "paper")
    }

    return order_spec, win_charges, loss_charges


def main():
    p = argparse.ArgumentParser(description="Position Sizing & Dynamic Risk for Indian Equities")
    p.add_argument("--budget", type=float, help="Total trading capital (Rs)")
    p.add_argument("--max-loss", type=float, help="Max loss per trade (Rs)")
    p.add_argument("--dynamic-risk", action="store_true", help="Apply drawdown scaling")
    p.add_argument("--write", action="store_true", help="Write to trader/orders.json")
    p.add_argument("--charges", action="store_true", help="Print complete tax breakdown")
    args = p.parse_args()

    if not os.path.exists(DEFAULT_PLAN_FILE):
        print(f"ERROR: {DEFAULT_PLAN_FILE} not found. Run /trader-exit first.")
        sys.exit(1)

    with open(DEFAULT_PLAN_FILE, "r", encoding="utf-8") as f:
        plan = json.load(f)

    cfg = load_config()
    if args.budget:
        cfg["budget"] = args.budget
    if args.max_loss:
        cfg["max_loss_per_trade_inr"] = args.max_loss

    try:
        order, win_ch, loss_ch = size_trade(plan, cfg, apply_dynamic=args.dynamic_risk or cfg.get("dynamic_drawdown_scaling", True))

        print("==================================================")
        print(f"POSITION SIZING: {order['symbol']} ({order['exchange']} - {order['product']})")
        print("==================================================")
        print(f"Shares to Buy:      {order['qty']} shares (Whole shares only)")
        print(f"Total Order Value:  Rs {order['order_value']:,.2f}")
        print(f"Entry Price:        Rs {order['entry_price']:,.2f}")
        print(f"Stop-Loss:          Rs {order['stop_loss_price']:,.2f}")
        print(f"Take-Profit:        Rs {order['take_profit_price']:,.2f}")
        if order.get("drawdown_multiplier", 1.0) < 1.0:
            print(f"Drawdown Protection: Active (Risk scaled to {int(order['drawdown_multiplier']*100)}% due to drawdown)")
        print("--------------------------------------------------")
        print(f"Max Loss at Stop:   Rs {order['actual_loss_at_stop']:,.2f} (Includes taxes + slippage)")
        print(f"Net Gain at Target: Rs {order['actual_gain_at_target']:,.2f} (Includes taxes + slippage)")
        print(f"Breakeven Move:     Rs {order['breakeven_move_pts']:.2f}/share")
        print(f"Sizing Bottleneck:  {order['deciding_limit']}")
        print(f"Square-off Time:    {order['flat_by']} IST")
        print("==================================================")

        if args.charges:
            print("\nINTRADAY STATUTORY CHARGES & SLIPPAGE AT TARGET:")
            print(format_charges_summary(win_ch))

        if args.write:
            os.makedirs(os.path.dirname(os.path.abspath(DEFAULT_ORDERS_FILE)), exist_ok=True)
            with open(DEFAULT_ORDERS_FILE, "w", encoding="utf-8") as f:
                json.dump({"orders": [order]}, f, indent=2)
            print(f"Wrote order proposal to {DEFAULT_ORDERS_FILE} for /trader-risk")
        sys.exit(0)

    except Exception as err:
        print(f"ERROR: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
