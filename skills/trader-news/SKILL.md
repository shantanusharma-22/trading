---
name: trader-news
description: >-
  News Monitor for Indian Equities (NSE/BSE). Monitors breaking headlines and
  corporate disclosures for Indian stocks (.NS) across Yahoo Finance India and
  Google News India RSS feeds, tagging earnings, regulatory notices, and deals.
---

# trader-news (Indian Equities)

Tracks live breaking news for stocks in your watchlist or portfolio.

```bash
python3 news.py                                  # watches active watchlist & plan tickers
python3 news.py --tickers RELIANCE.NS TCS.NS
python3 news.py --tickers INFY.NS --all          # print all news without filtering seen items
```

