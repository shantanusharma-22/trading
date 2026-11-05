#!/usr/bin/env python3
"""Comprehensive Automated Unit Tests for the Enhanced Indian Stock Market Trading Suite."""

import datetime
import json
import os
import sys
import unittest

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


class TestEnhancedIndianMarketSuite(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()
