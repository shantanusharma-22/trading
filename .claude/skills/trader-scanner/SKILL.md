---
name: trader-scanner
description: >-
  Chart Scanner for Indian Equities (NSE/BSE). Scans Nifty 100, F&O constituent
  stocks, and index ETFs for daily setups (20-day high breakouts, bull flags,
  MA20 reclaim, oversold bounces) and intraday 15-minute Opening Range Breakouts
  (ORB 09:15-09:30 IST). Free Yahoo Finance data with .NS tickers.
---

# trader-scanner (Indian Equities)

Scans thousands of charts for setups before the market open and detects intraday opening range breakouts after 09:30 IST.

```bash
python3 scan.py universe                          # builds trader/universe.txt (Nifty 100 / F&O / ETFs)
python3 scan.py universe --download               # downloads official NSE equity master list
python3 scan.py daily                             # pre-market daily setups
python3 scan.py daily --symbols RELIANCE.NS,TCS.NS,INFY.NS
python3 scan.py orb                               # intraday 15-min ORB scan (09:15-09:30 range)
python3 scan.py orb --watchlist trader/watchlist.json
```

