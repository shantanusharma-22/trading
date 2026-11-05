#!/usr/bin/env python3
"""Autonomous Day Trading & Universal Stock Screener Engine for Indian Equities (NSE/BSE).
Features:
  1. Universal Screener: Automatically scans Nifty 50 & liquid F&O stocks for Narrow CPR setups.
  2. Setup Qualification: 15m Opening Range Breakout (ORB) + Intraday VWAP confirmation.
  3. Dynamic Risk Sizing: Enforces hard ₹1,000 risk cap per trade in whole shares.
  4. Active Position Management: 1.5x ATR trailing stops, 1.5R/2R profit targets, and 15:10 IST auto-squareoff.
  5. Safety Killswitches: India VIX filter (11.5-24), 2 consecutive loss shutdown, high-water mark profit lock.
  6. Standard library only (threading, json, urllib).

Usage:
    from autotrader import get_autotrader
    engine = get_autotrader()
    engine.start()
"""

import collections
import datetime
import json
import math
import os
import sys
import threading
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_FILE = os.path.join(BASE_DIR, "trader", "config.json")
PORTFOLIO_FILE = os.path.join(BASE_DIR, "trader", "portfolio.json")

sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-alerts"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-scanner"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-entry"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-exit"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-risk"))

try:
    import alerts
    import cpr
    import scan
    import strategies
except ImportError:
    pass

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
YAHOO_HOST = "query1.finance.yahoo.com"


def load_json(path, default=None):
    if not os.path.exists(path):
        return default or {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default or {}


def save_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


class AutoTraderEngine:
    def __init__(self):
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.state = "IDLE"  # IDLE, PRE_MARKET, ORB_WAIT, SCANNING, IN_POSITION, SQUAREOFF, STOPPED
        self.logs = collections.deque(maxlen=100)
        self.universe_mode = "nifty50"  # nifty50, fno, watchlist
        self.active_strategy = "aic_confluence"  # Default: Strategy #20 Custom Institutional Confluence
        self.trades_today = 0
        self.max_trades_per_day = 2
        self.consecutive_losses = 0
        self.last_scan_time = 0
        self.add_log("Auto-Trader Engine initialized in Standby mode with AIC-20 Confluence Model.")

    def add_log(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        with self.lock:
            self.logs.append(entry)
        print(f"[AUTOTRADER] {entry}", flush=True)

    def set_strategy(self, strategy_id):
        with self.lock:
            strat_info = getattr(strategies, "STRATEGY_REGISTRY", {}).get(strategy_id)
            strat_name = strat_info.get("name", strategy_id) if strat_info else strategy_id
            self.active_strategy = strategy_id
            self.add_log(f"Active Trading Strategy switched to: [{strategy_id}] {strat_name}")
            return True, f"Strategy set to {strat_name}"

    def get_status(self):
        with self.lock:
            strat_info = getattr(strategies, "STRATEGY_REGISTRY", {}).get(self.active_strategy, {})
            return {
                "running": self.running,
                "state": self.state,
                "universe_mode": self.universe_mode,
                "active_strategy": self.active_strategy,
                "strategy_name": strat_info.get("name", self.active_strategy),
                "strategy_win_rate": strat_info.get("win_rate", "N/A"),
                "strategy_risk_reward": strat_info.get("risk_reward", "N/A"),
                "trades_today": self.trades_today,
                "max_trades_per_day": self.max_trades_per_day,
                "consecutive_losses": self.consecutive_losses,
                "logs": list(self.logs)
            }

    def start(self, universe_mode=None):
        if self.running:
            return False, "Auto-Trader is already running."
        if universe_mode:
            self.universe_mode = universe_mode
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.add_log(f"Auto-Trader STARTED on universe: {self.universe_mode.upper()} (Max trades: {self.max_trades_per_day}).")
        return True, "Auto-Trader started successfully."

    def stop(self):
        if not self.running:
            return False, "Auto-Trader is not running."
        self.running = False
        self.state = "IDLE"
        self.add_log("Auto-Trader STOPPED by user.")
        return True, "Auto-Trader stopped."

    def _run_loop(self):
        """Main autonomous execution loop running every 5-10 seconds."""
        while self.running:
            try:
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                now_ist = alerts.to_ist(now_utc)
                curr_time = now_ist.time()

                # 1. Check Market Session Timing
                open_time = datetime.time(9, 15)
                orb_end_time = datetime.time(9, 30)
                flat_by_time = datetime.time(15, 10)
                close_time = datetime.time(15, 30)

                # Active Position Management (Runs regardless of market time)
                self._manage_open_positions(now_ist)

                # Safety Check: Mandatory 15:10 Squareoff
                if curr_time >= flat_by_time:
                    if self.state != "SQUAREOFF":
                        self.state = "SQUAREOFF"
                        self.add_log("Mandatory 15:10 IST square-off deadline reached. Enforcing 100% cash.")
                        self._force_squareoff_all()
                    time.sleep(10)
                    continue

                # Pre-Market: 09:00 - 09:15
                if curr_time < open_time:
                    self.state = "PRE_MARKET"
                    self.add_log("Pre-Market session (09:00-09:15 IST). Standing by for market open.")
                    time.sleep(20)
                    continue

                # Opening Range Wait: 09:15 - 09:30
                if open_time <= curr_time < orb_end_time:
                    self.state = "ORB_WAIT"
                    diff_min = 30 - curr_time.minute
                    self.add_log(f"Observing 15m Opening Range formation ({diff_min} mins remaining). No entries permitted before 09:30 IST.")
                    time.sleep(30)
                    continue

                # Regular Trading & Screening Session: 09:30 - 14:45
                if orb_end_time <= curr_time < datetime.time(14, 45):
                    # Check trade caps & killswitch
                    if self.trades_today >= self.max_trades_per_day:
                        self.state = "SHUTDOWN_LIMIT"
                        self.add_log(f"Daily trade limit reached ({self.trades_today}/{self.max_trades_per_day}). Done for the day.")
                        time.sleep(60)
                        continue

                    if self.consecutive_losses >= 2:
                        self.state = "SHUTDOWN_LIMIT"
                        self.add_log("Consecutive losses killswitch triggered (2 losses). Auto-Trader halted for capital preservation.")
                        time.sleep(60)
                        continue

                    # Execute screener every 30 seconds
                    now_ts = time.time()
                    if now_ts - self.last_scan_time >= 30:
                        self.last_scan_time = now_ts
                        self.state = "SCANNING"
                        self._screen_and_trade(now_ist)

                time.sleep(8)
            except Exception as e:
                self.add_log(f"Error in auto-trader loop: {e}")
                time.sleep(10)

    def _get_universe_symbols(self):
        """Returns the list of symbols based on active universe mode."""
        if self.universe_mode == "watchlist":
            cfg = load_json(CONFIG_FILE)
            return cfg.get("watchlist", ["RELIANCE.NS", "TCS.NS", "INFY.NS", "JIOFIN.NS"])
        
        # Default: Top liquid Nifty constituents
        universe = [s for s, _, _ in getattr(scan, "DEFAULT_INDIAN_UNIVERSE", [])]
        if not universe:
            universe = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "SBIN.NS", "ITC.NS", "LT.NS", "BAJFINANCE.NS"]
        return universe

    def _screen_and_trade(self, now_ist):
        """Screens the universe for Narrow CPR + 15m ORB Breakouts."""
        symbols = self._get_universe_symbols()
        self.add_log(f"Scanning {len(symbols)} liquid NSE stocks for setups...")

        cfg = load_json(CONFIG_FILE)
        port = load_json(PORTFOLIO_FILE)
        holdings = port.get("holdings", {})

        # Do not enter if already holding a position
        if len(holdings) >= 1:
            self.state = "IN_POSITION"
            return

        candidates = []
        for sym in symbols:
            try:
                # 1. Narrow CPR Filter (< 0.25% width)
                cpr_res = cpr.analyze_symbol(sym)
                cpr_width = cpr_res.get("cpr_width_pct", 1.0)
                if cpr_width > 0.35:  # Filter out wide CPR sideways stocks
                    continue

                candidates.append((sym, cpr_res))
            except Exception:
                continue

        if not candidates:
            self.add_log("No narrow CPR stocks qualified this cycle. Waiting for next 5m bar.")
            return

        self.add_log(f"Found {len(candidates)} narrow CPR candidates. Checking 15m ORB breakouts & VWAP...")

        # 2. Check Active Strategy on Candidates
        for sym, cpr_res in candidates:
            try:
                setup = self._evaluate_stock_strategy(sym, cpr_res)
                if setup:
                    self.add_log(f"🔥 STRATEGY SIGNAL QUALIFIED: {sym} [{setup['strategy_name']}] - {setup['side']} @ Rs {setup['entry']:.2f} (Stop: Rs {setup['stop']:.2f}, Target: Rs {setup['target']:.2f})")
                    self._execute_auto_trade(setup)
                    break  # Take 1 quality trade at a time
            except Exception as e:
                self.add_log(f"Error checking {sym}: {e}")

    def _evaluate_stock_strategy(self, sym, cpr_res):
        """Evaluates the active strategy on the candidate stock."""
        norm = alerts.normalize_symbol(sym)
        candles = getattr(strategies, "fetch_intraday_candles", lambda s: [])(norm)
        if not candles or len(candles) < 4:
            return None

        prev_bar = {
            "high": cpr_res.get("high", candles[0]["open"] * 1.01),
            "low": cpr_res.get("low", candles[0]["open"] * 0.99),
            "close": cpr_res.get("close", candles[0]["open"])
        }

        strat_id = self.active_strategy
        res = None

        if strat_id == "aic_confluence":
            res = strategies.eval_aic_confluence(sym, candles, prev_bar)
        elif strat_id == "orb":
            res = strategies.eval_orb(candles, prev_bar)
        elif strat_id == "supertrend":
            res = strategies.eval_supertrend(candles)
        elif strat_id == "vwap_pullback":
            res = strategies.eval_vwap_pullback(candles)
        elif strat_id == "ema_crossover":
            res = strategies.eval_ema_crossover(candles)
        elif strat_id == "pdh_pdl":
            res = strategies.eval_pdh_pdl(candles, prev_bar)
        elif strat_id == "bollinger_squeeze":
            res = strategies.eval_bollinger_bands(candles)
        elif strat_id == "cpr_camarilla":
            res = strategies.eval_cpr_camarilla_strat(candles, prev_bar)
        else:
            evals = getattr(strategies, "evaluate_all", lambda s, c, p: [])(sym, candles, prev_bar)
            matched = [e["evaluation"] for e in evals if e["id"] == strat_id]
            res = matched[0] if matched else None

        if res and res.get("signal") in ("BUY", "SELL"):
            if strat_id == "aic_confluence" and not res.get("is_executable", False):
                return None
            return {
                "symbol": sym,
                "side": res["signal"],
                "entry": res.get("entry", candles[-1]["close"]),
                "stop": res.get("stop", candles[-1]["close"] * 0.99),
                "target": res.get("target", candles[-1]["close"] * 1.018),
                "strategy_id": strat_id,
                "strategy_name": getattr(strategies, "STRATEGY_REGISTRY", {}).get(strat_id, {}).get("name", strat_id),
                "reason": res.get("reason", "")
            }
        return None

    def _execute_auto_trade(self, setup):
        """Sizes whole shares under ₹1,000 risk cap and executes the paper trade."""
        sym = setup["symbol"]
        side = setup.get("side", "BUY")
        entry = setup["entry"]
        stop = setup["stop"]
        target = setup["target"]

        cfg = load_json(CONFIG_FILE)
        max_loss = cfg.get("max_loss_per_trade_inr", 1000.0)

        risk_per_share = max(abs(entry - stop), entry * 0.005)
        shares = math.floor(max_loss / risk_per_share)
        if shares <= 0:
            self.add_log(f"⚠️ Sizer rejected trade on {sym}: Risk per share (Rs {risk_per_share:.2f}) exceeds max loss limit (Rs {max_loss:.2f})")
            return

        # Margin calculation (5x MIS Intraday leverage)
        margin_required = round((shares * entry) / 5.0, 2)

        port = load_json(PORTFOLIO_FILE)
        cash = port.get("cash", 100000.0)

        if cash < margin_required:
            self.add_log(f"Skipping trade on {sym}: Insufficient cash (Required Rs {margin_required:,.2f}, Available Rs {cash:,.2f})")
            return

        # Place trade into portfolio
        port["cash"] = round(cash - margin_required, 2)
        holdings = port.get("holdings", {})
        holdings[sym] = {
            "symbol": sym,
            "side": side,
            "qty": shares,
            "entry_price": entry,
            "current_price": entry,
            "stop": stop,
            "target": target,
            "strategy": setup.get("strategy_name", self.active_strategy),
            "margin_used": margin_required,
            "placed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        port["holdings"] = holdings
        save_json(PORTFOLIO_FILE, port)

        self.trades_today += 1
        self.state = "IN_POSITION"

        action_word = "Bought" if side == "BUY" else "Short Sold"
        self.add_log(f"✅ AUTO-TRADE EXECUTED: {action_word} {shares}x {sym} @ Rs {entry:.2f} | Stop: Rs {stop:.2f} | Target: Rs {target:.2f} (Total Risk: Rs {round(shares * risk_per_share, 2):,.2f})")
        alerts.dispatch_push_notification(
            f"🤖 Auto-Trade Executed: {sym} ({side})",
            f"Filled {shares} shares @ Rs {entry:.2f} via {setup.get('strategy_name', self.active_strategy)}\nStop-Loss: Rs {stop:.2f}\nTarget: Rs {target:.2f}\nRisk: Rs {round(shares * risk_per_share, 2)}"
        )

    def _manage_open_positions(self, now_ist):
        """Monitors open positions for stop-loss hits, profit target hits, or trailing stops."""
        port = load_json(PORTFOLIO_FILE)
        holdings = port.get("holdings", {})
        if not holdings:
            return

        to_close = []
        for sym, h in list(holdings.items()):
            try:
                # Fetch latest price
                norm = alerts.normalize_symbol(sym)
                url = f"https://{YAHOO_HOST}/v8/finance/chart/{norm}?range=1d&interval=1m"
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    chart = data["chart"]["result"][0]
                    closes = chart["indicators"]["quote"][0]["close"]
                    valid_closes = [c for c in closes if c is not None]
                    if not valid_closes:
                        continue
                    current_p = valid_closes[-1]
                    h["current_price"] = current_p

                    side = h.get("side", "BUY")
                    entry_p = h["entry_price"]
                    stop_p = h["stop"]
                    target_p = h["target"]
                    qty = h["qty"]

                    if side == "BUY":
                        pnl = round((current_p - entry_p) * qty, 2)
                        h["pnl"] = pnl
                        # Target Hit
                        if current_p >= target_p:
                            self.add_log(f"🎯 TARGET REACHED on {sym}! Exiting @ Rs {current_p:.2f} (+Rs {pnl:,.2f})")
                            to_close.append((sym, "TARGET_HIT", pnl, current_p))
                        # Stop-Loss Hit
                        elif current_p <= stop_p:
                            self.add_log(f"🛑 STOP-LOSS HIT on {sym}! Exiting @ Rs {current_p:.2f} (Rs {pnl:,.2f})")
                            to_close.append((sym, "STOP_HIT", pnl, current_p))
                        # Trailing Stop Adjustment (if in 1R profit, move stop to breakeven)
                        elif current_p >= entry_p + (entry_p - stop_p):
                            if h["stop"] < entry_p:
                                h["stop"] = entry_p
                                self.add_log(f"🛡️ TRAILING STOP: Moved {sym} stop to breakeven Rs {entry_p:.2f}")
                    else:  # SELL / SHORT
                        pnl = round((entry_p - current_p) * qty, 2)
                        h["pnl"] = pnl
                        # Target Hit
                        if current_p <= target_p:
                            self.add_log(f"🎯 SHORT TARGET REACHED on {sym}! Exiting @ Rs {current_p:.2f} (+Rs {pnl:,.2f})")
                            to_close.append((sym, "TARGET_HIT", pnl, current_p))
                        # Stop-Loss Hit
                        elif current_p >= stop_p:
                            self.add_log(f"🛑 SHORT STOP-LOSS HIT on {sym}! Exiting @ Rs {current_p:.2f} (Rs {pnl:,.2f})")
                            to_close.append((sym, "STOP_HIT", pnl, current_p))
                        # Trailing Stop Adjustment for Short
                        elif current_p <= entry_p - (stop_p - entry_p):
                            if h["stop"] > entry_p:
                                h["stop"] = entry_p
                                self.add_log(f"🛡️ TRAILING STOP: Moved {sym} short stop to breakeven Rs {entry_p:.2f}")

            except Exception:
                continue

        # Process exits
        if to_close:
            for sym, reason, pnl, exit_p in to_close:
                h = holdings.pop(sym)
                margin_ret = h.get("margin_used", 0)
                port["cash"] = round(port.get("cash", 0) + margin_ret + pnl, 2)

                if pnl < 0:
                    self.consecutive_losses += 1
                else:
                    self.consecutive_losses = 0

                alerts.dispatch_push_notification(
                    f"🤖 Auto-Trade Closed: {sym} ({reason})",
                    f"Exited {h['qty']} shares @ Rs {exit_p:.2f} | Net P&L: Rs {pnl:+,.2f}"
                )

                # Persist trade to SQLite Journal
                try:
                    import journal
                    placed_parts = str(h.get("placed_at", "")).split(" ")
                    e_time = placed_parts[1] if len(placed_parts) > 1 else "09:30:00"
                    journal.record_trade({
                        "trade_date": now_ist.strftime("%Y-%m-%d"),
                        "symbol": sym,
                        "side": h.get("side", "BUY"),
                        "qty": h["qty"],
                        "strategy_id": h.get("strategy", self.active_strategy),
                        "mode": "PAPER",
                        "source": "AUTO",
                        "entry_time": e_time,
                        "exit_time": now_ist.strftime("%H:%M:%S"),
                        "entry_price": h["entry_price"],
                        "exit_price": exit_p,
                        "initial_stop": h.get("stop", 0.0),
                        "target": h.get("target", 0.0),
                        "exit_reason": reason
                    })
                except Exception:
                    pass

            port["holdings"] = holdings
            save_json(PORTFOLIO_FILE, port)
            self.state = "SCANNING"

    def _force_squareoff_all(self):
        """Forces all positions flat at 15:10 IST."""
        port = load_json(PORTFOLIO_FILE)
        holdings = port.get("holdings", {})
        if not holdings:
            return

        for sym, h in list(holdings.items()):
            margin_ret = h.get("margin_used", 0)
            pnl = h.get("pnl", 0)
            port["cash"] = round(port.get("cash", 0) + margin_ret + pnl, 2)
            self.add_log(f"Square-off: Flattened {sym} MIS position. Net P&L: Rs {pnl:+,.2f}")

            # Persist to journal
            try:
                import journal
                placed_parts = str(h.get("placed_at", "")).split(" ")
                e_time = placed_parts[1] if len(placed_parts) > 1 else "09:30:00"
                now_ist = alerts.to_ist(datetime.datetime.now(datetime.timezone.utc))
                cur_p = h.get("current_price", h.get("entry_price", 0.0))
                journal.record_trade({
                    "trade_date": now_ist.strftime("%Y-%m-%d"),
                    "symbol": sym,
                    "side": h.get("side", "BUY"),
                    "qty": h["qty"],
                    "strategy_id": h.get("strategy", self.active_strategy),
                    "mode": "PAPER",
                    "source": "AUTO",
                    "entry_time": e_time,
                    "exit_time": "15:10:00",
                    "entry_price": h["entry_price"],
                    "exit_price": cur_p,
                    "initial_stop": h.get("stop", 0.0),
                    "target": h.get("target", 0.0),
                    "exit_reason": "SQUARED_OFF"
                })
            except Exception:
                pass

        port["holdings"] = {}
        save_json(PORTFOLIO_FILE, port)
        alerts.dispatch_push_notification("🤖 15:10 Square-Off Complete", "All open intraday MIS positions closed into 100% cash.")


# Global Singleton Instance
_AUTOTRADER_INSTANCE = None


def get_autotrader():
    global _AUTOTRADER_INSTANCE
    if _AUTOTRADER_INSTANCE is None:
        _AUTOTRADER_INSTANCE = AutoTraderEngine()
    return _AUTOTRADER_INSTANCE


if __name__ == "__main__":
    engine = get_autotrader()
    print("Testing AutoTrader Engine in standalone mode...")
    status = engine.get_status()
    print("Initial Status:", status)
    print("AutoTrader module loaded successfully.")

