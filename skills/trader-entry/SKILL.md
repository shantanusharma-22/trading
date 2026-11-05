---
name: trader-entry
description: >-
  Entry Timer for Indian Equities (NSE/BSE). Watches 15-minute Opening Range
  Breakouts (09:15-09:30 IST) bar-by-bar and confirms entry when a 5-minute
  candle closes strictly above the opening range high. Writes trader/entry.json.
---

# trader-entry (Indian Equities)

Watches 1-minute or 5-minute bars to confirm exact breakout entries after 09:30 IST.

```bash
python3 entry.py check RELIANCE.NS                    # check 15m ORB trigger
python3 entry.py check RELIANCE.NS --setup level --level 3050.00
python3 entry.py check RELIANCE.NS --write            # save trigger to trader/entry.json
python3 entry.py watchlist                            # evaluate all hits from watchlist
```

