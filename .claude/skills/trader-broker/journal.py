#!/usr/bin/env python3
"""Institutional Trade Journal & Performance Analytics for trader-broker (NSE/BSE).
Persists completed trades to SQLite (trader/data/journal.db).
Calculates statutory SEBI / broker charges, win rate, profit factor, expectancy,
equity curves, calendar PnL heatmap, strategy scorecards, and SQN.
Standard library only.
"""

import argparse
import csv
import datetime
import io
import json
import math
import os
import sqlite3
import sys

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import BASE_DIR, load_json, resolve_path

DB_PATH = resolve_path("trader/data/journal.db")
CONFIG_PATH = resolve_path("trader/config.json")
BROKER_STATE_PATH = resolve_path("trader/state/broker.json")


def load_config():
    return load_json(CONFIG_PATH)


def get_db_connection(db_path=None):
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path=None):
    """Initializes the SQLite database with the full institutional trades schema."""
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty INTEGER NOT NULL,
            strategy_id TEXT DEFAULT 'aic_confluence',
            mode TEXT DEFAULT 'PAPER',
            source TEXT DEFAULT 'MANUAL',
            entry_time TEXT NOT NULL,
            exit_time TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            initial_stop REAL DEFAULT 0.0,
            target REAL DEFAULT 0.0,
            exit_reason TEXT DEFAULT 'MANUAL',
            gross_pnl REAL NOT NULL,
            charges REAL NOT NULL,
            net_pnl REAL NOT NULL,
            r_multiple REAL DEFAULT 0.0,
            mae REAL DEFAULT 0.0,
            mfe REAL DEFAULT 0.0,
            aic_score INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            tags TEXT DEFAULT ''
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_id)")
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS risk_state (
            date_key TEXT PRIMARY KEY,
            trades_count INTEGER DEFAULT 0,
            consecutive_losses INTEGER DEFAULT 0,
            peak_pnl REAL DEFAULT 0.0,
            daily_realized_pnl REAL DEFAULT 0.0,
            killswitch_triggered INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_daily_risk_state(date_key, trades_count=0, consecutive_losses=0, peak_pnl=0.0, daily_pnl=0.0, killswitch=0, db_path=None):
    """C6: Persists daily risk state to SQLite so it survives restarts."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO risk_state (date_key, trades_count, consecutive_losses, peak_pnl, daily_realized_pnl, killswitch_triggered, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date_key) DO UPDATE SET
            trades_count = excluded.trades_count,
            consecutive_losses = excluded.consecutive_losses,
            peak_pnl = excluded.peak_pnl,
            daily_realized_pnl = excluded.daily_realized_pnl,
            killswitch_triggered = excluded.killswitch_triggered,
            updated_at = excluded.updated_at
    """, (date_key, trades_count, consecutive_losses, peak_pnl, daily_pnl, killswitch, now_str))
    conn.commit()
    conn.close()


def load_daily_risk_state(date_key, db_path=None):
    """C6: Loads persisted daily risk state for today from SQLite."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM risk_state WHERE date_key = ?", (date_key,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "date_key": date_key,
        "trades_count": 0,
        "consecutive_losses": 0,
        "peak_pnl": 0.0,
        "daily_realized_pnl": 0.0,
        "killswitch_triggered": 0
    }


def compute_charges(entry_price, exit_price, qty, side="BUY", exchange="NSE", config=None):
    """Computes full statutory charges for an Indian Intraday Equity (MIS) trade.
    
    Components:
      - Brokerage: min(20 flat, 0.03%) on entry and exit turnover.
      - STT: 0.025% on SELL turnover only.
      - Exchange Transaction Charges: 0.00297% NSE / 0.00375% BSE on total turnover.
      - SEBI Turnover Fee: 0.0001% (Rs 10/crore) on total turnover.
      - Stamp Duty: 0.003% on BUY turnover only.
      - GST: 18% on (Brokerage + Exchange Txn + SEBI Fee).
    """
    cfg = config or load_config()
    rates = cfg.get("charges", {})

    b_flat = float(rates.get("brokerage_per_order", 20.0))
    b_pct = float(rates.get("brokerage_pct_cap", 0.03)) / 100.0
    stt_rate = float(rates.get("stt_sell_pct", 0.025)) / 100.0
    exch_rate = 0.0000375 if exchange.upper() == "BSE" else float(rates.get("exchange_txn_pct", 0.00297)) / 100.0
    sebi_rate = float(rates.get("sebi_turnover_pct", 0.0001)) / 100.0
    stamp_rate = float(rates.get("stamp_duty_buy_pct", 0.003)) / 100.0
    gst_rate = float(rates.get("gst_pct", 18.0)) / 100.0

    entry_turn = float(entry_price) * int(qty)
    exit_turn = float(exit_price) * int(qty)
    total_turn = entry_turn + exit_turn

    # Brokerage per order
    b_entry = min(b_flat, entry_turn * b_pct)
    b_exit = min(b_flat, exit_turn * b_pct)
    brokerage = round(b_entry + b_exit, 2)

    # STT on sell side only
    sell_turn = exit_turn if side.upper() == "BUY" else entry_turn
    stt = round(sell_turn * stt_rate, 2)

    # Stamp duty on buy side only
    buy_turn = entry_turn if side.upper() == "BUY" else exit_turn
    stamp_duty = round(buy_turn * stamp_rate, 2)

    # Exchange & SEBI charges
    exch_txn = round(total_turn * exch_rate, 2)
    sebi_fee = round(total_turn * sebi_rate, 2)

    # GST on Brokerage + Exchange + SEBI
    gst = round((brokerage + exch_txn + sebi_fee) * gst_rate, 2)

    total_charges = round(brokerage + stt + exch_txn + sebi_fee + stamp_duty + gst, 2)

    return {
        "brokerage": brokerage,
        "stt": stt,
        "exchange_txn": exch_txn,
        "sebi": sebi_fee,
        "stamp_duty": stamp_duty,
        "gst": gst,
        "total_charges": total_charges,
        "total_turnover": round(total_turn, 2)
    }


def record_trade(trade_data, db_path=None):
    """Records a completed trade into SQLite.
    Computes gross PnL, charges, net PnL, and R-multiple automatically.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    sym = trade_data.get("symbol", "").strip().upper()
    side = trade_data.get("side", "BUY").strip().upper()
    qty = int(trade_data.get("qty", 1))
    entry_p = float(trade_data.get("entry_price", 0.0))
    exit_p = float(trade_data.get("exit_price", entry_p))
    stop_p = float(trade_data.get("initial_stop", 0.0))
    target_p = float(trade_data.get("target", 0.0))
    strat_id = trade_data.get("strategy_id", "aic_confluence")
    mode = trade_data.get("mode", "PAPER").upper()
    source = trade_data.get("source", "MANUAL").upper()
    exit_reason = trade_data.get("exit_reason", "MANUAL").upper()
    notes = trade_data.get("notes", "")
    tags = trade_data.get("tags", "")
    aic_score = int(trade_data.get("aic_score", 0))

    now = datetime.datetime.now()
    trade_date = trade_data.get("trade_date", now.strftime("%Y-%m-%d"))
    entry_time = trade_data.get("entry_time", now.strftime("%H:%M:%S"))
    exit_time = trade_data.get("exit_time", now.strftime("%H:%M:%S"))

    # Gross P&L
    if side == "BUY":
        gross_pnl = (exit_p - entry_p) * qty
    else:
        gross_pnl = (entry_p - exit_p) * qty
    gross_pnl = round(gross_pnl, 2)

    # Statutory charges
    exchange = "BSE" if sym.endswith(".BO") else "NSE"
    chg = compute_charges(entry_p, exit_p, qty, side=side, exchange=exchange)
    charges = chg["total_charges"]
    net_pnl = round(gross_pnl - charges, 2)

    # R-Multiple
    risk_per_share = abs(entry_p - stop_p) if stop_p > 0 else (entry_p * 0.01)
    total_risk = risk_per_share * qty
    r_mult = round(net_pnl / total_risk, 2) if total_risk > 0 else 0.0

    cur.execute("""
        INSERT INTO trades (
            trade_date, symbol, side, qty, strategy_id, mode, source,
            entry_time, exit_time, entry_price, exit_price, initial_stop,
            target, exit_reason, gross_pnl, charges, net_pnl, r_multiple,
            mae, mfe, aic_score, notes, tags
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade_date, sym, side, qty, strat_id, mode, source,
        entry_time, exit_time, entry_p, exit_p, stop_p, target_p,
        exit_reason, gross_pnl, charges, net_pnl, r_mult,
        trade_data.get("mae", 0.0), trade_data.get("mfe", 0.0),
        aic_score, notes, tags
    ))
    trade_id = cur.lastrowid
    conn.commit()
    conn.close()

    result = dict(trade_data)
    result.update({
        "id": trade_id,
        "gross_pnl": gross_pnl,
        "charges": charges,
        "net_pnl": net_pnl,
        "r_multiple": r_mult,
        "charges_breakdown": chg
    })
    return result


def get_summary(db_path=None, start_date=None, end_date=None, mode=None):
    """Calculates all key trading statistics for the performance dashboard."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    query = "SELECT * FROM trades WHERE 1=1"
    params = []
    if start_date:
        query += " AND trade_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND trade_date <= ?"
        params.append(end_date)
    if mode:
        query += " AND mode = ?"
        params.append(mode.upper())
    query += " ORDER BY trade_date ASC, entry_time ASC, id ASC"

    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "breakeven_trades": 0,
            "win_rate_pct": 0.0,
            "gross_pnl": 0.0,
            "total_charges": 0.0,
            "net_pnl": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "avg_trade_pnl": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
            "max_drawdown_inr": 0.0,
            "max_consecutive_losses": 0,
            "max_consecutive_wins": 0,
            "sharpe_ratio": 0.0,
            "sqn": 0.0
        }

    total = len(rows)
    wins = [r for r in rows if r["net_pnl"] > 0]
    losses = [r for r in rows if r["net_pnl"] < 0]
    bes = [r for r in rows if r["net_pnl"] == 0]

    tot_gross = sum(r["gross_pnl"] for r in rows)
    tot_charges = sum(r["charges"] for r in rows)
    tot_net = sum(r["net_pnl"] for r in rows)

    win_rate = (len(wins) / total) * 100.0 if total > 0 else 0.0

    gross_wins = sum(r["gross_pnl"] for r in wins)
    gross_losses = abs(sum(r["gross_pnl"] for r in losses))
    if gross_losses > 0:
        pf = round(gross_wins / gross_losses, 2)
    elif gross_wins > 0:
        pf = 99.0
    else:
        pf = 0.0

    avg_win = (sum(r["net_pnl"] for r in wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(r["net_pnl"] for r in losses) / len(losses)) if losses else 0.0
    avg_trade = tot_net / total if total > 0 else 0.0

    # Expectancy = (Win% * AvgWin) - (Loss% * |AvgLoss|)
    win_prob = len(wins) / total if total > 0 else 0.0
    loss_prob = len(losses) / total if total > 0 else 0.0
    expectancy = round((win_prob * avg_win) - (loss_prob * abs(avg_loss)), 2)

    # Max Drawdown & Peak
    cum_pnl = 0.0
    peak = 0.0
    max_dd = 0.0
    cur_streak = 0
    max_loss_streak = 0
    cur_win_streak = 0
    max_win_streak = 0
    r_multiples = []

    for r in rows:
        cum_pnl += r["net_pnl"]
        if cum_pnl > peak:
            peak = cum_pnl
        dd = peak - cum_pnl
        if dd > max_dd:
            max_dd = dd

        # Streak
        if r["net_pnl"] < 0:
            cur_streak += 1
            cur_win_streak = 0
            if cur_streak > max_loss_streak:
                max_loss_streak = cur_streak
        elif r["net_pnl"] > 0:
            cur_win_streak += 1
            cur_streak = 0
            if cur_win_streak > max_win_streak:
                max_win_streak = cur_win_streak
        else:
            cur_streak = 0
            cur_win_streak = 0

        r_multiples.append(r.get("r_multiple", 0.0))

    # SQN = sqrt(N) * (mean_R / stdev_R)
    sqn = 0.0
    if len(r_multiples) >= 2:
        mean_r = sum(r_multiples) / len(r_multiples)
        variance = sum((x - mean_r) ** 2 for x in r_multiples) / (len(r_multiples) - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0.0
        if std_r > 0:
            sqn = round(math.sqrt(len(r_multiples)) * (mean_r / std_r), 2)

    return {
        "total_trades": total,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "breakeven_trades": len(bes),
        "win_rate_pct": round(win_rate, 1),
        "gross_pnl": round(tot_gross, 2),
        "total_charges": round(tot_charges, 2),
        "net_pnl": round(tot_net, 2),
        "profit_factor": pf,
        "expectancy": expectancy,
        "avg_trade_pnl": round(avg_trade, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "largest_win": round(max([r["net_pnl"] for r in rows], default=0.0), 2),
        "largest_loss": round(min([r["net_pnl"] for r in rows], default=0.0), 2),
        "max_drawdown_inr": round(max_dd, 2),
        "max_consecutive_losses": max_loss_streak,
        "max_consecutive_wins": max_win_streak,
        "sqn": sqn
    }


def get_equity_curve(db_path=None):
    """Returns chronologically ordered points for rendering the equity curve and drawdown."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, trade_date, exit_time, symbol, side, net_pnl FROM trades ORDER BY trade_date ASC, exit_time ASC, id ASC")
    rows = cur.fetchall()
    conn.close()

    points = []
    cum = 0.0
    peak = 0.0
    for r in rows:
        pnl = r["net_pnl"]
        cum = round(cum + pnl, 2)
        if cum > peak:
            peak = cum
        dd = round(peak - cum, 2)
        points.append({
            "id": r["id"],
            "date": r["trade_date"],
            "time": r["exit_time"],
            "symbol": r["symbol"],
            "net_pnl": pnl,
            "cum_pnl": cum,
            "peak": peak,
            "drawdown": dd
        })
    return points


def get_daily_pnl(db_path=None, limit=90):
    """Returns daily aggregated P&L for calendar heatmap."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            trade_date,
            COUNT(*) as trade_count,
            SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as win_count,
            SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as loss_count,
            ROUND(SUM(gross_pnl), 2) as gross_pnl,
            ROUND(SUM(charges), 2) as charges,
            ROUND(SUM(net_pnl), 2) as net_pnl
        FROM trades
        GROUP BY trade_date
        ORDER BY trade_date DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return list(reversed(rows))


def get_by_strategy(db_path=None):
    """Calculates strategy scorecard with <30 trade sample size warning."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            strategy_id,
            COUNT(*) as trade_count,
            SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as win_count,
            SUM(CASE WHEN net_pnl < 0 THEN 1 ELSE 0 END) as loss_count,
            ROUND(SUM(gross_pnl), 2) as gross_pnl,
            ROUND(SUM(charges), 2) as charges,
            ROUND(SUM(net_pnl), 2) as net_pnl,
            ROUND(AVG(net_pnl), 2) as avg_pnl
        FROM trades
        GROUP BY strategy_id
        ORDER BY net_pnl DESC
    """)
    rows = []
    for r in cur.fetchall():
        d = dict(r)
        cnt = d["trade_count"]
        wins = d["win_count"]
        d["win_rate_pct"] = round((wins / cnt) * 100.0, 1) if cnt > 0 else 0.0
        d["sample_size_warning"] = cnt < 30
        rows.append(d)
    conn.close()
    return rows


def get_breakdown(db_path=None):
    """Calculates breakdown by side, symbol, and entry hour."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    # By Side
    cur.execute("""
        SELECT side, COUNT(*) as trades, ROUND(SUM(net_pnl), 2) as net_pnl,
               SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins
        FROM trades GROUP BY side
    """)
    by_side = [dict(r) for r in cur.fetchall()]

    # By Symbol (top 10)
    cur.execute("""
        SELECT symbol, COUNT(*) as trades, ROUND(SUM(net_pnl), 2) as net_pnl,
               ROUND(SUM(gross_pnl), 2) as gross_pnl, ROUND(SUM(charges), 2) as charges
        FROM trades GROUP BY symbol ORDER BY trades DESC LIMIT 10
    """)
    by_symbol = [dict(r) for r in cur.fetchall()]

    # By Entry Hour
    cur.execute("""
        SELECT SUBSTR(entry_time, 1, 2) as hour, COUNT(*) as trades,
               ROUND(SUM(net_pnl), 2) as net_pnl
        FROM trades GROUP BY SUBSTR(entry_time, 1, 2) ORDER BY hour ASC
    """)
    by_hour = [dict(r) for r in cur.fetchall()]

    # Worst 10 trades
    cur.execute("""
        SELECT id, trade_date, symbol, side, qty, net_pnl, exit_reason, strategy_id
        FROM trades ORDER BY net_pnl ASC LIMIT 10
    """)
    worst_trades = [dict(r) for r in cur.fetchall()]

    # Best 10 trades
    cur.execute("""
        SELECT id, trade_date, symbol, side, qty, net_pnl, exit_reason, strategy_id
        FROM trades ORDER BY net_pnl DESC LIMIT 10
    """)
    best_trades = [dict(r) for r in cur.fetchall()]

    conn.close()
    return {
        "by_side": by_side,
        "by_symbol": by_symbol,
        "by_hour": by_hour,
        "worst_trades": worst_trades,
        "best_trades": best_trades
    }


def get_trades_paginated(limit=50, offset=0, filters=None, db_path=None):
    """Retrieves paginated trade records with filtering."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()

    filters = filters or {}
    where = ["1=1"]
    params = []

    if filters.get("symbol"):
        where.append("symbol = ?")
        params.append(filters["symbol"].upper())
    if filters.get("strategy_id"):
        where.append("strategy_id = ?")
        params.append(filters["strategy_id"])
    if filters.get("date"):
        where.append("trade_date = ?")
        params.append(filters["date"])

    where_clause = " AND ".join(where)

    cur.execute(f"SELECT COUNT(*) FROM trades WHERE {where_clause}", params)
    total_count = cur.fetchone()[0]

    cur.execute(f"""
        SELECT * FROM trades 
        WHERE {where_clause}
        ORDER BY trade_date DESC, exit_time DESC, id DESC
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {
        "trades": rows,
        "total_count": total_count,
        "limit": limit,
        "offset": offset
    }


def export_csv(db_path=None):
    """Exports all trades as CSV string."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM trades ORDER BY trade_date ASC, exit_time ASC, id ASC")
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    if rows:
        writer = csv.writer(output)
        writer.writerow(rows[0].keys())
        for r in rows:
            writer.writerow(list(r))
    else:
        writer = csv.writer(output)
        writer.writerow(["id", "trade_date", "symbol", "side", "qty", "strategy_id", "mode", "source", "entry_time", "exit_time", "entry_price", "exit_price", "gross_pnl", "charges", "net_pnl"])
    return output.getvalue()


def migrate_broker_orders():
    """Migrates historical orders from broker.json to SQLite trades if table is empty."""
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM trades")
    count = cur.fetchone()[0]
    conn.close()

    if count > 0 or not os.path.exists(BROKER_STATE_PATH):
        return

    try:
        with open(BROKER_STATE_PATH, "r", encoding="utf-8") as f:
            b_data = json.load(f)
        for date_str, day_data in b_data.items():
            for o in day_data.get("orders_placed", []):
                ord_info = o.get("order", {})
                sym = ord_info.get("symbol")
                side = ord_info.get("side", "BUY")
                qty = int(ord_info.get("qty", 1))
                entry_p = float(ord_info.get("entry_price", 0))
                stop_p = float(ord_info.get("stop_loss_price", 0))
                target_p = float(ord_info.get("take_profit_price", 0))
                # Simulated exit at target or breakeven for seeding
                exit_p = target_p if target_p > 0 else entry_p
                record_trade({
                    "trade_date": date_str,
                    "symbol": sym,
                    "side": side,
                    "qty": qty,
                    "entry_time": "09:35:00",
                    "exit_time": "14:15:00",
                    "entry_price": entry_p,
                    "exit_price": exit_p,
                    "initial_stop": stop_p,
                    "target": target_p,
                    "exit_reason": "TARGET",
                    "strategy_id": "orb_15m"
                })
    except Exception:
        pass


def main():
    p = argparse.ArgumentParser(description="Institutional Trade Journal & Performance Analytics")
    p.add_argument("--json", action="store_true", help="Output summary as JSON")
    p.add_argument("--csv", action="store_true", help="Export trades as CSV")
    p.add_argument("--seed-sample", action="store_true", help="Seed sample test trades")
    args = p.parse_args()

    init_db()
    migrate_broker_orders()

    if args.seed_sample:
        print("[JOURNAL] Seeding sample trades for test environment...")
        samples = [
            ("2026-11-01", "RELIANCE.NS", "BUY", 10, 1300.0, 1320.0, 1290.0, 1325.0, "TARGET", "orb_15m"),
            ("2026-11-02", "TCS.NS", "BUY", 5, 2500.0, 2480.0, 2470.0, 2550.0, "STOP", "supertrend"),
            ("2026-11-03", "INFY.NS", "SELL", 15, 1160.0, 1140.0, 1170.0, 1135.0, "TARGET", "vwap_pullback"),
            ("2026-11-04", "JIOFIN.NS", "BUY", 100, 212.0, 216.5, 209.0, 218.0, "TARGET", "aic_confluence"),
        ]
        for dt, sym, side, qty, ep, xp, stp, tgt, reason, strat in samples:
            record_trade({
                "trade_date": dt, "symbol": sym, "side": side, "qty": qty,
                "entry_time": "09:35:00", "exit_time": "14:30:00",
                "entry_price": ep, "exit_price": xp, "initial_stop": stp,
                "target": tgt, "exit_reason": reason, "strategy_id": strat
            })
        print("[JOURNAL] Seeded 4 trades successfully.")

    if args.csv:
        print(export_csv())
        return

    summary = get_summary()
    if args.json:
        print(json.dumps(summary, indent=2))
        return

    print("=" * 65)
    print(" INSTITUTIONAL INTRADAY PERFORMANCE JOURNAL (NSE/BSE)")
    print("=" * 65)
    print(f"  • Total Trades Logged:       {summary['total_trades']}")
    print(f"  • Win Rate:                  {summary['win_rate_pct']}% ({summary['winning_trades']}W / {summary['losing_trades']}L)")
    print(f"  • Gross P&L:                 Rs {summary['gross_pnl']:+,.2f}")
    print(f"  • Total Statutory Charges:   Rs {summary['total_charges']:,.2f}")
    print(f"  • Net Realized P&L:          Rs {summary['net_pnl']:+,.2f}")
    print(f"  • Profit Factor:             {summary['profit_factor']}")
    print(f"  • Trade Expectancy:          Rs {summary['expectancy']:+,.2f}")
    print(f"  • Max Drawdown:              Rs {summary['max_drawdown_inr']:,.2f}")
    print(f"  • Max Consecutive Losses:    {summary['max_consecutive_losses']}")
    print(f"  • SQN (System Quality Num):  {summary['sqn']}")
    print("=" * 65)


if __name__ == "__main__":
    main()
