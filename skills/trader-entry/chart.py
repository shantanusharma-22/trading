#!/usr/bin/env python3
"""Chart Snapshot Generator for trader-entry (Indian Equities - NSE/BSE).
Generates annotated 5-minute charts with Opening Range boxes, VWAP, entry triggers,
and stop/target levels using matplotlib.

    python3 chart.py RELIANCE.NS                     # generates trader/charts/RELIANCE.NS.png
    python3 chart.py --from-plan                     # plot chart for current trade plan
"""

import argparse
import datetime
import json
import os
import sys

try:
    import matplotlib
    matplotlib.use("Agg")  # headless mode
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
except ImportError:
    print("matplotlib not installed. Run 'pip install matplotlib' to generate charts.")
    sys.exit(1)

from entry import fetch_intraday_bars, calculate_intraday_vwap, normalize_symbol

CHARTS_DIR = "trader/charts"
DEFAULT_PLAN_FILE = "trader/plan.json"


def plot_trade_chart(sym, bars, plan=None):
    os.makedirs(CHARTS_DIR, exist_ok=True)
    if not bars:
        print(f"No bars to plot for {sym}")
        return None

    times = [b["time"] for b in bars]
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]

    # Calculate cumulative VWAP
    vwap_values = []
    cum_pv = 0.0
    cum_vol = 0
    for b in bars:
        typ = (b["high"] + b["low"] + b["close"]) / 3.0
        v = b["vol"]
        cum_pv += typ * v
        cum_vol += v
        vwap_values.append(cum_pv / cum_vol if cum_vol > 0 else b["close"])

    # Opening range (09:15 to 09:30)
    range_bars = [b for b in bars if b["time"].time() < datetime.time(9, 30)]
    range_high = max(b["high"] for b in range_bars) if range_bars else None
    range_low = min(b["low"] for b in range_bars) if range_bars else None

    fig, ax = plt.subplots(figsize=(12, 6), dpi=120)

    # Plot Price & VWAP
    ax.plot(times, closes, label=f"{sym} Price (5m)", color="#1f77b4", linewidth=1.5)
    ax.plot(times, vwap_values, label="Intraday VWAP", color="#ff7f0e", linestyle="--", linewidth=1.2)

    # Plot Opening Range Box
    if range_high and range_low and len(range_bars) >= 2:
        ax.axhline(range_high, color="#2ca02c", linestyle=":", alpha=0.8, label=f"Range High (Rs {range_high:.2f})")
        ax.axhline(range_low, color="#d62728", linestyle=":", alpha=0.8, label=f"Range Low (Rs {range_low:.2f})")
        ax.axvspan(range_bars[0]["time"], range_bars[-1]["time"], color="#2ca02c", alpha=0.08, label="ORB 15m Window")

    # Plot Trade Plan (Entry, Stop, Target)
    if plan:
        entry_p = plan.get("entry")
        stop_p = plan.get("stop")
        target_p = plan.get("target")
        if entry_p:
            ax.axhline(entry_p, color="#3b82f6", linestyle="-", linewidth=1.2, label=f"Entry (Rs {entry_p:.2f})")
        if stop_p:
            ax.axhline(stop_p, color="#ef4444", linestyle="-", linewidth=1.4, label=f"Stop Loss (Rs {stop_p:.2f})")
        if target_p:
            ax.axhline(target_p, color="#10b981", linestyle="-", linewidth=1.4, label=f"Target (Rs {target_p:.2f})")

    ax.set_title(f"{sym} - Intraday 5-Minute Chart & Trade Setup (NSE)", fontsize=14, fontweight="bold")
    ax.set_ylabel("Price (INR)", fontsize=11)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper left", framealpha=0.9, fontsize=9)

    fig.tight_layout()
    dest = os.path.join(CHARTS_DIR, f"{sym}.png")
    plt.savefig(dest)
    plt.close()
    print(f"Generated chart snapshot: {dest}")
    return dest


def main():
    p = argparse.ArgumentParser(description="Intraday Trade Chart Generator")
    p.add_argument("symbol", nargs="?", help="Stock ticker (e.g. RELIANCE.NS)")
    p.add_argument("--from-plan", action="store_true")
    args = p.parse_args()

    sym = args.symbol
    plan = None
    if args.from_plan or not sym:
        if os.path.exists(DEFAULT_PLAN_FILE):
            with open(DEFAULT_PLAN_FILE, "r", encoding="utf-8") as f:
                plan = json.load(f)
                sym = sym or plan.get("symbol")

    if not sym:
        sym = "RELIANCE.NS"

    sym = normalize_symbol(sym)
    bars = fetch_intraday_bars(sym, interval="5m")
    if not bars:
        print(f"Could not fetch bars for {sym}")
        sys.exit(1)

    plot_trade_chart(sym, bars, plan=plan)
    sys.exit(0)


if __name__ == "__main__":
    main()

