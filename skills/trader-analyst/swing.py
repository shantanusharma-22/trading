#!/usr/bin/env python3
"""Multi-Week Swing Trading & Fibonacci Analysis Engine for Indian Equities (NSE/BSE).
Features:
  1. Classical Fibonacci Retracements (23.6%, 38.2%, 50.0%, 61.8% Golden Pocket, 78.6%) & Extensions (127.2%, 161.8%).
  2. Mathematical RSI(14) Calculation with Regular & Hidden Divergence Detection.
  3. Elder's 3-Screen Multi-Timeframe Confluence Scoring System (Weekly Bias -> Daily Setup -> Entry Timing).
  4. Standard library only (no external pip dependencies).

Usage:
    python swing.py RELIANCE.NS
    python swing.py JIOFIN.NS --json
    python swing.py TCS.NS INFY.NS
"""

import argparse
import json
import math
import os
import sys
import urllib.request

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import UA, normalize_symbol

YAHOO_HOST = "query1.finance.yahoo.com"


def fetch_historical_candles(symbol: str, range_period="6mo", interval="1d", offline=None):
    """Fetches historical OHLCV candles from unauthenticated Yahoo Finance chart API."""
    if offline:
        # Generate deterministic synthetic data for unit testing / offline mode
        base = 200.0
        candles = []
        for i in range(90):
            p = base + math.sin(i / 5.0) * 15.0 + (i * 0.2)
            candles.append({
                "open": round(p - 1.0, 2),
                "high": round(p + 2.0, 2),
                "low": round(p - 2.0, 2),
                "close": round(p, 2),
                "volume": 1000000 + i * 5000
            })
        return candles

    symbol = normalize_symbol(symbol)
    url = f"https://{YAHOO_HOST}/v8/finance/chart/{symbol}?range={range_period}&interval={interval}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        res = data["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        opens = q.get("open", [])
        highs = q.get("high", [])
        lows = q.get("low", [])
        closes = q.get("close", [])
        volumes = q.get("volume", [])

        candles = []
        for i in range(len(closes)):
            if closes[i] is not None and highs[i] is not None and lows[i] is not None:
                candles.append({
                    "open": float(opens[i]) if opens[i] is not None else float(closes[i]),
                    "high": float(highs[i]),
                    "low": float(lows[i]),
                    "close": float(closes[i]),
                    "volume": int(volumes[i]) if volumes[i] is not None else 0
                })
        return candles


# ---------------------------------------------------------------- Mathematical RSI & Divergences

def calculate_rsi_series(closes, period=14):
    """Calculates Wilder's Smoothed Relative Strength Index (RSI) across price series."""
    if len(closes) <= period:
        return [50.0] * len(closes)

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rsi_series = [50.0] * period

    if avg_loss == 0.0:
        rsi_series.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi_series.append(round(100.0 - (100.0 / (1.0 + rs)), 2))

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0.0:
            rsi_series.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_series.append(round(100.0 - (100.0 / (1.0 + rs)), 2))

    return rsi_series


def detect_rsi_divergence(candles, rsi_series, lookback=45):
    """Detects Regular (Reversal) and Hidden (Continuation) RSI Divergences."""
    if len(candles) < lookback or len(rsi_series) < lookback:
        return None

    recent_candles = candles[-lookback:]
    recent_rsi = rsi_series[-lookback:]
    closes = [c["close"] for c in recent_candles]

    # Find swing highs and lows in price
    price_troughs = []
    price_peaks = []
    for i in range(2, len(closes) - 2):
        if closes[i] < closes[i - 1] and closes[i] < closes[i - 2] and closes[i] < closes[i + 1] and closes[i] < closes[i + 2]:
            price_troughs.append((i, closes[i], recent_rsi[i]))
        if closes[i] > closes[i - 1] and closes[i] > closes[i - 2] and closes[i] > closes[i + 1] and closes[i] > closes[i + 2]:
            price_peaks.append((i, closes[i], recent_rsi[i]))

    divergences = []

    # 1. Regular Bullish Divergence: Lower Low in Price, Higher Low in RSI (Reversal)
    if len(price_troughs) >= 2:
        t1, t2 = price_troughs[-2], price_troughs[-1]
        if t2[1] < t1[1] and t2[2] > t1[2]:
            divergences.append({
                "type": "REGULAR_BULLISH",
                "bias": "BULLISH_REVERSAL",
                "detail": f"Price made Lower Low (Rs {t2[1]:.2f} < Rs {t1[1]:.2f}) but RSI made Higher Low ({t2[2]:.1f} > {t1[2]:.1f})",
                "strength": "High (Momentum Divergence)"
            })
        # Hidden Bullish Divergence: Higher Low in Price, Lower Low in RSI (Continuation)
        elif t2[1] > t1[1] and t2[2] < t1[2]:
            divergences.append({
                "type": "HIDDEN_BULLISH",
                "bias": "BULLISH_CONTINUATION",
                "detail": f"Price made Higher Low (Rs {t2[1]:.2f} > Rs {t1[1]:.2f}) while RSI made Lower Low ({t2[2]:.1f} < {t1[2]:.1f})",
                "strength": "High (Trend Continuation)"
            })

    # 2. Regular Bearish Divergence: Higher High in Price, Lower High in RSI (Reversal)
    if len(price_peaks) >= 2:
        p1, p2 = price_peaks[-2], price_peaks[-1]
        if p2[1] > p1[1] and p2[2] < p1[2]:
            divergences.append({
                "type": "REGULAR_BEARISH",
                "bias": "BEARISH_REVERSAL",
                "detail": f"Price made Higher High (Rs {p2[1]:.2f} > Rs {p1[1]:.2f}) but RSI made Lower High ({p2[2]:.1f} < {p1[2]:.1f})",
                "strength": "High (Exhaustion Divergence)"
            })
        # Hidden Bearish Divergence: Lower High in Price, Higher High in RSI (Continuation)
        elif p2[1] < p1[1] and p2[2] > p1[2]:
            divergences.append({
                "type": "HIDDEN_BEARISH",
                "bias": "BEARISH_CONTINUATION",
                "detail": f"Price made Lower High (Rs {p2[1]:.2f} < Rs {p1[1]:.2f}) while RSI made Higher High ({p2[2]:.1f} > {p1[2]:.1f})",
                "strength": "High (Downtrend Continuation)"
            })

    return divergences


# ---------------------------------------------------------------- Classical Fibonacci Retracements & Extensions

def calculate_fibonacci_levels(candles, lookback=90):
    """Calculates Swing High, Swing Low, Retracements, Golden Pocket, and Extensions."""
    lookback = min(lookback, len(candles))
    subset = candles[-lookback:]

    highs = [c["high"] for c in subset]
    lows = [c["low"] for c in subset]

    swing_high = max(highs)
    swing_low = min(lows)
    high_idx = highs.index(swing_high)
    low_idx = lows.index(swing_low)

    diff = swing_high - swing_low
    if diff == 0:
        diff = 1.0

    current_price = subset[-1]["close"]
    is_uptrend = low_idx < high_idx  # Low occurred before High

    if is_uptrend:
        # Bullish Pullback: Retracing from High down towards Low
        levels = {
            "0.0% (Swing High)": round(swing_high, 2),
            "23.6%": round(swing_high - diff * 0.236, 2),
            "38.2%": round(swing_high - diff * 0.382, 2),
            "50.0% (Equilibrium)": round(swing_high - diff * 0.500, 2),
            "61.8% (Golden Ratio)": round(swing_high - diff * 0.618, 2),
            "78.6%": round(swing_high - diff * 0.786, 2),
            "100.0% (Swing Low)": round(swing_low, 2),
            "127.2% Ext": round(swing_high + diff * 0.272, 2),
            "161.8% Ext (Target 1)": round(swing_high + diff * 0.618, 2),
            "261.8% Ext (Target 2)": round(swing_high + diff * 1.618, 2),
        }
        golden_pocket = (round(swing_high - diff * 0.618, 2), round(swing_high - diff * 0.500, 2))
    else:
        # Bearish Bounce: Retracing from Low up towards High
        levels = {
            "0.0% (Swing Low)": round(swing_low, 2),
            "23.6%": round(swing_low + diff * 0.236, 2),
            "38.2%": round(swing_low + diff * 0.382, 2),
            "50.0% (Equilibrium)": round(swing_low + diff * 0.500, 2),
            "61.8% (Golden Ratio)": round(swing_low + diff * 0.618, 2),
            "78.6%": round(swing_low + diff * 0.786, 2),
            "100.0% (Swing High)": round(swing_high, 2),
            "127.2% Ext": round(swing_low - diff * 0.272, 2),
            "161.8% Ext (Target 1)": round(swing_low - diff * 0.618, 2),
            "261.8% Ext (Target 2)": round(swing_low - diff * 1.618, 2),
        }
        golden_pocket = (round(swing_low + diff * 0.500, 2), round(swing_low + diff * 0.618, 2))

    # Evaluate current price proximity to Golden Pocket
    gp_min, gp_max = min(golden_pocket), max(golden_pocket)
    in_golden_pocket = (gp_min <= current_price <= gp_max)
    near_golden_pocket = abs(current_price - gp_min) / current_price < 0.015 or abs(current_price - gp_max) / current_price < 0.015

    return {
        "swing_high": swing_high,
        "swing_low": swing_low,
        "current_price": current_price,
        "primary_trend": "UPTREND (Bullish Impulse)" if is_uptrend else "DOWNTREND (Bearish Impulse)",
        "levels": levels,
        "golden_pocket": f"Rs {gp_min:.2f} - Rs {gp_max:.2f}",
        "in_golden_pocket": in_golden_pocket,
        "near_golden_pocket": near_golden_pocket
    }


# ---------------------------------------------------------------- 3-Screen Multi-Timeframe Confluence Engine

def analyze_swing_setup(symbol: str, offline=None):
    """Executes full 3-Screen Confluence & Fibonacci Swing Analysis."""
    candles = fetch_historical_candles(symbol, range_period="6mo", interval="1d", offline=offline)
    if len(candles) < 30:
        return {"error": f"Insufficient historical bars for {symbol} ({len(candles)})"}

    closes = [c["close"] for c in candles]
    current_price = closes[-1]

    # Moving Averages
    sma_20 = sum(closes[-20:]) / 20.0 if len(closes) >= 20 else current_price
    sma_50 = sum(closes[-50:]) / 50.0 if len(closes) >= 50 else current_price

    # RSI & Divergences
    rsi_series = calculate_rsi_series(closes, period=14)
    current_rsi = rsi_series[-1]
    divergences = detect_rsi_divergence(candles, rsi_series)

    # Fibonacci Analysis
    fib = calculate_fibonacci_levels(candles, lookback=90)

    # Confluence Scoring (0 to 10 points)
    score = 0
    checks = []

    # Screen 1: Primary Trend Direction (Weekly / Macro)
    if current_price > sma_50:
        score += 2
        checks.append("Screen 1 (Macro Trend): Price above 50-day SMA (+2 pts)")
    else:
        checks.append("Screen 1 (Macro Trend): Price below 50-day SMA (0 pts)")

    if sma_20 > sma_50:
        score += 2
        checks.append("Screen 1 (Trend Alignment): 20 SMA > 50 SMA bullish stack (+2 pts)")

    # Screen 2: Setup Confirmation (Fibonacci Golden Pocket & RSI)
    if fib["in_golden_pocket"]:
        score += 3
        checks.append("Screen 2 (Setup): Price actively in Fibonacci Golden Pocket 50%-61.8% (+3 pts)")
    elif fib["near_golden_pocket"]:
        score += 2
        checks.append("Screen 2 (Setup): Price within 1.5% of Fibonacci Golden Pocket (+2 pts)")

    if 40.0 <= current_rsi <= 60.0:
        score += 1
        checks.append(f"Screen 2 (RSI Health): Neutral healthy pullback RSI {current_rsi:.1f} (+1 pt)")
    elif current_rsi < 35.0:
        score += 2
        checks.append(f"Screen 2 (RSI Oversold): Deep pullback discount RSI {current_rsi:.1f} (+2 pts)")

    if divergences:
        for div in divergences:
            if "BULLISH" in div["type"]:
                score += 2
                checks.append(f"Screen 2 (Divergence): {div['type']} detected ({div['detail']}) (+2 pts)")
            elif "BEARISH" in div["type"]:
                score -= 2
                checks.append(f"Screen 2 (Divergence Alert): {div['type']} detected (-2 pts)")

    # Screen 3: Timing & Risk-Reward Targets
    if fib["primary_trend"].startswith("UPTREND"):
        entry_ideal = fib["levels"]["61.8% (Golden Ratio)"]
        stop_loss = round(fib["levels"]["78.6%"] * 0.995, 2)
        target_1 = fib["levels"]["127.2% Ext"]
        target_2 = fib["levels"]["161.8% Ext (Target 1)"]
        risk = max(current_price - stop_loss, 0.05)
        reward = max(target_2 - current_price, 0.05)
        rr_ratio = round(reward / risk, 2) if risk > 0 else 0.0
    else:
        entry_ideal = fib["levels"]["38.2%"]
        stop_loss = round(fib["swing_high"] * 1.005, 2)
        target_1 = fib["levels"]["127.2% Ext"]
        target_2 = fib["levels"]["161.8% Ext (Target 1)"]
        risk = max(stop_loss - current_price, 0.05)
        reward = max(current_price - target_2, 0.05)
        rr_ratio = round(reward / risk, 2) if risk > 0 else 0.0

    if rr_ratio >= 2.0:
        score += 1
        checks.append(f"Screen 3 (Risk-Reward): Favorable swing R:R ratio of {rr_ratio:.2f}:1 (+1 pt)")

    score = min(max(score, 0), 10)

    if score >= 8:
        verdict = "STRONG BUY (High-Probability Multi-Timeframe Swing Setup 🚀)"
    elif score >= 5:
        verdict = "MODERATE WATCH (Valid Structure, Await Precise Lower-Timeframe Trigger 👀)"
    else:
        verdict = "NEUTRAL / AVOID (Low Confluence or Counter-Trend ⚠️)"

    return {
        "symbol": symbol,
        "current_price": current_price,
        "primary_trend": fib["primary_trend"],
        "sma_20": round(sma_20, 2),
        "sma_50": round(sma_50, 2),
        "rsi_14": round(current_rsi, 2),
        "divergences": divergences or [],
        "fibonacci": fib,
        "confluence_score": score,
        "max_score": 10,
        "confluence_checks": checks,
        "swing_plan": {
            "ideal_entry": entry_ideal,
            "stop_loss": stop_loss,
            "target_1": target_1,
            "target_2": target_2,
            "risk_reward_ratio": rr_ratio
        },
        "verdict": verdict
    }


def print_swing_report(res):
    if "error" in res:
        print(f"ERROR: {res['error']}")
        return

    sym = res["symbol"]
    fib = res["fibonacci"]
    plan = res["swing_plan"]

    print("=" * 65)
    print(f" MULTI-WEEK SWING & FIBONACCI REPORT: {sym} ")
    print("=" * 65)
    print(f"Current Price:          Rs {res['current_price']:.2f}")
    print(f"Primary Trend Bias:     {res['primary_trend']}")
    print(f"Daily Moving Averages:  20-SMA: Rs {res['sma_20']:.2f} | 50-SMA: Rs {res['sma_50']:.2f}")
    print(f"Daily RSI(14):          {res['rsi_14']:.2f}")

    if res["divergences"]:
        print("\n⚡ RSI DIVERGENCES DETECTED:")
        for div in res["divergences"]:
            print(f"  • [{div['type']}] {div['detail']}")
    else:
        print("\nRSI Divergences:        None active (Momentum tracks price closely)")

    print("-" * 65)
    print(f"FIBONACCI RETRACEMENT & EXTENSION MATRIX (90-Day Range):")
    print(f"Swing High: Rs {fib['swing_high']:.2f} | Swing Low: Rs {fib['swing_low']:.2f}")
    print(f"Golden Pocket Zone:     {fib['golden_pocket']} {'[ACTIVE HIT! 🔥]' if fib['in_golden_pocket'] else ''}")
    print("\nKey Fibonacci Levels:")
    for name, lvl in fib["levels"].items():
        prefix = "  ★ " if "61.8%" in name or "161.8%" in name else "    "
        print(f"{prefix}{name.ljust(24)}: Rs {lvl:.2f}")

    print("-" * 65)
    print(f"INSTITUTIONAL CONFLUENCE SCORE: {res['confluence_score']} / {res['max_score']}")
    print(f"Verdict: {res['verdict']}")
    print("\nConfluence Factors:")
    for chk in res["confluence_checks"]:
        print(f"  ✓ {chk}")

    print("-" * 65)
    print("ACTIONABLE SWING TRADING PLAN:")
    print(f"  • Entry Zone:         Rs {plan['ideal_entry']:.2f} (or current Rs {res['current_price']:.2f})")
    print(f"  • Stop Loss:          Rs {plan['stop_loss']:.2f} (Below structural invalidation)")
    print(f"  • Profit Target 1:    Rs {plan['target_1']:.2f} (127.2% Extension)")
    print(f"  • Profit Target 2:    Rs {plan['target_2']:.2f} (161.8% Golden Extension)")
    print(f"  • Risk : Reward:      1 : {plan['risk_reward_ratio']:.2f}")
    print("=" * 65)


def main():
    p = argparse.ArgumentParser(description="Multi-Week Swing & Fibonacci Analysis Engine")
    p.add_argument("symbols", nargs="+", help="NSE Stock Ticker(s), e.g. RELIANCE.NS JIOFIN.NS")
    p.add_argument("--json", action="store_true", help="Output JSON format")
    p.add_argument("--offline", action="store_true", help="Use deterministic mock data for testing")
    args = p.parse_args()

    results = []
    for s in args.symbols:
        res = analyze_swing_setup(s, offline=args.offline)
        results.append(res)
        if not args.json:
            print_swing_report(res)

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))


if __name__ == "__main__":
    main()
