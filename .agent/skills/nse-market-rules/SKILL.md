---
name: nse-market-rules
description: Use when code involves NSE/BSE trading hours, holidays, expiry days, tick size, circuit bands, MIS margin or lot sizes. Never hardcode these; load and cite them.
---
- Sessions are Asia/Kolkata: pre-open 09:00-09:15, regular 09:15-15:30.
  Bars use start time; keep 09:15 <= t < 15:30.
- Holidays and special sessions come from one calendar (NSE_HOLIDAYS plus
  events.json). Unknown year = treat as closed and warn, never as open.
- Expiry weekday is per instrument and configurable. Verify against current
  NSE circulars before changing it; never assume Thursday.
- Tick size: 0.05 for most equities, 0.01 for ETFs and some series. Look it up
  per instrument.
- MIS leverage is per scrip from the broker margin list. Never use one
  multiplier for every stock.
- Circuit band, ASM, GSM and T2T come from loaded NSE lists with an as-of
  date. If no list is loaded, say "unknown"; never show a pass.
- Cite the source and date for every rule you encode.

