---
name: trader-insider
description: >-
  SEBI Insider Trading & SAST Tracker for Indian Equities (NSE/BSE). Monitors
  high-value transactions (Rs 10 Lakhs+) filed by Promoters, Directors, and Key
  Management Personnel under SEBI (Prohibition of Insider Trading) Regulations.
---

# trader-insider (Indian Equities)

Tracks market-moving promoter and insider transactions in Indian listed stocks.

```bash
python3 insider.py                               # checks watchlist + plan tickers
python3 insider.py --symbol RELIANCE.NS
python3 insider.py --min-val 1000000             # min trade value Rs 10 Lakhs
```

