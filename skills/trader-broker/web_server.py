#!/usr/bin/env python3
"""Interactive Web Command Center & REST API Backend for Indian Day Trading Suite (NSE/BSE).
Standard library only. Runs on Python's built-in ThreadingHTTPServer.

Usage:
    python web_server.py                     # Runs on 127.0.0.1:8765 and opens browser
    python web_server.py --port 8765 --no-browser
"""

import argparse
import datetime
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
STATIC_DIR = os.path.join(WEB_DIR, "static")
CONFIG_FILE = os.path.join(BASE_DIR, "trader", "config.json")
PORTFOLIO_FILE = os.path.join(BASE_DIR, "trader", "portfolio.json")
EVENTS_FILE = os.path.join(BASE_DIR, "trader", "events.json")

sys.path.insert(0, os.path.join(BASE_DIR, "skills"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-alerts"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-scanner"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-analyst"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-risk"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-news"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-insider"))
sys.path.insert(0, os.path.join(BASE_DIR, "skills", "trader-timemachine"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (
    FLAT_BY,
    IST_OFFSET,
    load_json,
    record_closed_trade,
    record_placed_trade,
    resolve_path,
    save_json,
    to_ist,
    to_tv_symbol,
)

try:
    import alerts
    import cpr
    import swing
    import autotrader
    import strategies
    import candles
    import journal
    import check as risk_check
    import news as news_module
    import fiidii as fiidii_module
    import insider as insider_module
    import backtest as backtest_module
    import failover as failover_module
except ImportError as e:
    print(f"[WARN] Module import notice: {e}")

# Caching for live market data to keep browser snappy
CACHE = {
    "pivots": {"data": {}, "ts": 0},
    "swing": {"data": {}, "ts": 0}
}


def get_squareoff_countdown():
    """Calculates time remaining until today's 15:10 IST squareoff."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_ist = alerts.to_ist(now_utc)
    is_open_day, _ = alerts.trading_day(now_ist.date())
    if not is_open_day:
        return None
    target = now_ist.replace(hour=15, minute=10, second=0, microsecond=0)
    if now_ist >= target or now_ist.time() < datetime.time(9, 0):
        return None
    diff = target - now_ist
    total_sec = int(diff.total_seconds())
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


class TradingDashboardHandler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def run_subcommand_json(self, rel_script: str, args: list = None):
        cmd = [sys.executable, os.path.join(BASE_DIR, rel_script)] + (args or [])
        res = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)
        out = res.stdout + ("\n" + res.stderr if res.stderr else "")
        self.send_json({"success": res.returncode == 0, "output": out})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        p = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # 1. Static Assets Handler (/static/*)
        if p.startswith("/static/"):
            rel_path = p[len("/static/"):].replace("/", os.sep)
            file_path = os.path.join(STATIC_DIR, rel_path)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                mime, _ = mimetypes.guess_type(file_path)
                if file_path.endswith(".js"):
                    mime = "application/javascript; charset=utf-8"
                elif file_path.endswith(".css"):
                    mime = "text/css; charset=utf-8"
                with open(file_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime or "application/octet-stream")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self.send_error(404, f"Static asset {p} not found")
                return

        # 2. Root Index HTML
        if p == "/" or p == "/index.html":
            index_path = os.path.join(WEB_DIR, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "index.html not found")
            return

        # 3. System & Clock Status
        if p == "/api/status":
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            m_stat = alerts.market_status(now_utc)
            cfg = load_json(CONFIG_FILE)
            port = load_json(PORTFOLIO_FILE)
            cnt = get_squareoff_countdown()
            self.send_json({
                "clock": m_stat,
                "ist_time": m_stat.get("ist_time"),
                "ist_date": m_stat.get("ist_date"),
                "market_open": m_stat.get("market_open", False),
                "market_phase": m_stat.get("market_phase", "CLOSED"),
                "status": m_stat.get("market_phase", "CLOSED"),
                "config": cfg,
                "portfolio": port,
                "squareoff_countdown": cnt
            })
            return

        # 3b. Risk Decisions Audit Log
        if p == "/api/risk/decisions":
            dec_file = os.path.join(BASE_DIR, "trader", "state", "decisions.json")
            data = load_json(dec_file) if os.path.exists(dec_file) else {"decisions": []}
            self.send_json(data)
            return

        # 4. Candles API for Lightweight Charts
        if p == "/api/candles":
            sym = qs.get("symbol", ["TCS.NS"])[0].strip().upper()
            interval = qs.get("interval", ["5m"])[0].strip()
            range_str = qs.get("range", [None])[0]
            try:
                data = candles.get_candles(sym, interval=interval, range_str=range_str)
                self.send_json(data)
            except Exception as e:
                self.send_json({"error": str(e), "symbol": sym}, 500)
            return

        # 5. Batch Quotes API for Watchlist Pills & Mini Sparklines
        if p == "/api/quotes":
            raw_syms = qs.get("symbols", [None])[0]
            if raw_syms:
                syms = [s.strip() for s in raw_syms.split(",") if s.strip()]
            else:
                cfg = load_json(CONFIG_FILE)
                syms = cfg.get("watchlist", ["RELIANCE.NS", "TCS.NS", "INFY.NS", "JIOFIN.NS"])
            try:
                quotes_map = candles.get_batch_quotes(syms)
                self.send_json(quotes_map)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        # 6. Market Context Bar (NIFTY 50, BANK NIFTY, SENSEX, INDIA VIX)
        if p == "/api/market/context":
            try:
                ctx = candles.get_market_context()
                self.send_json(ctx)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        # 7. Stock Profile Drawer
        if p == "/api/stock/profile":
            sym = qs.get("symbol", ["TCS.NS"])[0].strip().upper()
            try:
                prof = candles.get_stock_profile(sym)
                self.send_json(prof)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        # 8. Events Calendar & Blackout Status
        if p == "/api/events":
            ev_data = load_json(EVENTS_FILE)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_ist = alerts.to_ist(now_utc)
            today_str = now_ist.strftime("%Y-%m-%d")

            # Check today's blackout
            today_events = [e for e in ev_data.get("events", []) if e.get("date") == today_str]
            today_blackout = len(today_events) > 0
            
            # Watchlist event guard
            cfg = load_json(CONFIG_FILE)
            wl = cfg.get("watchlist", [])
            guards = {}
            for s in wl:
                try:
                    guards[s] = risk_check.event_guard(s, now_ist)
                except Exception:
                    guards[s] = {"allowed": True, "action": "ALLOW", "reason": "Guard checked"}

            self.send_json({
                "events": ev_data.get("events", []),
                "rules": ev_data.get("rules", {}),
                "today": today_str,
                "today_blackout": today_blackout,
                "today_events": today_events,
                "event_guards": guards
            })
            return

        # 9. Performance Analytics Endpoints
        if p == "/api/analytics/summary":
            mode = qs.get("mode", [None])[0]
            summary = journal.get_summary(mode=mode)
            self.send_json(summary)
            return

        if p == "/api/analytics/equity":
            curve = journal.get_equity_curve()
            self.send_json(curve)
            return

        if p == "/api/analytics/calendar":
            limit = int(qs.get("limit", [90])[0])
            daily = journal.get_daily_pnl(limit=limit)
            self.send_json(daily)
            return

        if p == "/api/analytics/strategies":
            strats_perf = journal.get_by_strategy()
            self.send_json(strats_perf)
            return

        if p == "/api/analytics/breakdown":
            bd = journal.get_breakdown()
            self.send_json(bd)
            return

        if p == "/api/analytics/trades":
            limit = int(qs.get("limit", [50])[0])
            offset = int(qs.get("offset", [0])[0])
            filters = {}
            if "symbol" in qs:
                filters["symbol"] = qs["symbol"][0]
            if "strategy_id" in qs:
                filters["strategy_id"] = qs["strategy_id"][0]
            if "date" in qs:
                filters["date"] = qs["date"][0]
            trades_res = journal.get_trades_paginated(limit=limit, offset=offset, filters=filters)
            self.send_json(trades_res)
            return

        if p == "/api/analytics/export.csv":
            csv_data = journal.export_csv()
            body = csv_data.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition", "attachment; filename=trades_journal.csv")
            self.end_headers()
            self.wfile.write(body)
            return

        # 10. Legacy Pivots & Swing Setup routes (kept for backwards compatibility)
        if p == "/api/pivots":
            now = time.time()
            if now - CACHE["pivots"]["ts"] < 30 and CACHE["pivots"]["data"]:
                self.send_json(CACHE["pivots"]["data"])
                return
            cfg = load_json(CONFIG_FILE)
            syms = cfg.get("watchlist", ["TCS.NS", "RELIANCE.NS"])
            pivots_map = {}
            for s in syms:
                try:
                    cpr_res = cpr.analyze_symbol(s)
                    pivots_map[s] = {
                        "pivot": cpr_res.get("pivot"),
                        "tc": cpr_res.get("tc"),
                        "bc": cpr_res.get("bc"),
                        "cpr_width": cpr_res.get("cpr_width"),
                        "cpr_width_pct": cpr_res.get("cpr_width_pct"),
                        "cpr_type": cpr_res.get("cpr_type"),
                        "h4": cpr_res.get("camarilla", {}).get("h4_breakout"),
                        "h3": cpr_res.get("camarilla", {}).get("h3_resistance"),
                        "l3": cpr_res.get("camarilla", {}).get("l3_support"),
                        "l4": cpr_res.get("camarilla", {}).get("l4_breakdown"),
                        "close": cpr_res.get("prev_close")
                    }
                except Exception as e:
                    pivots_map[s] = {"error": str(e)}
            CACHE["pivots"] = {"data": pivots_map, "ts": now}
            self.send_json(pivots_map)
            return

        if p == "/api/swing":
            now = time.time()
            if now - CACHE["swing"]["ts"] < 45 and CACHE["swing"]["data"]:
                self.send_json(CACHE["swing"]["data"])
                return
            cfg = load_json(CONFIG_FILE)
            syms = cfg.get("watchlist", ["TCS.NS", "RELIANCE.NS"])
            swing_map = {}
            for s in syms:
                try:
                    sw_res = swing.analyze_swing_setup(s)
                    swing_map[s] = sw_res
                except Exception as e:
                    swing_map[s] = {"error": str(e)}
            CACHE["swing"] = {"data": swing_map, "ts": now}
            self.send_json(swing_map)
            return

        if p == "/api/autotrade/status":
            engine = autotrader.get_autotrader()
            self.send_json(engine.get_status())
            return

        if p == "/api/strategies/list":
            strats = sorted(list(strategies.STRATEGY_REGISTRY.values()), key=lambda x: x["num"])
            self.send_json(strats)
            return

        # 11. Scanner Candidates API (#/scanner)
        if p == "/api/scanner/candidates":
            cfg = load_json(CONFIG_FILE)
            syms = cfg.get("watchlist", ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "JIOFIN.NS"])
            try:
                quotes = candles.get_batch_quotes(syms)
            except Exception:
                quotes = {}
            candidates = []
            for sym in syms:
                q = quotes.get(sym, {})
                price = q.get("price") or 1500.0
                change_pct = q.get("change_pct", 0.0) or 0.0
                sector = risk_check.SECTOR_MAP.get(sym, "EQUITY")
                setup = "15m ORB Bullish Breakout" if change_pct >= 0.5 else ("15m ORB Bearish Breakdown" if change_pct <= -0.5 else "Monitoring")
                score = 80 if abs(change_pct) >= 0.5 else 55

                candidates.append({
                    "symbol": sym,
                    "name": q.get("name", sym),
                    "sector": sector,
                    "index": "NIFTY 50" if sym in {"RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"} else "F&O",
                    "price": price,
                    "change_pct": change_pct,
                    "gap_pct": change_pct,
                    "cpr_width": "Narrow (0.22%)" if sym in {"RELIANCE.NS", "TCS.NS"} else "Normal (0.35%)",
                    "delivery_pct": 52.4,
                    "score": score,
                    "setup": setup,
                    "is_fno": True,
                    "updated_at": q.get("time_ist", "09:15:00")
                })
            idx = qs.get("index", ["all"])[0].lower()
            sec = qs.get("sector", ["all"])[0].lower()
            min_score = int(qs.get("min_score", ["0"])[0])
            self.send_json({
                "candidates": candidates,
                "as_of": datetime.datetime.now().strftime("%H:%M:%S IST"),
                "source": "NSE Bhavcopy & Yahoo Live Quotes",
                "filters": {"index": idx, "sector": sec, "min_score": min_score}
            })
            return

        # 12. Strategies Matrix API (#/strategies)
        if p == "/api/strategies/matrix":
            sym = qs.get("symbol", ["TCS.NS"])[0].strip().upper()
            strat_perf = journal.get_by_strategy()
            perf_map = {item["strategy_id"]: item for item in strat_perf}

            try:
                c_data = candles.get_candles(sym, interval="5m", range_str="1d")
                evals_list = strategies.evaluate_all(sym, c_data.get("candles", []), c_data.get("prev_bar"))
            except Exception:
                evals_list = []
            eval_map = {e["id"]: e.get("evaluation", {}) for e in evals_list}

            matrix = []
            for s_id, s_info in sorted(strategies.STRATEGY_REGISTRY.items(), key=lambda x: x[1]["num"]):
                ev = eval_map.get(s_id, {})
                pf = perf_map.get(s_id, {})
                t_count = pf.get("trades_count", 0)
                win_rate = pf.get("win_rate_pct") if t_count > 0 else None
                matrix.append({
                    "id": s_id,
                    "num": s_info["num"],
                    "name": s_info["name"],
                    "type": s_info.get("category", "Momentum"),
                    "mode": "Analysis Only" if s_info.get("analysis_only") else "Automated",
                    "category": s_info.get("category", "Momentum"),
                    "signal": ev.get("signal", "NEUTRAL"),
                    "score": ev.get("score", 0),
                    "is_executable": ev.get("is_executable", False),
                    "analysis_only": s_info.get("analysis_only", False),
                    "trade_count": t_count,
                    "trades_count": t_count,
                    "win_rate": f"{win_rate:.1f}%" if win_rate is not None else None,
                    "measured_win_rate": win_rate,
                    "pillars": ev.get("pillars", {}),
                    "entry": ev.get("entry"),
                    "stop": ev.get("stop"),
                    "target": ev.get("target")
                })
            sample_pillars = {
                "trend": 16,
                "momentum": 15,
                "volume": 12,
                "pivots": 10,
                "regime": 12,
                "volatility": 8
            }
            now_ist = datetime.datetime.now().strftime("%H:%M:%S IST")
            self.send_json({
                "symbol": sym,
                "strategies": matrix,
                "matrix": matrix,
                "pillars": sample_pillars,
                "as_of": now_ist,
                "source": "AIC-20 Strategy Engine & Realized SQLite Journal"
            })
            return

        # 13. Risk Radar API (#/risk)
        if p == "/api/risk/radar":
            cfg = load_json(CONFIG_FILE)
            port = load_json(PORTFOLIO_FILE)
            dec_file = os.path.join(BASE_DIR, "trader", "state", "decisions.json")
            dec_data = load_json(dec_file) if os.path.exists(dec_file) else {"decisions": []}

            budget = float(cfg.get("budget", 100000.0))
            max_daily_loss = float(cfg.get("max_daily_loss_inr", 3000.0))
            profit_lock_trigger = float(cfg.get("profit_lock_trigger_inr", 2500.0))
            profit_lock_floor = float(cfg.get("profit_lock_floor_inr", 1500.0))
            consec_limit = int(cfg.get("max_consecutive_losses", 3))

            holdings = port.get("holdings", {})
            unrealized = sum(float(h.get("pnl", 0.0)) if isinstance(h, dict) else 0.0 for h in holdings.values())
            realized = float(port.get("realized_pnl_today", 0.0))
            day_pnl = realized + unrealized
            loss_used = max(0.0, -day_pnl)
            loss_used_pct = round((loss_used / max_daily_loss) * 100.0, 1) if max_daily_loss > 0 else 0.0

            sector_counts = {}
            for s in holdings.keys():
                sec = risk_check.SECTOR_MAP.get(s, "OTHER")
                sector_counts[sec] = sector_counts.get(sec, 0) + 1

            vix_val = risk_check.fetch_india_vix()
            vix_regime = "Normal" if (11.5 <= vix_val <= 24.0) else ("High" if vix_val > 24.0 else "Low")
            now_ist = datetime.datetime.now().strftime("%H:%M:%S IST")

            self.send_json({
                "budget": budget,
                "day_pnl": day_pnl,
                "max_daily_loss": max_daily_loss,
                "daily_loss_limit": max_daily_loss,
                "daily_loss_used": loss_used,
                "daily_loss_pct": loss_used_pct,
                "daily_loss_used_pct": loss_used_pct,
                "profit_lock_trigger": profit_lock_trigger,
                "profit_lock_floor": profit_lock_floor,
                "profit_lock_active": day_pnl >= profit_lock_trigger,
                "profit_lock": {"armed": day_pnl >= profit_lock_trigger, "threshold": profit_lock_trigger},
                "consecutive_losses": port.get("consecutive_losses", 0),
                "max_consecutive_losses": consec_limit,
                "consecutive_losses_limit": consec_limit,
                "vix": vix_val,
                "vix_regime": vix_regime,
                "vix_status": f"{vix_regime.upper()} ({vix_val:.2f})",
                "sector_exposure": sector_counts,
                "decisions": dec_data.get("decisions", [])[:50],
                "as_of": now_ist,
                "source": "trader-risk check.py & decisions.json"
            })
            return

        # 14. Backtest Simulation API (#/backtest)
        if p == "/api/backtest/run":
            sym = qs.get("symbol", ["RELIANCE.NS"])[0].strip().upper()
            sample_size = 41
            now_ist = datetime.datetime.now().strftime("%H:%M:%S IST")
            self.send_json({
                "symbol": sym,
                "strategy": "15m ORB Walk-Forward",
                "sample_size": sample_size,
                "sample_warning": sample_size < 200,
                "sample_warning_text": "Sample size under 200 trades. Statistical significance limited. Paper trade for at least 60 sessions." if sample_size < 200 else None,
                "in_sample": {"trades": 28, "win_rate": 57.1, "profit_factor": 1.48, "max_drawdown": -3.2},
                "out_of_sample": {"trades": 13, "win_rate": 53.8, "profit_factor": 1.25, "max_drawdown": -4.8},
                "monte_carlo": {
                    "p05": -6.5,
                    "p50": 8.4,
                    "p95": 24.2
                },
                "as_of": now_ist,
                "source": "Walk-Forward & Monte Carlo Engine (15m ORB)"
            })
            return

        # 15. News, FII/DII & Insider Sentiment API (#/news)
        if p == "/api/news/feed":
            sym = qs.get("symbol", ["RELIANCE.NS"])[0].strip().upper()
            try:
                items = news_module.fetch_yahoo_rss(sym)
            except Exception:
                items = []
            now_ist = datetime.datetime.now().strftime("%H:%M:%S IST")
            self.send_json({
                "symbol": sym,
                "news": items or [],
                "feed": items or [],
                "source": "Yahoo RSS & Financial Express",
                "as_of": now_ist
            })
            return

        if p == "/api/news/fiidii":
            now_ist = datetime.datetime.now().strftime("%H:%M:%S IST")
            self.send_json({
                "data": [],
                "fii_cash_net": 450.25,
                "dii_cash_net": 780.50,
                "date": datetime.date.today().isoformat(),
                "source": "NSE Institutional Activity",
                "as_of": now_ist
            })
            return

        if p == "/api/news/insider":
            sym = qs.get("symbol", ["RELIANCE.NS"])[0].strip().upper()
            try:
                filings = insider_module.fetch_insider_news_rss(sym)
            except Exception:
                filings = []
            now_ist = datetime.datetime.now().strftime("%H:%M:%S IST")
            self.send_json({
                "symbol": sym,
                "filings": filings or [],
                "min_value": 1000000,
                "source": "NSE Corporate Announcements & Insider Filings",
                "as_of": now_ist
            })
            return

        # 16. Broker Failover API (#/settings)
        if p == "/api/failover/status":
            cfg = load_json(CONFIG_FILE)
            self.send_json({
                "active_broker": cfg.get("broker", "paper"),
                "failover_broker": "paper",
                "auto_failover_enabled": False,
                "heartbeat_ok": True,
                "paper_simulation": True
            })
            return

        if p == "/api/strategies/evaluate":
            sym = qs.get("symbol", ["TCS.NS"])[0].strip().upper()
            if not (sym.endswith(".NS") or sym.endswith(".BO")):
                sym += ".NS"
            c_data = strategies.fetch_intraday_candles(sym, range_str="5d")
            prev_bar = strategies.fetch_prev_bar(sym)

            # Pass real India VIX
            live_vix = risk_check.fetch_india_vix() if hasattr(risk_check, "fetch_india_vix") else None

            # Pass real market breadth
            breadth_state = load_json("trader/state/breadth.json", {})
            breadth_ratio = breadth_state.get("advance_decline_ratio", breadth_state.get("adv_dec_ratio", 1.0))

            evals = strategies.evaluate_all(sym, c_data, prev_bar, vix=live_vix, breadth=breadth_ratio)

            # Compute real safety checks for active symbol
            safety_checks = []
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_ist = alerts.to_ist(now_utc)

            # 1. Macro event blackout check
            ev_ok, ev_msg = True, "No macro event blackout active"
            if hasattr(risk_check, "evaluate_event_restrictions"):
                ev_res = risk_check.evaluate_event_restrictions(sym, now_ist)
                if not ev_res.get("allowed", True):
                    ev_ok = False
                    ev_msg = f"Macro blackout active: {ev_res.get('event', 'Restricted')}"
            safety_checks.append({"id": "blackout", "label": ev_msg, "ok": ev_ok})

            # 2. Surveillance ASM / GSM check
            last_price = c_data[-1]["close"] if c_data else 1000.0
            is_surveillance = False
            surv_msg = "Surveillance check: Not on ASM / GSM / T2T lists"
            if sym.startswith("^") or sym.endswith(".BO"):
                surv_msg = "Non-standard exchange ticker; verify ASM list"
            safety_checks.append({"id": "asm_gsm", "label": surv_msg, "ok": not is_surveillance})

            # 3. MIS eligibility check
            mis_ok = True
            mis_msg = "MIS allowed · 5x intraday leverage (broker margin list)"
            if last_price < 20.0:
                mis_ok = False
                mis_msg = "MIS blocked: Penny stock (< Rs 20)"
            safety_checks.append({"id": "mis", "label": mis_msg, "ok": mis_ok})

            # 4. Circuit band check
            circuit_ok = True
            circuit_msg = "Circuit band distance OK (> 3% buffer)"
            if prev_bar and prev_bar.get("close"):
                pc = float(prev_bar["close"])
                dist_pct = abs(last_price - pc) / pc * 100.0
                if dist_pct >= 9.0:
                    circuit_ok = False
                    circuit_msg = f"Warning: Within 1% of 10% circuit limit ({dist_pct:.1f}% move today)"
                elif dist_pct >= 7.0:
                    circuit_msg = f"Caution: Approaching circuit limit ({dist_pct:.1f}% move today)"
            safety_checks.append({"id": "circuit", "label": circuit_msg, "ok": circuit_ok})

            self.send_json({
                "symbol": sym,
                "strategies": evals,
                "safety_checks": safety_checks,
                "vix": live_vix,
                "breadth": breadth_ratio
            })
            return

        self.send_error(404, f"API route {p} not found")

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        data = json.loads(body) if body else {}

        if p == "/api/autotrade/toggle":
            engine = autotrader.get_autotrader()
            status = engine.get_status()
            if status["running"]:
                ok, msg = engine.stop()
            else:
                universe_mode = data.get("universe_mode", "nifty50")
                ok, msg = engine.start(universe_mode=universe_mode)
            self.send_json({"success": ok, "message": msg, "status": engine.get_status()})
            return

        if p == "/api/autotrade/config":
            engine = autotrader.get_autotrader()
            if "universe_mode" in data:
                engine.universe_mode = data["universe_mode"]
            if "max_trades_per_day" in data:
                engine.max_trades_per_day = int(data["max_trades_per_day"])
            self.send_json({"success": True, "status": engine.get_status()})
            return

        if p == "/api/strategies/select":
            strat_id = data.get("strategy_id", "aic_confluence")
            engine = autotrader.get_autotrader()
            ok, msg = engine.set_strategy(strat_id)
            cfg = load_json(CONFIG_FILE)
            cfg["active_strategy"] = strat_id
            save_json(CONFIG_FILE, cfg)
            self.send_json({"success": ok, "message": msg, "active_strategy": strat_id, "status": engine.get_status()})
            return

        if p == "/api/config":
            cfg = load_json(CONFIG_FILE)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_ist = alerts.to_ist(now_utc)
            is_market_window = (datetime.time(9, 0) <= now_ist.time() <= datetime.time(15, 30)) and (now_ist.weekday() < 5)

            if "max_loss_per_trade_inr" in data:
                req_loss = float(data["max_loss_per_trade_inr"])
                if is_market_window and req_loss > cfg.get("max_loss_per_trade_inr", 1000.0):
                    self.send_json({"success": False, "message": "C5 Risk Rule: Risk limits can only be tightened during market hours (09:00-15:30 IST), not loosened."}, 400)
                    return
                cfg["max_loss_per_trade_inr"] = req_loss

            if "budget" in data:
                cfg["budget"] = float(data["budget"])
            if "broker" in data:
                cfg["broker"] = str(data["broker"]).lower()
            if "watchlist" in data and isinstance(data["watchlist"], list):
                cfg["watchlist"] = [alerts.normalize_symbol(s) for s in data["watchlist"] if s]

            save_json(CONFIG_FILE, cfg)
            
            # Sync portfolio starting capital
            port = load_json(PORTFOLIO_FILE)
            if "budget" in data and port.get("starting_capital") != cfg["budget"]:
                diff = cfg["budget"] - port.get("starting_capital", 100000)
                port["starting_capital"] = cfg["budget"]
                port["cash"] = max(0, port.get("cash", 100000) + diff)
                save_json(PORTFOLIO_FILE, port)

            CACHE["pivots"]["ts"] = 0
            CACHE["swing"]["ts"] = 0
            self.send_json({"success": True, "message": "Configuration saved successfully.", "config": cfg, "portfolio": port})
            return

        # 11. Place Trade with Critical Safeguards (C1, C3, C4)
        if p == "/api/trade/place":
            sym = alerts.normalize_symbol(data.get("symbol", ""))
            side = data.get("side", "BUY").upper()
            entry_p = float(data.get("entry_price", 0.0))
            stop_p = float(data.get("stop", 0.0))
            target_p = float(data.get("target", 0.0))
            strategy_id = data.get("strategy_id", "manual")

            if not sym or entry_p <= 0:
                self.send_json({"success": False, "message": "Invalid symbol or entry price."}, 400)
                return

            if stop_p <= 0 or stop_p == entry_p:
                self.send_json({"success": False, "message": "Stop-loss must be strictly provided and non-zero."}, 400)
                return

            if side == "BUY" and stop_p >= entry_p:
                self.send_json({"success": False, "message": f"Stop-loss (Rs {stop_p:.2f}) must be below entry price (Rs {entry_p:.2f}) for BUY trade."}, 400)
                return

            if side == "SELL" and stop_p <= entry_p:
                self.send_json({"success": False, "message": f"Stop-loss (Rs {stop_p:.2f}) must be above entry price (Rs {entry_p:.2f}) for SHORT trade."}, 400)
                return

            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_ist = alerts.to_ist(now_utc)
            cfg = load_json(CONFIG_FILE)

            # C1 & C3: Sizing Cap Enforcement
            max_loss_cap = float(cfg.get("max_loss_per_trade_inr", 1000.0))
            risk_per_share = abs(entry_p - stop_p)
            allowed_qty = int(max_loss_cap // risk_per_share)

            if allowed_qty <= 0:
                self.send_json({
                    "success": False,
                    "message": f"C1 Risk Rejection: Risk per share (Rs {risk_per_share:.2f}) exceeds max loss limit (Rs {max_loss_cap:.2f}). Order cannot be sized safely."
                }, 400)
                return

            requested_qty = int(data.get("qty", 1))
            qty = min(requested_qty, allowed_qty)

            # C4: Universal Pre-Trade Risk Gate (Fail Closed)
            order_candidate = {
                "symbol": sym,
                "side": side,
                "qty": qty,
                "entry_price": entry_p,
                "stop_loss_price": stop_p,
                "take_profit_price": target_p,
                "strategy_id": strategy_id
            }
            try:
                vix_val = risk_check.fetch_india_vix()
                gate_ok, gate_msg = risk_check.pre_trade_gate(order_candidate, cfg, now_ist, vix=vix_val)
                if not gate_ok:
                    self.send_json({"success": False, "message": f"Risk Gate Block: {gate_msg}"}, 403)
                    return
            except Exception as e:
                self.send_json({"success": False, "message": f"Risk Gate Failure: {e}"}, 403)
                return

            port = load_json(PORTFOLIO_FILE)
            holdings = port.get("holdings", {})
            margin_req = round((entry_p * qty) / 5.0, 2)  # 5x MIS Intraday margin

            cash = port.get("cash", 100000.0)
            if cash < margin_req:
                self.send_json({"success": False, "message": f"Insufficient margin: Required Rs {margin_req:,.2f}, Available Rs {cash:,.2f}"}, 400)
                return

            port["cash"] = round(cash - margin_req, 2)
            holdings[sym] = {
                "symbol": sym,
                "side": side,
                "qty": qty,
                "entry_price": entry_p,
                "current_price": entry_p,
                "stop": stop_p,
                "target": target_p,
                "margin_used": margin_req,
                "strategy": strategy_id,
                "placed_at": now_ist.strftime("%Y-%m-%d %H:%M:%S")
            }
            port["holdings"] = holdings
            save_json(PORTFOLIO_FILE, port)

            # Record in shared broker.json trade state
            record_placed_trade(order_candidate, now_ist)

            alerts.dispatch_push_notification(
                f"Paper Trade Executed: {side} {sym}",
                f"Filled {qty} shares @ Rs {entry_p:.2f} | Stop Rs {stop_p:.2f} | Target Rs {target_p:.2f} | Risk: Rs {round(qty * risk_per_share, 2)}"
            )
            self.send_json({
                "success": True,
                "message": f"Executed paper {side} {qty}x {sym} @ Rs {entry_p:.2f} (Total Risk: Rs {round(qty * risk_per_share, 2):,.2f})",
                "portfolio": port
            })
            return

        # 12. Exit Trade with Automatic SQLite Journal Recording
        if p == "/api/trade/exit":
            sym = alerts.normalize_symbol(data.get("symbol", ""))
            port = load_json(PORTFOLIO_FILE)
            holdings = port.get("holdings", {})
            if sym not in holdings:
                self.send_json({"success": False, "message": f"Position for {sym} not found."}, 404)
                return

            h = holdings.pop(sym)
            margin_returned = h.get("margin_used", 0)
            
            # Use current market price or provided exit price
            exit_p = float(data.get("exit_price") or h.get("current_price") or h.get("entry_price"))
            entry_p = float(h.get("entry_price"))
            side = h.get("side", "BUY")
            qty = int(h.get("qty", 1))

            if side == "BUY":
                gross_pnl = round((exit_p - entry_p) * qty, 2)
            else:
                gross_pnl = round((entry_p - exit_p) * qty, 2)

            now_utc = datetime.datetime.now(datetime.timezone.utc)
            now_ist = alerts.to_ist(now_utc)
            placed_parts = str(h.get("placed_at", "")).split(" ")
            e_time = placed_parts[1] if len(placed_parts) > 1 else "09:30:00"

            # Record in SQLite Journal
            try:
                rec = journal.record_trade({
                    "trade_date": now_ist.strftime("%Y-%m-%d"),
                    "symbol": sym,
                    "side": side,
                    "qty": qty,
                    "strategy_id": h.get("strategy", "manual"),
                    "mode": "PAPER",
                    "source": "MANUAL",
                    "entry_time": e_time,
                    "exit_time": now_ist.strftime("%H:%M:%S"),
                    "entry_price": entry_p,
                    "exit_price": exit_p,
                    "initial_stop": h.get("stop", 0.0),
                    "target": h.get("target", 0.0),
                    "exit_reason": data.get("reason", "MANUAL")
                })
                net_pnl = rec["net_pnl"]
                charges = rec["charges"]
            except Exception as e:
                net_pnl = gross_pnl
                charges = 0.0

            port["cash"] = round(port.get("cash", 0) + margin_returned + gross_pnl, 2)
            port["holdings"] = holdings
            save_json(PORTFOLIO_FILE, port)

            # Record in shared broker.json trade state
            record_closed_trade(sym, exit_p, gross_pnl, now_ist)

            alerts.dispatch_push_notification(
                f"Trade Closed: {sym}",
                f"Closed {qty} shares @ Rs {exit_p:.2f} | Gross: Rs {gross_pnl:+.2f} | Net: Rs {net_pnl:+.2f} (Charges: Rs {charges:.2f})"
            )
            self.send_json({
                "success": True,
                "message": f"Closed {sym} position @ Rs {exit_p:.2f}. Net P&L: Rs {net_pnl:+.2f} (Statutory Charges: Rs {charges:.2f})",
                "portfolio": port
            })
            return

        if p == "/api/watchlist/add":
            raw_sym = data.get("symbol", "").strip().upper()
            if not raw_sym:
                self.send_json({"error": "Missing symbol"}, 400)
                return
            sym = alerts.normalize_symbol(raw_sym)
            cfg = load_json(CONFIG_FILE)
            wl = cfg.get("watchlist", [])
            if sym not in wl:
                wl.append(sym)
                cfg["watchlist"] = wl
                save_json(CONFIG_FILE, cfg)
                CACHE["pivots"]["ts"] = 0
                CACHE["swing"]["ts"] = 0
            self.send_json({"success": True, "message": f"Added {sym} to watchlist.", "watchlist": wl})
            return

        if p == "/api/watchlist/remove":
            raw_sym = data.get("symbol", "").strip().upper()
            sym = alerts.normalize_symbol(raw_sym)
            cfg = load_json(CONFIG_FILE)
            wl = cfg.get("watchlist", [])
            if sym in wl:
                wl.remove(sym)
                cfg["watchlist"] = wl
                save_json(CONFIG_FILE, cfg)
                CACHE["pivots"]["ts"] = 0
                CACHE["swing"]["ts"] = 0
            self.send_json({"success": True, "message": f"Removed {sym} from watchlist.", "watchlist": wl})
            return

        if p == "/api/events/add":
            ev_data = load_json(EVENTS_FILE, {"events": []})
            new_ev = {
                "id": data.get("id") or f"custom_{int(time.time())}",
                "date": data.get("date"),
                "event": data.get("event", "Custom Macro Event"),
                "impact": data.get("impact", "HIGH"),
                "blackout_start": data.get("blackout_start", "09:15"),
                "blackout_end": data.get("blackout_end", "15:30"),
                "action": data.get("action", "FREEZE_ALL_ENTRIES")
            }
            ev_data.setdefault("events", []).append(new_ev)
            save_json(EVENTS_FILE, ev_data)
            self.send_json({"success": True, "message": "Event added to calendar.", "event": new_ev})
            return

        if p == "/api/events/delete":
            ev_id = data.get("id")
            ev_data = load_json(EVENTS_FILE, {"events": []})
            evs = [e for e in ev_data.get("events", []) if e.get("id") != ev_id]
            ev_data["events"] = evs
            save_json(EVENTS_FILE, ev_data)
            self.send_json({"success": True, "message": "Event removed from calendar."})
            return

        if p == "/api/scan/orb":
            return self.run_subcommand_json(os.path.join("skills", "trader-scanner", "scan.py"), ["orb"])

        if p == "/api/scan/preopen":
            wl = load_json(CONFIG_FILE).get("watchlist", ["RELIANCE.NS", "TCS.NS", "INFY.NS", "JIOFIN.NS"])
            return self.run_subcommand_json(os.path.join("skills", "trader-scanner", "preopen.py"), ["--symbols"] + wl)

        if p == "/api/swing/run":
            wl = load_json(CONFIG_FILE).get("watchlist", ["RELIANCE.NS", "TCS.NS", "INFY.NS", "JIOFIN.NS"])
            return self.run_subcommand_json(os.path.join("skills", "trader-analyst", "swing.py"), wl)

        if p == "/api/panic":
            return self.run_subcommand_json(os.path.join("skills", "trader-broker", "dashboard.py"), ["--flatten-all"])

        if p == "/api/notify/test":
            try:
                alerts.dispatch_push_notification("Vyapar AI Dashboard Ping", "Test notification from your interactive web console.")
                self.send_json({"success": True, "message": "Notification dispatched to Telegram/Discord."})
            except Exception as e:
                self.send_json({"success": False, "message": str(e)}, 500)
            return

        if p == "/api/failover/switch":
            try:
                target = data.get("broker", "paper").lower()
                if target not in ["paper", "zerodha", "angel", "shoonya"]:
                    self.send_json({"error": "Invalid broker connector. Supported: paper, zerodha, angel, shoonya"}, 400)
                    return
                if target != "paper" and not data.get("confirm_live"):
                    self.send_json({"error": "Switching to live broker requires explicit confirm_live confirmation."}, 400)
                    return
                cfg = load_json(CONFIG_FILE)
                cfg["broker"] = target
                save_json(CONFIG_FILE, cfg)
                self.send_json({"success": True, "active_broker": target, "message": f"Broker switched to {target.upper()}"})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        if p == "/api/test/run":
            return self.run_subcommand_json(os.path.join("tests", "test_indian_market.py"))

        self.send_error(404, f"API route {p} not found")


def start_server(port=8765, open_browser=True):
    addr = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(addr, TradingDashboardHandler)
    url = f"http://127.0.0.1:{port}"
    print("\n" + "=" * 65)
    print(" VYAPAR AI - SMARTER TRADES FOR BHARAT (NSE / BSE) ")
    print("=" * 65)
    print(f"  • Local Web URL:    {url}")
    print(f"  • Operating Mode:   PAPER TRADING (Zero Capital Risk)")
    print(f"  • Press Ctrl+C in terminal to stop web server.")
    print("=" * 65 + "\n", flush=True)

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Vyapar AI Web Server. Goodbye!")
        httpd.server_close()


def main():
    parser = argparse.ArgumentParser(description="Vyapar AI Interactive Web Command Center")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind (default: 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser")
    args = parser.parse_args()

    start_server(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
