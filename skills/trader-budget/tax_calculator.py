#!/usr/bin/env python3
"""Indian Stock Market (NSE/BSE) Intraday Tax, Charges & Slippage Calculator.
Standard library only.

Calculates statutory government taxes, exchange fees, SEBI charges, GST,
discount brokerage, and execution slippage for intraday equity trades on NSE/BSE.

Rates & Revisions:
  - Finance Act 2026-27 (effective April 1, 2026):
      * Equity Intraday (MIS): STT 0.025% on sell turnover
      * F&O Futures: STT 0.05% on sell turnover (₹50 per lakh)
      * F&O Options (Sold): STT 0.15% on sell premium
      * Equity Delivery (CNC): STT 0.1% on buy + 0.1% on sell
  - Statutory Rounding (Zerodha & NSE standard):
      * STT is rounded to the nearest whole rupee (>= 50 paise rounds up; < 50 paise rounds down)
      * Exchange transaction charges and GST round to the nearest paisa (0.01 INR)
  - Stamp Duty: 0.003% on buy turnover (Intraday), 0.002% (Futures), 0.015% (Delivery)
  - NSE Exchange Charges: 0.00297% (Equity), 0.00173% (Futures), 0.03503% (Options premium)
  - SEBI Turnover Fee: 0.0001% (Rs 10 per crore)
  - Brokerage: Rs 20 per executed order or 0.03% (whichever lower)
  - GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
  - Slippage: 0.05% default buffer on market execution
"""

import sys
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Union


def round_rupee(val: Union[Decimal, float]) -> Decimal:
    """Statutory STT rounding: >= 50 paise rounds up to next rupee, < 50 paise rounds down."""
    d = Decimal(str(val)) if not isinstance(val, Decimal) else val
    return d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def round_paisa(val: Union[Decimal, float]) -> Decimal:
    """Standard currency rounding to nearest paisa (0.01 INR)."""
    d = Decimal(str(val)) if not isinstance(val, Decimal) else val
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_indian_trade_charges(
    buy_price: Union[Decimal, float],
    sell_price: Union[Decimal, float],
    quantity: int,
    segment: str = "EQUITY_INTRADAY",
    exchange: str = "NSE",
    slippage_pct: float = 0.0,
) -> Dict[str, Decimal]:
    """
    Computes exact Indian brokerage and statutory levies (post-April 1, 2026 rates).
    Segments: EQUITY_INTRADAY, EQUITY_DELIVERY, FNO_FUTURES, FNO_OPTIONS
    """
    if quantity <= 0 or buy_price <= 0 or sell_price <= 0:
        zero = Decimal("0.00")
        return {
            "brokerage": zero,
            "stt": Decimal("0"),
            "exchange_txn_charge": zero,
            "sebi_charge": zero,
            "stamp_duty": zero,
            "gst": zero,
            "dp_charge": zero,
            "slippage_cost": zero,
            "total_charges": zero,
            "gross_pnl": zero,
            "net_pnl": zero,
            "breakeven_points_per_share": zero,
        }

    b_price = Decimal(str(buy_price))
    s_price = Decimal(str(sell_price))
    qty = Decimal(str(quantity))

    buy_turnover = b_price * qty
    sell_turnover = s_price * qty
    total_turnover = buy_turnover + sell_turnover

    # 1. Brokerage (Zerodha / standard discount broker benchmark: min(0.03%, Rs 20) per order)
    if segment == "EQUITY_DELIVERY":
        brokerage_buy = Decimal("0")
        brokerage_sell = Decimal("0")
    elif segment == "FNO_OPTIONS":
        brokerage_buy = Decimal("20.00")
        brokerage_sell = Decimal("20.00")
    else:
        brokerage_buy = min(Decimal("20.00"), round_paisa(buy_turnover * Decimal("0.0003")))
        brokerage_sell = min(Decimal("20.00"), round_paisa(sell_turnover * Decimal("0.0003")))
    total_brokerage = brokerage_buy + brokerage_sell

    # 2. Securities Transaction Tax (STT - effective April 1, 2026 Finance Act)
    if segment == "EQUITY_INTRADAY":
        stt = round_rupee(sell_turnover * Decimal("0.00025"))  # 0.025% on sell
    elif segment == "EQUITY_DELIVERY":
        stt = round_rupee(buy_turnover * Decimal("0.001")) + round_rupee(sell_turnover * Decimal("0.001"))
    elif segment == "FNO_FUTURES":
        stt = round_rupee(sell_turnover * Decimal("0.0005"))   # Revised 1 Apr 2026: 0.05% on sell
    elif segment == "FNO_OPTIONS":
        stt = round_rupee(sell_turnover * Decimal("0.0015"))   # Revised 1 Apr 2026: 0.15% on premium sell
    else:
        raise ValueError(f"Unsupported segment: {segment}")

    # 3. Exchange Transaction Charges (NSE uniform schedule)
    txn_rates = {
        "EQUITY_INTRADAY": Decimal("0.0000297"),  # 0.00297%
        "EQUITY_DELIVERY": Decimal("0.0000297"),  # 0.00297%
        "FNO_FUTURES": Decimal("0.0000173"),      # 0.00173%
        "FNO_OPTIONS": Decimal("0.0003503"),      # 0.03503% on premium
    }
    txn_charge = round_paisa(total_turnover * txn_rates.get(segment, Decimal("0.0000297")))

    # 4. SEBI Turnover Charges (Rs 10 per crore = 0.0001%)
    sebi_charge = round_paisa(total_turnover * Decimal("0.000001"))

    # 5. Stamp Duty (Buy side only)
    stamp_rates = {
        "EQUITY_INTRADAY": Decimal("0.00003"),    # 0.003%
        "EQUITY_DELIVERY": Decimal("0.00015"),    # 0.015%
        "FNO_FUTURES": Decimal("0.00002"),        # 0.002%
        "FNO_OPTIONS": Decimal("0.00003"),        # 0.003%
    }
    stamp_duty = round_paisa(buy_turnover * stamp_rates.get(segment, Decimal("0.00003")))

    # 6. GST at 18% on (Brokerage + Transaction Charges + SEBI Charges)
    gst = round_paisa((total_brokerage + txn_charge + sebi_charge) * Decimal("0.18"))

    # 7. Depository Participant (DP) charge on Delivery Sell (Rs 13 + 18% GST = Rs 15.34)
    dp_charge = Decimal("15.34") if segment == "EQUITY_DELIVERY" and sell_turnover > 0 else Decimal("0.00")

    # 8. Slippage buffer
    slip_cost = round_paisa(total_turnover * (Decimal(str(slippage_pct)) / Decimal("100.0"))) if slippage_pct > 0 else Decimal("0.00")

    total_charges = total_brokerage + stt + txn_charge + sebi_charge + stamp_duty + gst + dp_charge + slip_cost
    gross_pnl = sell_turnover - buy_turnover
    net_pnl = gross_pnl - total_charges

    return {
        "brokerage": total_brokerage,
        "stt": stt,
        "exchange_txn_charge": txn_charge,
        "sebi_charge": sebi_charge,
        "stamp_duty": stamp_duty,
        "gst": gst,
        "dp_charge": dp_charge,
        "slippage_cost": slip_cost,
        "total_charges": total_charges,
        "gross_pnl": round_paisa(gross_pnl),
        "net_pnl": round_paisa(net_pnl),
        "breakeven_points_per_share": round_paisa(total_charges / qty) if qty > 0 else Decimal("0.00"),
    }


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

    turnover_buy = round(float(buy_price) * qty, 2)
    turnover_sell = round(float(sell_price) * qty, 2)
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

    gross_pnl = round((float(sell_price) - float(buy_price)) * qty, 2)
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

    # Intraday equity rates: STT on sell only (0.025% with nearest-rupee rounding), Stamp duty on buy only (0.003%)
    stt_dec = round_rupee(Decimal(str(turnover)) * Decimal("0.00025")) if s == "SELL" else Decimal("0.00")
    stt = float(stt_dec)
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
