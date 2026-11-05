---
name: trader-alerts
description: >-
  Price Alerts & Market Clock for Indian Equities (NSE/BSE). Rings when a price,
  a stop, target, or opening bell (09:15 IST) hits, and reminds you to be flat
  by 15:10 IST before broker MIS auto-squareoff charges apply. Tracks NSE hours,
  holidays, and fetches live quotes for Indian tickers (.NS/.BO).
---

# trader-alerts (Indian Equities)

Watches stock prices and the NSE trading session so you do not have to stare at charts.

```bash
python3 alerts.py clock                          # NSE open or closed, next open
python3 alerts.py add --from-plan                # stop, target, flat by 15:10 from trader/plan.json
python3 alerts.py add --opening-bell             # alert at 09:15 IST
python3 alerts.py add --symbol RELIANCE.NS --stop 2950.00
python3 alerts.py add --symbol RELIANCE.NS --target 3050.00
python3 alerts.py add --at 15:10 --label "flat by 15:10"
python3 alerts.py check                          # check all alerts against live quotes
python3 alerts.py quote RELIANCE.NS --write      # write to trader/prices.json
python3 alerts.py quote --holdings --write       # portfolio + plan tickers
python3 alerts.py list
```

