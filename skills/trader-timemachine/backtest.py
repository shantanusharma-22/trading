#!/usr/bin/env python3
"""Walk-Forward Strategy Backtester for trader-timemachine (Indian Equities - NSE).
Simulates the 15-minute Opening Range Breakout (ORB) strategy with VWAP and Net Taxes
across historical 5-minute bars. Standard library only.

    python3 backtest.py RELIANCE.NS                  # backtest 15m ORB on Reliance
    python3 backtest.py RELIANCE.NS TCS.NS INFY.NS   # multi-symbol portfolio backtest
"""

import argparse
import datetime
import json
import os
import sys

try:
    from history import get_cached_bars, sync_symbol
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from history import get_cached_bars, sync_symbol

# Import tax engine
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trader-budget"))
from tax_calculator import calculate_intraday_charges

RANGE_END = datetime.time(9, 30)
CLOSE_TIME = datetime.time(15, 10)


def backtest_symbol(sym, bars, target_r=2.0):
    if not bars:
        return None

    # Group by trading date
    days = {}
    for b in bars:
        d = b["time"].date()
        days.setdefault(d, []).append(b)

    trades = []
    for d, s_bars in sorted(days.items()):
        if len(s_bars) < 40:
            continue

        # Opening range (09:15 to 09:30)
        range_bars = [b for b in s_bars if b["time"].time() < RANGE_END]
        if len(range_bars) < 2:
            continue

        r_high = max(b["high"] for b in range_bars)
        r_low = min(b["low"] for b in range_bars)
        stop = round((r_high + r_low) / 2.0, 2)  # midpoint stop
        risk_per_sh = r_high - stop
        if risk_per_sh <= 0:
            continue
        target = round(r_high + (risk_per_sh * target_r), 2)

        # Evaluate post-range bars (from 09:30)
        in_trade = False
        entry_price = 0.0
        outcome = None
        exit_price = 0.0

        post_bars = [b for b in s_bars if b["time"].time() >= RANGE_END]
        for b in post_bars:
            if not in_trade:
                if b["close"] > r_high and b["time"].time() <= datetime.time(14, 0):
                    in_trade = True
                    entry_price = b["close"]
            else:
                # In trade, check stop, target or close
                if b["low"] <= stop:
                    outcome = "STOP"
                    exit_price = stop
                    break
                elif b["high"] >= target:
                    outcome = "TARGET"
                    exit_price = target
                    break
                elif b["time"].time() >= CLOSE_TIME:
                    outcome = "TIME_FLAT"
                    exit_price = b["close"]
                    break

        if in_trade and outcome:
            qty = max(1, int(1000.0 / risk_per_sh))  # size to Rs 1,000 risk
            charges = calculate_intraday_charges(entry_price, exit_price, qty)
            trades.append({
                "date": str(d),
                "entry": entry_price,
                "exit": exit_price,
                "qty": qty,
                "outcome": outcome,
                "gross_pnl": charges["gross_pnl"],
                "net_pnl": charges["net_pnl"],
                "r_mult": round((exit_price - entry_price) / risk_per_sh, 2)
            })

    if not trades:
        return None

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    win_rate = round((len(wins) / len(trades)) * 100, 1)

    tot_net_pnl = round(sum(t["net_pnl"] for t in trades), 2)
    gross_profits = sum(t["gross_pnl"] for t in wins)
    gross_losses = abs(sum(t["gross_pnl"] for t in losses)) or 1.0
    profit_factor = round(gross_profits / gross_losses, 2)

    return {
        "symbol": sym,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "total_net_pnl": tot_net_pnl,
        "profit_factor": profit_factor,
        "avg_trade_pnl": round(tot_net_pnl / len(trades), 2)
    }


def main():
    p = argparse.ArgumentParser(description="15m ORB Strategy Backtester")
    p.add_argument("symbols", nargs="+")
    args = p.parse_args()

    for s in args.symbols:
        norm = s.strip().upper()
        if not norm.endswith(".NS") and not norm.endswith(".BO"):
            norm += ".NS"

        bars = get_cached_bars(norm)
        if not bars:
            print(f"Syncing historical data for {norm}...")
            sync_symbol(norm)
            bars = get_cached_bars(norm)

        res = backtest_symbol(norm, bars)
        if res:
            print("==================================================")
            print(f"15-MIN ORB BACKTEST REPORT: {res['symbol']}")
            print("==================================================")
            print(f"Total Trades:        {res['total_trades']}")
            print(f"Winning Trades:      {res['wins']} | Losing Trades: {res['losses']}")
            print(f"Win Rate:            {res['win_rate']}%")
            print(f"Net Realized P&L:    Rs {res['total_net_pnl']:+,.2f} (Net of all Indian taxes)")
            print(f"Profit Factor:       {res['profit_factor']}")
            print(f"Average Trade P&L:   Rs {res['avg_trade_pnl']:+,.2f}")
            print("==================================================\n")
        else:
            print(f"No trades triggered for {norm} in dataset.")
    sys.exit(0)


if __name__ == "__main__":
    main()

