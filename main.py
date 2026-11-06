#!/usr/bin/env python3
"""Unified Control Center & Master Orchestrator for Vyapar AI (NSE/BSE).
Standard library only. Provides an interactive menu and automated headless execution.

Usage:
    python main.py                     # Interactive Command Center
    python main.py status              # Show portfolio, budget, and live market clock
    python main.py pivots              # Calculate CPR & Camarilla pivots for watchlist
    python main.py preopen             # Check 09:08 AM Pre-open auction & gap analysis
    python main.py scan [args]         # Run 15-minute ORB & VWAP breakout scanner
    python main.py panic               # PANIC FLATTEN all open positions immediately
    python main.py journal             # Show EOD trade journal and P&L performance
    python main.py test                # Run automated unit test regression suite
    python main.py ui [--port 8765] [--no-browser] # Launch Web Dashboard
"""

import datetime
import json
import os
import subprocess
import sys

# Configure UTF-8 on Windows console safely
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "skills"))

from common import load_json, resolve_path, save_json

CONFIG_FILE = resolve_path("trader/config.json")
PORTFOLIO_FILE = resolve_path("trader/portfolio.json")


def mask_secret(val) -> str:
    """Masks sensitive credentials (tokens, webhooks) in CLI outputs."""
    if not val or not str(val).strip():
        return "Not configured"
    s = str(val).strip()
    if len(s) <= 6:
        return "******"
    return s[:3] + "*" * (len(s) - 6) + s[-3:]


def resolve_secrets(cfg: dict) -> dict:
    """Resolves Telegram and Discord secrets from environment variables first, config second.
    Warns if secrets are found in plaintext inside config.json.
    """
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN") or cfg.get("telegram_bot_token")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID") or cfg.get("telegram_chat_id")
    dc_url = os.environ.get("DISCORD_WEBHOOK_URL") or cfg.get("discord_webhook_url") or cfg.get("discord_webhook")

    has_cfg_secret = any(
        bool(cfg.get(k) and not str(cfg.get(k)).startswith("YOUR_"))
        for k in ("telegram_bot_token", "telegram_chat_id", "discord_webhook_url", "discord_webhook")
    )
    if has_cfg_secret:
        print("[WARN] Plaintext secret found in config.json. Consider moving to environment variables (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DISCORD_WEBHOOK_URL).", flush=True)

    return {
        "telegram_bot_token": tg_token,
        "telegram_chat_id": tg_chat,
        "discord_webhook_url": dc_url
    }


def print_header(title: str):
    print("\n" + "=" * 60, flush=True)
    print(f" {title.center(58)} ", flush=True)
    print("=" * 60, flush=True)


def run_subcommand(relative_script: str, args: list = None) -> int:
    """Executes a subcommand in a child process and returns its exit code."""
    script_path = os.path.join(BASE_DIR, relative_script)
    cmd = [sys.executable, script_path] + (args or [])
    res = subprocess.run(cmd, cwd=BASE_DIR)
    return res.returncode


def cmd_status() -> int:
    print_header("LIVE PORTFOLIO & CONFIGURATION STATUS")
    cfg = load_json(CONFIG_FILE)
    port = load_json(PORTFOLIO_FILE)

    broker = cfg.get("broker", "paper").lower()
    budget = float(cfg.get("budget", 100000.0))
    cash = float(port.get("cash", budget))
    holdings = port.get("holdings", {})
    watchlist = cfg.get("watchlist", ["RELIANCE.NS", "TCS.NS", "INFY.NS"])
    max_loss = float(cfg.get("max_loss_per_trade_inr", 1000.0))
    daily_loss = float(cfg.get("max_daily_loss_inr", 3000.0))

    loss_pct = (max_loss / budget * 100.0) if budget > 0 else 1.0
    daily_pct = (daily_loss / budget * 100.0) if budget > 0 else 3.0

    if broker == "paper":
        print("  [BROKER MODE: PAPER SIMULATION · ZERO FINANCIAL RISK]\n", flush=True)
    else:
        print(f"  [WARNING: LIVE BROKER MODE ({broker.upper()}) ACTIVE · REAL MONEY AT RISK]\n", flush=True)

    print(f"  • Capital Allocated:      Rs {budget:,.2f}", flush=True)
    print(f"  • Available Cash:         Rs {cash:,.2f}", flush=True)
    print(f"  • Max Loss Per Trade:     Rs {max_loss:,.2f} ({loss_pct:.1f}% Hard Stop)", flush=True)
    print(f"  • Max Daily Loss Limit:   Rs {daily_loss:,.2f} ({daily_pct:.1f}% Account Killswitch)", flush=True)
    print(f"  • Mandatory Square-off:   {cfg.get('flat_by', '15:10')} IST (MIS Intraday Auto-Exit)", flush=True)
    print(f"  • Active Watchlist:       {', '.join(watchlist)}", flush=True)
    print(f"  • Active Open Positions:  {len(holdings)}", flush=True)

    if holdings:
        for sym, h in holdings.items():
            qty = h.get("qty") if isinstance(h, dict) else h
            price = h.get("entry_price", 0) if isinstance(h, dict) else 0
            print(f"    - {sym}: {qty} shares @ Rs {price:.2f}", flush=True)
    else:
        print("    (No open positions. 100% in cash)", flush=True)

    print("-" * 60, flush=True)
    print("Market Session Clock:", flush=True)
    return run_subcommand("skills/trader-alerts/alerts.py", ["clock"])


def cmd_pivots() -> int:
    print_header("TOMORROW'S CPR & CAMARILLA PIVOT LEVELS")
    cfg = load_json(CONFIG_FILE)
    watchlist = cfg.get("watchlist", ["RELIANCE.NS", "TCS.NS", "INFY.NS"])
    return run_subcommand("skills/trader-scanner/cpr.py", watchlist)


def cmd_preopen() -> int:
    print_header("09:08 AM PRE-OPEN AUCTION & GAP SCAN")
    cfg = load_json(CONFIG_FILE)
    watchlist = cfg.get("watchlist", ["RELIANCE.NS", "TCS.NS", "INFY.NS"])
    return run_subcommand("skills/trader-scanner/preopen.py", ["--symbols"] + watchlist)


def cmd_scan(args: list = None) -> int:
    print_header("15-MINUTE ORB & VWAP BREAKOUT SCAN")
    scan_args = args if args else ["orb"]
    return run_subcommand("skills/trader-scanner/scan.py", scan_args)


def cmd_panic() -> int:
    print_header("PANIC BUTTON: FLATTEN ALL POSITIONS")
    rc = run_subcommand("skills/trader-broker/dashboard.py", ["--flatten-all"])
    if rc == 0:
        print("\n[SUCCESS] Panic flatten executed successfully. All positions closed.\n", flush=True)
    else:
        print(f"\n[FAILED] Panic flatten encountered an error (exit code {rc}). Check logs.\n", flush=True)
    return rc


def cmd_journal() -> int:
    print_header("END-OF-DAY TRADE JOURNAL & PERFORMANCE METRICS")
    return run_subcommand("skills/trader-broker/journal.py")


def cmd_test() -> int:
    print_header("RUNNING AUTOMATED REGRESSION TEST SUITE")
    return run_subcommand("tests/test_indian_market.py")


def cmd_notify_test() -> int:
    print_header("TESTING TELEGRAM / DISCORD NOTIFICATIONS")
    return run_subcommand("skills/trader-alerts/alerts.py", ["test-notify"])


def cmd_setup_notify() -> int:
    print_header("CONFIGURE TELEGRAM / DISCORD MOBILE ALERTS")
    cfg = load_json(CONFIG_FILE)
    secrets = resolve_secrets(cfg)
    print("Current Notification Settings (Masked):")
    print(f"  • Telegram Bot Token: {mask_secret(secrets['telegram_bot_token'])}")
    print(f"  • Telegram Chat ID:   {mask_secret(secrets['telegram_chat_id'])}")
    print(f"  • Discord Webhook:    {mask_secret(secrets['discord_webhook_url'])}")
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
        save_json(CONFIG_FILE, cfg)
        print("\n[OK] Notification settings saved atomically to trader/config.json!")
        print("Dispatching test notification to verify...")
        return run_subcommand("skills/trader-alerts/alerts.py", ["test-notify"])
    else:
        print("\nNo changes made.")
        return 0


def cmd_swing(symbols: list = None) -> int:
    print_header("MULTI-WEEK SWING & FIBONACCI ANALYSIS")
    if not symbols:
        cfg = load_json(CONFIG_FILE)
        symbols = cfg.get("watchlist", ["JIOFIN.NS", "RELIANCE.NS"])
    return run_subcommand("skills/trader-analyst/swing.py", symbols)


def cmd_strategies(args: list = None) -> int:
    print_header("ALL 20 INTRADAY STRATEGIES LIBRARY & AIC-20 CONFLUENCE")
    if not args:
        cfg = load_json(CONFIG_FILE)
        sym = cfg.get("watchlist", ["RELIANCE.NS"])[0]
        args = ["--symbol", sym]
    return run_subcommand("skills/trader-scanner/strategies.py", args)


def cmd_ui(port: int = 8765, open_browser: bool = True) -> int:
    print_header("LAUNCHING INTERACTIVE WEB DASHBOARD")
    script = os.path.join(BASE_DIR, "skills", "trader-broker", "web_server.py")
    cmd_args = ["--port", str(port)]
    if not open_browser:
        cmd_args.append("--no-browser")
    return run_subcommand("skills/trader-broker/web_server.py", cmd_args)


def cmd_install(args: list = None) -> int:
    print_header("INSTALLING SKILL SUITE")
    return run_subcommand("install.py", args or [])


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
        print(" [12] Launch Interactive Web Dashboard (Browser UI)")
        print(" [13] All 20 Intraday Strategies Library & Signals")
        print(" [14] Install Skill Suite (Claude / Antigravity / Cursor / Local)")
        print(" [0] Exit")
        print("-" * 60)

        choice = input("Select an option (0-14): ").strip()
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
        elif choice == "14":
            cmd_install()
        elif choice in ("0", "q", "exit"):
            print("\nExiting Vyapar AI Console. Smarter Trades for Bharat!\n")
            break
        else:
            print("\nInvalid choice, please select 0 to 14.")
        
        input("\nPress Enter to return to menu...")


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower().strip("-")
        rest = sys.argv[2:]
        rc = 0
        if cmd == "status":
            rc = cmd_status()
        elif cmd in ("pivots", "cpr"):
            rc = cmd_pivots()
        elif cmd in ("preopen", "gap"):
            rc = cmd_preopen()
        elif cmd in ("scan", "orb"):
            rc = cmd_scan(rest)
        elif cmd in ("swing", "fib", "fibonacci"):
            rc = cmd_swing(rest if rest else None)
        elif cmd in ("ui", "web", "dashboard", "gui"):
            port = 8765
            open_browser = True
            if "--no-browser" in rest:
                open_browser = False
            if "--port" in rest:
                try:
                    idx = rest.index("--port")
                    port = int(rest[idx + 1])
                except (ValueError, IndexError):
                    pass
            rc = cmd_ui(port=port, open_browser=open_browser)
        elif cmd in ("panic", "flatten"):
            rc = cmd_panic()
        elif cmd in ("journal", "pnl"):
            rc = cmd_journal()
        elif cmd in ("test", "tests"):
            rc = cmd_test()
        elif cmd in ("notify", "test-notify", "notify-test"):
            rc = cmd_notify_test()
        elif cmd in ("strategies", "strategy", "strat", "aic"):
            rc = cmd_strategies(rest)
        elif cmd in ("install", "setup", "skills"):
            rc = cmd_install(rest)
        else:
            print(f"Unknown command: {cmd}")
            print("Supported commands: status, pivots, preopen, scan, swing, ui, panic, journal, test, notify, strategies, install")
            sys.exit(1)
        sys.exit(rc if rc is not None else 0)
    else:
        try:
            interactive_menu()
        except KeyboardInterrupt:
            print("\nInterrupted by user. Goodbye!")
            sys.exit(0)


if __name__ == "__main__":
    main()
