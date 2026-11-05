---
name: trader-broker
description: >-
  Order Executor for Indian Equities (NSE/BSE). Renders order tickets, formats
  copy-ready API payloads for Zerodha Kite Connect, Angel One SmartAPI, and
  Shoonya (Finvasia), and provides a paper trading execution simulator.
---

# trader-broker (Indian Equities)

Safely prepares orders for Indian brokers (MIS intraday) or paper trades with zero risk.

```bash
python3 ticket.py show                           # display tickets & paper mode
python3 ticket.py show --broker zerodha          # generate Zerodha Kite snippet
python3 ticket.py show --broker angel            # generate Angel One SmartAPI JSON
python3 ticket.py show --broker shoonya          # generate Shoonya JSON
python3 ticket.py approve --index 1 --reply "yes" # explicit yes confirmation
python3 ticket.py fill --symbol RELIANCE.NS --side buy --qty 16 --price 3000.00
python3 ticket.py log                            # show today's trade ledger
```

