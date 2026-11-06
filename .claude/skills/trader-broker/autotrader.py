#!/usr/bin/env python3
"""Autonomous Day Trading & Universal Stock Screener Engine for Indian Equities (NSE/BSE).
Features:
  1. Universal Screener: Automatically scans Nifty 50 & liquid F&O stocks for Narrow CPR setups (<0.25% width).
  2. Setup Qualification: 15m Opening Range Breakout (ORB) + Intraday VWAP confirmation.
  3. Dynamic Risk Sizing: Enforces hard ₹1,000 risk cap per trade in whole shares, turnover capped at max_order_inr.
  4. Active Position Management: 1.5x ATR trailing stops, 1.5R/2R profit targets, and 15:10 IST auto-squareoff.
  5. Safety Killswitches: India VIX filter (11.5-24), consecutive loss shutdown, high-water mark profit lock.
  6. Standard library only (threading, json, urllib, math).
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

sys.path.insert(0, os.path.join(BASE_DIR, "skills"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-alerts"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-scanner"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-entry"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-exit"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-risk"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-budget"))

from common import (
    FLAT_BY,
    OPEN,
    STATE_LOCK,
    UA,
    load_json,
    record_closed_trade,
    record_placed_trade,
    resolve_path,
    save_json,
    to_ist,
)

try:
    import alerts
    import check as risk_check
    import cpr
    import scan
    import strategies
    import tax_calculator
except ImportError:
    pass

YAHOO_HOST = "query1.finance.yahoo.com"


def normalize_holding(sym: str, raw_holding) -> dict:
    """Validates and enforces the universal holdings schema."""
    if isinstance(raw_holding, (int, float)):
        return {
            "symbol": sym,
            "qty": int(raw_holding),
            "entry_price": 0.0,
            "side": "BUY",
            "stop": 0.0,
            "target": 0.0,
            "current_price": 0.0,
            "margin_used": 0.0,
            "strategy": "manual",
            "placed_at": "",
            "pnl": 0.0
        }
    if isinstance(raw_holding, dict):
        return {
            "symbol": raw_holding.get("symbol", sym),
            "qty": int(raw_holding.get("qty", 1)),
            "entry_price": float(raw_holding.get("entry_price", 0.0)),
            "side": raw_holding.get("side", "BUY").upper(),
            "stop": float(raw_holding.get("stop", 0.0)),
            "target": float(raw_holding.get("target", 0.0)),
            "current_price": float(raw_holding.get("current_price", raw_holding.get("entry_price", 0.0))),
            "margin_used": float(raw_holding.get("margin_used", 0.0)),
            "strategy": raw_holding.get("strategy", "manual"),
            "placed_at": str(raw_holding.get("placed_at", "")),
            "pnl": float(raw_holding.get("pnl", 0.0))
        }
    return {}


def calculate_atr(candles: list, period: int = 14) -> float:
    """Calculates Average True Range (ATR) across historical candles."""
    if not candles or len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h = candles[i].get("high", 0.0)
        l = candles[i].get("low", 0.0)
        prev_c = candles[i - 1].get("close", 0.0)
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    recent = trs[-period:] if len(trs) >= period else trs
    return sum(recent) / len(recent) if recent else 0.0


class AutoTraderEngine:
    def __init__(self):
        self.running = False
        self.thread = None
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.state = "IDLE"  # IDLE, PRE_MARKET, ORB_WAIT, SCANNING, IN_POSITION, SQUAREOFF, SHUTDOWN_LIMIT, STOPPED
        self.logs = collections.deque(maxlen=100)
        self.universe_mode = "nifty50"  # nifty50, fno, watchlist
        self.active_strategy = "aic_confluence"  # Default: Strategy #20 Custom Institutional Confluence
        self.trades_today = 0
        self.max_trades_per_day = 2
        self.consecutive_losses = 0
        self.last_scan_time = 0
        self.last_trading_day = None
        self.cpr_cache = {}  # key: (symbol, date_str) -> cpr_res
        self.fetch_failures = {}  # key: symbol -> consecutive failure count
        self.add_log("Auto-Trader Engine initialized in Standby mode with AIC-20 Confluence Model.")

    def add_log(self, message):
        """Safe log output with ASCII-sanitized console print to prevent Windows encoding crashes."""
        now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
        timestamp = now_ist.strftime("%H:%M:%S")
        clean_msg = message.encode("ascii", "ignore").decode("ascii").strip()
        entry = f"[{timestamp}] {clean_msg}"
        with self.lock:
            self.logs.append(entry)
        try:
            print(f"[AUTOTRADER] {entry}", flush=True)
        except Exception:
            pass

    def set_strategy(self, strategy_id):
        """Validates strategy selection, preventing analysis-only or options strategies from automated execution."""
        with self.lock:
            registry = getattr(strategies, "STRATEGY_REGISTRY", {})
            if strategy_id not in registry:
                return False, f"Invalid strategy id '{strategy_id}'"

            strat_info = registry[strategy_id]
            strat_name = strat_info.get("name", strategy_id)
            strat_style = str(strat_info.get("style", "")).lower()

            # Options and Analysis-only models cannot be auto-traded
            analysis_only_ids = {"options_delta_burst", "options_strangle", "options_920_straddle", "options_max_pain"}
            if strategy_id in analysis_only_ids or "analysis" in strat_style or "options" in strat_style:
                return False, f"Strategy '{strat_name}' is marked Analysis-Only. It cannot be selected for auto-trading."

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
        """Starts the autonomous trading loop, ensuring single-instance execution under lock."""
        with self.lock:
            if self.thread and self.thread.is_alive():
                if self.running:
                    return False, "Auto-Trader is already running."
                # Thread was in process of stopping, wait for it
                self.thread.join(timeout=3.0)
                if self.thread.is_alive():
                    return False, "Auto-Trader is already running."

            if universe_mode:
                self.universe_mode = universe_mode

            cfg = load_json(CONFIG_FILE, {})
            self.max_trades_per_day = cfg.get("max_trades_per_day", 3)

            self.running = True
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()
            self.add_log(f"Auto-Trader STARTED on universe: {self.universe_mode.upper()} (Max trades: {self.max_trades_per_day}).")
            return True, "Auto-Trader started successfully."

    def stop(self):
        """Stops the autonomous trading loop and cleanly joins the background worker."""
        with self.lock:
            if not self.running and not (self.thread and self.thread.is_alive()):
                return False, "Auto-Trader is not running."

            self.running = False
            self.stop_event.set()
            self.state = "IDLE"
            th = self.thread

        if th and th.is_alive() and threading.current_thread() != th:
            th.join(timeout=5.0)

        self.add_log("Auto-Trader STOPPED by user.")
        return True, "Auto-Trader stopped."

    def _check_day_rollover(self, now_ist: datetime.datetime):
        """Resets daily trade counters and consecutive losses at each new IST trading date."""
        today_date = now_ist.date()
        if self.last_trading_day != today_date:
            with self.lock:
                self.trades_today = 0
                self.consecutive_losses = 0
                self.cpr_cache.clear()
                self.fetch_failures.clear()
                self.last_trading_day = today_date
            self.add_log(f"New IST Trading Session initialized for {today_date.strftime('%Y-%m-%d')}. Reset trade counters.")

    def _fetch_live_price(self, sym: str) -> float:
        """Fetches fresh live quote for symbol."""
        norm = alerts.normalize_symbol(sym)
        url = f"https://{YAHOO_HOST}/v8/finance/chart/{norm}?range=1d&interval=1m"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                chart = data["chart"]["result"][0]
                closes = chart["indicators"]["quote"][0]["close"]
                valid = [c for c in closes if c is not None]
                if valid:
                    return float(valid[-1])
        except Exception:
            pass
        return 0.0

    def _run_loop(self):
        """Main autonomous execution loop running every 5-10 seconds."""
        while self.running and not self.stop_event.is_set():
            try:
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                now_ist = to_ist(now_utc)
                curr_time = now_ist.time()

                # Rollover check
                self._check_day_rollover(now_ist)

                # Check market session & holiday status
                status_info = alerts.market_status(now_utc)
                if not status_info.get("calendar_known", True):
                    if self.stop_event.wait(timeout=30):
                        break
                    continue

                d_str = now_ist.strftime("%Y-%m-%d")
                if now_ist.weekday() >= 5 or d_str in alerts.NSE_HOLIDAYS:
                    self.state = "MARKET_CLOSED"
                    if self.stop_event.wait(timeout=60):
                        break
                    continue

                cfg = load_json(CONFIG_FILE, {})
                open_time = datetime.time(9, 15)
                orb_end_time = datetime.time(9, 30)
                flat_by_time = datetime.time(15, 10)

                # Parse cutoff from config
                no_entries_after_str = cfg.get("no_entries_after", "14:45")
                no_after_parts = [int(p) for p in no_entries_after_str.split(":")[:2]]
                entry_cutoff_time = datetime.time(no_after_parts[0], no_after_parts[1])

                # Active Position Management
                self._manage_open_positions(now_ist)

                # Safety Check: Mandatory 15:10 Squareoff
                if curr_time >= flat_by_time:
                    if self.state != "SQUAREOFF":
                        self.state = "SQUAREOFF"
                        self.add_log("Mandatory 15:10 IST square-off deadline reached. Enforcing 100% cash.")
                        self._force_squareoff_all()
                    if self.stop_event.wait(timeout=10):
                        break
                    continue

                # Pre-Market: 09:00 - 09:15
                if curr_time < open_time:
                    self.state = "PRE_MARKET"
                    if self.stop_event.wait(timeout=20):
                        break
                    continue

                # Opening Range Wait: 09:15 - 09:30
                if open_time <= curr_time < orb_end_time:
                    self.state = "ORB_WAIT"
                    diff_min = 30 - curr_time.minute
                    self.add_log(f"Observing 15m Opening Range formation ({diff_min} mins remaining). No entries permitted before 09:30 IST.")
                    if self.stop_event.wait(timeout=30):
                        break
                    continue

                # Regular Trading & Screening Session: 09:30 - 14:45
                if orb_end_time <= curr_time < entry_cutoff_time:
                    max_trades = cfg.get("max_trades_per_day", 3)
                    max_consec = cfg.get("max_consecutive_losses", 2)

                    if self.trades_today >= max_trades:
                        self.state = "SHUTDOWN_LIMIT"
                        if self.stop_event.wait(timeout=60):
                            break
                        continue

                    if self.consecutive_losses >= max_consec:
                        self.state = "SHUTDOWN_LIMIT"
                        self.add_log(f"Consecutive losses killswitch triggered ({self.consecutive_losses} losses). Auto-Trader halted for capital preservation.")
                        if self.stop_event.wait(timeout=60):
                            break
                        continue

                    # Execute screener every 30 seconds
                    now_ts = time.time()
                    if now_ts - self.last_scan_time >= 30:
                        self.last_scan_time = now_ts
                        self.state = "SCANNING"
                        self._screen_and_trade(now_ist)

                if self.stop_event.wait(timeout=8):
                    break
            except Exception as e:
                self.add_log(f"Error in auto-trader loop: {e}")
                if self.stop_event.wait(timeout=10):
                    break

    def _get_universe_symbols(self):
        """Returns the list of symbols based on active universe mode."""
        if self.universe_mode == "watchlist":
            cfg = load_json(CONFIG_FILE, {})
            return cfg.get("watchlist", ["RELIANCE.NS", "TCS.NS", "INFY.NS", "JIOFIN.NS"])

        universe = [s for s, _, _ in getattr(scan, "DEFAULT_INDIAN_UNIVERSE", [])]
        if not universe:
            universe = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "SBIN.NS", "ITC.NS", "LT.NS", "BAJFINANCE.NS"]
        return universe

    def _screen_and_trade(self, now_ist):
        """Screens the universe for Narrow CPR (<0.25% width) + Strategy setups."""
        symbols = self._get_universe_symbols()
        self.add_log(f"Scanning {len(symbols)} liquid NSE stocks for setups...")

        port = load_json(PORTFOLIO_FILE, {})
        holdings = port.get("holdings", {})

        # Do not enter if already holding a position
        if len(holdings) >= 1:
            self.state = "IN_POSITION"
            return

        d_str = now_ist.strftime("%Y-%m-%d")
        candidates = []
        for sym in symbols:
            if self.stop_event.is_set() or not self.running:
                return
            try:
                # 1. Cached Narrow CPR Filter (<0.25% width)
                cache_key = (sym, d_str)
                if cache_key in self.cpr_cache:
                    cpr_res = self.cpr_cache[cache_key]
                else:
                    cpr_res = cpr.analyze_symbol(sym)
                    if cpr_res and not cpr_res.get("error"):
                        self.cpr_cache[cache_key] = cpr_res

                if not cpr_res or cpr_res.get("error"):
                    continue

                cpr_width = cpr_res.get("cpr_width_pct", 1.0)
                if cpr_width > 0.25:  # Standard 0.25% threshold
                    continue

                candidates.append((sym, cpr_res))
            except Exception:
                continue

        if not candidates:
            return

        self.add_log(f"Found {len(candidates)} narrow CPR candidate(s). Checking strategy confirmation...")

        # 2. Check Active Strategy on Candidates
        for sym, cpr_res in candidates:
            if self.stop_event.is_set() or not self.running:
                return
            try:
                setup = self._evaluate_stock_strategy(sym, cpr_res)
                if setup:
                    self.add_log(f"STRATEGY SIGNAL QUALIFIED: {sym} [{setup['strategy_name']}] - {setup['side']} @ Rs {setup['entry']:.2f}")
                    self._execute_auto_trade(setup)
                    break  # Take 1 quality trade at a time
            except Exception as e:
                self.add_log(f"Error checking {sym}: {e}")

    def _evaluate_stock_strategy(self, sym, cpr_res):
        """Evaluates active strategy using real previous day high/low/close from CPR analyzer."""
        norm = alerts.normalize_symbol(sym)
        candles = getattr(strategies, "fetch_intraday_candles", lambda s: [])(norm)
        if not candles or len(candles) < 4:
            return None

        # Candle Staleness Guard: refuse if last candle is older than 2 minutes
        now_utc_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
        last_candle_time = candles[-1].get("time", 0)
        if last_candle_time > 0 and (now_utc_ts - last_candle_time) > 120:
            self.add_log(f"Skipping {sym}: candle data is stale (last candle is older than 2 minutes).")
            return None

        # Build prev_bar strictly from real previous day levels returned by cpr.analyze_symbol
        prev_h = cpr_res.get("prev_high")
        prev_l = cpr_res.get("prev_low")
        prev_c = cpr_res.get("prev_close")

        if prev_h is None or prev_l is None or prev_c is None:
            self.add_log(f"Skipping {sym}: real previous-day levels missing from CPR analyzer.")
            return None

        prev_bar = {
            "high": float(prev_h),
            "low": float(prev_l),
            "close": float(prev_c)
        }

        strat_id = self.active_strategy
        res = None

        if strat_id == "aic_confluence":
            vix_val = risk_check.fetch_india_vix() if hasattr(risk_check, "fetch_india_vix") else None
            b_state = load_json("trader/state/breadth.json", {})
            b_ratio = b_state.get("advance_decline_ratio", b_state.get("adv_dec_ratio", 1.0))
            res = strategies.eval_aic_confluence(sym, candles, prev_bar, vix=vix_val, breadth_ratio=b_ratio)
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
        """Sizes order adhering to max_loss, max_order_inr, min_order_inr, and passes pre_trade_gate."""
        sym = setup["symbol"]
        side = setup.get("side", "BUY").upper()
        entry = float(setup["entry"])
        stop = float(setup["stop"])
        target = float(setup["target"])

        cfg = load_json(CONFIG_FILE, {})
        max_loss = cfg.get("max_loss_per_trade_inr", 1000.0)
        max_order_val = cfg.get("max_order_inr", 50000.0)
        min_order_val = cfg.get("min_order_inr", 1000.0)

        risk_per_share = max(abs(entry - stop), entry * 0.005)

        # Enforce both loss limit and maximum order turnover cap
        shares_by_risk = math.floor(max_loss / risk_per_share)
        shares_by_cap = math.floor(max_order_val / entry)
        shares = min(shares_by_risk, shares_by_cap)

        turnover = shares * entry
        if shares <= 0 or turnover < min_order_val:
            self.add_log(f"Sizer rejected trade on {sym}: Shares {shares} or turnover Rs {turnover:,.2f} below minimum limits.")
            return

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_ist = to_ist(now_utc)

        # Pre-Trade Risk Gate Validation (Fail Closed)
        order_candidate = {
            "symbol": sym,
            "side": side,
            "qty": shares,
            "entry_price": entry,
            "stop_loss_price": stop,
            "take_profit_price": target,
            "strategy_id": setup.get("strategy_id", self.active_strategy)
        }

        try:
            vix_val = risk_check.fetch_india_vix() if hasattr(risk_check, "fetch_india_vix") else None
            gate_ok, gate_msg = risk_check.pre_trade_gate(order_candidate, cfg, now_ist, vix=vix_val)
            if not gate_ok:
                self.add_log(f"Risk Gate Blocked {sym}: {gate_msg}")
                return
        except Exception as e:
            self.add_log(f"Risk Gate Failure on {sym}: {e}")
            return

        # MIS Margin calculation from config
        leverage = float(cfg.get("mis_margin_multiplier", {}).get(sym, cfg.get("default_mis_leverage", 5.0)))
        margin_required = round(turnover / leverage, 2)

        port = load_json(PORTFOLIO_FILE, {})
        cash = port.get("cash", 100000.0)

        if cash < margin_required:
            self.add_log(f"Skipping trade on {sym}: Insufficient cash (Required Rs {margin_required:,.2f}, Available Rs {cash:,.2f})")
            return

        # Place trade into portfolio atomically
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
            "placed_at": now_ist.strftime("%Y-%m-%d %H:%M:%S"),
            "pnl": 0.0
        }
        port["holdings"] = holdings
        save_json(PORTFOLIO_FILE, port)

        # Record in shared broker.json trade state
        record_placed_trade(order_candidate, now_ist)

        self.trades_today += 1
        self.state = "IN_POSITION"

        action_word = "Bought" if side == "BUY" else "Short Sold"
        self.add_log(f"AUTO-TRADE EXECUTED: {action_word} {shares}x {sym} @ Rs {entry:.2f} | Stop: Rs {stop:.2f} | Target: Rs {target:.2f} (Total Risk: Rs {round(shares * risk_per_share, 2):,.2f})")
        alerts.dispatch_push_notification(
            f"Auto-Trade Executed: {sym} ({side})",
            f"Filled {shares} shares @ Rs {entry:.2f} via {setup.get('strategy_name', self.active_strategy)}\nStop: Rs {stop:.2f} | Target: Rs {target:.2f}"
        )

    def _manage_open_positions(self, now_ist):
        """Monitors open positions, updates trailing stops, persists holdings every cycle, and exits upon stops/targets."""
        port = load_json(PORTFOLIO_FILE, {})
        holdings = port.get("holdings", {})
        if not holdings:
            return

        to_close = []
        updated_any = False

        for sym, raw_h in list(holdings.items()):
            h = normalize_holding(sym, raw_h)
            try:
                # Fetch fresh price
                current_p = self._fetch_live_price(sym)
                if current_p <= 0:
                    self.fetch_failures[sym] = self.fetch_failures.get(sym, 0) + 1
                    self.add_log(f"Price fetch failed for {sym} (attempt {self.fetch_failures[sym]}/3)")
                    if self.fetch_failures[sym] >= 3:
                        self.add_log(f"EMERGENCY FLATTEN: 3 consecutive price fetch failures for {sym}. Exiting position.")
                        to_close.append((sym, "FETCH_FAILURE_FLATTEN", h.get("pnl", 0.0), h.get("current_price", h.get("entry_price", 0.0))))
                    continue

                self.fetch_failures[sym] = 0
                h["current_price"] = current_p
                updated_any = True

                side = h.get("side", "BUY")
                entry_p = h["entry_price"]
                stop_p = h["stop"]
                target_p = h["target"]
                qty = h["qty"]

                # Fetch candles for ATR trailing stop
                candles = getattr(strategies, "fetch_intraday_candles", lambda s: [])(alerts.normalize_symbol(sym))
                atr_val = calculate_atr(candles, 14) if candles else (entry_p * 0.005)

                if side == "BUY":
                    pnl = round((current_p - entry_p) * qty, 2)
                    h["pnl"] = pnl

                    # Target Hit
                    if current_p >= target_p:
                        self.add_log(f"TARGET REACHED on {sym}! Exiting @ Rs {current_p:.2f} (+Rs {pnl:,.2f})")
                        to_close.append((sym, "TARGET_HIT", pnl, current_p))
                    # Stop-Loss Hit
                    elif current_p <= stop_p:
                        self.add_log(f"STOP-LOSS HIT on {sym}! Exiting @ Rs {current_p:.2f} (Rs {pnl:,.2f})")
                        to_close.append((sym, "STOP_HIT", pnl, current_p))
                    # ATR Trailing Stop: 1R profit -> move to breakeven; beyond 1R -> trail by 1.5x ATR
                    elif current_p >= entry_p + (entry_p - stop_p):
                        atr_trail = round(current_p - 1.5 * atr_val, 2)
                        new_stop = max(entry_p, atr_trail)
                        if new_stop > h["stop"]:
                            h["stop"] = new_stop
                            self.add_log(f"TRAILING STOP: Moved {sym} stop to Rs {new_stop:.2f}")
                else:  # SELL / SHORT
                    pnl = round((entry_p - current_p) * qty, 2)
                    h["pnl"] = pnl

                    # Target Hit
                    if current_p <= target_p:
                        self.add_log(f"SHORT TARGET REACHED on {sym}! Exiting @ Rs {current_p:.2f} (+Rs {pnl:,.2f})")
                        to_close.append((sym, "TARGET_HIT", pnl, current_p))
                    # Stop-Loss Hit
                    elif current_p >= stop_p:
                        self.add_log(f"SHORT STOP-LOSS HIT on {sym}! Exiting @ Rs {current_p:.2f} (Rs {pnl:,.2f})")
                        to_close.append((sym, "STOP_HIT", pnl, current_p))
                    # ATR Trailing Stop for Short
                    elif current_p <= entry_p - (stop_p - entry_p):
                        atr_trail = round(current_p + 1.5 * atr_val, 2)
                        new_stop = min(entry_p, atr_trail)
                        if new_stop < h["stop"]:
                            h["stop"] = new_stop
                            self.add_log(f"TRAILING STOP: Moved {sym} short stop to Rs {new_stop:.2f}")

                holdings[sym] = h
            except Exception as e:
                self.add_log(f"Error managing position {sym}: {e}")
                continue

        # Process exits
        if to_close:
            for sym, reason, gross_pnl, exit_p in to_close:
                h = holdings.pop(sym, {})
                margin_ret = h.get("margin_used", 0)
                qty = h.get("qty", 1)
                entry_p = h.get("entry_price", exit_p)
                side = h.get("side", "BUY")

                # Deduct all statutory charges and slippage via tax_calculator
                if side == "BUY":
                    charges_calc = tax_calculator.calculate_intraday_charges(buy_price=entry_p, sell_price=exit_p, qty=qty)
                else:
                    charges_calc = tax_calculator.calculate_intraday_charges(buy_price=exit_p, sell_price=entry_p, qty=qty)

                net_pnl = charges_calc.get("net_pnl", gross_pnl)
                total_charges = charges_calc.get("total_charges", 0.0)

                port["cash"] = round(port.get("cash", 0) + margin_ret + net_pnl, 2)

                if net_pnl < 0:
                    self.consecutive_losses += 1
                else:
                    self.consecutive_losses = 0

                alerts.dispatch_push_notification(
                    f"Auto-Trade Closed: {sym} ({reason})",
                    f"Exited {qty} shares @ Rs {exit_p:.2f} | Net P&L: Rs {net_pnl:+,.2f} (Charges: Rs {total_charges:.2f})"
                )

                # Record in shared broker.json trade state
                record_closed_trade(sym, exit_p, net_pnl, now_ist)

                # Persist trade to SQLite Journal
                try:
                    import journal
                    placed_parts = str(h.get("placed_at", "")).split(" ")
                    e_time = placed_parts[1] if len(placed_parts) > 1 else "09:30:00"
                    journal.record_trade({
                        "trade_date": now_ist.strftime("%Y-%m-%d"),
                        "symbol": sym,
                        "side": side,
                        "qty": qty,
                        "strategy_id": h.get("strategy", self.active_strategy),
                        "mode": "PAPER",
                        "source": "AUTO",
                        "entry_time": e_time,
                        "exit_time": now_ist.strftime("%H:%M:%S"),
                        "entry_price": entry_p,
                        "exit_price": exit_p,
                        "initial_stop": h.get("stop", 0.0),
                        "target": h.get("target", 0.0),
                        "exit_reason": reason
                    })
                except Exception as e:
                    self.add_log(f"Journal Write Warning on {sym}: {e}")

            updated_any = True

        # Persist holdings atomically after EVERY management cycle
        if updated_any or to_close:
            port["holdings"] = holdings
            save_json(PORTFOLIO_FILE, port)

        if not holdings and self.state == "IN_POSITION":
            self.state = "SCANNING"

    def _force_squareoff_all(self):
        """Forces all open positions flat at 15:10 IST, fetching fresh live exit quotes."""
        port = load_json(PORTFOLIO_FILE, {})
        holdings = port.get("holdings", {})
        if not holdings:
            return

        now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))

        for sym, raw_h in list(holdings.items()):
            h = normalize_holding(sym, raw_h)
            qty = h.get("qty", 1)
            entry_p = h.get("entry_price", 0.0)
            side = h.get("side", "BUY")

            fresh_p = self._fetch_live_price(sym)
            exit_p = fresh_p if fresh_p > 0 else (h.get("current_price") or entry_p)

            # Deduct statutory charges and slippage
            if side == "BUY":
                charges_calc = tax_calculator.calculate_intraday_charges(buy_price=entry_p, sell_price=exit_p, qty=qty)
            else:
                charges_calc = tax_calculator.calculate_intraday_charges(buy_price=exit_p, sell_price=entry_p, qty=qty)

            net_pnl = charges_calc.get("net_pnl", 0.0)
            margin_ret = h.get("margin_used", 0)

            port["cash"] = round(port.get("cash", 0) + margin_ret + net_pnl, 2)
            self.add_log(f"Square-off: Flattened {sym} MIS position @ Rs {exit_p:.2f}. Net P&L: Rs {net_pnl:+,.2f}")

            # Record closed trade in shared trade state
            record_closed_trade(sym, exit_p, net_pnl, now_ist)

            # Persist to journal
            try:
                import journal
                placed_parts = str(h.get("placed_at", "")).split(" ")
                e_time = placed_parts[1] if len(placed_parts) > 1 else "09:30:00"
                journal.record_trade({
                    "trade_date": now_ist.strftime("%Y-%m-%d"),
                    "symbol": sym,
                    "side": side,
                    "qty": qty,
                    "strategy_id": h.get("strategy", self.active_strategy),
                    "mode": "PAPER",
                    "source": "AUTO",
                    "entry_time": e_time,
                    "exit_time": "15:10:00",
                    "entry_price": entry_p,
                    "exit_price": exit_p,
                    "initial_stop": h.get("stop", 0.0),
                    "target": h.get("target", 0.0),
                    "exit_reason": "SQUARED_OFF_1510"
                })
            except Exception as e:
                self.add_log(f"Journal Write Warning on squareoff {sym}: {e}")

        port["holdings"] = {}
        save_json(PORTFOLIO_FILE, port)


# Global singleton instance
_AUTOTRADER_INSTANCE = None


def get_autotrader():
    global _AUTOTRADER_INSTANCE
    if _AUTOTRADER_INSTANCE is None:
        _AUTOTRADER_INSTANCE = AutoTraderEngine()
    return _AUTOTRADER_INSTANCE


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous Trading Engine CLI")
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--universe", default="nifty50", choices=["nifty50", "fno", "watchlist"])
    parser.add_argument("--strategy", default=None)
    args = parser.parse_args()

    engine = get_autotrader()
    if args.strategy:
        engine.set_strategy(args.strategy)

    if args.action == "start":
        ok, msg = engine.start(args.universe)
        print(f"[{'OK' if ok else 'ERROR'}] {msg}")
    elif args.action == "stop":
        ok, msg = engine.stop()
        print(f"[{'OK' if ok else 'ERROR'}] {msg}")
    elif args.action == "status":
        st = engine.get_status()
        print(json.dumps(st, indent=2))


if __name__ == "__main__":
    main()
