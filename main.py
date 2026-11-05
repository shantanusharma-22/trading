#!/usr/bin/env python3
"""Unified Control Center & Master Orchestrator for Indian Day Trading Suite (NSE/BSE).
Standard library only. Provides an interactive menu and automated headless execution.

Usage:
    python main.py                     # Interactive Command Center
    python main.py status              # Show portfolio, budget, and live market clock
    python main.py pivots              # Calculate CPR & Camarilla pivots for watchlist
    python main.py preopen             # Check 09:08 AM Pre-open auction & gap analysis
    python main.py scan                # Run 15-minute ORB & VWAP breakout scanner
    python main.py panic               # PANIC FLATTEN all open positions immediately
    python main.py journal             # Show EOD trade journal and P&L performance
    python main.py test                # Run 12/12 automated unit test suite
"""

import datetime
import json
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "skills"))

from common import load_json, resolve_path, save_json

CONFIG_FILE = resolve_path("trader/config.json")
PORTFOLIO_FILE = resolve_path("trader/portfolio.json")


def print_header(title):
    print("\n" + "=" * 60, flush=True)
    print(f" {title.center(58)} ", flush=True)
    print("=" * 60, flush=True)


def run_subcommand(relative_script, args=None):
    script_path = os.path.join(BASE_DIR, relative_script)
    cmd = [sys.executable, script_path] + (args or [])
    subprocess.run(cmd, cwd=BASE_DIR)


def cmd_status():
    print_header("LIVE PORTFOLIO & CONFIGURATION STATUS")
    cfg = load_json(CONFIG_FILE)
    port = load_json(PORTFOLIO_FILE)

    cash = port.get("cash", cfg.get("budget", 100000))
    holdings = port.get("holdings", {})
    watchlist = cfg.get("watchlist", ["RELIANCE.NS", "TCS.NS", "INFY.NS"])

    print(f"  • Broker Mode:            {cfg.get('broker', 'paper').upper()} (Zero Financial Risk)", flush=True)
    print(f"  • Capital Allocated:      Rs {cfg.get('budget', 100000):,.2f}", flush=True)
    print(f"  • Available Cash:         Rs {cash:,.2f}", flush=True)
    print(f"  • Max Loss Per Trade:     Rs {cfg.get('max_loss_per_trade_inr', 1000):,.2f} (1.0% Hard Stop)", flush=True)
    print(f"  • Max Daily Loss Limit:   Rs {cfg.get('max_daily_loss_inr', 3000):,.2f} (3.0% Account Killswitch)", flush=True)
    print(f"  • Mandatory Square-off:   {cfg.get('flat_by', '15:10')} IST (MIS Intraday Auto-Exit)", flush=True)
    print(f"  • Active Watchlist:       {', '.join(watchlist)}", flush=True)
    print(f"  • Active Open Positions:  {len(holdings)}", flush=True)

    if holdings:
        for sym, h in holdings.items():
            print(f"    - {sym}: {h.get('qty')} shares @ Rs {h.get('entry_price', 0):.2f}", flush=True)
    else:
        print("    (No open positions. 100% in cash)", flush=True)

    print("-" * 60, flush=True)
    print("Market Session Clock:", flush=True)
    run_subcommand("skills/trader-alerts/alerts.py", ["clock"])


def cmd_pivots():
    print_header("TOMORROW'S CPR & CAMARILLA PIVOT LEVELS")
    cfg = load_json(CONFIG_FILE)
    watchlist = cfg.get("watchlist", ["RELIANCE.NS", "TCS.NS", "INFY.NS"])
    run_subcommand("skills/trader-scanner/cpr.py", watchlist)


def cmd_preopen():
    print_header("09:08 AM PRE-OPEN AUCTION & GAP SCAN")
    cfg = load_json(CONFIG_FILE)
    watchlist = cfg.get("watchlist", ["RELIANCE.NS", "TCS.NS", "INFY.NS"])
    run_subcommand("skills/trader-scanner/preopen.py", ["--symbols"] + watchlist)


def cmd_scan():
    print_header("15-MINUTE ORB & VWAP BREAKOUT SCAN")
    run_subcommand("skills/trader-scanner/scan.py", ["orb"])


def cmd_panic():
    print_header("PANIC BUTTON: FLATTEN ALL POSITIONS")
    run_subcommand("skills/trader-broker/dashboard.py", ["--flatten-all"])


def cmd_journal():
    print_header("END-OF-DAY TRADE JOURNAL & PERFORMANCE METRICS")
    run_subcommand("skills/trader-broker/journal.py")


def cmd_test():
    print_header("RUNNING 14-POINT AUTOMATED UNIT TEST SUITE")
    run_subcommand("tests/test_indian_market.py")


def cmd_notify_test():
    print_header("TESTING TELEGRAM / DISCORD NOTIFICATIONS")
    run_subcommand("skills/trader-alerts/alerts.py", ["test-notify"])


def cmd_setup_notify():
    print_header("CONFIGURE TELEGRAM / DISCORD MOBILE ALERTS")
    cfg = load_json(CONFIG_FILE)
    print("Current Notification Settings:")
    print(f"  • Telegram Bot Token: {cfg.get('telegram_bot_token') or 'Not configured'}")
    print(f"  • Telegram Chat ID:   {cfg.get('telegram_chat_id') or 'Not configured'}")
    print(f"  • Discord Webhook:    {cfg.get('discord_webhook_url') or 'Not configured'}")
    print("-" * 60)
    print("Enter new values (leave blank to keep current):")
    
    tg_token = input("Telegram Bot Token: ").strip()
    tg_chat = input("Telegram Chat ID: ").strip()
    dc_url = input("Discord Webhook URL: ").strip()

    updated = False
    if tg_token:
        cfg["telegram_bot_token"] = tg_token
        updated = True
    if tg_chat:
        cfg["telegram_chat_id"] = tg_chat
        updated = True
    if dc_url:
        cfg["discord_webhook_url"] = dc_url
        updated = True

    if updated:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        print("\n[OK] Notification settings saved to trader/config.json!")
        print("Dispatching test notification to verify...")
        run_subcommand("skills/trader-alerts/alerts.py", ["test-notify"])
    else:
        print("\nNo changes made.")


def cmd_swing(symbols=None):
    print_header("MULTI-WEEK SWING & FIBONACCI ANALYSIS")
    if not symbols:
        cfg = load_json(CONFIG_FILE)
        symbols = cfg.get("watchlist", ["JIOFIN.NS", "RELIANCE.NS"])
    run_subcommand("skills/trader-analyst/swing.py", symbols)


def cmd_strategies(args=None):
    print_header("ALL 20 INTRADAY STRATEGIES LIBRARY & AIC-20 CONFLUENCE")
    if not args:
        cfg = load_json(CONFIG_FILE)
        sym = cfg.get("watchlist", ["RELIANCE.NS"])[0]
        args = ["--symbol", sym]
    run_subcommand("skills/trader-scanner/strategies.py", args)


def cmd_ui(port=8765, open_browser=True):
    print_header("LAUNCHING INTERACTIVE WEB DASHBOARD")
    script = os.path.join(BASE_DIR, "skills", "trader-broker", "web_server.py")
    cmd = [sys.executable, script, "--port", str(port)]
    if not open_browser:
        cmd.append("--no-browser")
    subprocess.run(cmd, cwd=BASE_DIR)


def interactive_menu():
    while True:
        print_header("VYAPAR AI - SMARTER TRADES FOR BHARAT")
        cfg = load_json(CONFIG_FILE)
        print(f" Capital: Rs {cfg.get('budget', 100000):,.0f} | Risk/Trade: Rs {cfg.get('max_loss_per_trade_inr', 1000):,.0f} | Broker: {cfg.get('broker', 'paper').upper()}")
        print(f" Watchlist: {', '.join(cfg.get('watchlist', []))}")
        print("-" * 60)
        print(" [1] View Portfolio & Market Clock Status")
        print(" [2] Calculate CPR & Camarilla Pivot Setups (Watchlist)")
        print(" [3] Run Morning Pre-Open Auction Scan (09:08 AM)")
        print(" [4] Run 15-Minute ORB & VWAP Breakout Scan (09:35 AM)")
        print(" [5] Multi-Week Swing & Fibonacci Analysis (RSI Divergence)")
        print(" [6] View Terminal Dashboard")
        print(" [7] Emergency PANIC Square-Off (Market Exit All)")
        print(" [8] View Trade Performance Journal")
        print(" [9] Run Automated Unit Tests (Verification)")
        print(" [10] Test Push Notifications (Telegram / Discord)")
        print(" [11] Configure Telegram / Discord Push Alerts")
        print(" [12] 🌐 Launch Interactive Web Dashboard (Browser UI)")
        print(" [13] 📊 All 20 Intraday Strategies Library & Signals")
        print(" [0] Exit")
        print("-" * 60)

        choice = input("Select an option (0-13): ").strip()
        if choice == "1":
            cmd_status()
        elif choice == "2":
            cmd_pivots()
        elif choice == "3":
            cmd_preopen()
        elif choice == "4":
            cmd_scan()
        elif choice == "5":
            cmd_swing()
        elif choice == "6":
            run_subcommand("skills/trader-broker/dashboard.py")
        elif choice == "7":
            cmd_panic()
        elif choice == "8":
            cmd_journal()
        elif choice == "9":
            cmd_test()
        elif choice == "10":
            cmd_notify_test()
        elif choice == "11":
            cmd_setup_notify()
        elif choice == "12":
            cmd_ui()
        elif choice == "13":
            cmd_strategies()
        elif choice in ("0", "q", "exit"):
            print("\nExiting Vyapar AI Console. Smarter Trades for Bharat!\n")
            break
        else:
            print("\nInvalid choice, please select 0 to 13.")
        
        input("\nPress Enter to return to menu...")


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower().strip("-")
        rest = sys.argv[2:]
        if cmd == "status":
            cmd_status()
        elif cmd in ("pivots", "cpr"):
            cmd_pivots()
        elif cmd in ("preopen", "gap"):
            cmd_preopen()
        elif cmd in ("scan", "orb"):
            cmd_scan()
        elif cmd in ("swing", "fib", "fibonacci"):
            cmd_swing(rest if rest else None)
        elif cmd in ("ui", "web", "dashboard", "gui"):
            cmd_ui()
        elif cmd in ("panic", "flatten"):
            cmd_panic()
        elif cmd in ("journal", "pnl"):
            cmd_journal()
        elif cmd in ("test", "tests"):
            cmd_test()
        elif cmd in ("notify", "test-notify", "notify-test"):
            cmd_notify_test()
        elif cmd in ("strategies", "strategy", "strat", "aic"):
            cmd_strategies(rest)
        else:
            print(f"Unknown command: {cmd}")
            print("Supported commands: status, pivots, preopen, scan, swing, ui, panic, journal, test, notify, strategies")
            sys.exit(1)
    else:
        try:
            interactive_menu()
        except KeyboardInterrupt:
            print("\nInterrupted by user. Goodbye!")
            sys.exit(0)


if __name__ == "__main__":
    main()
