---
name: python-stdlib-windows
description: Use for Python server, CLI, and filesystem code. Ensures standard-library only, atomic file writes, shared thread locks, and safe Windows console encoding.
---
- Python 3 standard library only on the backend (urllib, http.server, json, math, sqlite3, threading).
- Atomic file writes: write to temporary file in the same directory, then atomic rename with os.replace().
- Shared threading lock: guard concurrent read/writes to portfolio.json, broker.json, risk.json, config.json.
- Windows console safety: sys.stdout.reconfigure(encoding="utf-8") with safe fallback; never crash on emojis or special characters.
- Path resolution: always use absolute paths or resolve_path relative to repository root.

