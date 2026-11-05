#!/usr/bin/env python3
"""Unified Common Utilities for Vyapar AI (NSE / BSE).
Single source of truth for Indian market constants, session hours,
timezone math, ticker normalization, holidays, and JSON persistence.
Standard library only.
"""

import datetime
import json
import os
import sys

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


def load_json(path: str, default=None):
    """Safely loads a JSON file with utf-8-sig encoding."""
    if not os.path.exists(path):
        return default or {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default or {}


def save_json(path: str, data):
    """Safely serializes and saves data to a JSON file."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
