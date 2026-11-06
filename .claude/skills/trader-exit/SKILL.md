---
name: trader-exit
description: >-
  Exit Planner for Indian Equities (NSE/BSE). Computes exact stop-loss (opening
  range midpoint or low), 1R/2R profit targets, and net risk-reward after
  deducting Indian statutory charges (STT, Stamp Duty, GST, Brokerage). Sets
  flat_by to 15:10 IST and writes trader/plan.json.
---

# trader-exit (Indian Equities)

Plans stops and targets before entry, rounding to Indian tick size (0.05 INR) and accounting for STT and brokerage in net R:R.

```bash
python3 exit.py                                    # reads trader/entry.json
python3 exit.py --entry 3000 --stop 2970 --r 2.0 --symbol RELIANCE.NS
python3 exit.py --write                            # writes trader/plan.json
```

