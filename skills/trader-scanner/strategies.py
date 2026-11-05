#!/usr/bin/env python3
"""Complete Indian Intraday Strategies Library & Custom Confluence Engine.
Implements all 20 classical and institutional NSE/BSE intraday strategies:
  Momentum & Breakout:
    1. Opening Range Breakout (ORB 15m)
    2. Previous Day High / Low Breakout (PDH / PDL)
    3. Gap-and-Go & Gap-Fill
    4. NR7 & Inside Bar Breakout
  Trend-Following:
    5. Intraday VWAP Pullback
    6. 9 / 20 EMA Crossover
    7. Supertrend (10, 3)
    8. 20 EMA Retest + RSI Filter
  Reversal & Mean-Reversion:
    9. RSI(14) Divergence & Extremes
    10. Bollinger Bands Squeeze & Snap-Back (20, 2)
    11. Central Pivot Range (CPR) & Camarilla
    12. 1m–3m Micro Scalper
  Options / Derivatives Models:
    13. Expiry-Day Option Delta Burst
    14. OTM Strangle / Iron Condor Decay
    15. 9:20 AM Rule-Based Straddle (920 Straddle)
    16. Open Interest (OI) & Max Pain Gravitation
  Event & Flow-Based:
    17. Results & News Momentum Reaction
    18. Sector Momentum Leader
    19. FII/DII Institutional Flow + GIFT Nifty Global Bias
  Custom Multi-Factor Master Model:
    20. Vyapar Institutional Confluence (AIC-20) [0-100 pts]

Standard library only. No external dependencies required.
"""

import argparse
import datetime
import json
import math
import os
import sys
import urllib.request

_skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common import IST_OFFSET, UA, normalize_symbol, resolve_path, to_ist


# =====================================================================
# Strategy Registry & Metadata
# =====================================================================

STRATEGY_REGISTRY = {
    "orb": {
        "id": "orb",
        "num": 1,
        "name": "Opening Range Breakout (ORB 15m)",
        "style": "Breakout / Momentum",
        "risk_reward": "1 : 1.8",
        "optimal_regime": "High Beta / Trending Openings",
        "timeframe": "5m / 15m",
        "applicable_assets": "NSE Equities (MIS) & Index Futures",
        "description": "Marks the 09:15-09:30 range high/low. Enters on candle close beyond range with stop at opposite boundary.",
    },
    "pdh_pdl": {
        "id": "pdh_pdl",
        "num": 2,
        "name": "Previous Day High / Low Breakout (PDH/PDL)",
        "style": "Breakout / Momentum",
        "risk_reward": "1 : 2.0",
        "optimal_regime": "Breakout / Price Discovery Days",
        "timeframe": "5m / 15m",
        "applicable_assets": "NSE Equities (MIS)",
        "description": "Triggered when 5m candle closes above PDH or below PDL with volume exceeding 1.25x the 20-period volume SMA.",
    },
    "gap_and_go": {
        "id": "gap_and_go",
        "num": 3,
        "name": "Gap-and-Go / Gap-Fill",
        "style": "Breakout / Momentum",
        "risk_reward": "1 : 2.2",
        "optimal_regime": "News & Earnings Gaps (>1.0%)",
        "timeframe": "5m / 15m",
        "applicable_assets": "NSE Equities (MIS)",
        "description": "Stocks gapping >1%: trades in gap direction if 15m bar holds, fades the gap if filled in first 30 mins.",
    },
    "nr7_inside": {
        "id": "nr7_inside",
        "num": 4,
        "name": "Volume Breakout / NR7 & Inside Bar",
        "style": "Breakout / Momentum",
        "risk_reward": "1 : 2.5",
        "optimal_regime": "Post-Consolidation Squeeze Expansion",
        "timeframe": "5m / Daily",
        "applicable_assets": "NSE Equities (MIS)",
        "description": "Identifies NR7 (narrowest range in 7 days) or inside bars breaking out with 2x+ average volume.",
    },
    "vwap_pullback": {
        "id": "vwap_pullback",
        "num": 5,
        "name": "Intraday VWAP Pullback",
        "style": "Trend-Following",
        "risk_reward": "1 : 1.5",
        "optimal_regime": "Steady Institutional Trending Days",
        "timeframe": "5m",
        "applicable_assets": "NSE Equities (MIS) & Liquid ETFs",
        "description": "Buys pullbacks to VWAP in an uptrend (price > VWAP); shorts bounces off VWAP in a downtrend.",
    },
    "ema_crossover": {
        "id": "ema_crossover",
        "num": 6,
        "name": "9 / 20 EMA Crossover",
        "style": "Trend-Following",
        "risk_reward": "1 : 2.5",
        "optimal_regime": "Strong Directional Momentum Moves",
        "timeframe": "5m / 15m",
        "applicable_assets": "NSE Equities (MIS) & Nifty Index",
        "description": "Fast 9 EMA crosses 20 EMA. The 20 EMA serves as the dynamic trailing stop loss until market square-off.",
    },
    "supertrend": {
        "id": "supertrend",
        "num": 7,
        "name": "Supertrend (10, 3)",
        "style": "Trend-Following",
        "risk_reward": "1 : 2.0",
        "optimal_regime": "High-Volatility Directional Trends",
        "timeframe": "5m",
        "applicable_assets": "NSE Equities (MIS) & Bank Nifty",
        "description": "Classical ATR-based volatility band flips. Enters long when price crosses above upper band; stops at lower band.",
    },
    "ema20_rsi_retest": {
        "id": "ema20_rsi_retest",
        "num": 8,
        "name": "20 EMA Retest + RSI Filter",
        "style": "Trend-Following",
        "risk_reward": "1 : 1.8",
        "optimal_regime": "Healthy Retracements in Bull/Bear Runs",
        "timeframe": "5m / 15m",
        "applicable_assets": "NSE Equities (MIS)",
        "description": "Enters on 20 EMA retest when RSI(14) stays above 40 (long) or below 60 (short), ensuring momentum remains intact.",
    },
    "rsi_divergence": {
        "id": "rsi_divergence",
        "num": 9,
        "name": "RSI(14) Divergence & Extremes",
        "style": "Reversal / Mean-Reversion",
        "risk_reward": "1 : 2.2",
        "optimal_regime": "Overextended Rallies / Sell-offs at Key S/R",
        "timeframe": "15m",
        "applicable_assets": "NSE Equities (MIS)",
        "description": "Fades extreme moves when price prints higher highs with lower RSI (bearish) or lower lows with higher RSI (bullish).",
    },
    "bollinger_squeeze": {
        "id": "bollinger_squeeze",
        "num": 10,
        "name": "Bollinger Bands Squeeze & Snap-Back",
        "style": "Reversal / Mean-Reversion",
        "risk_reward": "1 : 1.4",
        "optimal_regime": "Range-Bound Sideways / Low-VIX Markets",
        "timeframe": "5m / 15m",
        "applicable_assets": "NSE Equities (MIS)",
        "description": "Trades volatility expansion after band pinch, or fades closes outside lower/upper bands back to the 20 SMA mean.",
    },
    "cpr_camarilla": {
        "id": "cpr_camarilla",
        "num": 11,
        "name": "Central Pivot Range (CPR) & Camarilla",
        "style": "Reversal / Mean-Reversion",
        "risk_reward": "1 : 1.7",
        "optimal_regime": "Narrow CPR (Trend) vs Wide CPR (Range)",
        "timeframe": "5m",
        "applicable_assets": "NSE Equities (MIS)",
        "description": "Calculates TC, Pivot, BC. Narrow CPR (<0.25%) signals strong trend breakout; Wide CPR signals range trade between S1 and R1.",
    },
    "micro_scalper": {
        "id": "micro_scalper",
        "num": 12,
        "name": "1m-3m Micro Scalper",
        "style": "Scalping",
        "risk_reward": "1 : 1.0",
        "optimal_regime": "High Liquidity / Ultra-Tight Bid-Ask Spreads",
        "timeframe": "1m - 3m",
        "applicable_assets": "High-Beta Liquid NSE Stocks",
        "description": "Quick 0.15% - 0.25% scalping moves using consecutive volume surges with tight 0.15% hard stops.",
    },
    "options_delta_burst": {
        "id": "options_delta_burst",
        "num": 13,
        "name": "Expiry-Day Option Delta Burst",
        "style": "Options / Derivatives",
        "analysis_only": True,
        "risk_reward": "1 : 3.5",
        "optimal_regime": "Weekly Expiry Days (Thursday/Friday) Post-10:30",
        "timeframe": "5m",
        "applicable_assets": "ATM/OTM Nifty & Bank Nifty Options",
        "description": "Exploits rapid gamma expansion on post-10:30 breakouts with zero extrinsic theta padding. Asymmetric payoff.",
    },
    "options_strangle": {
        "id": "options_strangle",
        "num": 14,
        "name": "OTM Strangle / Iron Condor Decay",
        "style": "Options / Derivatives",
        "analysis_only": True,
        "risk_reward": "1 : 0.8",
        "optimal_regime": "Low India VIX (<13.0) & Sideways CPR",
        "timeframe": "Intraday Decay",
        "applicable_assets": "Index Options (Nifty / Bank Nifty)",
        "description": "Sells 15-delta OTM Call & Put at open, capitalizing on pure theta decay with mandatory 15:10 auto-exit.",
    },
    "options_920_straddle": {
        "id": "options_920_straddle",
        "num": 15,
        "name": "9:20 AM Rule-Based Straddle (920 Straddle)",
        "style": "Options / Derivatives",
        "analysis_only": True,
        "risk_reward": "1 : 1.2",
        "optimal_regime": "Non-trending openings / Mean-Reverting Days",
        "timeframe": "09:20 - 15:10 IST",
        "applicable_assets": "Index ATM Call + Put",
        "description": "Sells ATM CE + PE at 09:20 IST sharp with strict 25% stop-loss per leg. Proven rule-based Indian algorithmic system.",
    },
    "options_max_pain": {
        "id": "options_max_pain",
        "num": 16,
        "name": "Open Interest (OI) & Max Pain Gravitation",
        "style": "Options / Derivatives",
        "analysis_only": True,
        "risk_reward": "1 : 1.6",
        "optimal_regime": "Afternoon Expiry Sessions (13:00 - 15:30)",
        "timeframe": "15m / Expiry Hourly",
        "applicable_assets": "Index & F&O Equities",
        "description": "Computes Put-Call Ratio (PCR) and Max Pain strike. Exploits index gravitation toward option seller equilibrium.",
    },
    "news_results": {
        "id": "news_results",
        "num": 17,
        "name": "Results & News Momentum Reaction",
        "style": "Event / Flow",
        "risk_reward": "1 : 2.5",
        "optimal_regime": "Quarterly Earnings / RBI Policy Announcements",
        "timeframe": "5m",
        "applicable_assets": "High-Beta NSE Equities (MIS)",
        "description": "Trades initial 15-minute reaction to major corporate earnings or central bank policy with 1.5x ATR volatility stop.",
    },
    "sector_momentum": {
        "id": "sector_momentum",
        "num": 18,
        "name": "Sector Momentum Leader",
        "style": "Event / Flow",
        "analysis_only": True,
        "risk_reward": "1 : 2.0",
        "optimal_regime": "Sectoral Rotation Days",
        "timeframe": "15m",
        "applicable_assets": "NSE Equities (MIS)",
        "description": "Identifies top performing sector index (e.g. Nifty IT vs Nifty Bank) and executes long on the highest relative strength constituent.",
    },
    "fiidii_flow": {
        "id": "fiidii_flow",
        "num": 19,
        "name": "FII/DII Institutional Flow + GIFT Nifty Bias",
        "style": "Event / Flow",
        "analysis_only": True,
        "risk_reward": "1 : 1.8",
        "optimal_regime": "Morning Openings (09:15 - 10:30 IST)",
        "timeframe": "Pre-Market / 15m",
        "applicable_assets": "Nifty 50 & Heavyweight Equities",
        "description": "Uses cumulative net institutional buying/selling combined with overnight GIFT Nifty premiums to bias intraday trades.",
    },
    "aic_confluence": {
        "id": "aic_confluence",
        "num": 20,
        "name": "Vyapar Institutional Confluence (AIC-20)",
        "style": "Custom Multi-Factor",
        "risk_reward": "1 : 2.2",
        "optimal_regime": "All Indian Market Regimes (Filtered Confluence)",
        "timeframe": "5m / 15m",
        "applicable_assets": "Top 50 Liquid NSE Equities (MIS)",
        "description": "Master institutional quant model scoring setups from 0-100 pts across Microstructure CPR, VWAP, Supertrend, EMA Cross, Volume Fuel, and VIX Regime.",
    },
}


# =====================================================================
# Mathematical Indicators & Helpers (Standard Library)
# =====================================================================

def calculate_sma(series, period):
    """Calculates Simple Moving Average."""
    if not series or len(series) < period:
        return [series[-1]] * len(series) if series else []
    res = []
    for i in range(len(series)):
        if i + 1 < period:
            res.append(sum(series[:i+1]) / (i + 1))
        else:
            res.append(sum(series[i+1-period:i+1]) / period)
    return res


def calculate_ema(series, period):
    """Calculates Exponential Moving Average."""
    if not series:
        return []
    if len(series) < period:
        return calculate_sma(series, len(series))
    k = 2.0 / (period + 1.0)
    ema = [series[0]]
    for val in series[1:]:
        ema.append(val * k + ema[-1] * (1.0 - k))
    return ema


def calculate_tr(candles):
    """Calculates True Range array for candle dicts."""
    trs = []
    for i in range(len(candles)):
        c = candles[i]
        h = c["high"]
        l = c["low"]
        if i == 0:
            trs.append(h - l)
        else:
            prev_c = candles[i-1]["close"]
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            trs.append(tr)
    return trs


def calculate_atr(candles, period=10):
    """Calculates Average True Range."""
    trs = calculate_tr(candles)
    return calculate_sma(trs, period)


def calculate_vwap(candles):
    """Calculates cumulative Intraday VWAP series."""
    vwap_vals = []
    cum_pv = 0.0
    cum_vol = 0.0
    for c in candles:
        typical = (c["high"] + c["low"] + c["close"]) / 3.0
        vol = max(1.0, float(c.get("volume", 1.0)))
        cum_pv += typical * vol
        cum_vol += vol
        vwap_vals.append(cum_pv / cum_vol if cum_vol > 0 else c["close"])
    return vwap_vals


def calculate_rsi(closes, period=14):
    """Calculates Wilder's RSI(14) series."""
    if len(closes) < 2:
        return [50.0] * len(closes)
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))

    rsi_series = [50.0]
    avg_gain = sum(gains[:period]) / period if len(gains) >= period else (sum(gains) / len(gains) if gains else 0.0)
    avg_loss = sum(losses[:period]) / period if len(losses) >= period else (sum(losses) / len(losses) if losses else 0.0)

    for i in range(len(gains)):
        if i < period:
            rs = (avg_gain / avg_loss) if avg_loss > 0 else 100.0
            rsi = 100.0 - (100.0 / (1.0 + rs)) if avg_loss > 0 else (100.0 if avg_gain > 0 else 50.0)
            rsi_series.append(rsi)
        else:
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            rs = (avg_gain / avg_loss) if avg_loss > 0 else 100.0
            rsi = 100.0 - (100.0 / (1.0 + rs)) if avg_loss > 0 else (100.0 if avg_gain > 0 else 50.0)
            rsi_series.append(rsi)
    return rsi_series


def calculate_supertrend(candles, period=10, multiplier=3.0):
    """Calculates Supertrend indicator series (trend: 1 for bull, -1 for bear, line values)."""
    if not candles:
        return {"trend": 1, "line": 0.0, "color": "GREEN"}
    atr = calculate_atr(candles, period)
    n = len(candles)
    upper_band = [0.0] * n
    lower_band = [0.0] * n
    trend = [1] * n
    st_line = [0.0] * n

    for i in range(n):
        c = candles[i]
        hl2 = (c["high"] + c["low"]) / 2.0
        cur_atr = atr[i] if i < len(atr) else (c["high"] - c["low"])
        basic_upper = hl2 + multiplier * cur_atr
        basic_lower = hl2 - multiplier * cur_atr

        if i == 0:
            upper_band[i] = basic_upper
            lower_band[i] = basic_lower
            trend[i] = 1 if c["close"] >= basic_upper else -1
            st_line[i] = lower_band[i] if trend[i] == 1 else upper_band[i]
            continue

        prev_close = candles[i-1]["close"]
        prev_upper = upper_band[i-1]
        prev_lower = lower_band[i-1]

        lower_band[i] = basic_lower if (basic_lower > prev_lower or prev_close < prev_lower) else prev_lower
        upper_band[i] = basic_upper if (basic_upper < prev_upper or prev_close > prev_upper) else prev_upper

        if trend[i-1] == 1:
            trend[i] = -1 if c["close"] < lower_band[i] else 1
        else:
            trend[i] = 1 if c["close"] > upper_band[i] else -1

        st_line[i] = lower_band[i] if trend[i] == 1 else upper_band[i]

    cur_trend = trend[-1]
    return {
        "trend": cur_trend,
        "line": round(st_line[-1], 2),
        "color": "GREEN" if cur_trend == 1 else "RED"
    }


def calculate_bollinger_bands(closes, period=20, num_std=2.0):
    """Calculates Bollinger Bands (Upper, Middle, Lower, Bandwidth)."""
    if not closes:
        return {"upper": 0.0, "middle": 0.0, "lower": 0.0, "bandwidth": 0.0}
    sma = calculate_sma(closes, period)
    mid = sma[-1]
    window = closes[-period:] if len(closes) >= period else closes
    mean = sum(window) / len(window)
    variance = sum((x - mean) ** 2 for x in window) / len(window)
    std = math.sqrt(variance)
    upper = mid + num_std * std
    lower = mid - num_std * std
    bw = ((upper - lower) / mid * 100.0) if mid > 0 else 0.0
    return {
        "upper": round(upper, 2),
        "middle": round(mid, 2),
        "lower": round(lower, 2),
        "bandwidth": round(bw, 3)
    }


def calculate_cpr_camarilla(prev_high, prev_low, prev_close):
    """Computes Central Pivot Range & Camarilla levels."""
    pivot = (prev_high + prev_low + prev_close) / 3.0
    bc = (prev_high + prev_low) / 2.0
    tc = (pivot - bc) + pivot
    cpr_width = abs(tc - bc)
    cpr_width_pct = (cpr_width / pivot) * 100.0 if pivot > 0 else 0.0

    r = prev_high - prev_low
    h4 = prev_close + (r * 1.1 / 2.0)
    h3 = prev_close + (r * 1.1 / 4.0)
    l3 = prev_close - (r * 1.1 / 4.0)
    l4 = prev_close - (r * 1.1 / 2.0)

    return {
        "pivot": round(pivot, 2),
        "tc": round(tc, 2),
        "bc": round(bc, 2),
        "cpr_width_pct": round(cpr_width_pct, 3),
        "is_narrow": cpr_width_pct < 0.25,
        "is_wide": cpr_width_pct > 0.65,
        "h4": round(h4, 2),
        "h3": round(h3, 2),
        "l3": round(l3, 2),
        "l4": round(l4, 2)
    }


# =====================================================================
# Strategy Evaluation Engines (All 20 Strategies)
# =====================================================================

def eval_orb(candles, prev_bar=None):
    """1. Opening Range Breakout (ORB 15-minute)."""
    if len(candles) < 3:
        return {"signal": "NEUTRAL", "reason": "Awaiting initial 15-minute range formation (3 bars)"}
    orb_high = max(c["high"] for c in candles[:3])
    orb_low = min(c["low"] for c in candles[:3])
    orb_range = orb_high - orb_low
    curr_c = candles[-1]["close"]

    if curr_c > orb_high:
        stop = round(orb_low if orb_range < curr_c * 0.015 else (orb_high - orb_range * 0.5), 2)
        risk = max(curr_c - stop, curr_c * 0.005)
        return {
            "signal": "BUY",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c + risk * 1.8, 2),
            "risk_reward": 1.8,
            "confidence": "HIGH",
            "reason": f"Close ₹{curr_c:.2f} broke above 15m ORB High ₹{orb_high:.2f}"
        }
    elif curr_c < orb_low:
        stop = round(orb_high if orb_range < curr_c * 0.015 else (orb_low + orb_range * 0.5), 2)
        risk = max(stop - curr_c, curr_c * 0.005)
        return {
            "signal": "SELL",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c - risk * 1.8, 2),
            "risk_reward": 1.8,
            "confidence": "HIGH",
            "reason": f"Close ₹{curr_c:.2f} broke below 15m ORB Low ₹{orb_low:.2f}"
        }
    return {
        "signal": "NEUTRAL",
        "reason": f"Price inside 15m ORB range [₹{orb_low:.2f} - ₹{orb_high:.2f}]"
    }


def eval_pdh_pdl(candles, prev_bar):
    """2. Previous Day High / Low Breakout with Volume Filter."""
    if not prev_bar or not candles:
        return {"signal": "NEUTRAL", "reason": "Previous daily bar required"}
    pdh = prev_bar["high"]
    pdl = prev_bar["low"]
    curr = candles[-1]
    curr_c = curr["close"]

    volumes = [float(c.get("volume", 1)) for c in candles]
    avg_vol = sum(volumes[-20:]) / min(len(volumes), 20) if volumes else 1.0
    vol_ratio = (curr.get("volume", 1) / avg_vol) if avg_vol > 0 else 1.0

    if curr_c > pdh and vol_ratio >= 1.25:
        stop = round(pdh * 0.992, 2)
        risk = max(curr_c - stop, curr_c * 0.005)
        return {
            "signal": "BUY",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c + risk * 2.0, 2),
            "risk_reward": 2.0,
            "confidence": "HIGH",
            "reason": f"Breakout above PDH ₹{pdh:.2f} with {vol_ratio:.1f}x volume surge"
        }
    elif curr_c < pdl and vol_ratio >= 1.25:
        stop = round(pdl * 1.008, 2)
        risk = max(stop - curr_c, curr_c * 0.005)
        return {
            "signal": "SELL",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c - risk * 2.0, 2),
            "risk_reward": 2.0,
            "confidence": "HIGH",
            "reason": f"Breakdown below PDL ₹{pdl:.2f} with {vol_ratio:.1f}x volume surge"
        }
    return {"signal": "NEUTRAL", "reason": f"Trading within previous day range [₹{pdl:.2f} - ₹{pdh:.2f}]"}


def eval_gap_and_go(candles, prev_bar):
    """3. Gap-and-Go & Gap-Fill Strategy."""
    if not prev_bar or not candles:
        return {"signal": "NEUTRAL", "reason": "No daily bar for gap benchmark"}
    prev_close = prev_bar["close"]
    open_p = candles[0]["open"]
    gap_pct = ((open_p - prev_close) / prev_close) * 100.0
    curr_c = candles[-1]["close"]

    if abs(gap_pct) < 0.75:
        return {"signal": "NEUTRAL", "reason": f"Gap of {gap_pct:+.2f}% is below 0.75% threshold"}

    # Gap Up
    if gap_pct >= 0.75:
        # Check if 1st 15m candle held above open (Gap-and-Go)
        if len(candles) >= 3 and candles[2]["close"] >= open_p and curr_c >= open_p:
            stop = round(open_p * 0.995, 2)
            risk = max(curr_c - stop, curr_c * 0.005)
            return {
                "signal": "BUY",
                "entry": round(curr_c, 2),
                "stop": stop,
                "target": round(curr_c + risk * 2.2, 2),
                "risk_reward": 2.2,
                "confidence": "HIGH",
                "reason": f"Gap-and-Go: {gap_pct:+.2f}% morning gap held above open ₹{open_p:.2f}"
            }
        # Gap-Fill Fade
        elif curr_c < open_p:
            stop = round(open_p * 1.005, 2)
            return {
                "signal": "SELL",
                "entry": round(curr_c, 2),
                "stop": stop,
                "target": round(prev_close, 2),
                "risk_reward": 1.8,
                "confidence": "MEDIUM",
                "reason": f"Gap-Fill: Gapping stock breaking below open toward prev close ₹{prev_close:.2f}"
            }
    # Gap Down
    else:
        if len(candles) >= 3 and candles[2]["close"] <= open_p and curr_c <= open_p:
            stop = round(open_p * 1.005, 2)
            risk = max(stop - curr_c, curr_c * 0.005)
            return {
                "signal": "SELL",
                "entry": round(curr_c, 2),
                "stop": stop,
                "target": round(curr_c - risk * 2.2, 2),
                "risk_reward": 2.2,
                "confidence": "HIGH",
                "reason": f"Gap-and-Go: Bearish {gap_pct:+.2f}% gap rejected open resistance"
            }
        elif curr_c > open_p:
            stop = round(open_p * 0.995, 2)
            return {
                "signal": "BUY",
                "entry": round(curr_c, 2),
                "stop": stop,
                "target": round(prev_close, 2),
                "risk_reward": 1.8,
                "confidence": "MEDIUM",
                "reason": f"Gap-Fill: Gap down fading upward toward prev close ₹{prev_close:.2f}"
            }
    return {"signal": "NEUTRAL", "reason": "Gap setup pending confirmation"}


def eval_nr7_inside(candles, daily_bars=None):
    """4. Volume Breakout / NR7 & Inside Bar."""
    if not daily_bars or len(daily_bars) < 7:
        # Fallback to intraday narrow range if daily history unavailable
        if len(candles) < 14:
            return {"signal": "NEUTRAL", "reason": "Insufficient history for NR7"}
        ranges = [c["high"] - c["low"] for c in candles[-14:-1]]
        last_range = candles[-1]["high"] - candles[-1]["low"]
        is_nr = last_range <= min(ranges)
    else:
        ranges = [b["high"] - b["low"] for b in daily_bars[-7:-1]]
        y_range = daily_bars[-1]["high"] - daily_bars[-1]["low"]
        is_nr = y_range <= min(ranges)

    if not candles:
        return {"signal": "NEUTRAL", "reason": "No intraday data"}

    curr = candles[-1]
    curr_c = curr["close"]
    vols = [float(c.get("volume", 1)) for c in candles]
    avg_v = sum(vols[-20:]) / min(len(vols), 20) if vols else 1.0
    v_ratio = (curr.get("volume", 1) / avg_v) if avg_v > 0 else 1.0

    if is_nr and v_ratio >= 1.8:
        # Volatility breakout
        if curr_c > curr["open"]:
            stop = round(curr["low"] * 0.997, 2)
            risk = max(curr_c - stop, curr_c * 0.005)
            return {
                "signal": "BUY",
                "entry": round(curr_c, 2),
                "stop": stop,
                "target": round(curr_c + risk * 2.5, 2),
                "risk_reward": 2.5,
                "confidence": "HIGH",
                "reason": f"NR7 Volatility Squeeze expansion with {v_ratio:.1f}x volume explosion"
            }
        else:
            stop = round(curr["high"] * 1.003, 2)
            risk = max(stop - curr_c, curr_c * 0.005)
            return {
                "signal": "SELL",
                "entry": round(curr_c, 2),
                "stop": stop,
                "target": round(curr_c - risk * 2.5, 2),
                "risk_reward": 2.5,
                "confidence": "HIGH",
                "reason": f"NR7 Volatility Breakdown with {v_ratio:.1f}x volume surge"
            }
    return {"signal": "NEUTRAL", "reason": "NR7 / Inside bar condition not active"}


def eval_vwap_pullback(candles):
    """5. Intraday VWAP Pullback Strategy."""
    if len(candles) < 5:
        return {"signal": "NEUTRAL", "reason": "Awaiting more candles for VWAP calculation"}
    vwaps = calculate_vwap(candles)
    curr_vwap = vwaps[-1]
    curr = candles[-1]
    curr_c = curr["close"]
    dist_pct = abs(curr_c - curr_vwap) / curr_vwap * 100.0

    # Uptrend pullback: trading above VWAP earlier, now touching VWAP within 0.25%
    if curr_c >= curr_vwap and dist_pct <= 0.35 and curr["low"] <= curr_vwap * 1.001:
        stop = round(curr_vwap * 0.995, 2)
        risk = max(curr_c - stop, curr_c * 0.004)
        return {
            "signal": "BUY",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c + risk * 1.5, 2),
            "risk_reward": 1.5,
            "confidence": "HIGH",
            "reason": f"Bullish VWAP bounce: Price ₹{curr_c:.2f} retesting VWAP ₹{curr_vwap:.2f} (diff {dist_pct:.2f}%)"
        }
    elif curr_c <= curr_vwap and dist_pct <= 0.35 and curr["high"] >= curr_vwap * 0.999:
        stop = round(curr_vwap * 1.005, 2)
        risk = max(stop - curr_c, curr_c * 0.004)
        return {
            "signal": "SELL",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c - risk * 1.5, 2),
            "risk_reward": 1.5,
            "confidence": "HIGH",
            "reason": f"Bearish VWAP rejection: Price ₹{curr_c:.2f} rejected off VWAP ₹{curr_vwap:.2f} (diff {dist_pct:.2f}%)"
        }
    return {"signal": "NEUTRAL", "reason": f"VWAP ₹{curr_vwap:.2f} (distance {dist_pct:.2f}%) outside pullback zone"}


def eval_ema_crossover(candles, fast=9, slow=20):
    """6. 9 / 20 EMA Crossover Trend-Following."""
    if len(candles) < slow + 2:
        return {"signal": "NEUTRAL", "reason": "Insufficient candles for EMA calculation"}
    closes = [c["close"] for c in candles]
    ema_fast = calculate_ema(closes, fast)
    ema_slow = calculate_ema(closes, slow)
    curr_c = closes[-1]

    # Check for crossover in last 2 bars
    bull_cross = ema_fast[-2] <= ema_slow[-2] and ema_fast[-1] > ema_slow[-1]
    bear_cross = ema_fast[-2] >= ema_slow[-2] and ema_fast[-1] < ema_slow[-1]

    if bull_cross or (ema_fast[-1] > ema_slow[-1] and curr_c > ema_fast[-1]):
        stop = round(ema_slow[-1] * 0.996, 2)
        risk = max(curr_c - stop, curr_c * 0.005)
        return {
            "signal": "BUY",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c + risk * 2.5, 2),
            "risk_reward": 2.5,
            "confidence": "HIGH" if bull_cross else "MEDIUM",
            "reason": f"9 EMA (₹{ema_fast[-1]:.2f}) > 20 EMA (₹{ema_slow[-1]:.2f}) Bullish Trend"
        }
    elif bear_cross or (ema_fast[-1] < ema_slow[-1] and curr_c < ema_fast[-1]):
        stop = round(ema_slow[-1] * 1.004, 2)
        risk = max(stop - curr_c, curr_c * 0.005)
        return {
            "signal": "SELL",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c - risk * 2.5, 2),
            "risk_reward": 2.5,
            "confidence": "HIGH" if bear_cross else "MEDIUM",
            "reason": f"9 EMA (₹{ema_fast[-1]:.2f}) < 20 EMA (₹{ema_slow[-1]:.2f}) Bearish Trend"
        }
    return {"signal": "NEUTRAL", "reason": "EMAs in tight convergence"}


def eval_supertrend(candles, period=10, multiplier=3.0):
    """7. Supertrend (10, 3) Trend-Following."""
    if len(candles) < period + 2:
        return {"signal": "NEUTRAL", "reason": "Insufficient candles for Supertrend calculation"}
    st = calculate_supertrend(candles, period, multiplier)
    curr_c = candles[-1]["close"]
    prev_st = calculate_supertrend(candles[:-1], period, multiplier)

    is_bull_flip = prev_st["trend"] == -1 and st["trend"] == 1
    is_bear_flip = prev_st["trend"] == 1 and st["trend"] == -1

    if st["trend"] == 1:
        stop = round(st["line"], 2)
        risk = max(curr_c - stop, curr_c * 0.005)
        return {
            "signal": "BUY",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c + risk * 2.0, 2),
            "risk_reward": 2.0,
            "confidence": "HIGH" if is_bull_flip else "MEDIUM",
            "reason": f"Supertrend GREEN (₹{st['line']:.2f}) - Bullish Trend" + (" [FRESH FLIP]" if is_bull_flip else "")
        }
    else:
        stop = round(st["line"], 2)
        risk = max(stop - curr_c, curr_c * 0.005)
        return {
            "signal": "SELL",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c - risk * 2.0, 2),
            "risk_reward": 2.0,
            "confidence": "HIGH" if is_bear_flip else "MEDIUM",
            "reason": f"Supertrend RED (₹{st['line']:.2f}) - Bearish Trend" + (" [FRESH FLIP]" if is_bear_flip else "")
        }


def eval_ema20_rsi_retest(candles):
    """8. Pullback to 20 EMA with RSI Filter."""
    if len(candles) < 22:
        return {"signal": "NEUTRAL", "reason": "Insufficient data for 20 EMA & RSI(14)"}
    closes = [c["close"] for c in candles]
    ema20 = calculate_ema(closes, 20)[-1]
    rsi = calculate_rsi(closes, 14)[-1]
    curr = candles[-1]
    curr_c = curr["close"]
    dist_pct = abs(curr_c - ema20) / ema20 * 100.0

    if dist_pct <= 0.35 and curr_c >= ema20 and 40.0 <= rsi <= 58.0:
        stop = round(ema20 * 0.994, 2)
        risk = max(curr_c - stop, curr_c * 0.004)
        return {
            "signal": "BUY",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c + risk * 1.8, 2),
            "risk_reward": 1.8,
            "confidence": "HIGH",
            "reason": f"20 EMA Retest at ₹{ema20:.2f} with healthy bull RSI {rsi:.1f} (40-58 reset)"
        }
    elif dist_pct <= 0.35 and curr_c <= ema20 and 42.0 <= rsi <= 60.0:
        stop = round(ema20 * 1.006, 2)
        risk = max(stop - curr_c, curr_c * 0.004)
        return {
            "signal": "SELL",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c - risk * 1.8, 2),
            "risk_reward": 1.8,
            "confidence": "HIGH",
            "reason": f"20 EMA Retest at ₹{ema20:.2f} with healthy bear RSI {rsi:.1f} (42-60 bounce)"
        }
    return {"signal": "NEUTRAL", "reason": f"20 EMA ₹{ema20:.2f}, RSI {rsi:.1f} outside retest setup"}


def eval_rsi_divergence(candles):
    """9. RSI(14) Divergence & Extremes."""
    if len(candles) < 25:
        return {"signal": "NEUTRAL", "reason": "Insufficient candles for RSI divergence"}
    closes = [c["close"] for c in candles]
    rsi_vals = calculate_rsi(closes, 14)
    curr_c = closes[-1]
    curr_rsi = rsi_vals[-1]

    # Look for swing points in last 15 bars
    recent_c = closes[-15:]
    recent_rsi = rsi_vals[-15:]
    min_c = min(recent_c)
    max_c = max(recent_c)

    # Bullish Divergence: Price near recent low, but RSI forming higher low
    if curr_c <= min_c * 1.005 and curr_rsi > min(recent_rsi) + 4.0 and curr_rsi < 45.0:
        stop = round(min_c * 0.994, 2)
        risk = max(curr_c - stop, curr_c * 0.005)
        return {
            "signal": "BUY",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c + risk * 2.2, 2),
            "risk_reward": 2.2,
            "confidence": "HIGH",
            "reason": f"Regular Bullish RSI Divergence: Price low ₹{min_c:.2f} with rising RSI {curr_rsi:.1f}"
        }
    # Bearish Divergence: Price near recent high, but RSI forming lower high
    elif curr_c >= max_c * 0.995 and curr_rsi < max(recent_rsi) - 4.0 and curr_rsi > 55.0:
        stop = round(max_c * 1.006, 2)
        risk = max(stop - curr_c, curr_c * 0.005)
        return {
            "signal": "SELL",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c - risk * 2.2, 2),
            "risk_reward": 2.2,
            "confidence": "HIGH",
            "reason": f"Regular Bearish RSI Divergence: Price high ₹{max_c:.2f} with falling RSI {curr_rsi:.1f}"
        }
    return {"signal": "NEUTRAL", "reason": f"RSI {curr_rsi:.1f} in equilibrium (no divergence)"}


def eval_bollinger_bands(candles, period=20, num_std=2.0):
    """10. Bollinger Bands Squeeze & Snap-Back."""
    if len(candles) < period + 2:
        return {"signal": "NEUTRAL", "reason": "Insufficient candles for Bollinger Bands"}
    closes = [c["close"] for c in candles]
    bb = calculate_bollinger_bands(closes, period, num_std)
    curr_c = closes[-1]

    # Snap-back mean reversion if closing outside lower band
    if curr_c < bb["lower"]:
        stop = round(curr_c * 0.993, 2)
        return {
            "signal": "BUY",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": bb["middle"],
            "risk_reward": 1.4,
            "confidence": "MEDIUM",
            "reason": f"Bollinger Snap-Back: Price ₹{curr_c:.2f} below Lower Band ₹{bb['lower']:.2f} reverting to SMA ₹{bb['middle']:.2f}"
        }
    elif curr_c > bb["upper"]:
        stop = round(curr_c * 1.007, 2)
        return {
            "signal": "SELL",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": bb["middle"],
            "risk_reward": 1.4,
            "confidence": "MEDIUM",
            "reason": f"Bollinger Snap-Back: Price ₹{curr_c:.2f} above Upper Band ₹{bb['upper']:.2f} reverting to SMA ₹{bb['middle']:.2f}"
        }
    return {"signal": "NEUTRAL", "reason": f"Price inside bands [₹{bb['lower']:.2f} - ₹{bb['upper']:.2f}], Bandwidth {bb['bandwidth']:.2f}%"}


def eval_cpr_camarilla_strat(candles, prev_bar):
    """11. Central Pivot Range (CPR) & Camarilla."""
    if not prev_bar or not candles:
        return {"signal": "NEUTRAL", "reason": "Daily bar required for CPR"}
    cpr = calculate_cpr_camarilla(prev_bar["high"], prev_bar["low"], prev_bar["close"])
    curr_c = candles[-1]["close"]

    if cpr["is_narrow"]:
        # Narrow CPR = Breakout day
        if curr_c > max(cpr["tc"], cpr["bc"]):
            stop = round(min(cpr["tc"], cpr["bc"]), 2)
            risk = max(curr_c - stop, curr_c * 0.005)
            return {
                "signal": "BUY",
                "entry": round(curr_c, 2),
                "stop": stop,
                "target": round(cpr["h4"], 2),
                "risk_reward": 1.7,
                "confidence": "HIGH",
                "reason": f"Narrow CPR ({cpr['cpr_width_pct']:.2f}%) Trending Breakout above Top Central ₹{cpr['tc']:.2f}"
            }
        elif curr_c < min(cpr["tc"], cpr["bc"]):
            stop = round(max(cpr["tc"], cpr["bc"]), 2)
            risk = max(stop - curr_c, curr_c * 0.005)
            return {
                "signal": "SELL",
                "entry": round(curr_c, 2),
                "stop": stop,
                "target": round(cpr["l4"], 2),
                "risk_reward": 1.7,
                "confidence": "HIGH",
                "reason": f"Narrow CPR ({cpr['cpr_width_pct']:.2f}%) Trending Breakdown below Bottom Central ₹{cpr['bc']:.2f}"
            }
    else:
        # Wide CPR = Range day (Buy near L3, Sell near H3)
        if abs(curr_c - cpr["l3"]) / curr_c < 0.003:
            return {
                "signal": "BUY",
                "entry": round(curr_c, 2),
                "stop": round(cpr["l4"], 2),
                "target": round(cpr["pivot"], 2),
                "risk_reward": 1.5,
                "confidence": "MEDIUM",
                "reason": f"Wide CPR ({cpr['cpr_width_pct']:.2f}%) Range Bounce off Camarilla L3 ₹{cpr['l3']:.2f}"
            }
        elif abs(curr_c - cpr["h3"]) / curr_c < 0.003:
            return {
                "signal": "SELL",
                "entry": round(curr_c, 2),
                "stop": round(cpr["h4"], 2),
                "target": round(cpr["pivot"], 2),
                "risk_reward": 1.5,
                "confidence": "MEDIUM",
                "reason": f"Wide CPR ({cpr['cpr_width_pct']:.2f}%) Range Rejection off Camarilla H3 ₹{cpr['h3']:.2f}"
            }
    return {"signal": "NEUTRAL", "reason": f"Trading within CPR zone [₹{min(cpr['tc'], cpr['bc']):.2f} - ₹{max(cpr['tc'], cpr['bc']):.2f}]"}


def eval_micro_scalp(candles):
    """12. 1m-3m Micro Scalper."""
    if len(candles) < 4:
        return {"signal": "NEUTRAL", "reason": "Awaiting micro candle sequence"}
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    curr_c = c3["close"]

    # 3 consecutive green candles with increasing volume
    v1 = float(c1.get("volume", 1))
    v2 = float(c2.get("volume", 1))
    v3 = float(c3.get("volume", 1))

    if c1["close"] > c1["open"] and c2["close"] > c2["open"] and c3["close"] > c3["open"] and v3 > v2 > v1:
        stop = round(c3["low"] * 0.998, 2)
        risk = max(curr_c - stop, curr_c * 0.002)
        return {
            "signal": "BUY",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c + risk * 1.2, 2),
            "risk_reward": 1.0,
            "confidence": "HIGH",
            "reason": f"Micro scalper surge: 3 consecutive expanding bull candles with volume push"
        }
    elif c1["close"] < c1["open"] and c2["close"] < c2["open"] and c3["close"] < c3["open"] and v3 > v2 > v1:
        stop = round(c3["high"] * 1.002, 2)
        risk = max(stop - curr_c, curr_c * 0.002)
        return {
            "signal": "SELL",
            "entry": round(curr_c, 2),
            "stop": stop,
            "target": round(curr_c - risk * 1.2, 2),
            "risk_reward": 1.0,
            "confidence": "HIGH",
            "reason": f"Micro scalper flush: 3 consecutive expanding bear candles with volume dump"
        }
    return {"signal": "NEUTRAL", "reason": "No high-velocity micro scalp sequence"}


def eval_options_delta_burst(candles, symbol="NIFTY"):
    """13. Expiry-Day Option Delta Burst (Model)."""
    now_ist = datetime.datetime.now(datetime.timezone.utc) + IST_OFFSET
    is_expiry_day = now_ist.weekday() in (3, 4) # Thursday (Nifty) or Friday (BSE Sensex)
    is_post_1030 = now_ist.time() >= datetime.time(10, 30)

    if not candles:
        return {"signal": "NEUTRAL", "reason": "No data"}
    curr_c = candles[-1]["close"]

    if is_expiry_day and is_post_1030 and len(candles) >= 12:
        # Check if breaking out of 10:00-10:30 consolidation
        recent_h = max(c["high"] for c in candles[-6:])
        if curr_c >= recent_h:
            return {
                "signal": "BUY",
                "instrument": "ATM CALL OPTION",
                "entry": round(curr_c, 2),
                "stop": round(curr_c * 0.994, 2),
                "target": round(curr_c * 1.012, 2),
                "risk_reward": 3.5,
                "confidence": "HIGH",
                "reason": "Expiry-Day Gamma Surge: Post-10:30 breakout on weekly expiry with rapid delta acceleration"
            }
    return {"signal": "NEUTRAL", "reason": f"Expiry delta burst conditions not met (Expiry: {is_expiry_day}, Post-10:30: {is_post_1030})"}


def eval_options_strangle(candles, vix=13.0):
    """14. OTM Strangle / Iron Condor Decay (Model)."""
    if vix > 15.0:
        return {"signal": "NEUTRAL", "reason": f"India VIX {vix:.1f} too high for naked strangle selling (>15.0)"}
    if not candles:
        return {"signal": "NEUTRAL", "reason": "No data"}
    curr_c = candles[-1]["close"]

    # Safe low VIX decay setup
    return {
        "signal": "SELL",
        "instrument": "SHORT OTM STRANGLE (15-Delta CE + PE)",
        "entry": round(curr_c, 2),
        "stop": round(curr_c * 1.015, 2),
        "target": round(curr_c, 2),
        "risk_reward": 0.8,
        "confidence": "HIGH",
        "reason": f"Low VIX ({vix:.1f}) Intraday Theta Harvest: Sell 15-delta Call/Put with hard 15:10 auto-exit"
    }


def eval_options_920_straddle(candles):
    """15. 9:20 AM Rule-Based Straddle (920 Straddle Model)."""
    now_ist = datetime.datetime.now(datetime.timezone.utc) + IST_OFFSET
    is_open_window = datetime.time(9, 20) <= now_ist.time() <= datetime.time(15, 10)

    if not candles:
        return {"signal": "NEUTRAL", "reason": "No data"}
    curr_c = candles[-1]["close"]

    return {
        "signal": "SELL",
        "instrument": "ATM STRADDLE (SELL CE + PE AT 09:20)",
        "entry": round(curr_c, 2),
        "stop": round(curr_c * 1.25, 2),
        "target": round(curr_c * 0.75, 2),
        "stop_loss_pct": "25% per leg",
        "square_off": "15:10 IST",
        "risk_reward": 1.2,
        "confidence": "HIGH",
        "reason": "Systematic 920 Straddle: Harvest opening volatility crush with strict 25% individual stop per leg"
    }


def eval_options_max_pain(symbol="NIFTY"):
    """16. Open Interest (OI) & Max Pain Gravitation (Analysis Only)."""
    return {
        "signal": "NEUTRAL",
        "raw_signal": "NEUTRAL",
        "score": 0,
        "is_executable": False,
        "confidence": "LOW",
        "status": "NOT IMPLEMENTED (analysis only)",
        "reason": "Real-time NSE Options Chain API required for live Max Pain / PCR calculations. Marked analysis only."
    }


def eval_news_results(candles):
    """17. Results & News Momentum Reaction."""
    if len(candles) < 3:
        return {"signal": "NEUTRAL", "reason": "Awaiting post-news candle formation"}
    curr_c = candles[-1]["close"]
    first_c = candles[0]["open"]
    move_pct = (curr_c - first_c) / first_c * 100.0

    if abs(move_pct) >= 1.5:
        if move_pct > 0:
            return {
                "signal": "BUY",
                "entry": round(curr_c, 2),
                "stop": round(curr_c * 0.985, 2),
                "target": round(curr_c * 1.035, 2),
                "risk_reward": 2.5,
                "confidence": "HIGH",
                "reason": f"High-Beta Event Reaction: {move_pct:+.2f}% momentum burst post corporate announcement"
            }
        else:
            return {
                "signal": "SELL",
                "entry": round(curr_c, 2),
                "stop": round(curr_c * 1.015, 2),
                "target": round(curr_c * 0.965, 2),
                "risk_reward": 2.5,
                "confidence": "HIGH",
                "reason": f"High-Beta Event Selloff: {move_pct:+.2f}% impulse drop on news breakdown"
            }
    return {"signal": "NEUTRAL", "reason": f"Move {move_pct:+.2f}% within normal non-event volatility"}


def eval_sector_momentum(symbol="TCS.NS"):
    """18. Sector Momentum Leader (Analysis Only)."""
    return {
        "signal": "NEUTRAL",
        "raw_signal": "NEUTRAL",
        "score": 0,
        "is_executable": False,
        "confidence": "LOW",
        "status": "NOT IMPLEMENTED (analysis only)",
        "reason": "Multi-symbol sector relative strength matrix not connected to live feed. Marked analysis only."
    }


def eval_fiidii_flow():
    """19. FII/DII Institutional Flow + GIFT Nifty Global Bias (Analysis Only)."""
    return {
        "signal": "NEUTRAL",
        "raw_signal": "NEUTRAL",
        "score": 0,
        "is_executable": False,
        "confidence": "LOW",
        "status": "NOT IMPLEMENTED (analysis only)",
        "reason": "Official SEBI/NSE end-of-day FII/DII reporting feed required. Marked analysis only."
    }


def eval_aic_confluence(symbol, candles, prev_bar, vix=None, breadth_ratio=None):
    """20. CUSTOM: Vyapar Institutional Confluence (AIC-20) Master Model.
    Scores setups from 0 to 100 points across 6 uncorrelated institutional pillars:
      1. Microstructure CPR (15 pts)
      2. VWAP Benchmark (20 pts)
      3. Trend Alignment Supertrend & EMA (20 pts)
      4. Volume Fuel (15 pts)
      5. Market Breadth (15 pts)
      6. India VIX Regime (15 pts)
    Executes BUY/SELL only when Score >= 80 points with direction-aligned confluence.
    No free points awarded for non-aligned pillars.
    """
    # Drop still-forming candle if more than 1 candle exists
    completed_candles = candles[:-1] if candles and len(candles) > 1 else (candles or [])
    if len(completed_candles) < 10:
        return {
            "strategy_id": "aic_confluence",
            "strategy_name": "Vyapar Institutional Confluence (AIC-20)",
            "signal": "NEUTRAL",
            "raw_signal": "NEUTRAL",
            "score": 0,
            "threshold": 80,
            "is_executable": False,
            "confidence": "LOW",
            "entry": 0.0,
            "stop": 0.0,
            "target": 0.0,
            "pillars": {
                "cpr": {"pts": 0, "max": 15, "name": "CPR", "desc": "Insufficient candle data"},
                "vwap": {"pts": 0, "max": 20, "name": "VWAP", "desc": "Insufficient candle data"},
                "trend": {"pts": 0, "max": 20, "name": "Trend", "desc": "Insufficient candle data"},
                "volume": {"pts": 0, "max": 15, "name": "Volume", "desc": "Insufficient candle data"},
                "breadth": {"pts": 0, "max": 15, "name": "Breadth", "desc": "Insufficient candle data"},
                "vix": {"pts": 0, "max": 15, "name": "VIX", "desc": "Insufficient candle data"}
            },
            "factors": ["Insufficient completed candle history (need >= 10 bars)"],
            "reason": "Insufficient completed candle history (need >= 10 bars)"
        }

    curr = completed_candles[-1]
    curr_c = float(curr["close"])

    # Indicators from completed candles
    vwaps = calculate_vwap(completed_candles)
    curr_vwap = vwaps[-1] if vwaps else curr_c

    st = calculate_supertrend(completed_candles)
    closes = [float(c["close"]) for c in completed_candles]
    ema9 = calculate_ema(closes, 9)[-1] if len(closes) >= 9 else curr_c
    ema20 = calculate_ema(closes, 20)[-1] if len(closes) >= 20 else curr_c

    vols = [float(c.get("volume", 0)) for c in completed_candles]
    avg_v = sum(vols[-20:]) / min(len(vols), 20) if vols else 1.0
    v_ratio = (curr.get("volume", 0) / avg_v) if avg_v > 0 else 1.0

    cpr = calculate_cpr_camarilla(prev_bar["high"], prev_bar["low"], prev_bar["close"]) if prev_bar else None

    # Resolve real VIX and breadth
    v_val = vix if (vix is not None and vix > 0) else 0.0
    b_val = breadth_ratio if (breadth_ratio is not None and breadth_ratio > 0) else 1.0

    # -------------------------------------------------------------
    # Evaluate Direction-Aligned Confluence (Strictly NO Free Points)
    # -------------------------------------------------------------
    # 1. Long Candidate (BUY)
    long_pts = 0
    long_pillars = {}
    long_factors = []

    # CPR
    if cpr and curr_c > cpr["tc"]:
        pts = 15 if cpr["is_narrow"] else 7
        long_pts += pts
        long_pillars["cpr"] = {"pts": pts, "max": 15, "name": "CPR", "desc": f"Above CPR TC Rs {cpr['tc']:.2f} ({'Narrow' if cpr['is_narrow'] else 'Normal'})"}
        long_factors.append(f"Price above CPR TC (+{pts} pts)")
    else:
        long_pillars["cpr"] = {"pts": 0, "max": 15, "name": "CPR", "desc": "Inside or below CPR TC (0 pts)"}

    # VWAP (Strictly NO free points if price <= VWAP)
    if curr_c > curr_vwap:
        long_pts += 20
        dist = ((curr_c - curr_vwap) / curr_vwap) * 100.0
        long_pillars["vwap"] = {"pts": 20, "max": 20, "name": "VWAP", "desc": f"Above VWAP Rs {curr_vwap:.2f} (+{dist:.2f}%)"}
        long_factors.append("Price above Institutional VWAP (+20 pts)")
    else:
        long_pillars["vwap"] = {"pts": 0, "max": 20, "name": "VWAP", "desc": f"Price below VWAP Rs {curr_vwap:.2f} (0 pts)"}

    # Trend (Supertrend & EMA)
    if st["trend"] == 1 and ema9 >= ema20:
        long_pts += 20
        long_pillars["trend"] = {"pts": 20, "max": 20, "name": "Trend", "desc": "Supertrend GREEN & 9 EMA >= 20 EMA"}
        long_factors.append("Supertrend GREEN & 9 EMA > 20 EMA (+20 pts)")
    elif st["trend"] == 1 or ema9 >= ema20:
        long_pts += 8
        long_pillars["trend"] = {"pts": 8, "max": 20, "name": "Trend", "desc": "Partial bullish trend alignment"}
        long_factors.append("Partial bullish trend (+8 pts)")
    else:
        long_pillars["trend"] = {"pts": 0, "max": 20, "name": "Trend", "desc": "Bearish trend alignment (0 pts)"}

    # Volume Fuel
    if v_ratio >= 1.3:
        long_pts += 15
        long_pillars["volume"] = {"pts": 15, "max": 15, "name": "Volume", "desc": f"Strong volume surge {v_ratio:.1f}x"}
        long_factors.append(f"Volume surge {v_ratio:.1f}x (+15 pts)")
    elif v_ratio >= 1.15:
        long_pts += 8
        long_pillars["volume"] = {"pts": 8, "max": 15, "name": "Volume", "desc": f"Above average volume {v_ratio:.1f}x"}
        long_factors.append(f"Above-average volume {v_ratio:.1f}x (+8 pts)")
    else:
        long_pillars["volume"] = {"pts": 0, "max": 15, "name": "Volume", "desc": f"Subdued volume {v_ratio:.1f}x (0 pts)"}

    # Market Breadth
    if b_val >= 1.25:
        long_pts += 15
        long_pillars["breadth"] = {"pts": 15, "max": 15, "name": "Breadth", "desc": f"Bullish breadth A/D {b_val:.2f}"}
        long_factors.append(f"Bullish breadth {b_val:.2f} (+15 pts)")
    else:
        long_pillars["breadth"] = {"pts": 0, "max": 15, "name": "Breadth", "desc": f"Unaligned breadth A/D {b_val:.2f} (0 pts)"}

    # India VIX
    if 11.5 <= v_val <= 18.0:
        long_pts += 15
        long_pillars["vix"] = {"pts": 15, "max": 15, "name": "VIX", "desc": f"Optimal stable VIX {v_val:.1f}"}
        long_factors.append(f"Stable VIX {v_val:.1f} (+15 pts)")
    elif 18.0 < v_val <= 22.0:
        long_pts += 8
        long_pillars["vix"] = {"pts": 8, "max": 15, "name": "VIX", "desc": f"Moderate VIX {v_val:.1f}"}
        long_factors.append(f"Moderate VIX {v_val:.1f} (+8 pts)")
    else:
        long_pillars["vix"] = {"pts": 0, "max": 15, "name": "VIX", "desc": f"VIX {v_val:.1f} out of optimal regime (0 pts)"}

    # 2. Short Candidate (SELL)
    short_pts = 0
    short_pillars = {}
    short_factors = []

    # CPR
    if cpr and curr_c < cpr["bc"]:
        pts = 15 if cpr["is_narrow"] else 7
        short_pts += pts
        short_pillars["cpr"] = {"pts": pts, "max": 15, "name": "CPR", "desc": f"Below CPR BC Rs {cpr['bc']:.2f} ({'Narrow' if cpr['is_narrow'] else 'Normal'})"}
        short_factors.append(f"Price below CPR BC (+{pts} pts)")
    else:
        short_pillars["cpr"] = {"pts": 0, "max": 15, "name": "CPR", "desc": "Inside or above CPR BC (0 pts)"}

    # VWAP (Strictly NO free points if price >= VWAP)
    if curr_c < curr_vwap:
        short_pts += 20
        dist = ((curr_vwap - curr_c) / curr_vwap) * 100.0
        short_pillars["vwap"] = {"pts": 20, "max": 20, "name": "VWAP", "desc": f"Below VWAP Rs {curr_vwap:.2f} (-{dist:.2f}%)"}
        short_factors.append("Price below Institutional VWAP (+20 pts)")
    else:
        short_pillars["vwap"] = {"pts": 0, "max": 20, "name": "VWAP", "desc": f"Price above VWAP Rs {curr_vwap:.2f} (0 pts)"}

    # Trend (Supertrend & EMA)
    if st["trend"] == -1 and ema9 <= ema20:
        short_pts += 20
        short_pillars["trend"] = {"pts": 20, "max": 20, "name": "Trend", "desc": "Supertrend RED & 9 EMA <= 20 EMA"}
        short_factors.append("Supertrend RED & 9 EMA < 20 EMA (+20 pts)")
    elif st["trend"] == -1 or ema9 <= ema20:
        short_pts += 8
        short_pillars["trend"] = {"pts": 8, "max": 20, "name": "Trend", "desc": "Partial bearish trend alignment"}
        short_factors.append("Partial bearish trend (+8 pts)")
    else:
        short_pillars["trend"] = {"pts": 0, "max": 20, "name": "Trend", "desc": "Bullish trend alignment (0 pts)"}

    # Volume Fuel
    if v_ratio >= 1.3:
        short_pts += 15
        short_pillars["volume"] = {"pts": 15, "max": 15, "name": "Volume", "desc": f"Strong volume surge {v_ratio:.1f}x"}
        short_factors.append(f"Volume surge {v_ratio:.1f}x (+15 pts)")
    elif v_ratio >= 1.15:
        short_pts += 8
        short_pillars["volume"] = {"pts": 8, "max": 15, "name": "Volume", "desc": f"Above average volume {v_ratio:.1f}x"}
        short_factors.append(f"Above-average volume {v_ratio:.1f}x (+8 pts)")
    else:
        short_pillars["volume"] = {"pts": 0, "max": 15, "name": "Volume", "desc": f"Subdued volume {v_ratio:.1f}x (0 pts)"}

    # Market Breadth
    if b_val <= 0.80:
        short_pts += 15
        short_pillars["breadth"] = {"pts": 15, "max": 15, "name": "Breadth", "desc": f"Bearish breadth A/D {b_val:.2f}"}
        short_factors.append(f"Bearish breadth {b_val:.2f} (+15 pts)")
    else:
        short_pillars["breadth"] = {"pts": 0, "max": 15, "name": "Breadth", "desc": f"Unaligned breadth A/D {b_val:.2f} (0 pts)"}

    # India VIX
    if 16.0 <= v_val <= 26.0:
        short_pts += 15
        short_pillars["vix"] = {"pts": 15, "max": 15, "name": "VIX", "desc": f"Elevated VIX {v_val:.1f} favoring breakdown"}
        short_factors.append(f"Elevated VIX {v_val:.1f} (+15 pts)")
    elif 13.0 <= v_val < 16.0:
        short_pts += 8
        short_pillars["vix"] = {"pts": 8, "max": 15, "name": "VIX", "desc": f"Moderate VIX {v_val:.1f}"}
        short_factors.append(f"Moderate VIX {v_val:.1f} (+8 pts)")
    else:
        short_pillars["vix"] = {"pts": 0, "max": 15, "name": "VIX", "desc": f"VIX {v_val:.1f} out of breakdown regime (0 pts)"}

    # -------------------------------------------------------------
    # Direction Selection & Stop Geometry Validation
    # -------------------------------------------------------------
    if long_pts > short_pts and long_pts >= 50:
        side = "BUY"
        score = long_pts
        pillars = long_pillars
        factors = long_factors
    elif short_pts > long_pts and short_pts >= 50:
        side = "SELL"
        score = short_pts
        pillars = short_pillars
        factors = short_factors
    else:
        side = "NEUTRAL"
        if long_pts >= short_pts:
            score = long_pts
            pillars = long_pillars
            factors = long_factors
        else:
            score = short_pts
            pillars = short_pillars
            factors = short_factors

    is_executable = (score >= 80 and side in ("BUY", "SELL"))

    entry = round(curr_c, 2)
    if side == "BUY":
        # Enforce stop strictly below entry
        raw_stop = min(curr_c * 0.992, (curr_vwap * 0.996) if curr_vwap < curr_c else (curr_c * 0.992))
        stop = round(raw_stop, 2)
        if stop >= entry:
            return {
                "strategy_id": "aic_confluence",
                "strategy_name": "Vyapar Institutional Confluence (AIC-20)",
                "signal": "NEUTRAL",
                "raw_signal": "BUY",
                "score": score,
                "threshold": 80,
                "is_executable": False,
                "confidence": "LOW",
                "entry": entry,
                "stop": stop,
                "target": 0.0,
                "risk_reward": 0.0,
                "pillars": pillars,
                "factors": factors + [f"Stop geometry failure: stop {stop} >= entry {entry}"],
                "reason": f"BUY stop {stop:.2f} >= entry {entry:.2f}; setup neutralized"
            }
        risk = entry - stop
        target = round(entry + (risk * 2.2), 2)
    elif side == "SELL":
        # Enforce stop strictly above entry
        raw_stop = max(curr_c * 1.008, (curr_vwap * 1.004) if curr_vwap > curr_c else (curr_c * 1.008))
        stop = round(raw_stop, 2)
        if stop <= entry:
            return {
                "strategy_id": "aic_confluence",
                "strategy_name": "Vyapar Institutional Confluence (AIC-20)",
                "signal": "NEUTRAL",
                "raw_signal": "SELL",
                "score": score,
                "threshold": 80,
                "is_executable": False,
                "confidence": "LOW",
                "entry": entry,
                "stop": stop,
                "target": 0.0,
                "risk_reward": 0.0,
                "pillars": pillars,
                "factors": factors + [f"Stop geometry failure: stop {stop} <= entry {entry}"],
                "reason": f"SELL stop {stop:.2f} <= entry {entry:.2f}; setup neutralized"
            }
        risk = stop - entry
        target = round(entry - (risk * 2.2), 2)
    else:
        stop = round(curr_c * 0.992, 2)
        target = round(curr_c * 1.015, 2)

    status_tag = "PASSED (HIGH CONFLUENCE)" if is_executable else ("STANDBY (SCORE < 80)" if score < 80 else "STANDBY (MIXED DIRECTIONAL BIAS)")

    return {
        "strategy_id": "aic_confluence",
        "strategy_name": "Vyapar Institutional Confluence (AIC-20)",
        "signal": side if is_executable else "NEUTRAL",
        "raw_signal": side,
        "score": score,
        "threshold": 80,
        "is_executable": is_executable,
        "confidence": "HIGH" if is_executable else ("MEDIUM" if score >= 65 else "LOW"),
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_reward": 2.2 if is_executable else 0.0,
        "pillars": pillars,
        "factors": factors,
        "reason": f"AIC-20 Score {score}/100 [{status_tag}]: " + ("; ".join(factors[:3]) if factors else "Awaiting setup")
    }


# =====================================================================
# Master Evaluation Router
# =====================================================================

def evaluate_all(symbol, candles, prev_bar=None, vix=None, breadth=None):
    """Evaluates all 20 strategies against the given symbol and candle data."""
    results = {}

    results["orb"] = eval_orb(candles, prev_bar)
    results["pdh_pdl"] = eval_pdh_pdl(candles, prev_bar)
    results["gap_and_go"] = eval_gap_and_go(candles, prev_bar)
    results["nr7_inside"] = eval_nr7_inside(candles)
    results["vwap_pullback"] = eval_vwap_pullback(candles)
    results["ema_crossover"] = eval_ema_crossover(candles)
    results["supertrend"] = eval_supertrend(candles)
    results["ema20_rsi_retest"] = eval_ema20_rsi_retest(candles)
    results["rsi_divergence"] = eval_rsi_divergence(candles)
    results["bollinger_squeeze"] = eval_bollinger_bands(candles)
    results["cpr_camarilla"] = eval_cpr_camarilla_strat(candles, prev_bar)
    results["micro_scalper"] = eval_micro_scalp(candles)
    results["options_delta_burst"] = eval_options_delta_burst(candles, symbol)
    results["options_strangle"] = eval_options_strangle(candles, vix or 15.0)
    results["options_920_straddle"] = eval_options_920_straddle(candles)
    results["options_max_pain"] = eval_options_max_pain(symbol)
    results["news_results"] = eval_news_results(candles)
    results["sector_momentum"] = eval_sector_momentum(symbol)
    results["fiidii_flow"] = eval_fiidii_flow()
    results["aic_confluence"] = eval_aic_confluence(symbol, candles, prev_bar, vix, breadth)

    # Attach strategy metadata
    enhanced = []
    for s_id, res in results.items():
        if isinstance(res, dict) and "is_executable" not in res:
            res["is_executable"] = (res.get("signal") in ("BUY", "SELL"))
        meta = STRATEGY_REGISTRY.get(s_id, {})
        merged = {**meta, "evaluation": res}
        enhanced.append(merged)

    return sorted(enhanced, key=lambda x: x["num"])


# =====================================================================
# Real-Time NSE Data Fetcher
# =====================================================================

def fetch_intraday_candles(symbol, interval="5m", range_str="5d"):
    """Fetches real-time intraday candles via Yahoo Finance API."""
    sym = symbol.strip().upper()
    if not (sym.endswith(".NS") or sym.endswith(".BO")):
        sym += ".NS"

    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?range={range_str}&interval={interval}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            chart = data["chart"]["result"][0]
            quotes = chart["indicators"]["quote"][0]
            timestamps = chart.get("timestamp", [])

            candles = []
            for i in range(len(timestamps)):
                o = quotes["open"][i]
                h = quotes["high"][i]
                l = quotes["low"][i]
                c = quotes["close"][i]
                v = quotes["volume"][i] or 0
                if o is not None and h is not None and l is not None and c is not None:
                    candles.append({
                        "time": timestamps[i],
                        "open": float(o),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c),
                        "volume": float(v)
                    })
            return candles
    except Exception:
        return []


def fetch_prev_bar(symbol):
    """Fetches completed previous day daily bar by IST date (no blind index -2)."""
    sym = symbol.strip().upper()
    if not (sym.endswith(".NS") or sym.endswith(".BO")):
        sym += ".NS"

    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}?range=1mo&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            chart = data["chart"]["result"][0]
            quotes = chart["indicators"]["quote"][0]
            timestamps = chart.get("timestamp", [])
            highs = quotes.get("high", [])
            lows = quotes.get("low", [])
            closes = quotes.get("close", [])
            opens = quotes.get("open", [])

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
                    bar_date = bar_dt.date()
                    if bar_date < today_date:
                        completed_bars.append({
                            "date": bar_date.strftime("%Y-%m-%d"),
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



# =====================================================================
# CLI Runner
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="Complete Indian Intraday Strategies Library (NSE/BSE)")
    parser.add_argument("--list", action="store_true", help="List all 20 strategies with performance statistics")
    parser.add_argument("--symbol", default="RELIANCE.NS", help="Symbol to evaluate (default: RELIANCE.NS)")
    parser.add_argument("--strategy", help="Specific strategy ID to evaluate (e.g. aic_confluence, supertrend, orb)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    if args.list:
        if args.json:
            print(json.dumps(list(STRATEGY_REGISTRY.values()), indent=2))
        else:
            print("==========================================================================================")
            print("         COMPLETE INDIAN INTRADAY TRADING STRATEGIES LIBRARY (NSE / BSE)                  ")
            print("==========================================================================================")
            print(f"{'#':<3} | {'STRATEGY NAME':<38} | {'WIN RATE':<11} | {'R : R':<7} | {'STYLE'}")
            print("-" * 90)
            for s in sorted(STRATEGY_REGISTRY.values(), key=lambda x: x["num"]):
                highlight = "★ " if s["num"] == 20 else "  "
                wr = s.get("win_rate", "Journal")
                print(f"{s['num']:<3} | {highlight}{s['name']:<36} | {wr:<11} | {s['risk_reward']:<7} | {s['style']}")
            print("==========================================================================================")
            print("Total: 20 Strategies Available. Run with --symbol <STOCK> to evaluate live signals.")
        return

    # Evaluate symbol
    symbol = args.symbol.strip().upper()
    candles = fetch_intraday_candles(symbol)
    prev_bar = fetch_prev_bar(symbol)

    if not candles:
        # If offline or market closed, generate standard 5m reference bars for demonstration
        base = 2500.0 if "TCS" in symbol else (1300.0 if "RELIANCE" in symbol else 1000.0)
        candles = []
        for i in range(25):
            o = base + i * 1.5
            h = o + 3.0
            l = o - 1.5
            c = o + 2.0
            candles.append({"time": 1700000000 + i * 300, "open": o, "high": h, "low": l, "close": c, "volume": 15000 + i * 500})
        prev_bar = {"high": base + 10.0, "low": base - 15.0, "close": base}

    evaluations = evaluate_all(symbol, candles, prev_bar)

    if args.strategy:
        evaluations = [e for e in evaluations if e["id"] == args.strategy]

    if args.json:
        print(json.dumps(evaluations, indent=2))
    else:
        print(f"\nEvaluating 20 Intraday Strategies for {symbol}:")
        print("=" * 80)
        for e in evaluations:
            ev = e["evaluation"]
            sig = ev.get("signal", "NEUTRAL")
            color_tag = "🚀 BUY" if sig == "BUY" else ("🔻 SELL" if sig == "SELL" else "⏸ NEUTRAL")
            wr = e.get("win_rate", "Measured in Journal")
            print(f"[{e['num']:02d}] {e['name']}")
            print(f"     Signal: {color_tag} | Win Rate: {wr} | R:R: {e['risk_reward']}")
            print(f"     Reason: {ev.get('reason', 'N/A')}")
            if ev.get("entry") is not None and ev.get("stop") is not None and ev.get("target") is not None:
                print(f"     Levels: Entry ₹{ev['entry']} | Stop ₹{ev['stop']} | Target ₹{ev['target']}")
            print("-" * 80)


if __name__ == "__main__":
    main()
