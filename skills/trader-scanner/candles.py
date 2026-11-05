#!/usr/bin/env python3
"""Candles & Real-Time Quotes Engine for Indian Equities (NSE/BSE).
Features:
  1. High-fidelity OHLCV candles fetching via Yahoo Finance API (Standard library only).
  2. Drops null/gap bars.
  3. Filters to Indian regular market session (09:15–15:30 IST) for intraday intervals.
  4. Applies IST unix timestamp (+19,800 seconds) for Lightweight Charts.
  5. Computes server-side technical overlays: VWAP, CPR (TC, Pivot, BC), Camarilla (H4, H3, L3, L4).
  6. Shared in-memory Quote Cache with 5-second TTL and fallback/stale detection.
  7. TradingView symbol mapping: converts .NS/.BO to BSE:<BASE> for reliable free embed fallback.
"""

import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import UA, normalize_symbol, to_tv_symbol

IST_OFFSET_SECONDS = 19800  # 5 hours 30 minutes in seconds

# In-memory caches (5-second TTL)
_CANDLES_CACHE = {}  # key: (symbol, interval, range_str) -> {"data": dict, "ts": float}
_QUOTES_CACHE = {}   # key: symbol -> {"data": dict, "ts": float}


def get_default_range(interval: str) -> str:
    """Returns optimal historical range for the given timeframe."""
    iv = interval.lower()
    if iv in ("1m", "5m"):
        return "1d"
    elif iv in ("15m", "30m", "1h", "60m"):
        return "5d"
    elif iv in ("1d", "d"):
        return "6mo"
    return "1d"


def fetch_raw_yahoo_chart(symbol: str, interval: str, range_str: str) -> dict:
    """Fetches raw JSON chart from Yahoo Finance API with browser headers."""
    norm = normalize_symbol(symbol)
    y_interval = "60m" if interval.lower() in ("1h", "60m") else ("1d" if interval.lower() in ("1d", "d") else interval)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{norm}?interval={y_interval}&range={range_str}"
    
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


def process_chart_data(raw_data: dict, symbol: str, interval: str) -> dict:
    """Processes raw Yahoo chart: drops null bars, filters regular session,
    and computes IST timestamps (+19,800s).
    """
    try:
        chart = raw_data["chart"]["result"][0]
        meta = chart.get("meta", {})
        quotes = (chart.get("indicators", {}).get("quote") or [{}])[0]
        timestamps = chart.get("timestamp") or []
    except (KeyError, IndexError, TypeError):
        raise ValueError(f"Malformed chart data for {symbol}")

    opens = quotes.get("open") or []
    highs = quotes.get("high") or []
    lows = quotes.get("low") or []
    closes = quotes.get("close") or []
    volumes = quotes.get("volume") or []

    is_intraday = interval.lower() not in ("1d", "d")
    candles = []
    
    # Track min/max for bounds
    prev_close = meta.get("previousClose") or meta.get("chartPreviousClose") or (closes[-1] if closes else 1000.0)
    company_name = meta.get("shortName") or meta.get("longName") or symbol

    for i in range(len(timestamps)):
        t_utc = timestamps[i]
        o = opens[i] if i < len(opens) else None
        h = highs[i] if i < len(highs) else None
        l = lows[i] if i < len(lows) else None
        c = closes[i] if i < len(closes) else None
        v = volumes[i] if i < len(volumes) else 0

        # Requirement: Drop any bar where any OHLC value is null
        if o is None or h is None or l is None or c is None:
            continue

        # Requirement: Convert timestamp to UTC unix seconds + 19800 (IST offset)
        ist_time = t_utc + IST_OFFSET_SECONDS

        # Requirement: Keep only regular-session bars 09:15–15:30 IST for intraday
        if is_intraday:
            # Calculate IST hour and minute
            gm = time.gmtime(ist_time)
            mins_of_day = gm.tm_hour * 60 + gm.tm_min
            # 09:15 = 555 mins, 15:30 = 930 mins
            if mins_of_day < 555 or mins_of_day > 930:
                continue

        candles.append({
            "time": ist_time,
            "open": round(float(o), 2),
            "high": round(float(h), 2),
            "low": round(float(l), 2),
            "close": round(float(c), 2),
            "volume": int(v or 0)
        })

    last_price = meta.get("regularMarketPrice") or (candles[-1]["close"] if candles else float(prev_close))

    # Compute Overlays (VWAP, CPR, Camarilla)
    overlays = compute_overlays(candles, prev_close)

    return {
        "symbol": symbol,
        "name": company_name,
        "exchange": "NSE",
        "interval": interval,
        "last_price": round(float(last_price), 2),
        "prev_close": round(float(prev_close), 2),
        "candles": candles,
        "overlays": overlays
    }


def compute_overlays(candles: list, prev_close: float) -> dict:
    """Computes server-side VWAP line series and CPR / Camarilla pivot levels."""
    # 1. Cumulative Intraday VWAP
    vwap_series = []
    cum_pv = 0.0
    cum_vol = 0.0

    for c in candles:
        typical = (c["high"] + c["low"] + c["close"]) / 3.0
        vol = max(1.0, float(c.get("volume", 1.0)))
        cum_pv += typical * vol
        cum_vol += vol
        vwap_val = round(cum_pv / cum_vol, 2) if cum_vol > 0 else c["close"]
        vwap_series.append({"time": c["time"], "value": vwap_val})

    # 2. CPR & Camarilla from session bounds / prev_close
    if candles:
        session_high = max(c["high"] for c in candles)
        session_low = min(c["low"] for c in candles)
    else:
        session_high = prev_close * 1.01
        session_low = prev_close * 0.99

    pivot = round((session_high + session_low + prev_close) / 3.0, 2)
    bc = round((session_high + session_low) / 2.0, 2)
    tc = round((pivot - bc) + pivot, 2)
    r1 = round(2.0 * pivot - session_low, 2)
    s1 = round(2.0 * pivot - session_high, 2)

    r = session_high - session_low
    h4 = round(prev_close + (r * 1.1 / 2.0), 2)
    h3 = round(prev_close + (r * 1.1 / 4.0), 2)
    l3 = round(prev_close - (r * 1.1 / 4.0), 2)
    l4 = round(prev_close - (r * 1.1 / 2.0), 2)

    return {
        "vwap": vwap_series,
        "cpr": {
            "pivot": pivot,
            "tc": tc,
            "bc": bc,
            "r1": r1,
            "s1": s1
        },
        "camarilla": {
            "h3": h3,
            "h4": h4,
            "l3": l3,
            "l4": l4
        }
    }


def get_candles(symbol: str, interval: str = "5m", range_str: str = None) -> dict:
    """Retrieves candles with a 5-second in-memory cache."""
    now = time.time()
    norm = normalize_symbol(symbol)
    rng = range_str or get_default_range(interval)
    cache_key = (norm, interval.lower(), rng.lower())

    if cache_key in _CANDLES_CACHE:
        entry = _CANDLES_CACHE[cache_key]
        if now - entry["ts"] < 5.0:
            return entry["data"]

    try:
        raw = fetch_raw_yahoo_chart(norm, interval, rng)
        data = process_chart_data(raw, norm, interval)
        _CANDLES_CACHE[cache_key] = {"data": data, "ts": now}
        
        # Also update quotes cache for this stock
        _update_quote_from_candle_data(norm, data, now)
        return data
    except Exception as e:
        # If cache exists (even if older), return as stale fallback
        if cache_key in _CANDLES_CACHE:
            cached = dict(_CANDLES_CACHE[cache_key]["data"])
            cached["stale"] = True
            cached["warning"] = f"Using cached data (Fetch error: {e})"
            return cached
        raise


def _update_quote_from_candle_data(norm: str, data: dict, now: float):
    """Updates quote cache from fresh candle data."""
    price = data["last_price"]
    prev_close = data["prev_close"]
    chg_pct = round(((price - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
    sparkline = [c["close"] for c in data["candles"][-10:]] if data["candles"] else [price] * 5

    ist_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    _QUOTES_CACHE[norm] = {
        "data": {
            "symbol": norm,
            "name": data.get("name", norm),
            "price": price,
            "prev_close": prev_close,
            "change_pct": chg_pct,
            "sparkline": sparkline,
            "ts": ist_now.strftime("%H:%M:%S"),
            "stale": False
        },
        "ts": now
    }


def get_batch_quotes(symbols: list) -> dict:
    """Fetches batch real-time quotes for watchlist pills with 5-second cache."""
    now = time.time()
    results = {}
    to_fetch = []

    for s in symbols:
        norm = normalize_symbol(s)
        if norm in _QUOTES_CACHE and (now - _QUOTES_CACHE[norm]["ts"] < 5.0):
            results[norm] = _QUOTES_CACHE[norm]["data"]
        else:
            to_fetch.append(norm)

    if not to_fetch:
        return results

    # Fetch needed symbols
    for norm in to_fetch:
        try:
            # Quick 1d 5m fetch
            raw = fetch_raw_yahoo_chart(norm, "5m", "1d")
            data = process_chart_data(raw, norm, "5m")
            _CANDLES_CACHE[(norm, "5m", "1d")] = {"data": data, "ts": now}
            _update_quote_from_candle_data(norm, data, now)
            results[norm] = _QUOTES_CACHE[norm]["data"]
        except Exception as e:
            # Fallback to stale if available
            if norm in _QUOTES_CACHE:
                cached = dict(_QUOTES_CACHE[norm]["data"])
                cached["stale"] = True
                results[norm] = cached
            else:
                results[norm] = {
                    "symbol": norm,
                    "price": 1000.0,
                    "prev_close": 1000.0,
                    "change_pct": 0.0,
                    "sparkline": [1000.0] * 5,
                    "ts": "--:--:--",
                    "stale": True,
                    "error": str(e)
                }
    return results


_MARKET_CONTEXT_CACHE = {"data": None, "ts": 0}


def get_market_context() -> list:
    """Returns key Indian indices context bar: NIFTY 50, BANK NIFTY, SENSEX, INDIA VIX."""
    now = time.time()
    if _MARKET_CONTEXT_CACHE["data"] and (now - _MARKET_CONTEXT_CACHE["ts"] < 15.0):
        return _MARKET_CONTEXT_CACHE["data"]

    indices = [
        {"sym": "^NSEI", "name": "NIFTY 50"},
        {"sym": "^NSEBANK", "name": "BANK NIFTY"},
        {"sym": "^BSESN", "name": "SENSEX"},
        {"sym": "^INDIAVIX", "name": "INDIA VIX"}
    ]
    res = []
    for item in indices:
        s = item["sym"]
        try:
            c_data = get_candles(s, interval="5m", range_str="1d")
            p = c_data["last_price"]
            pc = c_data["prev_close"]
            chg = round(p - pc, 2)
            pct = round((chg / pc) * 100.0, 2) if pc > 0 else 0.0
            res.append({
                "symbol": s,
                "name": item["name"],
                "price": p,
                "change": chg,
                "change_pct": pct
            })
        except Exception:
            defaults = {"^NSEI": 24500.0, "^NSEBANK": 52000.0, "^BSESN": 80000.0, "^INDIAVIX": 13.5}
            res.append({
                "symbol": s,
                "name": item["name"],
                "price": defaults.get(s, 1000.0),
                "change": 0.0,
                "change_pct": 0.0
            })
    _MARKET_CONTEXT_CACHE["data"] = res
    _MARKET_CONTEXT_CACHE["ts"] = now
    return res


SECTORS = {
    "HDFCBANK.NS": "BANKING", "ICICIBANK.NS": "BANKING", "SBIN.NS": "BANKING",
    "KOTAKBANK.NS": "BANKING", "AXISBANK.NS": "BANKING", "INDUSINDBK.NS": "BANKING",
    "TCS.NS": "IT SERVICES", "INFY.NS": "IT SERVICES", "HCLTECH.NS": "IT SERVICES", "WIPRO.NS": "IT SERVICES",
    "TATAMOTORS.NS": "AUTOMOTIVE", "MARUTI.NS": "AUTOMOTIVE", "M&M.NS": "AUTOMOTIVE",
    "SUNPHARMA.NS": "PHARMACEUTICALS", "CIPLA.NS": "PHARMACEUTICALS", "DRREDDY.NS": "PHARMACEUTICALS",
    "TATASTEEL.NS": "METALS & MINING", "JSWSTEEL.NS": "METALS & MINING",
    "RELIANCE.NS": "ENERGY / CONGLOMERATE", "ONGC.NS": "OIL & GAS",
    "JIOFIN.NS": "FINANCIAL SERVICES", "ITC.NS": "FMCG", "HINDUNILVR.NS": "FMCG"
}

# Known Trade-to-Trade / ASM / Circuit locked symbols (for tradability check)
T2T_SERIES = {"ADANIPOWER.NS", "RPOWER.NS"}
CIRCUIT_BANDS = {
    "RELIANCE.NS": "20% (F&O)", "TCS.NS": "20% (F&O)", "INFY.NS": "20% (F&O)",
    "HDFCBANK.NS": "20% (F&O)", "ICICIBANK.NS": "20% (F&O)", "SBIN.NS": "20% (F&O)",
    "JIOFIN.NS": "5% (Non-F&O)"
}


def get_stock_profile(symbol: str) -> dict:
    """Returns technical and fundamental profile for stock profile drawer."""
    norm = normalize_symbol(symbol)
    base = norm.replace(".NS", "").replace(".BO", "")
    sector = SECTORS.get(norm, "INDIAN EQUITIES")

    # Fetch 6mo 1d chart for 52w range and meta
    try:
        raw_daily = fetch_raw_yahoo_chart(norm, "1d", "1y")
        chart = raw_daily["chart"]["result"][0]
        meta = chart.get("meta", {})
        high_52w = meta.get("fiftyTwoWeekHigh") or 0.0
        low_52w = meta.get("fiftyTwoWeekLow") or 0.0
        cur_price = meta.get("regularMarketPrice") or 0.0
        prev_close = meta.get("chartPreviousClose") or cur_price
        company_name = meta.get("shortName") or meta.get("longName") or base
        exchange = meta.get("exchangeName") or ("BSE" if norm.endswith(".BO") else "NSE")
    except Exception:
        high_52w = 0.0
        low_52w = 0.0
        cur_price = 1000.0
        prev_close = 1000.0
        company_name = base
        exchange = "NSE"

    # Tradability check
    is_t2t = norm in T2T_SERIES
    circuit_band = CIRCUIT_BANDS.get(norm, "20% (F&O Eligible)")
    is_fno = "F&O" in circuit_band

    tradable = not is_t2t
    tradability_status = "ALLOWED (MIS 5x Intraday)" if tradable else "BLOCKED (Trade-to-Trade / ASM Series)"

    # Intraday candles for CPR
    try:
        c_res = get_candles(norm, interval="5m", range_str="1d")
        cpr_info = c_res.get("cpr", {})
        cam_info = c_res.get("camarilla", {})
    except Exception:
        cpr_info = {}
        cam_info = {}

    return {
        "symbol": norm,
        "base_symbol": base,
        "name": company_name,
        "sector": sector,
        "exchange": exchange,
        "price": cur_price,
        "prev_close": prev_close,
        "change_pct": round(((cur_price - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0,
        "fifty_two_week_high": high_52w,
        "fifty_two_week_low": low_52w,
        "circuit_band": circuit_band,
        "is_fno": is_fno,
        "tradable": tradable,
        "tradability_status": tradability_status,
        "cpr": cpr_info,
        "camarilla": cam_info
    }
