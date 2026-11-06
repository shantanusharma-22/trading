---
name: trader-budget
description: >-
  Budget & Position Sizing Manager for Indian Equities (NSE/BSE). Sizes orders
  strictly to rupee limits, whole shares, and max risk per trade, calculating
  statutory Indian deductions (STT, Stamp Duty, GST, Exchange fees, and Brokerage)
  to ensure positive net expectancy. Writes trader/orders.json.
---

# trader-budget (Indian Equities)

Sizes trades to rupee constraints and accounts for taxes and brokerage.

```bash
python3 size.py                                  # reads trader/plan.json
python3 size.py --write                          # writes trader/orders.json for /trader-risk
python3 size.py --budget 100000 --max-loss 1000
python3 size.py --charges                        # print complete Indian tax breakdown
```

