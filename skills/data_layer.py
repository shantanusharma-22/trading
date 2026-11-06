#!/usr/bin/env python3
"""Unified Resilient Data Layer for Indian Market Data (NSE/BSE).
Standard library only.

Features:
  1. Thread-safe in-flight request deduplication (prevents duplicate HTTP calls).
  2. Bounded size-limited TTL cache with LRU eviction (max 500 entries).
  3. Exponential backoff and HTTP 429 (Rate Limit) handling with Retry-After support.
  4. Strict input validation for tickers, intervals, and ranges.
"""

import collections
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def get_db_connection(db_path, timeout: float = 10.0):
    """Context manager for thread-safe, concurrent SQLite access in WAL mode."""
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=timeout)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Allowed parameters for Yahoo Finance API queries
TICKER_REGEX = re.compile(r"^[A-Z0-9_\-\.\^%]{1,20}$")
ALLOWED_INTERVALS = {
    "1m", "2m", "5m", "15m", "30m", "60m", "1h", "1d", "d", "1wk", "wk", "1mo", "mo"
}
ALLOWED_RANGES = {
    "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"
}

# Cache & Concurrency structures
_CACHE_LOCK = threading.RLock()
_CACHE = collections.OrderedDict()  # key -> (data, expires_at)
_MAX_CACHE_ENTRIES = 500

_IN_FLIGHT_LOCK = threading.Lock()
_IN_FLIGHT = {}  # key -> threading.Event()
_IN_FLIGHT_RESULTS = {}  # key -> (result, error)


def validate_market_params(symbol: str, interval: str = None, range_str: str = None) -> bool:
    """Validates ticker symbol, interval, and range against strict allowlists."""
    sym = (symbol or "").strip().upper()
    if not sym or not TICKER_REGEX.match(sym):
        raise ValueError(f"Invalid market symbol '{symbol}'. Must match {TICKER_REGEX.pattern}")

    if interval is not None:
        iv = interval.lower()
        if iv not in ALLOWED_INTERVALS:
            raise ValueError(f"Invalid interval '{interval}'. Allowed: {sorted(list(ALLOWED_INTERVALS))}")

    if range_str is not None:
        rg = range_str.lower()
        if rg not in ALLOWED_RANGES:
            raise ValueError(f"Invalid range '{range_str}'. Allowed: {sorted(list(ALLOWED_RANGES))}")

    return True


def get_cached(key: str):
    """Retrieves an entry from the bounded TTL cache if not expired."""
    now = time.time()
    with _CACHE_LOCK:
        if key in _CACHE:
            data, expires_at = _CACHE[key]
            if now < expires_at:
                _CACHE.move_to_end(key)
                return data
            else:
                del _CACHE[key]
    return None


def set_cached(key: str, data, ttl_seconds: float = 5.0):
    """Stores data in the bounded TTL cache, evicting oldest if capacity reached."""
    now = time.time()
    with _CACHE_LOCK:
        if key in _CACHE:
            del _CACHE[key]
        elif len(_CACHE) >= _MAX_CACHE_ENTRIES:
            _CACHE.popitem(last=False)  # evict oldest
        _CACHE[key] = (data, now + ttl_seconds)


def fetch_json_with_retry(url: str, timeout: float = 8.0, max_retries: int = 2,
                          backoff_factor: float = 1.0, cache_ttl: float = 0.0) -> dict:
    """Fetches JSON via HTTP with in-flight deduplication, exponential backoff, and 429 handling."""
    if cache_ttl > 0:
        cached = get_cached(url)
        if cached is not None:
            return cached

    # In-flight deduplication: if another thread is already fetching this exact URL, wait for it
    wait_event = None
    is_worker = False
    with _IN_FLIGHT_LOCK:
        if url in _IN_FLIGHT:
            wait_event = _IN_FLIGHT[url]
        else:
            wait_event = threading.Event()
            _IN_FLIGHT[url] = wait_event
            is_worker = True

    if not is_worker:
        # Wait on designated worker thread
        wait_event.wait(timeout=timeout + 5.0)
        with _IN_FLIGHT_LOCK:
            res, err = _IN_FLIGHT_RESULTS.get(url, (None, None))
        if err:
            raise err
        if res is not None:
            return res

    # This thread is the designated worker for this URL
    last_err = None
    data = None

    try:
        for attempt in range(max_retries + 1):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/json, text/plain, */*",
                        "Accept-Language": "en-US,en;q=0.9"
                    }
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw_bytes = resp.read()
                    data = json.loads(raw_bytes.decode("utf-8"))
                    if cache_ttl > 0:
                        set_cached(url, data, ttl_seconds=cache_ttl)
                    return data
            except urllib.error.HTTPError as http_err:
                last_err = http_err
                # 429 Too Many Requests
                if http_err.code == 429:
                    retry_after = http_err.headers.get("Retry-After")
                    sleep_time = float(retry_after) if retry_after and retry_after.isdigit() else (backoff_factor * (2 ** attempt))
                    time.sleep(min(sleep_time, 4.0))
                    continue
                # 5xx Server Errors
                elif http_err.code in (500, 502, 503, 504) and attempt < max_retries:
                    time.sleep(backoff_factor * (attempt + 1))
                    continue
                else:
                    raise
            except (urllib.error.URLError, TimeoutError) as net_err:
                last_err = net_err
                if attempt < max_retries:
                    time.sleep(backoff_factor * (attempt + 1))
                    continue
                raise

        if last_err:
            raise last_err
        raise RuntimeError(f"Failed to fetch data from {url}")
    except Exception as e:
        if is_worker:
            with _IN_FLIGHT_LOCK:
                _IN_FLIGHT_RESULTS[url] = (None, e)
                wait_event.set()
        raise
    finally:
        if is_worker:
            with _IN_FLIGHT_LOCK:
                if data is not None:
                    _IN_FLIGHT_RESULTS[url] = (data, None)
                wait_event.set()
                _IN_FLIGHT.pop(url, None)

