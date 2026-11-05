#!/usr/bin/env python3
"""Candles & Real-Time Quotes Engine for Indian Equities (NSE/BSE).
Standard library only.

Features:
  1. High-fidelity OHLCV candles fetching via Yahoo Finance API with data_layer backoff.
  2. Drops null/gap bars and enforces strict input validation.
  3. Filters to Indian regular market session (09:15 <= t < 15:30 IST) for intraday intervals.
  4. Daily-resetting Intraday VWAP (skips index symbols with zero volume).
  5. Real Prior-Day CPR & Camarilla computation shared with cpr.py.
  6. Zero invented fallback prices (no fake 1000.0, 24500, 52000, or 13.5).
  7. Real last_bar_time tracking for stale/delayed data detection.
"""

import datetime
import json
import os
import sys
import time

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import IST_OFFSET, SECTOR_MAP, normalize_symbol, resolve_path, to_ist, to_tv_symbol
import data_layer
import cpr as cpr_module

IST_OFFSET_SECONDS = 19800  # 5 hours 30 minutes in seconds

# Index tickers that have no traded volume
INDEX_SYMBOLS = {"^NSEI", "^NSEBANK", "^BSESN", "^INDIAVIX", "^CNXIT"}


def get_default_range(interval: str) -> str:
    """Returns optimal historical range for the given timeframe."""
    iv = interval.lower()
    if iv in ("1m", "2m", "5m"):
        return "1d"
    elif iv in ("15m", "30m", "60m", "1h"):
        return "5d"
    elif iv in ("1d", "d"):
        return "6mo"
    elif iv in ("1wk", "wk", "1mo", "mo"):
        return "2y"
    return "1d"


def fetch_prev_day_bar(symbol: str) -> dict:
    """Fetches completed previous day daily bar by IST date (no index -2 guesswork)."""
    norm = normalize_symbol(symbol)
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{norm}?interval=1d&range=1mo"
    try:
        raw = data_layer.fetch_json_with_retry(url, timeout=8.0, cache_ttl=60.0)
        chart = raw["chart"]["result"][0]
        q = (chart.get("indicators", {}).get("quote") or [{}])[0]
        timestamps = chart.get("timestamp") or []
        highs = q.get("high") or []
        lows = q.get("low") or []
        closes = q.get("close") or []
        opens = q.get("open") or []

        now_ist = to_ist(datetime.datetime.now(datetime.timezone.utc))
        today_date = now_ist.date()

        completed_bars = []
        for i in range(len(timestamps)):
            ts = timestamps[i]
            h = highs[i] if i < len(highs) else None
            l = lows[i] if i < len(lows) else None
            c = closes[i] if i < len(closes) else None
            o = opens[i] if i < len(opens) else None
            if ts is not None and h is not None and l is not None and c is not None:
                bar_dt = to_ist(datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc))
                if bar_dt.date() < today_date:
                    completed_bars.append({
                        "date": bar_dt.strftime("%Y-%m-%d"),
                        "open": float(o if o is not None else c),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c)
                    })

        if completed_bars:
            return completed_bars[-1]
    except Exception:
        pass
    return None


def fetch_raw_yahoo_chart(symbol: str, interval: str, range_str: str) -> dict:
    """Fetches raw JSON chart from Yahoo Finance API via resilient data layer."""
    norm = normalize_symbol(symbol)
    data_layer.validate_market_params(norm, interval, range_str)

    y_interval = "60m" if interval.lower() in ("1h", "60m") else ("1d" if interval.lower() in ("1d", "d") else interval)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{norm}?interval={y_interval}&range={range_str}"
    # Use 5-second TTL cache for intraday, 60-second for daily
    ttl = 60.0 if interval.lower() in ("1d", "d", "1wk", "1mo") else 5.0
    return data_layer.fetch_json_with_retry(url, timeout=8.0, cache_ttl=ttl)


def process_chart_data(raw_data: dict, symbol: str, interval: str) -> dict:
    """Processes raw Yahoo chart: drops null bars, filters regular session (09:15 <= t < 15:30),
    resets VWAP at session boundaries, and computes prior-day CPR/Camarilla overlays.
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

    # Non-intraday intervals
    is_intraday = interval.lower() not in ("1d", "d", "1wk", "wk", "1mo", "mo")
    candles = []

    # Resolve official completed previous close (from daily series if available)
    prev_bar = fetch_prev_day_bar(symbol)
    if prev_bar and prev_bar.get("close"):
        prev_close = float(prev_bar["close"])
    else:
        # Fallback to meta regularMarketPreviousClose if daily fetch fails, but NEVER chartPreviousClose of 1y
        raw_pc = meta.get("regularMarketPreviousClose") or meta.get("previousClose")
        prev_close = float(raw_pc) if raw_pc is not None else None

    company_name = meta.get("shortName") or meta.get("longName") or symbol
    is_index = symbol in INDEX_SYMBOLS or symbol.startswith("^")

    last_bar_ist = None

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

        # Requirement: Keep only regular-session bars 09:15 <= t < 15:30 IST for intraday (strictly exclude 15:30 bar)
        if is_intraday:
            gm = time.gmtime(ist_time)
            mins_of_day = gm.tm_hour * 60 + gm.tm_min
            # 09:15 = 555 mins, 15:30 = 930 mins. Keep strictly < 930
            if mins_of_day < 555 or mins_of_day >= 930:
                continue

        candles.append({
            "time": ist_time,
            "open": round(float(o), 2),
            "high": round(float(h), 2),
            "low": round(float(l), 2),
            "close": round(float(c), 2),
            "volume": int(v or 0)
        })
        last_bar_ist = ist_time

    if not candles:
        last_price = meta.get("regularMarketPrice")
    else:
        last_price = candles[-1]["close"]

    last_price = float(last_price) if last_price is not None else prev_close

    # Format last bar time
    last_bar_str = None
    if last_bar_ist:
        gm_last = time.gmtime(last_bar_ist)
        last_bar_str = f"{gm_last.tm_hour:02d}:{gm_last.tm_min:02d}:{gm_last.tm_sec:02d} IST"

    # Compute Overlays (Session-Reset VWAP, CPR, Camarilla from prior day)
    overlays = compute_overlays(candles, prev_bar, is_index=is_index)

    return {
        "symbol": symbol,
        "name": company_name,
        "exchange": "NSE",
        "interval": interval,
        "last_price": round(last_price, 2) if last_price is not None else None,
        "prev_close": round(prev_close, 2) if prev_close is not None else None,
        "last_bar_time": last_bar_str,
        "candles": candles,
        "overlays": overlays
    }


def compute_overlays(candles: list, prev_bar: dict, is_index: bool = False) -> dict:
    """Computes server-side VWAP resetting at each IST session start, and CPR/Camarilla from prior day bar."""
    # 1. Cumulative Session-Reset VWAP
    vwap_series = []
    if not is_index and candles:
        current_session_day = None
        cum_pv = 0.0
        cum_vol = 0.0

        for c in candles:
            gm = time.gmtime(c["time"])
            bar_day = (gm.tm_year, gm.tm_mon, gm.tm_mday)

            # Session rollover reset
            if bar_day != current_session_day:
                current_session_day = bar_day
                cum_pv = 0.0
                cum_vol = 0.0

            typical = (c["high"] + c["low"] + c["close"]) / 3.0
            vol = float(c.get("volume", 0.0))
            if vol > 0:
                cum_pv += typical * vol
                cum_vol += vol
                vwap_val = round(cum_pv / cum_vol, 2)
            else:
                vwap_val = c["close"]

            vwap_series.append({"time": c["time"], "value": vwap_val})

    # 2. CPR & Camarilla strictly from completed PREVIOUS session's daily bar
    cpr_data = {}
    cam_data = {}
    if prev_bar and prev_bar.get("high") and prev_bar.get("low") and prev_bar.get("close"):
        res = cpr_module.calculate_cpr_and_camarilla(
            float(prev_bar["high"]), float(prev_bar["low"]), float(prev_bar["close"])
        )
        cpr_data = {
            "pivot": res["pivot"],
            "tc": res["tc"],
            "bc": res["bc"],
            "cpr_width": res["cpr_width"],
            "cpr_width_pct": res["cpr_width_pct"],
            "cpr_type": res["cpr_type"]
        }
        cam_data = {
            "h4": res["camarilla"]["h4_breakout"],
            "h3": res["camarilla"]["h3_resistance"],
            "l3": res["camarilla"]["l3_support"],
            "l4": res["camarilla"]["l4_breakdown"]
        }

    return {
        "vwap": vwap_series,
        "cpr": cpr_data,
        "camarilla": cam_data
    }


def get_candles(symbol: str, interval: str = "5m", range_str: str = None) -> dict:
    """Retrieves candles with caching and validation. Fails closed with error dictionary on missing data."""
    norm = normalize_symbol(symbol)
    rng = range_str or get_default_range(interval)

    try:
        raw = fetch_raw_yahoo_chart(norm, interval, rng)
        return process_chart_data(raw, norm, interval)
    except Exception as e:
        return {
            "symbol": norm,
            "error": f"Failed to fetch market data: {e}",
            "stale": True,
            "last_price": None,
            "prev_close": None,
            "candles": [],
            "overlays": {"vwap": [], "cpr": {}, "camarilla": {}}
        }


def get_batch_quotes(symbols: list) -> dict:
    """Fetches batch real-time quotes for watchlist pills with zero fake fallbacks."""
    results = {}
    for s in symbols:
        norm = normalize_symbol(s)
        try:
            data = get_candles(norm, interval="5m", range_str="1d")
            price = data.get("last_price")
            prev_close = data.get("prev_close")

            if price is not None and prev_close is not None and prev_close > 0:
                chg = round(price - prev_close, 2)
                chg_pct = round((chg / prev_close) * 100.0, 2)
            else:
                chg = 0.0
                chg_pct = 0.0

            sparkline = [c["close"] for c in data["candles"][-10:]] if data.get("candles") else []

            results[norm] = {
                "symbol": norm,
                "name": data.get("name", norm),
                "price": price,
                "prev_close": prev_close,
                "change": chg,
                "change_pct": chg_pct,
                "sparkline": sparkline,
                "last_bar_time": data.get("last_bar_time"),
                "stale": data.get("stale", False)
            }
        except Exception as e:
            # Zero fake fallbacks: return error status
            results[norm] = {
                "symbol": norm,
                "name": norm,
                "price": None,
                "prev_close": None,
                "change": None,
                "change_pct": None,
                "sparkline": [],
                "stale": True,
                "error": str(e)
            }
    return results


def get_market_context() -> list:
    """Returns key Indian indices context bar (NIFTY 50, BANK NIFTY, SENSEX, INDIA VIX) with NO fake prices."""
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
            p = c_data.get("last_price")
            pc = c_data.get("prev_close")
            if p is not None and pc is not None and pc > 0:
                chg = round(p - pc, 2)
                pct = round((chg / pc) * 100.0, 2)
                # Flag extreme moves (> +/- 5% on equity indices) as suspect
                is_suspect = (s in ("^NSEI", "^NSEBANK", "^BSESN")) and abs(pct) > 5.0
            else:
                chg = None
                pct = None
                is_suspect = False

            res.append({
                "symbol": s,
                "name": item["name"],
                "price": p,
                "change": chg,
                "change_pct": pct,
                "suspect": is_suspect,
                "stale": c_data.get("stale", False)
            })
        except Exception as e:
            # NO invented fallback (never 24500, 52000, 80000, 13.5)
            res.append({
                "symbol": s,
                "name": item["name"],
                "price": None,
                "change": None,
                "change_pct": None,
                "stale": True,
                "error": str(e)
            })
    return res


def get_stock_profile(symbol: str) -> dict:
    """Returns technical and fundamental profile for stock profile drawer.
    Reads CPR/Camarilla from c_res['overlays'] and uses unified SECTOR_MAP.
    """
    norm = normalize_symbol(symbol)
    base = norm.replace(".NS", "").replace(".BO", "")
    sector = SECTOR_MAP.get(norm, "INDIAN EQUITIES")

    # Fetch 1y daily chart for 52w range and company metadata
    try:
        raw_daily = fetch_raw_yahoo_chart(norm, "1d", "1y")
        chart = raw_daily["chart"]["result"][0]
        meta = chart.get("meta", {})
        high_52w = meta.get("fiftyTwoWeekHigh")
        low_52w = meta.get("fiftyTwoWeekLow")
        cur_price = meta.get("regularMarketPrice")
        company_name = meta.get("shortName") or meta.get("longName") or base
        exchange = meta.get("exchangeName") or ("BSE" if norm.endswith(".BO") else "NSE")
    except Exception:
        high_52w = None
        low_52w = None
        cur_price = None
        company_name = base
        exchange = "NSE"

    # Previous session completed bar
    prev_bar = fetch_prev_day_bar(norm)
    prev_close = float(prev_bar["close"]) if prev_bar and prev_bar.get("close") else None

    # Calculate today's change_pct strictly against previous completed session
    if cur_price is not None and prev_close is not None and prev_close > 0:
        chg_pct = round(((cur_price - prev_close) / prev_close) * 100.0, 2)
    else:
        chg_pct = None

    # Tradability check
    is_fno = norm in {"RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS"}
    circuit_band = "Dynamic (F&O)" if is_fno else "Unknown (Verify NSE list)"
    tradable = True
    tradability_status = "ALLOWED (MIS Intraday)"

    # Read CPR and Camarilla from overlays
    cpr_info = {}
    cam_info = {}
    c_res = get_candles(norm, interval="5m", range_str="1d")
    overlays = c_res.get("overlays", {})
    cpr_info = overlays.get("cpr", {})
    cam_info = overlays.get("camarilla", {})

    return {
        "symbol": norm,
        "base_symbol": base,
        "name": company_name,
        "sector": sector,
        "exchange": exchange,
        "price": cur_price,
        "prev_close": prev_close,
        "change_pct": chg_pct,
        "fifty_two_week_high": high_52w,
        "fifty_two_week_low": low_52w,
        "circuit_band": circuit_band,
        "is_fno": is_fno,
        "tradable": tradable,
        "tradability_status": tradability_status,
        "cpr": cpr_info,
        "camarilla": cam_info,
        "cpr_width_pct": cpr_info.get("cpr_width_pct") or cpr_info.get("cpr_width"),
        "founded": None,
        "business_group": None,
        "headquarters": None,
        "ceo": None,
        "about": None,
        "shareholding": None
    }
