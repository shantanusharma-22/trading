---
name: trader-risk
description: >-
  Risk Manager for Indian Equities (NSE/BSE). Strictly validates orders against
  hard risk limits: max loss per trade (Rs), daily loss cap, reward-to-risk
  ratio, NSE 0.05 tick size, and IST market trading windows (09:30-14:45 IST).
  Writes trader/state/risk.json.
---

# trader-risk (Indian Equities)

Enforces strict risk management rules and protects capital before orders reach the broker.

```bash
python3 check.py                                 # checks trader/orders.json
python3 check.py --json                          # print verdict as JSON
python3 check.py --now "2026-10-19 10:15"        # pin the clock (IST)
```

