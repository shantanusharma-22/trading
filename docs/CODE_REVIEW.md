# Vyapar AI — Forensic Code Audit & Quality Review (CR-01 to CR-12)

**Audit Date**: November 2026  
**Project**: Vyapar AI (NSE / BSE Equities Toolkit)  
**Standard**: Indian Market Microstructure & Python 3 Zero-Dependency Standard Library  
**Auditor**: Senior Software Architect, Security Auditor, and Principal QA Engineer  

---

## Executive Summary

A forensic review of the Vyapar AI repository identified twelve (12) discrete findings across security, state persistence, risk gating, statutory tax calculations, concurrency, and UI/API contracts. 

All 12 findings have been remediated and verified through 76 automated regression tests (`tests/test_indian_market.py`).

| ID | Category | Severity | File | Section / Lines | Title & Core Defect | Status |
|---|---|---|---|---|---|---|
| **CR-01** | Security / Safety | **Critical** | `skills/trader-risk/check.py` | Lines 509-510 | Risk decision audit masking via `except Exception: pass` | **RESOLVED** |
| **CR-02** | Security | **Critical** | `trader/config.json`, `main.py` | Git index & `main.py:40-68` | Plaintext API credentials in repository and config | **RESOLVED** |
| **CR-03** | Concurrency / Data | **High** | `skills/common.py` | `save_json` / `atomic_write_json` | Non-atomic state writes under concurrent threads | **RESOLVED** |
| **CR-04** | Bug / Accounting | **High** | `skills/trader-broker/web_server.py` | Lines 910, 915 | Phantom cash inflation & gross turnover credit on trade exit | **RESOLVED** |
| **CR-05** | Compliance / Financial | **High** | `skills/trader-budget/tax_calculator.py` | Statutory Tax Module | Finance Act 2026-27 STT revision & nearest-rupee rounding | **RESOLVED** |
| **CR-06** | Concurrency | **Medium** | `skills/data_layer.py` | `get_db_connection`, Cache | SQLite concurrency deadlocks (`database is locked`) | **RESOLVED** |
| **CR-07** | Concurrency | **Medium** | `skills/data_layer.py` | `fetch_json_with_retry` | In-flight request deduplication lock race condition | **RESOLVED** |
| **CR-08** | Reliability / Upstream | **Medium** | `skills/trader-alerts/alerts.py` | `check_alerts` | Percentage move alerts miscalculated from intraday open | **RESOLVED** |
| **CR-09** | Reliability / Network | **Medium** | `skills/trader-scanner/bhavcopy.py`, `preopen.py` | NSE HTTP Queries | Direct urllib requests blocked by NSE bot mitigation | **RESOLVED** |
| **CR-10** | Safety / Accounting | **Medium** | `skills/trader-broker/dashboard.py` | `emergency_flatten_all` | Short position panic-exit crediting full market value | **RESOLVED** |
| **CR-11** | Reliability / Threading | **Medium** | `skills/trader-broker/autotrader.py` | Thread lifecycle | Autotrader scanner hanging and blocking thread restart | **RESOLVED** |
| **CR-12** | Security / Web | **Medium** | `skills/trader-broker/web_server.py` | Routes & CORS | Wildcard CORS and missing CSRF guard on order endpoints | **RESOLVED** |

---

## Detailed Audit Findings & Remediations

### CR-01: Risk Decision Audit Masking (`check.py`)
- **Severity**: Critical
- **Description**: In `skills/trader-risk/check.py`, `log_risk_decision` was wrapped in a bare `except Exception: pass`, violating Project Safety Rule 2 (Fail CLOSED). If disk space was exhausted or permissions were locked, audit logs silently failed to persist without alerting the operator.
- **Impact**: Pre-trade verdicts could not be cryptographically reconstructed or verified during compliance inquiries.
- **Remediation**: Removed the bare `except: pass`. Integrated structured logging to `sys.stderr` on I/O error and bound each verdict to an immutable SHA-256 fingerprint computed via `compute_order_fingerprint(order)`.
- **Status**: **RESOLVED** (Verified in unit tests).

---

### CR-02: Plaintext Credentials & Git Hygiene
- **Severity**: Critical
- **Description**: Runtime SQLite databases (`history.db`, `journal.db`), Python 3.14 compiled bytecode (`__pycache__/*.pyc`), and `trader/config.json` containing placeholder secrets were committed into Git history.
- **Impact**: Potential leakage of sensitive API keys, Telegram bot tokens, and Discord webhook URLs.
- **Remediation**: Added comprehensive root `.gitignore` entries covering `__pycache__/`, `*.pyc`, `trader/data/*.db`, and `trader/config.json`. Provided `trader/portfolio.example.json` and `trader/config.example.json`. Added `resolve_secrets()` in `main.py` that prioritizes environment variables (`TELEGRAM_BOT_TOKEN`, `DISCORD_WEBHOOK_URL`) and masks tokens in console output.
- **Status**: **RESOLVED** (Git index purged, zero secrets tracked).

---

### CR-03: Non-Atomic State Persistence Under Concurrent Threads
- **Severity**: High
- **Description**: Several modules wrote directly to critical state files (`portfolio.json`, `broker.json`, `breadth.json`) using raw `open(..., "w")`. In a multithreaded server environment, a crash or concurrent write during `json.dump()` could truncate or corrupt state.
- **Impact**: Corrupted portfolio balance or trade history resulting in application crash.
- **Remediation**: Implemented `atomic_write_json(target_path, payload)` in `skills/common.py` using `tempfile.NamedTemporaryFile` + `os.fsync` + `os.replace` under `STATE_LOCK`. Refactored all modules to write atomically.
- **Status**: **RESOLVED** (Verified in `test_atomic_write_json`).

---

### CR-04: Phantom Cash Credit & Margin Inflation on Trade Exit (`web_server.py`)
- **Severity**: High
- **Description**: In `/api/trade/exit`, the server calculated `net_pnl = rec["net_pnl"]` and `charges = rec["charges"]`, but updated the portfolio with:
  `port["cash"] = round(port.get("cash", 0) + margin_returned + gross_pnl, 2)`.
- **Impact**: Statutory charges were phantom-credited back to cash on every exit, causing portfolio balance to diverge from actual capital.
- **Remediation**: Changed cash reconciliation to `port["cash"] = round(port.get("cash", 0) + margin_returned + net_pnl, 2)` and passed `net_pnl` to `record_closed_trade()`.
- **Status**: **RESOLVED** (Verified in trade lifecycle integration tests).

---

### CR-05: Indian Statutory Tax Drift & Finance Act 2026-27 Rates (`tax_calculator.py`)
- **Severity**: High
- **Description**: Tax calculator used pre-2026 STT rates and unrounded floating-point calculations for Securities Transaction Tax.
- **Impact**: Incorrect tax deduction understating transaction fees for F&O instruments and violating statutory nearest-rupee rounding mandates.
- **Remediation**: Implemented `calculate_indian_trade_charges` in `skills/trader-budget/tax_calculator.py` supporting post-April 2026 rates:
  - Equity Intraday: STT 0.025% on sell.
  - F&O Futures: STT 0.05% on sell.
  - F&O Options: STT 0.15% on sell premium.
  - Rounding: Applied statutory `round_rupee` (`ROUND_HALF_UP`) to STT while retaining backward compatibility for legacy callers.
- **Status**: **RESOLVED** (Verified in `test_post_april_2026_stt_rates_and_rounding`).

---

### CR-06: SQLite Concurrency Deadlocks
- **Severity**: Medium
- **Description**: Default SQLite connections in `history.py` and `journal.py` used standard rollback journal mode without timeout handling, leading to `sqlite3.OperationalError: database is locked` under multithreaded web server access.
- **Impact**: Web dashboard requests failed when backtests or journal recordings occurred simultaneously.
- **Remediation**: Upgraded all SQLite initializations to use Write-Ahead Logging (WAL) mode with `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, and `PRAGMA busy_timeout=5000;`.
- **Status**: **RESOLVED** (Verified in `test_sqlite_wal_mode_and_concurrency`).

---

### CR-07: In-Flight Request Deduplication Race Condition (`data_layer.py`)
- **Severity**: Medium
- **Description**: In `data_layer.py`, waiting threads unblocked after an in-flight fetch event, but the result dictionary was cleared before waiting threads could read the cached response.
- **Impact**: Secondary threads raised `NoneType` errors or duplicated HTTP requests.
- **Remediation**: Hardened the designated worker thread lifecycle so waiting threads safely consume the worker's result before cleanup under lock.
- **Status**: **RESOLVED** (Verified in concurrent stress tests).

---

### CR-08: Percentage Move Alerts Miscalculated from Open (`alerts.py`)
- **Severity**: Medium
- **Description**: Inherited from upstream day-trader-skill issue #3: percentage moves were calculated from the session open price rather than previous close, understating intraday moves by up to two-thirds.
- **Impact**: Price breakout alerts failed to trigger for stocks that gapped up or moved significantly overnight.
- **Remediation**: Updated `check_alerts` in `skills/trader-alerts/alerts.py` to calculate percentage moves against `prev_close` (`previousClose` or `chartPreviousClose`) from official exchange metadata.
- **Status**: **RESOLVED** (Verified in alert unit tests).

---

### CR-09: NSE HTTP Query Bot Mitigation Blocks
- **Severity**: Medium
- **Description**: Raw `urllib.request.urlopen` calls to NSE endpoints (`bhavcopy.py`, `preopen.py`, `fiidii.py`) lacked persistent session cookie cookies, triggering HTTP 403 Forbidden blocks.
- **Impact**: Daily Bhavcopy download and pre-open scanner failed during market hours.
- **Remediation**: Implemented `create_nse_session_opener()` in `skills/common.py` using `http.cookiejar.CookieJar` to perform pre-flight cookie priming before querying data APIs.
- **Status**: **RESOLVED** (Verified in `test_create_nse_session_opener`).

---

### CR-10: Short Position Panic Square-Off Accounting (`dashboard.py`)
- **Severity**: Medium
- **Description**: `emergency_flatten_all()` in `dashboard.py` treated all holdings as long positions (`side == "BUY"`), calculating cash recovery as `price * qty` regardless of whether the position was short.
- **Impact**: Panic flattening an intraday short position credited gross turnover to cash instead of returning locked margin and net P&L.
- **Remediation**: Differentiated position side: for long positions, recover market proceeds; for short positions, return locked margin plus short PnL `(entry_price - current_price) * qty - charges`.
- **Status**: **RESOLVED** (Verified in panic button unit tests).

---

### CR-11: Autotrader Thread Termination & Restart Hang (`autotrader.py`)
- **Severity**: Medium
- **Description**: When stopped during market hours, the background thread in `autotrader.py` iterated through 54 universe stocks without checking the stop event inside the loop, causing `stop()` to timeout and subsequent `start()` calls to fail.
- **Impact**: Auto-trader could not be cleanly toggled from the web terminal.
- **Remediation**: Added `if self.stop_event.is_set(): return` checks inside candidate screening loops and increased join timeout gracefully.
- **Status**: **RESOLVED** (Verified in `test_autotrader_restart_and_double_start`).

---

### CR-12: Wildcard CORS & Missing CSRF Guard (`web_server.py`)
- **Severity**: Medium
- **Description**: `send_json` emitted `Access-Control-Allow-Origin: *` unconditionally, and state-modifying POST endpoints accepted requests without verifying origin.
- **Impact**: Cross-origin web pages running in a user's browser could theoretically invoke API endpoints on localhost.
- **Remediation**: Bound server strictly to `127.0.0.1`, restricted CORS headers to localhost origin, generated `SESSION_CSRF_TOKEN`, and enforced CSRF validation on all state-mutating POST routes.
- **Status**: **RESOLVED** (Verified in web server security suite).

