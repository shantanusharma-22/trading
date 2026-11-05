#!/usr/bin/env python3
"""Indian Stock Market (NSE/BSE) Intraday Tax, Charges & Slippage Calculator.
Standard library only.

Calculates statutory government taxes, exchange fees, SEBI charges, GST,
discount brokerage, and execution slippage for intraday equity trades on NSE/BSE.

Rates (FY 2025-2027 SEBI / Central Govt schedule):
  - STT: 0.025% on sell turnover
  - Stamp Duty: 0.003% on buy turnover
  - NSE Exchange Charges: 0.00297% on total turnover
  - SEBI Turnover Fee: 0.0001% (Rs 10 per crore)
  - Brokerage: Rs 20 per executed order or 0.03% (whichever lower)
  - GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
  - Slippage: 0.05% default buffer on market execution
"""

import sys
import json


def calculate_intraday_charges(buy_price: float, sell_price: float, qty: int,
                               brokerage_per_order: float = 20.0,
                               slippage_pct: float = 0.05) -> dict:
    """Calculate all charges, slippage, net P&L, and breakeven point for an intraday equity trade."""
    if qty <= 0 or buy_price <= 0 or sell_price <= 0:
        return {
            "turnover_buy": 0.0,
            "turnover_sell": 0.0,
            "total_turnover": 0.0,
            "stt": 0.0,
            "stamp_duty": 0.0,
            "exchange_charges": 0.0,
            "sebi_charges": 0.0,
            "brokerage": 0.0,
            "gst": 0.0,
            "slippage_cost": 0.0,
            "statutory_charges": 0.0,
            "total_charges": 0.0,
            "gross_pnl": 0.0,
            "net_pnl": 0.0,
            "breakeven_points": 0.0,
        }

    turnover_buy = round(buy_price * qty, 2)
    turnover_sell = round(sell_price * qty, 2)
    total_turnover = round(turnover_buy + turnover_sell, 2)

    # 1. STT: 0.025% on sell side for equity intraday
    stt = round(turnover_sell * 0.00025, 2)

    # 2. Stamp duty: 0.003% on buy side
    stamp_duty = round(turnover_buy * 0.00003, 2)

    # 3. Exchange turnover charges: 0.00297% on total turnover
    exchange_charges = round(total_turnover * 0.0000297, 2)

    # 4. SEBI turnover fee: Rs 10 per crore (0.000001)
    sebi_charges = round(total_turnover * 0.000001, 2)

    # 5. Brokerage: Rs 20 or 0.03% per leg (whichever lower)
    brokerage_buy = min(brokerage_per_order, round(turnover_buy * 0.0003, 2))
    brokerage_sell = min(brokerage_per_order, round(turnover_sell * 0.0003, 2))
    brokerage = round(brokerage_buy + brokerage_sell, 2)

    # 6. GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
    gst = round((brokerage + exchange_charges + sebi_charges) * 0.18, 2)

    # 7. Conservative Market Slippage buffer (0.05% round-trip)
    slippage_cost = round(total_turnover * (slippage_pct / 100.0), 2) if slippage_pct > 0 else 0.0

    statutory_charges = round(stt + stamp_duty + exchange_charges + sebi_charges + brokerage + gst, 2)
    total_charges = round(statutory_charges + slippage_cost, 2)

    gross_pnl = round((sell_price - buy_price) * qty, 2)
    net_pnl = round(gross_pnl - total_charges, 2)
    breakeven_points = round(total_charges / qty, 2) if qty > 0 else 0.0

    return {
        "turnover_buy": turnover_buy,
        "turnover_sell": turnover_sell,
        "total_turnover": total_turnover,
        "stt": stt,
        "stamp_duty": stamp_duty,
        "exchange_charges": exchange_charges,
        "sebi_charges": sebi_charges,
        "brokerage": brokerage,
        "gst": gst,
        "slippage_cost": slippage_cost,
        "statutory_charges": statutory_charges,
        "total_charges": total_charges,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "breakeven_points": breakeven_points,
    }


def calculate_single_leg_charges(price: float, qty: int, side: str = "BUY",
                                 brokerage_per_order: float = 20.0) -> dict:
    """Calculates statutory charges and brokerage for a single order execution leg (BUY or SELL)."""
    if qty <= 0 or price <= 0:
        return {
            "turnover": 0.0,
            "brokerage": 0.0,
            "stt": 0.0,
            "stamp_duty": 0.0,
            "exchange_charges": 0.0,
            "sebi_charges": 0.0,
            "gst": 0.0,
            "statutory_charges": 0.0,
            "total_charges": 0.0
        }

    turnover = round(price * qty, 2)
    s = str(side).upper()

    # Intraday equity rates: STT on sell only (0.025%), Stamp duty on buy only (0.003%)
    stt = round(turnover * 0.00025, 2) if s == "SELL" else 0.0
    stamp_duty = round(turnover * 0.00003, 2) if s == "BUY" else 0.0
    exchange_charges = round(turnover * 0.0000297, 2)
    sebi_charges = round(turnover * 0.000001, 2)
    brokerage = min(brokerage_per_order, round(turnover * 0.0003, 2))
    gst = round((brokerage + exchange_charges + sebi_charges) * 0.18, 2)
    statutory_charges = round(stt + stamp_duty + exchange_charges + sebi_charges + brokerage + gst, 2)

    return {
        "turnover": turnover,
        "brokerage": brokerage,
        "stt": stt,
        "stamp_duty": stamp_duty,
        "exchange_charges": exchange_charges,
        "sebi_charges": sebi_charges,
        "gst": gst,
        "statutory_charges": statutory_charges,
        "total_charges": statutory_charges
    }


def format_charges_summary(res: dict) -> str:
    """Format charges into an easy-to-read summary table."""
    lines = [
        f"Buy: Rs {res['turnover_buy']:,.2f} | Sell: Rs {res['turnover_sell']:,.2f} | Total Turnover: Rs {res['total_turnover']:,.2f}",
        f"Brokerage: Rs {res['brokerage']:.2f} | STT: Rs {res['stt']:.2f} | Exchange: Rs {res['exchange_charges']:.2f}",
        f"Stamp Duty: Rs {res['stamp_duty']:.2f} | SEBI: Rs {res['sebi_charges']:.2f} | GST (18%): Rs {res['gst']:.2f}",
        f"Slippage Buffer (0.05%): Rs {res['slippage_cost']:.2f} | Statutory Fees: Rs {res['statutory_charges']:.2f}",
        f"Total Deductions: Rs {res['total_charges']:.2f} | Breakeven Price Move: Rs {res['breakeven_points']:.2f}/share",
        f"Gross P&L: Rs {res['gross_pnl']:+,.2f} ===> NET P&L: Rs {res['net_pnl']:+,.2f}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python tax_calculator.py <buy_price> <sell_price> <qty> [brokerage_per_leg=20] [slippage_pct=0.05]")
        sys.exit(1)

    bp = float(sys.argv[1])
    sp = float(sys.argv[2])
    q = int(sys.argv[3])
    brk = float(sys.argv[4]) if len(sys.argv) > 4 else 20.0
    slip = float(sys.argv[5]) if len(sys.argv) > 5 else 0.05

    result = calculate_intraday_charges(bp, sp, q, brk, slip)
    print(format_charges_summary(result))
