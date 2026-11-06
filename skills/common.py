#!/usr/bin/env python3
"""Unified Common Utilities for Vyapar AI (NSE / BSE).
Single source of truth for Indian market constants, session hours,
timezone math, ticker normalization, holidays, and JSON persistence.
Standard library only.
"""

import datetime
import hashlib
import http.cookiejar
import json
import os
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

# Configure UTF-8 on Windows console safely
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Thread lock for atomic shared state I/O
STATE_LOCK = threading.RLock()

# Official Indian Standard Time (+05:30)
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)
OPEN = datetime.time(9, 15)
CLOSE = datetime.time(15, 30)
FLAT_BY = datetime.time(15, 10)
ENTRY_CUTOFF = datetime.time(14, 45)
EXPIRY_CUTOFF = datetime.time(13, 45)

# Standard browser User-Agent for free data scraping
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (VyaparAI/1.0)"

# Official NSE Trading Holidays Calendar (2026 - 2027)
CALENDAR_YEARS = (2026, 2027)
NSE_HOLIDAYS = {
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-20": "Id-Ul-Fitr (Ramzan Id)",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-27": "Bakri Id (Id-Ul-Zuha)",
    "2026-06-26": "Muharram",
    "2026-08-15": "Independence Day",
    "2026-09-16": "Milad-un-Nabi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan (Muhurat Trading)",
    "2026-11-24": "Gurunanak Jayanti",
    "2026-12-25": "Christmas Day",
    "2027-01-26": "Republic Day",
    "2027-03-10": "Id-Ul-Fitr",
    "2027-03-22": "Holi",
    "2027-03-26": "Good Friday",
    "2027-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2027-05-01": "Maharashtra Day",
    "2027-05-17": "Bakri Id",
    "2027-06-16": "Muharram",
    "2027-08-15": "Independence Day",
    "2027-10-02": "Mahatma Gandhi Jayanti",
    "2027-10-09": "Dussehra",
    "2027-10-29": "Diwali Laxmi Pujan",
    "2027-11-14": "Gurunanak Jayanti",
    "2027-12-25": "Christmas Day",
}

# Unified Sector Map across Equities
SECTOR_MAP = {
    "HDFCBANK.NS": "BANKING", "ICICIBANK.NS": "BANKING", "SBIN.NS": "BANKING",
    "KOTAKBANK.NS": "BANKING", "AXISBANK.NS": "BANKING", "INDUSINDBK.NS": "BANKING",
    "TCS.NS": "IT", "INFY.NS": "IT", "HCLTECH.NS": "IT", "WIPRO.NS": "IT", "TECHM.NS": "IT",
    "TATAMOTORS.NS": "AUTO", "MARUTI.NS": "AUTO", "M&M.NS": "AUTO", "BAJAJ-AUTO.NS": "AUTO", "EICHERMOT.NS": "AUTO",
    "SUNPHARMA.NS": "PHARMA", "CIPLA.NS": "PHARMA", "DRREDDY.NS": "PHARMA", "DIVISLAB.NS": "PHARMA",
    "TATASTEEL.NS": "METAL", "JSWSTEEL.NS": "METAL", "HINDALCO.NS": "METAL",
    "RELIANCE.NS": "ENERGY", "ONGC.NS": "ENERGY", "BPCL.NS": "ENERGY", "COALINDIA.NS": "ENERGY",
    "JIOFIN.NS": "FINANCIALS", "HDFC.NS": "FINANCIALS", "BAJFINANCE.NS": "FINANCIALS", "LICI.NS": "FINANCIALS",
    "ITC.NS": "FMCG", "HINDUNILVR.NS": "FMCG", "NESTLEIND.NS": "FMCG",
    "BHARTIARTL.NS": "TELECOM", "LT.NS": "INFRA", "TITAN.NS": "CONSUMER",
    "NTPC.NS": "POWER", "POWERGRID.NS": "POWER", "ADANIENT.NS": "CONGLOMERATE"
}

# Known ETFs with 0.01 tick size
KNOWN_ETFS = {
    "NIFTYBEES.NS", "BANKBEES.NS", "GOLDBEES.NS", "ITBEES.NS", "JUNIORBEES.NS",
    "LIQUIDBEES.NS", "SILVERBEES.NS", "MON100.NS", "SETFNIF50.NS"
}

# Repository Root Resolution
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_path(rel_path: str) -> str:
    """Resolves path relative to repository root or current directory."""
    root_path = os.path.join(BASE_DIR, rel_path)
    return root_path if os.path.exists(root_path) else rel_path


def to_ist(utc: datetime.datetime) -> datetime.datetime:
    """Converts a UTC datetime to Indian Standard Time (IST / UTC+05:30)."""
    return utc.replace(tzinfo=None) + IST_OFFSET


def ist_to_utc(local: datetime.datetime) -> datetime.datetime:
    """Converts an IST local datetime back to UTC datetime."""
    return local.replace(tzinfo=None) - IST_OFFSET


def normalize_symbol(sym: str) -> str:
    """Normalizes symbol to standard Yahoo Finance format (defaults to .NS for NSE)."""
    s = sym.strip().upper()
    if s.startswith("^") or s.endswith(".NS") or s.endswith(".BO"):
        return s
    return s + ".NS"


def to_tv_symbol(sym: str) -> str:
    """Maps ticker to reliable TradingView embed symbol (BSE exchange fallback)."""
    if not sym:
        return "BSE:RELIANCE"
    s = sym.strip().upper()
    if ":" in s:
        return s
    if s == "^NSEI":
        return "NSE:NIFTY"
    if s == "^NSEBANK":
        return "NSE:BANKNIFTY"
    if s == "^BSESN":
        return "BSE:SENSEX"
    if s == "^INDIAVIX":
        return "NSE:INDIAVIX"
    base = s.replace(".NS", "").replace(".BO", "").strip()
    return f"BSE:{base}"


def get_tick_size(sym: str) -> float:
    """Returns official minimum price variation (tick size) for instrument."""
    norm = normalize_symbol(sym)
    if norm in KNOWN_ETFS or norm.endswith("BEES.NS") or norm.endswith("ETF.NS"):
        return 0.01
    return 0.05


def is_valid_tick(price: float, tick: float = 0.05) -> bool:
    """Validates if a price falls exactly on the exchange tick grid."""
    if price <= 0:
        return False
    # Using integer cents/paise arithmetic to eliminate floating-point precision issues
    price_cents = round(price * 100)
    tick_cents = round(tick * 100)
    return (price_cents % tick_cents) == 0


def compute_order_fingerprint(order: dict, trade_date: str = None) -> str:
    """Generates an immutable cryptographic fingerprint for an order including trade date and target."""
    sym = order.get("symbol", "")
    side = order.get("side", "BUY").upper()
    qty = order.get("qty", 1)
    entry = order.get("entry_price", 0.0)
    stop = order.get("stop_loss_price", 0.0)
    target = order.get("take_profit_price", 0.0)
    date_str = trade_date or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    raw = f"{sym}:{side}:{qty}:{entry}:{stop}:{target}:{date_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def load_json(path: str, default=None):
    """Safely loads a JSON file with utf-8-sig encoding under shared lock."""
    with STATE_LOCK:
        resolved = resolve_path(path)
        if not os.path.exists(resolved):
            return default if default is not None else {}
        try:
            with open(resolved, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}


def atomic_write_json(target_path, payload) -> None:
    """Atomically writes JSON to disk using a temp file and os.replace under STATE_LOCK."""
    with STATE_LOCK:
        resolved = resolve_path(str(target_path))
        p = Path(resolved)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(p.parent),
            prefix=f".{p.name}.",
            suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, str(p))
        except Exception:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
            raise


def save_json(path: str, data):
    """Atomically writes JSON file using a temp file and os.replace under shared lock."""
    atomic_write_json(path, data)


def create_nse_session_opener() -> urllib.request.OpenerDirector:
    """Initializes a standard-library urllib opener with primed NSE session cookies."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers = [
        ("User-Agent", UA),
        ("Accept", "application/json, text/plain, */*"),
        ("Accept-Language", "en-US,en;q=0.9"),
        ("Referer", "https://www.nseindia.com/"),
    ]
    opener.addheaders = headers
    try:
        req = urllib.request.Request("https://www.nseindia.com/", method="GET")
        with opener.open(req, timeout=10):
            pass
    except Exception:
        pass
    return opener


# =====================================================================
# Shared Trade State Management (broker.json)
# =====================================================================

DEFAULT_BROKER_STATE_FILE = "trader/state/broker.json"


def get_todays_trade_state(now_ist: datetime.datetime = None, broker_state_path: str = None) -> dict:
    """Returns today's active broker state containing trades_today and orders_placed."""
    path = broker_state_path or resolve_path(DEFAULT_BROKER_STATE_FILE)
    b_data = load_json(path, default={})
    if now_ist is None:
        now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
    d_str = now_ist.strftime("%Y-%m-%d")
    return b_data.get(d_str, {"trades_today": [], "orders_placed": []})


def record_placed_trade(order: dict, now_ist: datetime.datetime = None, broker_state_path: str = None) -> dict:
    """Records an executed or approved trade into the shared broker.json trade state."""
    path = broker_state_path or resolve_path(DEFAULT_BROKER_STATE_FILE)
    if now_ist is None:
        now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
    d_str = now_ist.strftime("%Y-%m-%d")

    with STATE_LOCK:
        b_data = load_json(path, default={})
        day_entry = b_data.setdefault(d_str, {"trades_today": [], "orders_placed": []})

        entry_p = float(order.get("entry_price", 0.0))
        stop_p = float(order.get("stop_loss_price", 0.0))
        qty = int(order.get("qty", 1))
        side = order.get("side", "BUY").upper()

        if side == "BUY":
            risk_per_share = max(0.0, entry_p - stop_p)
        else:
            risk_per_share = max(0.0, stop_p - entry_p)
        max_loss = round(risk_per_share * qty, 2)

        trade_record = {
            "symbol": order.get("symbol"),
            "side": side,
            "qty": qty,
            "entry_price": entry_p,
            "stop_loss_price": stop_p,
            "take_profit_price": order.get("take_profit_price", 0.0),
            "max_loss": max_loss,
            "strategy": order.get("strategy_id", "manual"),
            "status": "OPEN",
            "placed_at_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S")
        }
        day_entry["trades_today"].append(trade_record)
        day_entry["orders_placed"].append({
            "order": order,
            "fingerprint": compute_order_fingerprint(order, d_str),
            "placed_at_ist": now_ist.strftime("%H:%M:%S"),
            "status": "FILLED"
        })
        save_json(path, b_data)
        return trade_record


def record_closed_trade(symbol: str, exit_price: float, pnl: float, now_ist: datetime.datetime = None, broker_state_path: str = None) -> bool:
    """Updates the shared trade state when a position is closed, recording exit price and realized P&L."""
    path = broker_state_path or resolve_path(DEFAULT_BROKER_STATE_FILE)
    if now_ist is None:
        now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
    d_str = now_ist.strftime("%Y-%m-%d")

    with STATE_LOCK:
        b_data = load_json(path, default={})
        day_entry = b_data.get(d_str)
        if not day_entry:
            return False

        # Find the open trade for this symbol and mark closed
        for t in reversed(day_entry.get("trades_today", [])):
            if t.get("symbol") == symbol and t.get("status") == "OPEN":
                t["status"] = "CLOSED"
                t["exit_price"] = exit_price
                t["pnl"] = round(pnl, 2)
                t["closed_at_ist"] = now_ist.strftime("%Y-%m-%d %H:%M:%S")
                save_json(path, b_data)
                return True

        # If no open trade matched, record exit PnL record
        day_entry.setdefault("trades_today", []).append({
            "symbol": symbol,
            "status": "CLOSED",
            "exit_price": exit_price,
            "pnl": round(pnl, 2),
            "closed_at_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S")
        })
        save_json(path, b_data)
        return True


def normalize_holding(sym: str, raw_holding) -> dict:
    """Validates and enforces the universal holdings schema across broker and portfolio."""
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


