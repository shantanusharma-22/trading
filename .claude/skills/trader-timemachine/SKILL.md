---
name: trader-timemachine
description: >-
  Time Machine for Indian Equities (NSE/BSE). Replays the remainder of the Indian
  trading session 10,000 times using empirical 5-minute bars (75 bars/session)
  to calculate statistical odds of hitting target vs stop loss before 15:10 IST.
---

# trader-timemachine (Indian Equities)

Monte Carlo trade outcome simulator built specifically for the 75-bar Indian market session (09:15 to 15:30 IST).

```bash
python3 timemachine.py                           # reads trader/plan.json
python3 timemachine.py --symbol RELIANCE.NS --entry 3000 --stop 2970 --target 3060
python3 timemachine.py --replays 5000 --seed 42
```

