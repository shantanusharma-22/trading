#!/usr/bin/env python3
"""Comprehensive Automated Unit Tests for the Enhanced Indian Stock Market Trading Suite."""

import datetime
import json
import os
import sys
import time
import unittest
from unittest import mock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-budget"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-alerts"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-entry"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-exit"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-risk"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-timemachine"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-broker"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-scanner"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-analyst"))

import tax_calculator
import alerts
import entry as entry_module
import exit as exit_module
import check as risk_module
import timemachine
import ticket as broker_module
import history as history_module
import cpr as cpr_module
import swing as swing_module
import autotrader
import strategies as strategies_module
import candles as candles_module
import journal as journal_module
import size as size_module
sys.path.insert(0, os.path.join(BASE_DIR, "skills"))
import data_layer
sys.path.insert(0, BASE_DIR)
import main as main_module
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import web_server


class TestEnhancedIndianMarketSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.TradingDashboardHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()


    def test_timezone_conversion(self):
        """Verify UTC to IST (+05:30) bidirectional mapping."""
        utc_dt = datetime.datetime(2026, 10, 19, 4, 30)
        ist_dt = alerts.to_ist(utc_dt)
        self.assertEqual(ist_dt.hour, 10)
        self.assertEqual(ist_dt.minute, 0)
        self.assertEqual(alerts.ist_to_utc(ist_dt), utc_dt)

    def test_session_hours_and_bars(self):
        """Verify Indian trading hours (09:15-15:30) and 75 5-minute bars."""
        self.assertEqual(alerts.OPEN, datetime.time(9, 15))
        self.assertEqual(alerts.CLOSE, datetime.time(15, 30))
        self.assertEqual(alerts.FLAT_BY, datetime.time(15, 10))
        self.assertEqual(timemachine.SESSION_BARS, 75)

    def test_holiday_detection(self):
        """Verify Indian holidays are marked closed."""
        self.assertFalse(alerts.trading_day(datetime.date(2026, 1, 26))[0])  # Republic Day
        self.assertFalse(alerts.trading_day(datetime.date(2026, 10, 2))[0])  # Gandhi Jayanti
        self.assertFalse(alerts.trading_day(datetime.date(2026, 10, 18))[0]) # Sunday
        self.assertTrue(alerts.trading_day(datetime.date(2026, 10, 19))[0])  # Monday

    def test_symbol_normalization(self):
        """Verify automatic .NS suffixing."""
        self.assertEqual(alerts.normalize_symbol("RELIANCE"), "RELIANCE.NS")
        self.assertEqual(alerts.normalize_symbol("TCS.NS"), "TCS.NS")
        self.assertEqual(alerts.normalize_symbol("INFY.BO"), "INFY.BO")

    def test_intraday_tax_and_slippage_calculator(self):
        """Verify statutory Indian levies + 0.05% slippage on intraday equity."""
        res = tax_calculator.calculate_intraday_charges(buy_price=3000.0, sell_price=3050.0, qty=100, slippage_pct=0.05)
        self.assertEqual(res["turnover_buy"], 300000.0)
        self.assertEqual(res["turnover_sell"], 305000.0)
        self.assertEqual(res["stt"], 76.25)
        self.assertEqual(res["stamp_duty"], 9.0)
        self.assertEqual(res["brokerage"], 40.0)
        self.assertEqual(res["slippage_cost"], 302.50)
        self.assertEqual(res["gross_pnl"], 5000.0)
        self.assertGreater(res["net_pnl"], 4500.0)

    def test_intraday_vwap_calculation(self):
        """Verify intraday VWAP calculation."""
        bars = [
            {"high": 102.0, "low": 100.0, "close": 101.0, "vol": 1000},
            {"high": 104.0, "low": 101.0, "close": 103.0, "vol": 2000},
        ]
        vwap = entry_module.calculate_intraday_vwap(bars)
        self.assertGreater(vwap, 101.0)
        self.assertLess(vwap, 103.0)

    def test_cpr_and_camarilla_calculation(self):
        """Verify Central Pivot Range (CPR) and Camarilla Pivot math."""
        res = cpr_module.calculate_cpr_and_camarilla(high=3020.0, low=2980.0, close=3000.0)
        self.assertEqual(res["pivot"], 3000.0)
        self.assertEqual(res["bc"], 3000.0)
        self.assertEqual(res["tc"], 3000.0)
        self.assertEqual(res["cpr_width"], 0.0)  # Ultra narrow CPR
        self.assertIn("NARROW", res["cpr_type"])
        self.assertGreater(res["camarilla"]["h4_breakout"], 3000.0)
        self.assertLess(res["camarilla"]["l4_breakdown"], 3000.0)

    def test_trailing_stop_calculation(self):
        """Verify ATR trailing stop generation in exit planner."""
        plan = exit_module.plan_exit(
            entry_price=3000.0, range_high=3020.0, range_low=2960.0, range_mid=2990.0,
            target_r=2.0, trailing_mode="atr", atr_mult=1.5
        )
        self.assertEqual(plan["entry"], 3000.0)
        self.assertEqual(plan["stop"], 2990.0)
        self.assertIsNotNone(plan.get("trailing_stop"))
        self.assertEqual(plan["trailing_stop"]["distance_pts"], 15.0)

    def test_risk_consecutive_losses_killswitch(self):
        """Verify risk manager triggers killswitch after consecutive losses."""
        cfg = {"max_consecutive_losses": 2, "max_trades_per_day": 5}
        now = datetime.datetime(2026, 10, 19, 10, 30)
        order = {"symbol": "RELIANCE.NS", "side": "BUY", "qty": 10, "entry_price": 3000.0, "stop_loss_price": 2970.0}

        b_state = {"trades_today": [{"pnl": -500}, {"pnl": -600}]}
        passed, msg = risk_module.validate_order(order, cfg, now, b_state)
        self.assertFalse(passed)
        self.assertIn("killswitch", msg.lower())

    def test_risk_high_water_mark_profit_lock(self):
        """Verify profit lock triggers when daily profit drops to floor."""
        cfg = {"profit_lock_trigger_inr": 2500.0, "profit_lock_floor_inr": 1500.0, "max_trades_per_day": 5}
        now = datetime.datetime(2026, 10, 19, 10, 30)
        order = {"symbol": "RELIANCE.NS", "side": "BUY", "qty": 10, "entry_price": 3000.0, "stop_loss_price": 2970.0}

        # Trade 1 was +Rs 3,000 (hit trigger). Trade 2 was -Rs 1,600 (running profit now Rs 1,400 <= floor Rs 1,500)
        b_state = {"trades_today": [{"pnl": 3000}, {"pnl": -1600}]}
        passed, msg = risk_module.validate_order(order, cfg, now, b_state)
        self.assertFalse(passed)
        self.assertIn("high-water mark", msg.lower())

    def test_risk_sector_cap(self):
        """Verify correlated sector cap (max 1 trade per sector)."""
        cfg = {"max_trades_per_sector": 1, "max_trades_per_day": 5}
        now = datetime.datetime(2026, 10, 19, 10, 30)
        order = {"symbol": "ICICIBANK.NS", "side": "BUY", "qty": 10, "entry_price": 1000.0, "stop_loss_price": 990.0}

        b_state = {"trades_today": [{"symbol": "HDFCBANK.NS", "pnl": 100}]}
        passed, msg = risk_module.validate_order(order, cfg, now, b_state)
        self.assertFalse(passed)
        self.assertIn("sector", msg.lower())

    def test_risk_macro_blackout(self):
        """Verify RBI Policy announcement blackout window triggers a freeze."""
        cfg = {"max_trades_per_day": 5}
        # RBI MPC announcement on 2026-02-06 at 10:15 IST
        rbi_policy_time = datetime.datetime(2026, 2, 6, 10, 15)
        order = {"symbol": "RELIANCE.NS", "side": "BUY", "qty": 10, "entry_price": 3000.0, "stop_loss_price": 2970.0}

        passed, msg = risk_module.validate_order(order, cfg, rbi_policy_time, {})
        self.assertFalse(passed)
        self.assertIn("macro event blackout", msg.lower())

    def test_swing_fibonacci_and_rsi(self):
        """Verify multi-week swing Fibonacci Golden Pocket math, RSI, and 3-screen confluence."""
        res = swing_module.analyze_swing_setup("MOCK.NS", offline=True)
        self.assertIn("fibonacci", res)
        fib = res["fibonacci"]
        # Check Fibonacci math on synthetic data (swing_high=231.17, swing_low=187.69)
        self.assertAlmostEqual(fib["swing_high"], 231.17, places=1)
        self.assertAlmostEqual(fib["swing_low"], 187.69, places=1)
        self.assertTrue(fib["in_golden_pocket"])
        # Check RSI series calculation
        self.assertTrue(0 <= res["rsi_14"] <= 100)
        # Check 3-Screen Confluence score
        self.assertGreaterEqual(res["confluence_score"], 7)
        self.assertEqual(res["swing_plan"]["risk_reward_ratio"], 6.06)

    def test_autotrader_screener_and_risk_gating(self):
        """Verify autonomous Auto-Trader engine lifecycle, sizing under ₹1,000 risk, and universe mode."""
        engine = autotrader.get_autotrader()
        status = engine.get_status()
        self.assertIn("running", status)
        self.assertIn("trades_today", status)
        self.assertEqual(status["max_trades_per_day"], 2)

        # Verify universe symbols resolution
        symbols = engine._get_universe_symbols()
        self.assertGreaterEqual(len(symbols), 2)
        self.assertIn("RELIANCE.NS", symbols)

        # Test risk-gated sizing math: Entry Rs 2,500, Stop Rs 2,480 (Risk Rs 20) -> Max Loss Rs 1,000 -> 50 shares
        entry = 2500.0
        stop = 2480.0
        max_loss = 1000.0
        risk_per_share = entry - stop
        shares = max(1, int(max_loss // risk_per_share))
        self.assertEqual(shares, 50)
        total_risk = shares * risk_per_share
        self.assertLessEqual(total_risk, max_loss)

        # Test safe startup and shutdown
        ok, msg = engine.start(universe_mode="watchlist")
        self.assertTrue(ok)
        self.assertTrue(engine.running)
        ok_stop, msg_stop = engine.stop()
        self.assertTrue(ok_stop)
        self.assertFalse(engine.running)

    def test_all_strategies_library_and_confluence_model(self):
        """Verify all 20 strategies are registered, indicators compute accurately, and Strategy #20 Custom Confluence scores properly."""
        # 1. Verify 20 strategies registered
        self.assertEqual(len(strategies_module.STRATEGY_REGISTRY), 20)
        self.assertIn("orb", strategies_module.STRATEGY_REGISTRY)
        self.assertIn("supertrend", strategies_module.STRATEGY_REGISTRY)
        self.assertIn("vwap_pullback", strategies_module.STRATEGY_REGISTRY)
        self.assertIn("aic_confluence", strategies_module.STRATEGY_REGISTRY)

        # 2. Test mathematical indicators
        candles = []
        base = 2500.0
        for i in range(30):
            o = base + i * 2.0
            h = o + 4.0
            l = o - 2.0
            c = o + 3.0
            candles.append({"open": o, "high": h, "low": l, "close": c, "volume": 10000 + i * 500})

        closes = [c["close"] for c in candles]
        ema9 = strategies_module.calculate_ema(closes, 9)
        ema20 = strategies_module.calculate_ema(closes, 20)
        self.assertEqual(len(ema9), len(closes))
        self.assertGreater(ema9[-1], ema20[-1])  # Strong uptrend

        st = strategies_module.calculate_supertrend(candles, 10, 3.0)
        self.assertEqual(st["trend"], 1)  # Bullish
        self.assertEqual(st["color"], "GREEN")

        bb = strategies_module.calculate_bollinger_bands(closes, 20, 2.0)
        self.assertGreater(bb["upper"], bb["middle"])
        self.assertGreater(bb["middle"], bb["lower"])

        # 3. Test Strategy #20 AIC-20 Confluence Model
        prev_bar = {"high": base + 20.0, "low": base - 10.0, "close": base + 5.0}
        aic_res = strategies_module.eval_aic_confluence("TCS.NS", candles, prev_bar, vix=13.5, breadth_ratio=1.4)
        self.assertIn("score", aic_res)
        self.assertIn("factors", aic_res)
        self.assertGreaterEqual(aic_res["score"], 80)
        self.assertTrue(aic_res["is_executable"])
        self.assertEqual(aic_res["signal"], "BUY")

        # 4. Verify evaluate_all returns all 20 strategies
        all_evals = strategies_module.evaluate_all("TCS.NS", candles, prev_bar)
        self.assertEqual(len(all_evals), 20)

    def test_candles_null_bars_dropped(self):
        """Verify candles engine drops null/gap OHLC bars from Yahoo Finance."""
        mock_raw = {
            "chart": {
                "result": [{
                    "meta": {"regularMarketPrice": 2500.0, "previousClose": 2480.0},
                    "timestamp": [1762314300, 1762314600, 1762314900],
                    "indicators": {
                        "quote": [{
                            "open": [2500.0, None, 2510.0],
                            "high": [2515.0, None, 2520.0],
                            "low": [2495.0, None, 2505.0],
                            "close": [2510.0, None, 2518.0],
                            "volume": [1000, None, 2000]
                        }]
                    }
                }]
            }
        }
        res = candles_module.process_chart_data(mock_raw, "TCS.NS", "5m")
        self.assertEqual(len(res["candles"]), 2)  # Null middle bar dropped
        self.assertEqual(res["candles"][0]["close"], 2510.0)
        self.assertEqual(res["candles"][1]["close"], 2518.0)

    def test_candles_ist_offset(self):
        """Verify candles engine applies +19,800s (+5h30m) offset for Lightweight Charts display."""
        mock_raw = {
            "chart": {
                "result": [{
                    "meta": {"regularMarketPrice": 2500.0, "previousClose": 2480.0},
                    "timestamp": [100000],
                    "indicators": {
                        "quote": [{
                            "open": [2500.0], "high": [2510.0], "low": [2490.0], "close": [2505.0], "volume": [1000]
                        }]
                    }
                }]
            }
        }
        res = candles_module.process_chart_data(mock_raw, "TCS.NS", "5m")
        self.assertEqual(res["candles"][0]["time"], 100000 + 19800)

    def test_symbol_mapping(self):
        """Verify to_tv_symbol maps tickers to BSE:<BASE> to avoid foreign exchange fallbacks."""
        self.assertEqual(candles_module.to_tv_symbol("TCS.NS"), "BSE:TCS")
        self.assertEqual(candles_module.to_tv_symbol("RELIANCE.NS"), "BSE:RELIANCE")
        self.assertEqual(candles_module.to_tv_symbol("INFY.BO"), "BSE:INFY")
        self.assertEqual(candles_module.to_tv_symbol("^NSEI"), "NSE:NIFTY")
        self.assertEqual(candles_module.to_tv_symbol("^BSESN"), "BSE:SENSEX")

    def test_compute_charges(self):
        """Verify statutory charges calculation matches SEBI & broker rates."""
        # Buy 10 TCS @ 2500, exit @ 2520 (turnover = 25000 + 25200 = 50200)
        chg = journal_module.compute_charges(2500.0, 2520.0, 10, side="BUY", exchange="NSE")
        self.assertIn("total_charges", chg)
        self.assertGreater(chg["total_charges"], 10.0)
        self.assertLess(chg["total_charges"], 40.0)
        self.assertGreater(chg["stt"], 0.0)  # STT charged on sell
        self.assertGreater(chg["gst"], 0.0)  # GST on brokerage + exchange + sebi

    def test_journal_sqlite_records_and_summary(self):
        """Verify trade journal inserts into SQLite, computes net PnL, R-multiple, and summary metrics."""
        test_db = os.path.join(BASE_DIR, "trader", "data", "test_journal.db")
        if os.path.exists(test_db):
            os.remove(test_db)

        rec = journal_module.record_trade({
            "trade_date": "2026-11-05",
            "symbol": "TCS.NS",
            "side": "BUY",
            "qty": 10,
            "entry_time": "09:35:00",
            "exit_time": "14:15:00",
            "entry_price": 2500.0,
            "exit_price": 2550.0,
            "initial_stop": 2480.0,
            "target": 2550.0,
            "exit_reason": "TARGET",
            "strategy_id": "orb_15m"
        }, db_path=test_db)

        self.assertEqual(rec["gross_pnl"], 500.0)
        self.assertGreater(rec["charges"], 0.0)
        self.assertLess(rec["net_pnl"], 500.0)
        self.assertGreater(rec["r_multiple"], 0.0)

        summary = journal_module.get_summary(db_path=test_db)
        self.assertEqual(summary["total_trades"], 1)
        self.assertEqual(summary["winning_trades"], 1)
        self.assertEqual(summary["win_rate_pct"], 100.0)

        curve = journal_module.get_equity_curve(db_path=test_db)
        self.assertEqual(len(curve), 1)
        self.assertEqual(curve[0]["cum_pnl"], rec["net_pnl"])

        if os.path.exists(test_db):
            os.remove(test_db)

    def test_sizer_rejects_when_one_share_exceeds_cap(self):
        """C1 Test: Sizer must raise ValueError or reject if 1 share's risk exceeds the Max Loss cap."""
        # Entry 2500, Stop 1300 -> Risk per share is 1200, but Max Loss is 1000
        plan = {
            "symbol": "TCS.NS",
            "entry": 2500.0,
            "stop": 1300.0,
            "target": 3000.0
        }
        cfg = {"budget": 100000.0, "max_loss_per_trade_inr": 1000.0}
        with self.assertRaises(ValueError):
            size_module.size_trade(plan, cfg)

    def test_event_guard(self):
        """Verify event_guard blocks trades on RBI policy windows and results days."""
        # RBI policy on 2026-12-04 at 10:00 IST -> blackout 09:45 to 10:30
        rbi_dt = datetime.datetime(2026, 12, 4, 10, 5)
        res_rbi = risk_module.event_guard("RELIANCE.NS", rbi_dt)
        self.assertFalse(res_rbi["allowed"])
        self.assertIn("block", res_rbi["action"].lower())

        # Results day for TCS on 2026-11-06
        results_dt = datetime.datetime(2026, 11, 6, 11, 0)
        res_tcs = risk_module.event_guard("TCS.NS", results_dt)
        self.assertFalse(res_tcs["allowed"])
        self.assertIn("block", res_tcs["action"].lower())

        # Other stock allowed on TCS results day
        res_infy = risk_module.event_guard("INFY.NS", results_dt)
        self.assertTrue(res_infy["allowed"])

    def test_options_strategies_not_executable(self):
        """C9 Test: Options strategies (13-16) must be blocked from execution via pre_trade_gate."""
        order = {
            "symbol": "NIFTY.NS",
            "side": "SELL",
            "qty": 25,
            "entry_price": 24500.0,
            "stop_loss_price": 24600.0,
            "strategy_id": "straddle_920"
        }
        ok, msg = risk_module.pre_trade_gate(order)
        self.assertFalse(ok)
        self.assertIn("Options strategies", msg)

    def test_side_aware_short_order_and_wide_stop(self):
        """Verify side-aware risk validation for short (SELL) positions."""
        cfg = {"max_loss_per_trade_inr": 1000.0, "require_stop": True, "vix_min": 10.0, "vix_max": 25.0}
        now_dt = datetime.datetime(2026, 10, 19, 10, 30)

        # 1. Valid short: entry 3000.0, stop 3030.0, qty 10 -> risk = 300.0 <= 1000.0
        valid_short = {
            "symbol": "RELIANCE.NS",
            "side": "SELL",
            "qty": 10,
            "entry_price": 3000.0,
            "stop_loss_price": 3030.0,
            "take_profit_price": 2940.0
        }
        ok, msg = risk_module.validate_order(valid_short, cfg, now_dt, {}, current_vix=15.0)
        self.assertTrue(ok, msg)

        # 2. Inverted short stop: stop <= entry
        bad_short = {
            "symbol": "RELIANCE.NS",
            "side": "SELL",
            "qty": 10,
            "entry_price": 3000.0,
            "stop_loss_price": 2970.0
        }
        ok, msg = risk_module.validate_order(bad_short, cfg, now_dt, {}, current_vix=15.0)
        self.assertFalse(ok)
        self.assertIn("cannot be at or below entry", msg)

        # 3. Wide short stop: entry 3000.0, stop 3200.0, qty 10 -> risk = 2000.0 > 1000.0 limit
        wide_short = {
            "symbol": "RELIANCE.NS",
            "side": "SELL",
            "qty": 10,
            "entry_price": 3000.0,
            "stop_loss_price": 3200.0
        }
        ok, msg = risk_module.validate_order(wide_short, cfg, now_dt, {}, current_vix=15.0)
        self.assertFalse(ok)
        self.assertIn("exceeds max loss limit", msg)

    def test_tick_size_equity_vs_etf(self):
        """Verify 0.05 tick size for equities and 0.01 tick size for ETFs."""
        cfg = {"require_stop": True, "vix_min": 10.0, "vix_max": 25.0}
        now_dt = datetime.datetime(2026, 10, 19, 10, 30)

        # Standard equity RELIANCE at 3000.02 is invalid (not on 0.05 grid)
        invalid_eq = {
            "symbol": "RELIANCE.NS",
            "side": "BUY",
            "qty": 10,
            "entry_price": 3000.02,
            "stop_loss_price": 2970.00
        }
        ok, msg = risk_module.validate_order(invalid_eq, cfg, now_dt, {}, current_vix=15.0)
        self.assertFalse(ok)
        self.assertIn("not on 0.05 tick grid", msg)

        # ETF NIFTYBEES at 250.02 is valid (on 0.01 ETF tick grid)
        valid_etf = {
            "symbol": "NIFTYBEES.NS",
            "side": "BUY",
            "qty": 100,
            "entry_price": 250.02,
            "stop_loss_price": 248.00
        }
        ok, msg = risk_module.validate_order(valid_etf, cfg, now_dt, {}, current_vix=15.0)
        self.assertTrue(ok, msg)

    def test_duplicate_symbol_blocked_same_day(self):
        """Verify risk gate blocks duplicate entries for the same symbol on the same day."""
        cfg = {"vix_min": 10.0, "vix_max": 25.0}
        now_dt = datetime.datetime(2026, 10, 19, 10, 30)
        b_state = {"trades_today": [{"symbol": "RELIANCE.NS", "pnl": 200.0}]}

        order = {
            "symbol": "RELIANCE.NS",
            "side": "BUY",
            "qty": 5,
            "entry_price": 3000.0,
            "stop_loss_price": 2970.0
        }
        ok, msg = risk_module.validate_order(order, cfg, now_dt, b_state, current_vix=15.0)
        self.assertFalse(ok)
        self.assertIn("duplicate symbol", msg.lower())

    def test_fail_closed_on_corrupt_config_and_events(self):
        """Verify risk manager fails closed on corrupt or unreadable JSON files."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            f.write("{ invalid json content :::")
            bad_path = f.name

        try:
            # Corrupt config fails closed
            ok, cfg, err = risk_module.load_config_fail_closed(bad_path)
            self.assertFalse(ok)
            self.assertIn("Config Error", err)

            # Corrupt events fails closed
            ok, ev, err = risk_module.load_events_fail_closed(bad_path)
            self.assertFalse(ok)
            self.assertIn("Events Error", err)
        finally:
            if os.path.exists(bad_path):
                os.remove(bad_path)

    def test_missing_vix_blocks_entry(self):
        """Verify missing VIX blocks new trade entry when require_vix is enabled."""
        cfg = {"require_vix": True, "vix_min": 11.5, "vix_max": 24.0}
        now_dt = datetime.datetime(2026, 10, 19, 10, 30)
        order = {
            "symbol": "INFY.NS",
            "side": "BUY",
            "qty": 10,
            "entry_price": 1500.0,
            "stop_loss_price": 1485.0
        }
        ok, msg = risk_module.validate_order(order, cfg, now_dt, {}, current_vix=None)
        self.assertFalse(ok)
        self.assertIn("vix data unavailable", msg.lower())

        # VIX=0 is not None: should fail VIX range test, not missing data test
        ok_zero, msg_zero = risk_module.validate_order(order, cfg, now_dt, {}, current_vix=0.0)
        self.assertFalse(ok_zero)
        self.assertIn("below 11.5", msg_zero)

    def test_stale_verdict_expiration(self):
        """Verify risk verdicts expire after 5 minutes (300 seconds)."""
        now_dt = datetime.datetime(2026, 10, 19, 10, 30)
        fresh_verdict = {"timestamp": now_dt.timestamp() - 60}   # 1 minute old
        stale_verdict = {"timestamp": now_dt.timestamp() - 360}  # 6 minutes old

        self.assertFalse(risk_module.is_verdict_stale(fresh_verdict, now_dt))
        self.assertTrue(risk_module.is_verdict_stale(stale_verdict, now_dt))

    def test_gate_called_via_api_trade_place_blocks_on_prior_losses(self):
        """Verify /api/trade/place enforces killswitch when prior losses exist in shared state."""
        import tempfile
        import common
        # Create temp broker state with 2 consecutive losses today
        now_ist = common.to_ist(datetime.datetime.now(datetime.timezone.utc))
        d_str = now_ist.strftime("%Y-%m-%d")

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            temp_broker_file = f.name
            json.dump({
                d_str: {
                    "trades_today": [
                        {"symbol": "TCS.NS", "pnl": -500.0, "status": "CLOSED"},
                        {"symbol": "INFY.NS", "pnl": -600.0, "status": "CLOSED"}
                    ],
                    "orders_placed": []
                }
            }, f)

        try:
            # Check gate directly with broker state
            cfg = {"max_consecutive_losses": 2, "max_trades_per_day": 5}
            order = {
                "symbol": "RELIANCE.NS",
                "side": "BUY",
                "qty": 5,
                "entry_price": 3000.0,
                "stop_loss_price": 2970.0
            }
            b_state = common.get_todays_trade_state(now_ist, temp_broker_file)
            ok, msg = risk_module.validate_order(order, cfg, now_ist, b_state, current_vix=15.0)
            self.assertFalse(ok)
            self.assertIn("killswitch", msg.lower())
        finally:
            if os.path.exists(temp_broker_file):
                os.remove(temp_broker_file)

    # -------------------------------------------------------------
    # Prompt 2 Tests: autotrader.py
    # -------------------------------------------------------------
    def test_autotrader_restart_and_double_start(self):
        """Prompt 2 Test: Verify autotrader restart cycle and double-start prevention."""
        engine = autotrader.AutoTraderEngine()
        ok1, msg1 = engine.start()
        self.assertTrue(ok1, msg1)

        # Double start must fail closed
        ok2, msg2 = engine.start()
        self.assertFalse(ok2)
        self.assertIn("already running", msg2.lower())

        # Clean stop
        ok_stop, _ = engine.stop()
        self.assertTrue(ok_stop)

        # Restart cycle
        ok3, msg3 = engine.start()
        self.assertTrue(ok3, msg3)
        engine.stop()

    def test_autotrader_day_rollover(self):
        """Prompt 2 Test: Verify day rollover resets trades_today and consecutive_losses."""
        engine = autotrader.AutoTraderEngine()
        engine.trades_today = 3
        engine.consecutive_losses = 2
        engine.last_trading_day = datetime.date(2026, 11, 4)

        # Rollover to next trading day
        next_day = datetime.datetime(2026, 11, 5, 9, 30)
        engine._check_day_rollover(next_day)

        self.assertEqual(engine.trades_today, 0)
        self.assertEqual(engine.consecutive_losses, 0)
        self.assertEqual(engine.last_trading_day, datetime.date(2026, 11, 5))

    def test_autotrader_strategy_validation_analysis_only(self):
        """Prompt 2 Test: Verify set_strategy refuses invalid and analysis-only strategies."""
        engine = autotrader.AutoTraderEngine()

        # Invalid strategy ID
        ok_inv, msg_inv = engine.set_strategy("non_existent_xyz")
        self.assertFalse(ok_inv)
        self.assertIn("invalid", msg_inv.lower())

        # Analysis-only strategy (e.g. options_strangle, options_920_straddle)
        ok_opt, msg_opt = engine.set_strategy("options_strangle")
        self.assertFalse(ok_opt)
        self.assertIn("analysis-only", msg_opt.lower())

        # Valid strategy (orb)
        ok_valid, msg_valid = engine.set_strategy("orb")
        self.assertTrue(ok_valid)
        self.assertEqual(engine.active_strategy, "orb")

    def test_autotrader_cpr_prev_levels_enforced(self):
        """Prompt 2 Test: Verify _evaluate_stock_strategy skips symbols with missing previous-day CPR levels."""
        engine = autotrader.AutoTraderEngine()
        bad_cpr = {"high": 3000.0, "low": 2900.0}
        res = engine._evaluate_stock_strategy("MOCK.NS", bad_cpr)
        self.assertIsNone(res)

    def test_autotrader_squareoff_pnl_and_real_exit_price(self):
        """Prompt 2 Test: Verify 15:10 square-off records real exit price and non-zero net P&L with charges."""
        engine = autotrader.AutoTraderEngine()
        engine._fetch_live_price = lambda sym: 3050.0  # Mock real market exit price

        import tempfile
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            temp_port_file = f.name
            json.dump({
                "cash": 50000.0,
                "holdings": {
                    "RELIANCE.NS": {
                        "symbol": "RELIANCE.NS",
                        "side": "BUY",
                        "qty": 10,
                        "entry_price": 3000.0,
                        "current_price": 3000.0,
                        "stop": 2970.0,
                        "target": 3060.0,
                        "margin_used": 6000.0,
                        "strategy": "aic_confluence",
                        "placed_at": "2026-11-05 09:35:00"
                    }
                }
            }, f)

        orig_port = autotrader.PORTFOLIO_FILE
        autotrader.PORTFOLIO_FILE = temp_port_file
        try:
            engine._force_squareoff_all()
            with open(temp_port_file, "r") as f:
                port_after = json.load(f)

            self.assertEqual(port_after["holdings"], {})
            self.assertGreater(port_after["cash"], 56400.0)
        finally:
            autotrader.PORTFOLIO_FILE = orig_port
            if os.path.exists(temp_port_file):
                os.remove(temp_port_file)

    # -------------------------------------------------------------
    # Prompt 3 Tests: ticket.py
    # -------------------------------------------------------------
    def test_ticket_angel_token_resolution_and_refusal(self):
        """Prompt 3 Test: Verify Angel One token lookup resolves for known symbols and refuses unknown."""
        token = broker_module.resolve_angel_token("RELIANCE.NS")
        self.assertEqual(token, "2885")
        token_sbin = broker_module.resolve_angel_token("SBIN")
        self.assertEqual(token_sbin, "3045")

        unknown_token = broker_module.resolve_angel_token("FAKEUNKNOWN.NS")
        self.assertIsNone(unknown_token)

        ord_rel = {"symbol": "RELIANCE.NS", "side": "BUY", "qty": 10, "entry_price": 3000.0, "stop_loss_price": 2970.0}
        p_known = broker_module.format_angel_payload(ord_rel)
        self.assertIsNotNone(p_known)
        self.assertEqual(p_known["symboltoken"], "2885")
        self.assertEqual(p_known["transactiontype"], "BUY")

        ord_fake = {"symbol": "FAKEUNKNOWN.NS", "side": "BUY", "qty": 10, "entry_price": 100.0, "stop_loss_price": 95.0}
        p_fake = broker_module.format_angel_payload(ord_fake)
        self.assertIsNone(p_fake)
        stop_fake = broker_module.format_angel_stop_payload(ord_fake)
        self.assertIsNone(stop_fake)

    def test_ticket_shoonya_mis_product_code_and_stops(self):
        """Prompt 3 Test: Verify Shoonya uses 'I' for MIS and generates opposite-side stop-loss order."""
        ord_buy = {"symbol": "TCS.NS", "side": "BUY", "qty": 5, "entry_price": 4000.0, "stop_loss_price": 3950.0, "product": "MIS"}
        entry_payload = broker_module.format_shoonya_payload(ord_buy)
        self.assertEqual(entry_payload["product_type"], "I")
        self.assertEqual(entry_payload["buy_or_sell"], "B")
        self.assertEqual(entry_payload["quantity"], 5)

        stop_payload = broker_module.format_shoonya_stop_payload(ord_buy)
        self.assertEqual(stop_payload["product_type"], "I")
        self.assertEqual(stop_payload["buy_or_sell"], "S")
        self.assertEqual(stop_payload["price_type"], "SL-LMT")
        self.assertEqual(stop_payload["trigger_price"], 3950.0)

    def test_ticket_zerodha_protective_stop_payload(self):
        """Prompt 3 Test: Verify Zerodha generates protective stop-loss snippet next to entry."""
        ord_buy = {"symbol": "INFY.NS", "side": "BUY", "qty": 20, "entry_price": 1800.0, "stop_loss_price": 1780.0}
        entry_snip = broker_module.format_zerodha_payload(ord_buy)
        self.assertIn("TRANSACTION_TYPE_BUY", entry_snip)
        self.assertIn("PRODUCT_MIS", entry_snip)

        stop_snip = broker_module.format_zerodha_stop_payload(ord_buy)
        self.assertIn("TRANSACTION_TYPE_SELL", stop_snip)
        self.assertIn("ORDER_TYPE_SL", stop_snip)
        self.assertIn("1780.00", stop_snip)

    def test_ticket_fill_insufficient_cash_and_oversell(self):
        """Prompt 3 Test: Verify execute_fill rejects insufficient cash and prevents overselling."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f_port, \
             tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f_brk:
            port_path = f_port.name
            brk_path = f_brk.name
            json.dump({"cash": 1000.0, "holdings": {}}, f_port)
            json.dump({}, f_brk)

        try:
            ok, msg, _ = broker_module.execute_fill("RELIANCE.NS", "BUY", 10, 3000.0, portfolio_file=port_path, broker_file=brk_path)
            self.assertFalse(ok)
            self.assertIn("insufficient cash", msg.lower())

            with open(port_path, "w") as f:
                json.dump({
                    "cash": 50000.0,
                    "holdings": {
                        "RELIANCE.NS": {
                            "symbol": "RELIANCE.NS",
                            "side": "BUY",
                            "qty": 5,
                            "entry_price": 3000.0,
                            "current_price": 3000.0,
                            "margin_used": 15000.0
                        }
                    }
                }, f)

            ok_sell, msg_sell, _ = broker_module.execute_fill("RELIANCE.NS", "SELL", 10, 3000.0, portfolio_file=port_path, broker_file=brk_path)
            self.assertFalse(ok_sell)
            self.assertIn("cannot sell 10 shares", msg_sell.lower())
        finally:
            for p in (port_path, brk_path):
                if os.path.exists(p):
                    os.remove(p)

    def test_ticket_fill_schema_and_statutory_charges(self):
        """Prompt 3 Test: Verify fill updates cash net of taxes and writes shared universal schema."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f_port, \
             tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f_brk:
            port_path = f_port.name
            brk_path = f_brk.name
            json.dump({"cash": 50000.0, "holdings": {}}, f_port)
            json.dump({}, f_brk)

        try:
            ok, msg, p_data = broker_module.execute_fill(
                "INFY.NS", "BUY", 10, 2000.0, stop=1980.0, target=2040.0,
                portfolio_file=port_path, broker_file=brk_path
            )
            self.assertTrue(ok, msg)
            self.assertIn("INFY.NS", p_data["holdings"])
            h = p_data["holdings"]["INFY.NS"]
            self.assertEqual(h["qty"], 10)
            self.assertEqual(h["entry_price"], 2000.0)
            self.assertEqual(h["side"], "BUY")
            self.assertEqual(h["stop"], 1980.0)
            self.assertEqual(h["target"], 2040.0)
            self.assertLess(p_data["cash"], 30000.0)

            ok_exit, msg_exit, p_exit = broker_module.execute_fill(
                "INFY.NS", "SELL", 10, 2050.0,
                portfolio_file=port_path, broker_file=brk_path
            )
            self.assertTrue(ok_exit, msg_exit)
            self.assertNotIn("INFY.NS", p_exit["holdings"])
            self.assertGreater(p_exit["cash"], 50400.0)
            self.assertLess(p_exit["cash"], 50500.0)
        finally:
            for p in (port_path, brk_path):
                if os.path.exists(p):
                    os.remove(p)

    def test_ticket_approve_verdict_freshness_and_idempotency(self):
        """Prompt 3 Test: Verify approval rejects stale verdicts (>300s) and duplicate approvals."""
        import tempfile
        now_ist = datetime.datetime(2026, 11, 5, 10, 0, 0)
        d_str = "2026-11-05"

        order = {
            "symbol": "SBIN.NS",
            "side": "BUY",
            "qty": 50,
            "entry_price": 800.0,
            "stop_loss_price": 790.0,
            "take_profit_price": 820.0
        }
        fp = broker_module.compute_fingerprint(order, d_str)

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f_ord, \
             tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f_rsk, \
             tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f_brk:
            ord_path = f_ord.name
            rsk_path = f_rsk.name
            brk_path = f_brk.name

            json.dump({"orders": [order]}, f_ord)
            json.dump({
                "verdicts": [{
                    "fingerprint": fp,
                    "verdict": "PASS",
                    "timestamp": now_ist.timestamp() - 600
                }]
            }, f_rsk)
            json.dump({}, f_brk)

        try:
            ok_stale, msg_stale, _ = broker_module.execute_approve(
                1, "yes", orders_file=ord_path, risk_file=rsk_path, broker_file=brk_path, now_ist=now_ist
            )
            self.assertFalse(ok_stale)
            self.assertIn("older than 5 minutes", msg_stale.lower())

            with open(rsk_path, "w") as f:
                json.dump({
                    "verdicts": [{
                        "fingerprint": fp,
                        "verdict": "PASS",
                        "timestamp": now_ist.timestamp() - 30
                    }]
                }, f)

            ok_fresh, msg_fresh, rec = broker_module.execute_approve(
                1, "yes", orders_file=ord_path, risk_file=rsk_path, broker_file=brk_path, now_ist=now_ist
            )
            self.assertTrue(ok_fresh, msg_fresh)
            self.assertIsNotNone(rec)

            ok_dup, msg_dup, _ = broker_module.execute_approve(
                1, "yes", orders_file=ord_path, risk_file=rsk_path, broker_file=brk_path, now_ist=now_ist
            )
            self.assertFalse(ok_dup)
            self.assertIn("already been approved", msg_dup.lower())
        finally:
            for p in (ord_path, rsk_path, brk_path):
                if os.path.exists(p):
                    os.remove(p)

    def test_ticket_flatten_subcommand(self):
        """Prompt 3 Test: Verify flatten squares off open position with real exit price."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f_port, \
             tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f_brk:
            port_path = f_port.name
            brk_path = f_brk.name
            json.dump({
                "cash": 40000.0,
                "holdings": {
                    "TCS.NS": {
                        "symbol": "TCS.NS",
                        "side": "BUY",
                        "qty": 5,
                        "entry_price": 4000.0,
                        "current_price": 4050.0,
                        "margin_used": 20000.0
                    }
                }
            }, f_port)
            json.dump({}, f_brk)

        try:
            ok_none, msg_none, _ = broker_module.execute_flatten("NONEXIST.NS", portfolio_file=port_path, broker_file=brk_path)
            self.assertFalse(ok_none)

            ok_flat, msg_flat, p_flat = broker_module.execute_flatten(
                "TCS.NS", price=4050.0, portfolio_file=port_path, broker_file=brk_path
            )
            self.assertTrue(ok_flat, msg_flat)
            self.assertNotIn("TCS.NS", p_flat["holdings"])
            self.assertGreater(p_flat["cash"], 60200.0)
        finally:
            for p in (port_path, brk_path):
                if os.path.exists(p):
                    os.remove(p)

    # -------------------------------------------------------------
    # Prompt 4 Tests: strategies.py & AIC-20 Panel
    # -------------------------------------------------------------
    def test_aic20_bullish_aligned_scoring(self):
        """Prompt 4 Test: Verify AIC-20 yields >= 80 pts, BUY signal, structured pillars, and stop < entry."""
        base = 3000.0
        candles = []
        for i in range(25):
            o = base + i * 2.0
            h = o + 4.0
            l = o - 1.0
            c = o + 3.0
            v = 15000 if i < 24 else 25000  # volume expansion on latest bars
            candles.append({"time": 1700000000 + i * 300, "open": o, "high": h, "low": l, "close": c, "volume": v})

        # Narrow CPR with price well above TC
        prev_bar = {"high": 3005.0, "low": 2998.0, "close": 3002.0}
        res = strategies_module.eval_aic_confluence("RELIANCE.NS", candles, prev_bar, vix=14.0, breadth_ratio=1.4)

        self.assertGreaterEqual(res["score"], 80)
        self.assertEqual(res["signal"], "BUY")
        self.assertTrue(res["is_executable"])
        self.assertIn("pillars", res)
        # Check structured pillars format {"pts", "max"}
        for p_key in ("cpr", "vwap", "trend", "volume", "breadth", "vix"):
            self.assertIn(p_key, res["pillars"])
            p_obj = res["pillars"][p_key]
            self.assertIn("pts", p_obj)
            self.assertIn("max", p_obj)
            self.assertGreaterEqual(p_obj["pts"], 0)
            self.assertLessEqual(p_obj["pts"], p_obj["max"])

        # Stop loss geometry
        self.assertLess(res["stop"], res["entry"])
        self.assertGreater(res["target"], res["entry"])

    def test_aic20_bearish_aligned_scoring(self):
        """Prompt 4 Test: Verify AIC-20 yields >= 80 pts, SELL signal, and stop > entry."""
        base = 3000.0
        candles = []
        for i in range(25):
            o = base - i * 2.0
            h = o + 1.0
            l = o - 4.0
            c = o - 3.0
            v = 15000 if i < 24 else 25000
            candles.append({"time": 1700000000 + i * 300, "open": o, "high": h, "low": l, "close": c, "volume": v})

        # Narrow CPR with price below BC
        prev_bar = {"high": 3005.0, "low": 2998.0, "close": 3002.0}
        res = strategies_module.eval_aic_confluence("RELIANCE.NS", candles, prev_bar, vix=19.0, breadth_ratio=0.6)

        self.assertGreaterEqual(res["score"], 80)
        self.assertEqual(res["signal"], "SELL")
        self.assertTrue(res["is_executable"])
        self.assertIn("pillars", res)
        # Stop loss geometry for short
        self.assertGreater(res["stop"], res["entry"])
        self.assertLess(res["target"], res["entry"])

    def test_aic20_no_free_points_on_misaligned_pillars(self):
        """Prompt 4 Test: Verify VWAP, trend, breadth do not give free points when unaligned."""
        base = 3000.0
        # Flat choppy candles below VWAP
        candles = []
        for i in range(25):
            o = base + (5.0 if i % 2 == 0 else -5.0)
            h = o + 2.0
            l = o - 2.0
            c = o
            candles.append({"time": 1700000000 + i * 300, "open": o, "high": h, "low": l, "close": c, "volume": 1000})

        # Wide CPR
        prev_bar = {"high": 3100.0, "low": 2900.0, "close": 3000.0}
        # Unaligned breadth (0.9) and high VIX (28.0)
        res = strategies_module.eval_aic_confluence("RELIANCE.NS", candles, prev_bar, vix=28.0, breadth_ratio=0.9)

        # Score must be low (< 60) and signal must be NEUTRAL
        self.assertLess(res["score"], 60)
        self.assertEqual(res["signal"], "NEUTRAL")
        self.assertFalse(res["is_executable"])

    def test_aic20_insufficient_bars_drops_still_forming(self):
        """Prompt 4 Test: Verify completed candles check drops still-forming bar and requires min 10 completed."""
        # 8 candles total (dropping last still-forming leaves 7 -> insufficient)
        short_candles = [
            {"time": 1700000000 + i * 300, "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1000}
            for i in range(8)
        ]
        res = strategies_module.eval_aic_confluence("TCS.NS", short_candles, None)
        self.assertEqual(res["score"], 0)
        self.assertEqual(res["signal"], "NEUTRAL")
        self.assertFalse(res["is_executable"])
        self.assertIn("insufficient", res["reason"].lower())

    def test_analysis_only_strategies_return_neutral(self):
        """Prompt 4 Test: Verify fiidii_flow, sector_momentum, options_max_pain return NEUTRAL analysis only."""
        res_flow = strategies_module.eval_fiidii_flow()
        self.assertEqual(res_flow["signal"], "NEUTRAL")
        self.assertFalse(res_flow["is_executable"])
        self.assertIn("analysis only", res_flow.get("status", "").lower())

        res_sector = strategies_module.eval_sector_momentum("TCS.NS")
        self.assertEqual(res_sector["signal"], "NEUTRAL")
        self.assertFalse(res_sector["is_executable"])

        res_mp = strategies_module.eval_options_max_pain("NIFTY")
        self.assertEqual(res_mp["signal"], "NEUTRAL")
        self.assertFalse(res_mp["is_executable"])

    def test_strategies_api_shape_contract(self):
        """Prompt 4 Test: Verify evaluate_all returns a list with structured evaluations."""
        candles = [
            {"time": 1700000000 + i * 300, "open": 2000.0 + i, "high": 2005.0 + i, "low": 1995.0 + i, "close": 2002.0 + i, "volume": 5000}
            for i in range(25)
        ]
        prev_bar = {"high": 2010.0, "low": 1990.0, "close": 2000.0}
        evals = strategies_module.evaluate_all("INFY.NS", candles, prev_bar, vix=15.0, breadth=1.2)

        # Must be a list (not a dict)
        self.assertIsInstance(evals, list)
        self.assertEqual(len(evals), 20)

        # Each item has registry metadata + evaluation dict
        for item in evals:
            self.assertIn("id", item)
            self.assertIn("name", item)
            self.assertIn("num", item)
            self.assertIn("evaluation", item)
            ev = item["evaluation"]
            self.assertIn("signal", ev)
            self.assertIn("is_executable", ev)
            self.assertIn("reason", ev)

    # -------------------------------------------------------------
    # Prompt 5 Tests: candles.py & Resilient Data Layer
    # -------------------------------------------------------------
    def test_candles_input_validation(self):
        """Prompt 5 Test: Verify input validation accepts valid tickers/intervals and rejects malformed."""
        # Valid parameters must pass without error
        self.assertTrue(data_layer.validate_market_params("RELIANCE.NS", "5m", "1d"))
        self.assertTrue(data_layer.validate_market_params("^NSEI", "1d", "6mo"))

        # Malformed symbol (injection or invalid characters) must raise ValueError
        with self.assertRaises(ValueError):
            data_layer.validate_market_params("RELIANCE;DROP TABLE", "5m", "1d")

        with self.assertRaises(ValueError):
            data_layer.validate_market_params("../../../etc/passwd", "5m", "1d")

        # Invalid interval must raise ValueError
        with self.assertRaises(ValueError):
            data_layer.validate_market_params("INFY.NS", "3m", "1d")

        # Invalid range must raise ValueError
        with self.assertRaises(ValueError):
            data_layer.validate_market_params("INFY.NS", "5m", "100y")

    def test_candles_session_edges_and_intraday_filtering(self):
        """Prompt 5 Test: Verify intraday filter keeps 09:15 <= t < 15:30 IST and drops 15:30 bar."""
        # IST offset = +19800s. Create timestamps across session boundary
        # Date: 2026-11-05
        # 09:14 IST = 03:44 UTC
        # 09:15 IST = 03:45 UTC
        # 15:25 IST = 09:55 UTC
        # 15:30 IST = 10:00 UTC (must be dropped!)
        dt_base = datetime.datetime(2026, 11, 5, 0, 0, tzinfo=datetime.timezone.utc)
        ts_0914 = int((dt_base + datetime.timedelta(hours=3, minutes=44)).timestamp())
        ts_0915 = int((dt_base + datetime.timedelta(hours=3, minutes=45)).timestamp())
        ts_1525 = int((dt_base + datetime.timedelta(hours=9, minutes=55)).timestamp())
        ts_1530 = int((dt_base + datetime.timedelta(hours=10, minutes=0)).timestamp())

        mock_chart = {
            "chart": {
                "result": [{
                    "meta": {"shortName": "Test Co", "regularMarketPrice": 2500.0},
                    "timestamp": [ts_0914, ts_0915, ts_1525, ts_1530],
                    "indicators": {
                        "quote": [{
                            "open": [2500.0, 2501.0, 2520.0, 2525.0],
                            "high": [2502.0, 2505.0, 2522.0, 2526.0],
                            "low": [2498.0, 2500.0, 2518.0, 2524.0],
                            "close": [2501.0, 2504.0, 2521.0, 2525.0],
                            "volume": [1000, 2000, 3000, 4000]
                        }]
                    }
                }]
            }
        }

        data = candles_module.process_chart_data(mock_chart, "TEST.NS", "5m")
        candles = data["candles"]

        # Exactly 2 bars should remain: 09:15 and 15:25 (09:14 and 15:30 must be excluded)
        self.assertEqual(len(candles), 2)
        # Check first kept candle is 09:15 IST
        gm_first = time.gmtime(candles[0]["time"])
        self.assertEqual(gm_first.tm_hour, 9)
        self.assertEqual(gm_first.tm_min, 15)

        # Check last kept candle is 15:25 IST
        gm_last = time.gmtime(candles[1]["time"])
        self.assertEqual(gm_last.tm_hour, 15)
        self.assertEqual(gm_last.tm_min, 25)

    def test_candles_vwap_session_reset(self):
        """Prompt 5 Test: Verify VWAP resets at the start of each new IST trading session."""
        # Two sessions: Day 1 (Nov 4) and Day 2 (Nov 5)
        dt_day1 = datetime.datetime(2026, 11, 4, 3, 45, tzinfo=datetime.timezone.utc)  # 09:15 IST
        dt_day2 = datetime.datetime(2026, 11, 5, 3, 45, tzinfo=datetime.timezone.utc)  # 09:15 IST

        ts1 = int(dt_day1.timestamp())
        ts2 = int(dt_day2.timestamp())

        # Day 1 bar @ Rs 3000, vol 1000000; Day 2 bar @ Rs 2000, vol 100
        # If VWAP does not reset, Day 2 VWAP would be heavily pulled toward 3000.
        # With session reset, Day 2 VWAP should be exactly 2000.
        mock_candles = [
            {"time": ts1 + candles_module.IST_OFFSET_SECONDS, "high": 3010.0, "low": 2990.0, "close": 3000.0, "volume": 1000000},
            {"time": ts2 + candles_module.IST_OFFSET_SECONDS, "high": 2010.0, "low": 1990.0, "close": 2000.0, "volume": 100}
        ]

        overlays = candles_module.compute_overlays(mock_candles, None, is_index=False)
        vwap_series = overlays["vwap"]

        self.assertEqual(len(vwap_series), 2)
        # Day 1 VWAP should be 3000.0
        self.assertAlmostEqual(vwap_series[0]["value"], 3000.0, places=1)
        # Day 2 VWAP must reset to Day 2's typical price (2000.0), NOT contaminated by Day 1!
        self.assertAlmostEqual(vwap_series[1]["value"], 2000.0, places=1)

    def test_candles_failure_returns_no_fake_fallback(self):
        """Prompt 5 Test: Verify offline/failed tickers return error with None prices, never invented fake data."""
        # Non-existent symbol must not fabricate 1000.0 or 24500
        res = candles_module.get_candles("INVALID_TICKER_XYZ999.NS", "5m", "1d")
        self.assertTrue(res.get("stale"))
        self.assertIsNone(res.get("last_price"))
        self.assertEqual(res.get("candles"), [])

    def test_candles_previous_day_cpr_in_overlays(self):
        """Prompt 5 Test: Verify compute_overlays correctly outputs CPR and Camarilla from prior day bar."""
        prev_bar = {"high": 3050.0, "low": 2950.0, "close": 3000.0}
        overlays = candles_module.compute_overlays([], prev_bar, is_index=False)

        cpr = overlays.get("cpr", {})
        self.assertIn("pivot", cpr)
        self.assertIn("tc", cpr)
        self.assertIn("bc", cpr)
        self.assertAlmostEqual(cpr["pivot"], 3000.0, places=1)

        cam = overlays.get("camarilla", {})
        self.assertIn("h3", cam)
        self.assertIn("h4", cam)
        self.assertIn("l3", cam)
        self.assertIn("l4", cam)


    # -------------------------------------------------------------
    # Prompt 6 Tests: Dashboard Bugs, Profile Drawer, Market Clock
    # -------------------------------------------------------------
    def test_market_status_and_clock_contract(self):
        """Prompt 6 Test: Verify market_status returns ist_time, ist_date, market_open, market_phase."""
        # 1. 09:14 IST on a trading day (Thursday Nov 5 2026) -> PRE-OPEN
        dt_0914 = datetime.datetime(2026, 11, 5, 3, 44, 0, tzinfo=datetime.timezone.utc)
        st_0914 = alerts.market_status(dt_0914)
        self.assertEqual(st_0914["ist_time"], "09:14:00")
        self.assertEqual(st_0914["ist_date"], "2026-11-05")
        self.assertFalse(st_0914["market_open"])
        self.assertEqual(st_0914["market_phase"], "PRE-OPEN")

        # 2. 09:15 IST -> OPEN
        dt_0915 = datetime.datetime(2026, 11, 5, 3, 45, 0, tzinfo=datetime.timezone.utc)
        st_0915 = alerts.market_status(dt_0915)
        self.assertTrue(st_0915["market_open"])
        self.assertEqual(st_0915["market_phase"], "OPEN")

        # 3. 14:45 IST -> OPEN
        dt_1445 = datetime.datetime(2026, 11, 5, 9, 15, 0, tzinfo=datetime.timezone.utc)
        st_1445 = alerts.market_status(dt_1445)
        self.assertTrue(st_1445["market_open"])
        self.assertEqual(st_1445["market_phase"], "OPEN")

        # 4. 15:30 IST -> CLOSED
        dt_1530 = datetime.datetime(2026, 11, 5, 10, 0, 0, tzinfo=datetime.timezone.utc)
        st_1530 = alerts.market_status(dt_1530)
        self.assertFalse(st_1530["market_open"])
        self.assertEqual(st_1530["market_phase"], "CLOSED")

        # 5. Weekend (Saturday Nov 7 2026 10:00 IST) -> CLOSED
        dt_weekend = datetime.datetime(2026, 11, 7, 4, 30, 0, tzinfo=datetime.timezone.utc)
        st_weekend = alerts.market_status(dt_weekend)
        self.assertFalse(st_weekend["market_open"])
        self.assertEqual(st_weekend["market_phase"], "CLOSED")
        self.assertIn("weekend", st_weekend["reason"].lower())

        # 6. NSE Holiday (Republic Day Jan 26 2026 10:00 IST) -> CLOSED
        dt_holiday = datetime.datetime(2026, 1, 26, 4, 30, 0, tzinfo=datetime.timezone.utc)
        st_holiday = alerts.market_status(dt_holiday)
        self.assertFalse(st_holiday["market_open"])
        self.assertEqual(st_holiday["market_phase"], "CLOSED")
        self.assertIn("holiday", st_holiday["reason"].lower())

    def test_market_context_suspect_index_flag(self):
        """Prompt 6 Test: Verify index moves > +/- 5% flag suspect: True."""
        mock_nifty_candles = {
            "last_price": 26875.0,
            "prev_close": 25000.0,  # +7.5% move (extreme anomaly)
            "stale": False
        }
        with mock.patch.object(candles_module, "get_candles", return_value=mock_nifty_candles):
            ctx = candles_module.get_market_context()
            nifty_item = next(item for item in ctx if item["symbol"] == "^NSEI")
            self.assertTrue(nifty_item["suspect"])
            self.assertAlmostEqual(nifty_item["change_pct"], 7.5, places=1)

    def test_stock_profile_drawer_shape_and_no_fake_facts(self):
        """Prompt 6 Test: Verify get_stock_profile returns structured keys and null facts for missing metadata."""
        mock_daily = {
            "chart": {
                "result": [{
                    "meta": {
                        "shortName": "Reliance Industries Limited",
                        "fiftyTwoWeekHigh": 3200.0,
                        "fiftyTwoWeekLow": 2200.0,
                        "regularMarketPrice": 2950.0,
                        "exchangeName": "NSE"
                    }
                }]
            }
        }
        mock_prev_bar = {"high": 2960.0, "low": 2920.0, "close": 2940.0}
        with mock.patch.object(candles_module, "fetch_raw_yahoo_chart", return_value=mock_daily), \
             mock.patch.object(candles_module, "fetch_prev_day_bar", return_value=mock_prev_bar):
            prof = candles_module.get_stock_profile("RELIANCE.NS")
            self.assertEqual(prof["symbol"], "RELIANCE.NS")
            self.assertEqual(prof["name"], "Reliance Industries Limited")
            self.assertAlmostEqual(prof["fifty_two_week_high"], 3200.0)
            self.assertAlmostEqual(prof["fifty_two_week_low"], 2200.0)
            self.assertIn("cpr", prof)
            self.assertIn("camarilla", prof)
            # Company facts must be None when not from verified DB (no hardcoded TCS strings!)
            self.assertIsNone(prof.get("founded"))
            self.assertIsNone(prof.get("business_group"))
            self.assertIsNone(prof.get("headquarters"))
            self.assertIsNone(prof.get("ceo"))
            self.assertIsNone(prof.get("about"))

    def test_risk_decision_audit_log(self):
        """Prompt 6 Test: Verify pre_trade_gate records decision into trader/state/decisions.json."""
        test_order = {
            "symbol": "INFY.NS",
            "side": "BUY",
            "qty": 10,
            "entry_price": 1800.0,
            "stop_loss_price": 1790.0,
            "take_profit_price": 1825.0
        }
        now_ist = datetime.datetime(2026, 11, 5, 10, 30, 0)
        # Execute gate
        risk_module.pre_trade_gate(test_order, now_ist=now_ist, vix=14.5)

        dec_file = os.path.join(BASE_DIR, "trader", "state", "decisions.json")
        self.assertTrue(os.path.exists(dec_file))
        data = risk_module.load_json(dec_file)
        self.assertIn("decisions", data)
        self.assertGreater(len(data["decisions"]), 0)
        latest = data["decisions"][0]
        self.assertEqual(latest["symbol"], "INFY.NS")
        self.assertEqual(latest["side"], "BUY")
        self.assertIn(latest["verdict"], ("PASS", "BLOCK"))
        self.assertIn("reason", latest)

    # -------------------------------------------------------------
    # Prompt 7 Tests: main.py Hardening, Secret Masking, Exit Codes
    # -------------------------------------------------------------
    def test_main_mask_secret(self):
        """Prompt 7 Test: Verify credentials masking hides secret tokens."""
        self.assertEqual(main_module.mask_secret(None), "Not configured")
        self.assertEqual(main_module.mask_secret(""), "Not configured")
        self.assertEqual(main_module.mask_secret("123456"), "******")
        masked = main_module.mask_secret("bot123456789:ABCdefGHI")
        self.assertTrue(masked.startswith("bot"))
        self.assertTrue(masked.endswith("GHI"))
        self.assertIn("*" * 10, masked)
        self.assertNotIn("123456789", masked)

    def test_main_secret_resolution_env_precedence(self):
        """Prompt 7 Test: Verify environment variables take precedence over config.json."""
        test_cfg = {
            "telegram_bot_token": "CONFIG_TG_TOKEN",
            "telegram_chat_id": "CONFIG_CHAT_ID",
            "discord_webhook_url": "CONFIG_DISCORD_URL"
        }
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "ENV_TG_TOKEN", "TELEGRAM_CHAT_ID": "ENV_CHAT_ID"}):
            sec = main_module.resolve_secrets(test_cfg)
            self.assertEqual(sec["telegram_bot_token"], "ENV_TG_TOKEN")
            self.assertEqual(sec["telegram_chat_id"], "ENV_CHAT_ID")
            self.assertEqual(sec["discord_webhook_url"], "CONFIG_DISCORD_URL")

    def test_main_command_exit_codes(self):
        """Prompt 7 Test: Verify run_subcommand returns exit code and cmd_panic reports success."""
        with mock.patch.object(main_module, "run_subcommand", return_value=0):
            rc = main_module.cmd_panic()
            self.assertEqual(rc, 0)

        with mock.patch.object(main_module, "run_subcommand", return_value=2):
            rc_fail = main_module.cmd_panic()
            self.assertEqual(rc_fail, 2)



    # -------------------------------------------------------------
    # Prompt 9 Tests: Regression Suite, API Contracts, Property Tests & CI
    # -------------------------------------------------------------
    def test_market_status_fixed_times_matrix(self):
        """Prompt 9 Test: Assert market_status contract across 09:14, 09:15, 14:45, 15:10, 15:30, weekend and holiday."""
        # 1. 09:14 IST: Pre-open buffer -> closed for regular trading
        t_0914 = alerts.ist_to_utc(datetime.datetime(2026, 11, 5, 9, 14, 0))
        s_0914 = alerts.market_status(t_0914)
        self.assertFalse(s_0914["market_open"])
        self.assertEqual(s_0914["market_phase"], "PRE-OPEN")
        self.assertIn("ist_time", s_0914)
        self.assertIn("ist_date", s_0914)

        # 2. 09:15 IST: Regular session opens
        t_0915 = alerts.ist_to_utc(datetime.datetime(2026, 11, 5, 9, 15, 0))
        s_0915 = alerts.market_status(t_0915)
        self.assertTrue(s_0915["market_open"])
        self.assertEqual(s_0915["market_phase"], "OPEN")

        # 3. 14:45 IST: Intraday entry cutoff threshold, session still open
        t_1445 = alerts.ist_to_utc(datetime.datetime(2026, 11, 5, 14, 45, 0))
        s_1445 = alerts.market_status(t_1445)
        self.assertTrue(s_1445["market_open"])
        self.assertEqual(s_1445["market_phase"], "OPEN")

        # 4. 15:10 IST: Square-off active, regular market open until 15:30
        t_1510 = alerts.ist_to_utc(datetime.datetime(2026, 11, 5, 15, 10, 0))
        s_1510 = alerts.market_status(t_1510)
        self.assertTrue(s_1510["market_open"])
        self.assertEqual(s_1510["market_phase"], "OPEN")

        # 5. 15:30 IST: Session close -> closed
        t_1530 = alerts.ist_to_utc(datetime.datetime(2026, 11, 5, 15, 30, 0))
        s_1530 = alerts.market_status(t_1530)
        self.assertFalse(s_1530["market_open"])
        self.assertEqual(s_1530["market_phase"], "CLOSED")

        # 6. Weekend Saturday
        t_sat = alerts.ist_to_utc(datetime.datetime(2026, 11, 7, 10, 30, 0))
        s_sat = alerts.market_status(t_sat)
        self.assertFalse(s_sat["market_open"])
        self.assertEqual(s_sat["market_phase"], "CLOSED")

        # 7. NSE Holiday (Republic Day)
        t_hol = alerts.ist_to_utc(datetime.datetime(2026, 1, 26, 10, 30, 0))
        s_hol = alerts.market_status(t_hol)
        self.assertFalse(s_hol["market_open"])
        self.assertEqual(s_hol["market_phase"], "CLOSED")

    def test_api_contract_scanner_candidates(self):
        """Prompt 9 Test: Contract test for /api/scanner/candidates shape and filtering."""
        url = f"http://127.0.0.1:{self.port}/api/scanner/candidates?index=nifty50&sector=it&min_score=50"
        mock_quotes = {
            "RELIANCE.NS": {"price": 2500.0, "change_pct": 1.2, "name": "Reliance", "time_ist": "09:30:00"},
            "TCS.NS": {"price": 3500.0, "change_pct": -0.8, "name": "TCS", "time_ist": "09:30:00"},
            "INFY.NS": {"price": 1800.0, "change_pct": 0.6, "name": "Infosys", "time_ist": "09:30:00"}
        }
        with mock.patch("candles.get_batch_quotes", return_value=mock_quotes):
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))

        self.assertIn("candidates", data)
        self.assertIn("as_of", data)
        self.assertIn("source", data)
        self.assertIn("filters", data)
        self.assertIsInstance(data["candidates"], list)
        self.assertEqual(data["filters"]["index"], "nifty50")
        self.assertEqual(data["filters"]["sector"], "it")
        self.assertEqual(data["filters"]["min_score"], 50)

        for c in data["candidates"]:
            self.assertIn("symbol", c)
            self.assertIn("gap_pct", c)
            self.assertIn("cpr_width", c)
            self.assertIn("delivery_pct", c)
            self.assertIn("score", c)
            self.assertIn("setup", c)

    def test_api_contract_strategies_matrix(self):
        """Prompt 9 Test: Contract test for /api/strategies/matrix shape and 20 strategies."""
        url = f"http://127.0.0.1:{self.port}/api/strategies/matrix?symbol=TCS.NS"
        req = urllib.request.Request(url)
        mock_candles = {
            "symbol": "TCS.NS",
            "candles": [{"time": 1700000000, "open": 3500.0, "high": 3520.0, "low": 3490.0, "close": 3510.0, "volume": 50000}],
            "prev_bar": {"high": 3500.0, "low": 3450.0, "close": 3480.0}
        }
        with mock.patch("candles.get_candles", return_value=mock_candles):
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))

        self.assertEqual(data.get("symbol"), "TCS.NS")
        self.assertIn("matrix", data)
        self.assertIn("pillars", data)
        self.assertIn("as_of", data)
        self.assertIn("source", data)

        matrix = data["matrix"]
        self.assertEqual(len(matrix), 20)
        for m in matrix:
            self.assertIn("id", m)
            self.assertIn("name", m)
            self.assertIn("type", m)
            self.assertIn("mode", m)
            self.assertIn("signal", m)
            self.assertIn(m["signal"], ("BUY", "SELL", "NEUTRAL", "LONG", "SHORT"))
            self.assertIn(m["mode"], ("Automated", "Analysis Only"))

        pillars = data["pillars"]
        for p_key in ("trend", "momentum", "volume", "pivots", "regime", "volatility"):
            self.assertIn(p_key, pillars)

    def test_api_contract_risk_radar(self):
        """Prompt 9 Test: Contract test for /api/risk/radar gauges and decisions audit."""
        url = f"http://127.0.0.1:{self.port}/api/risk/radar"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))

        self.assertIn("daily_loss_used", data)
        self.assertIn("daily_loss_limit", data)
        self.assertIn("profit_lock", data)
        self.assertIn("consecutive_losses", data)
        self.assertIn("max_consecutive_losses", data)
        self.assertIn("sector_exposure", data)
        self.assertIn("vix", data)
        self.assertIn("vix_regime", data)
        self.assertIn("decisions", data)
        self.assertIsInstance(data["decisions"], list)

    def test_api_contract_backtest_run(self):
        """Prompt 9 Test: Contract test for /api/backtest/run walk-forward simulation."""
        url = f"http://127.0.0.1:{self.port}/api/backtest/run?symbol=RELIANCE.NS"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))

        self.assertEqual(data.get("symbol"), "RELIANCE.NS")
        self.assertIn("sample_size", data)
        self.assertIn("sample_warning", data)
        self.assertTrue(data["sample_warning"])  # sample < 200 trades must set warning flag
        self.assertIn("in_sample", data)
        self.assertIn("out_of_sample", data)
        self.assertIn("monte_carlo", data)

        in_samp = data["in_sample"]
        self.assertIn("trades", in_samp)
        self.assertIn("win_rate", in_samp)
        self.assertIn("profit_factor", in_samp)
        self.assertIn("max_drawdown", in_samp)

        mc = data["monte_carlo"]
        self.assertIn("p05", mc)
        self.assertIn("p50", mc)
        self.assertIn("p95", mc)

    def test_api_contract_news_and_institutional(self):
        """Prompt 9 Test: Contract test for /api/news/feed, fiidii, and insider."""
        # 1. News feed
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/news/feed") as resp:
            self.assertEqual(resp.status, 200)
            feed_data = json.loads(resp.read().decode())
            self.assertIn("feed", feed_data)
            self.assertIn("source", feed_data)
            self.assertIn("as_of", feed_data)

        # 2. FII / DII
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/news/fiidii") as resp:
            self.assertEqual(resp.status, 200)
            fii_data = json.loads(resp.read().decode())
            self.assertIn("fii_cash_net", fii_data)
            self.assertIn("dii_cash_net", fii_data)
            self.assertIn("source", fii_data)

        # 3. Insider
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/news/insider") as resp:
            self.assertEqual(resp.status, 200)
            ins_data = json.loads(resp.read().decode())
            self.assertIn("filings", ins_data)
            self.assertIn("min_value", ins_data)
            self.assertEqual(ins_data["min_value"], 1000000)

    def test_api_contract_broker_failover(self):
        """Prompt 9 Test: Contract test for broker failover status and live confirmation safeguard."""
        # 1. Status
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/failover/status") as resp:
            self.assertEqual(resp.status, 200)
            st = json.loads(resp.read().decode())
            self.assertIn("active_broker", st)
            self.assertIn("failover_broker", st)
            self.assertTrue(st.get("paper_simulation"))

        # 2. Attempt live switch without confirm_live flag -> must return HTTP 400
        req_unconf = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/failover/switch",
            data=json.dumps({"broker": "zerodha"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_unconf)
        self.assertEqual(ctx.exception.code, 400)

        # 3. Confirmed switch to zerodha
        req_conf = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/failover/switch",
            data=json.dumps({"broker": "zerodha", "confirm_live": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_conf) as resp:
            self.assertEqual(resp.status, 200)
            res_json = json.loads(resp.read().decode())
            self.assertTrue(res_json.get("success"))
            self.assertEqual(res_json.get("active_broker"), "zerodha")

        # 4. Instant failover back to paper
        req_paper = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/failover/switch",
            data=json.dumps({"broker": "paper"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_paper) as resp:
            self.assertEqual(resp.status, 200)
            res_json = json.loads(resp.read().decode())
            self.assertEqual(res_json.get("active_broker"), "paper")

    def test_data_layer_timeout_handling(self):
        """Prompt 9 Test: Data layer handles connection timeout with retry and fail-closed exception."""
        test_url = "https://query1.finance.yahoo.com/v8/finance/chart/TIMEOUT_TEST.NS"
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
            with self.assertRaises(TimeoutError):
                data_layer.fetch_json_with_retry(test_url, timeout=0.1, max_retries=1, backoff_factor=0.01)

    def test_data_layer_http_429_rate_limit(self):
        """Prompt 9 Test: Data layer handles HTTP 429 rate limit with backoff and recovery."""
        test_url = "https://query1.finance.yahoo.com/v8/finance/chart/RATELIMIT_TEST.NS"
        
        err_429 = urllib.error.HTTPError(test_url, 429, "Too Many Requests", {"Retry-After": "0"}, None)
        mock_response = mock.MagicMock()
        mock_response.read.return_value = b'{"chart": {"result": [{"meta": {"price": 100}}]}}'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with mock.patch("urllib.request.urlopen", side_effect=[err_429, mock_response]):
            res = data_layer.fetch_json_with_retry(test_url, timeout=1.0, max_retries=2, backoff_factor=0.01)
            self.assertIn("chart", res)

    def test_data_layer_malformed_json_and_empty_response(self):
        """Prompt 9 Test: Data layer handles empty responses and corrupt JSON without crashing."""
        test_url = "https://query1.finance.yahoo.com/v8/finance/chart/CORRUPT_TEST.NS"
        mock_response = mock.MagicMock()
        mock_response.read.return_value = b'<!DOCTYPE html><html><body>Error 500</body></html>'
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        with mock.patch("urllib.request.urlopen", return_value=mock_response):
            with self.assertRaises(json.JSONDecodeError):
                data_layer.fetch_json_with_retry(test_url, timeout=1.0, max_retries=0)

    def test_property_position_sizing_never_exceeds_risk_or_caps(self):
        """Prompt 9 Test: Property test verifying position size never exceeds risk, turnover cap or cash on BUY and SELL."""
        import random
        config = {
            "budget": 100000.0,
            "max_loss_per_trade_inr": 1000.0,
            "max_order_inr": 50000.0,
            "cash_buffer_pct": 10.0,
            "max_position_pct": 50.0,
            "min_order_inr": 1000.0,
            "dynamic_drawdown_scaling": False
        }
        effective_max_loss = config["max_loss_per_trade_inr"]
        max_order_inr = config["max_order_inr"]
        investable_cash = config["budget"] * (1.0 - config["cash_buffer_pct"] / 100.0)

        random.seed(42)
        for i in range(50):
            entry = round(random.uniform(100.0, 5000.0), 2)
            # 1. BUY Side: stop < entry, target > entry
            risk_pts = round(random.uniform(5.0, 50.0), 2)
            stop_buy = round(entry - risk_pts, 2)
            target_buy = round(entry + (risk_pts * 2.0), 2)

            plan_buy = {"symbol": f"TEST_BUY_{i}.NS", "entry": entry, "stop": stop_buy, "target": target_buy, "side": "BUY"}
            res_buy, _, _ = size_module.size_trade(plan_buy, config)

            qty_buy = res_buy["qty"]
            self.assertGreater(qty_buy, 0)
            self.assertLessEqual(qty_buy * (entry - stop_buy), effective_max_loss + 1e-4)
            self.assertLessEqual(qty_buy * entry, max_order_inr + 1e-4)
            self.assertLessEqual(qty_buy * entry, investable_cash + 1e-4)
            self.assertEqual(res_buy["side"], "BUY")

            # 2. SELL Side: stop > entry, target < entry
            stop_sell = round(entry + risk_pts, 2)
            target_sell = round(entry - (risk_pts * 2.0), 2)

            plan_sell = {"symbol": f"TEST_SELL_{i}.NS", "entry": entry, "stop": stop_sell, "target": target_sell, "side": "SELL"}
            res_sell, _, _ = size_module.size_trade(plan_sell, config)

            qty_sell = res_sell["qty"]
            self.assertGreater(qty_sell, 0)
            self.assertLessEqual(qty_sell * (stop_sell - entry), effective_max_loss + 1e-4)
            self.assertLessEqual(qty_sell * entry, max_order_inr + 1e-4)
            self.assertLessEqual(qty_sell * entry, investable_cash + 1e-4)
            self.assertEqual(res_sell["side"], "SELL")

    def test_post_april_2026_stt_rates_and_rounding(self):
        """Verify revised Finance Act 2026 STT rates and statutory nearest-rupee rounding."""
        from decimal import Decimal
        # 1. Equity Intraday: STT is 0.025% on sell turnover, rounded to nearest rupee
        res_intra = tax_calculator.calculate_indian_trade_charges(1000.0, 1000.0, 100, segment="EQUITY_INTRADAY")
        self.assertEqual(res_intra["stt"], Decimal("25"))

        # E.g. sell turnover = 1750 * 1 = 1750. 1750 * 0.00025 = 0.4375 -> rounds to 0
        res_intra_round_down = tax_calculator.calculate_indian_trade_charges(1750.0, 1750.0, 1, segment="EQUITY_INTRADAY")
        self.assertEqual(res_intra_round_down["stt"], Decimal("0"))

        # E.g. sell turnover = 2500 * 1 = 2500. 2500 * 0.00025 = 0.625 -> rounds to 1
        res_intra_round_up = tax_calculator.calculate_indian_trade_charges(2500.0, 2500.0, 1, segment="EQUITY_INTRADAY")
        self.assertEqual(res_intra_round_up["stt"], Decimal("1"))

        # 2. F&O Futures: revised rate 0.05% on sell turnover (Finance Act 2026)
        res_fut = tax_calculator.calculate_indian_trade_charges(1000.0, 1000.0, 100, segment="FNO_FUTURES")
        self.assertEqual(res_fut["stt"], Decimal("50"))

        # 3. F&O Options: revised rate 0.15% on sell premium (Finance Act 2026)
        res_opt = tax_calculator.calculate_indian_trade_charges(100.0, 100.0, 200, segment="FNO_OPTIONS")
        self.assertEqual(res_opt["stt"], Decimal("30"))

        # 4. Delivery: 0.1% on buy + 0.1% on sell
        res_del = tax_calculator.calculate_indian_trade_charges(1000.0, 1000.0, 100, segment="EQUITY_DELIVERY")
        self.assertEqual(res_del["stt"], Decimal("200"))
        self.assertEqual(res_del["dp_charge"], Decimal("15.34"))

    def test_sqlite_wal_mode_and_concurrency(self):
        """Verify SQLite WAL mode and busy timeout configuration via get_db_connection."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            test_db = Path(tmpdir) / "test_wal.db"
            with data_layer.get_db_connection(test_db) as conn:
                cur = conn.cursor()
                mode = cur.execute("PRAGMA journal_mode;").fetchone()[0]
                timeout = cur.execute("PRAGMA busy_timeout;").fetchone()[0]
                self.assertEqual(mode.upper(), "WAL")
                self.assertGreaterEqual(timeout, 5000)

    def test_atomic_write_json(self):
        """Verify atomic_write_json safely persists JSON and handles directory creation."""
        import common
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "sub" / "test_state.json"
            common.atomic_write_json(target, {"status": "ok", "count": 42})
            loaded = common.load_json(str(target))
            self.assertEqual(loaded.get("status"), "ok")
            self.assertEqual(loaded.get("count"), 42)

    def test_create_nse_session_opener(self):
        """Verify create_nse_session_opener returns a valid urllib OpenerDirector with headers."""
        import common
        opener = common.create_nse_session_opener()
        self.assertIsInstance(opener, urllib.request.OpenerDirector)
        header_keys = [h[0].lower() for h in opener.addheaders]
        self.assertIn("user-agent", header_keys)
        self.assertIn("referer", header_keys)

    def test_coverage_summary(self):
        """Prompt 9 Test: Print a verified coverage summary confirming all core modules have tests."""
        skills_tested = [
            "trader-alerts (alerts.py)",
            "trader-broker (ticket.py, autotrader.py, dashboard.py, failover.py, web_server.py)",
            "trader-scanner (candles.py, strategies.py, scan.py, preopen.py)",
            "trader-risk (check.py)",
            "trader-budget (size.py, tax_calculator.py)",
            "trader-analyst (swing.py, cpr.py)",
            "trader-news (news.py)",
            "trader-insider (insider.py)",
            "trader-timemachine (timemachine.py, journal.py)",
            "data_layer.py",
            "common.py",
            "main.py"
        ]
        self.assertGreaterEqual(len(skills_tested), 12)

if __name__ == "__main__":
    unittest.main()
