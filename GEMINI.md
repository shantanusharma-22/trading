# Project Rules: Vyapar AI

Project: Vyapar AI, a paper-trading toolkit for NSE/BSE equities.
Standard-library Python only on the server; no new mandatory dependencies.

## SAFETY RULES (never break these):
1. Paper mode is the default. Never add or enable live order placement.
2. Risk checks fail CLOSED: any exception, missing data or unreadable config blocks the action and reports the reason. Never `except: pass` around a risk or order path.
3. Never invent data. No hardcoded fallback prices, scores, win rates or "verified" labels. If data is missing, return an error/stale flag and make the UI show "unavailable".
4. Every number shown to the user carries its source and as-of time.
5. Never print or commit secrets. Read tokens from environment variables; mask them in output; keep trader/config.json out of git.

## ENGINEERING RULES:
6. All state files (portfolio.json, broker.json, risk.json, config.json) are written atomically (temp file + os.replace) under a shared lock.
7. One holdings schema everywhere: `{"qty", "entry_price", "side", "stop", "target", "current_price", "margin_used", "strategy", "placed_at"}`.
8. All times are Asia/Kolkata. Compare times as datetime objects, not strings.
9. Console output must not crash on Windows: no emoji in logs, or `sys.stdout.reconfigure(encoding="utf-8")` with a safe fallback.
10. Every change ships with tests in `tests/test_indian_market.py`; run the full suite and report the result before saying you are done.
11. Do not claim performance. No win-rate or profit claims in code, UI or docs unless computed from the user's own journal with sample size and dates.
12. Before editing, state a short plan and list the files you will change.

