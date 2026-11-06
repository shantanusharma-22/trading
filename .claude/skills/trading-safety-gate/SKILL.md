---
name: trading-safety-gate
description: Use for any change touching orders, risk checks, portfolio state, broker payloads or autopilot. Enforces fail-closed behavior and paper-only execution.
---
- Paper mode is the default. Never add live order placement or auto-enable it.
- Every entry path (CLI, dashboard, autopilot) must call the SAME
  pre_trade_gate and must write the trade to the SAME shared state.
- Fail closed: an exception, missing data or unreadable config blocks the
  order. No bare except or pass in these paths.
- Be side-aware: longs need stop < entry; shorts need stop > entry; risk is
  |entry - stop| x qty.
- Daily limits use realized P&L as well as planned risk.
- State writes are atomic and locked. One holdings schema.
- Any protective stop must exist at the broker, not only in-process.
- After the change, write a test that proves a blocked case is blocked
  through the real call path (not by calling the helper directly).

