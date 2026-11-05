---
name: no-fake-data
description: Use whenever code returns, stores or displays prices, scores, percentages, win rates, company facts or status flags.
---
- Never hardcode a fallback value to "keep the UI working" (no 1000.0, no
  24500, no score = 84, no ok: true).
- On failure return an error or stale flag, and make the UI show
  "unavailable" and disable actions that depend on it.
- Every displayed number carries source and as-of time. The as-of time is
  the time of the last real data point, not the fetch time.
- Do not write performance claims (win rates, expected returns). Show
  measured journal results with sample size and date range, or nothing.
- A feature that is a stub must say so ("NOT IMPLEMENTED") and return
  NEUTRAL; it must never produce a BUY/SELL.
- Remove static placeholder text from HTML that real data should fill.

