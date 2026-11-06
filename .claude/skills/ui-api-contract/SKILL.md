---
name: ui-api-contract
description: Use for changes to web_server.py endpoints, index.html, and JavaScript data fetching. Prevents contract mismatches.
---
- Endpoint contracts must match frontend expectations:
  - /api/status returns ist_time (HH:MM:SS), ist_date, market_open.
  - /api/strategies/evaluate returns a list of evaluated strategies, not a bare dict.
  - Error responses include {"error": "...", "stale": true}.
- Consistent field names across header, trade cockpit, position tables, and profile drawers.
- Test every endpoint contract for shape, empty responses, and upstream failure modes.

