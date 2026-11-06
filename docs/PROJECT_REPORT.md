# Vyapar AI — Comprehensive Project Audit, Architecture & Engineering Transformation Report

**Document ID**: VYAPAR-AUDIT-2026-v2  
**Date**: November 6, 2026  
**Subject**: Technical Audit, Safety Remediation, Concurrency Hardening, and Production Upgrade of Vyapar AI  
**Author**: Senior Software Architect, Principal Full-Stack Engineer, Security Auditor, and Lead QA Engineer  

---

## 1. Executive Summary

Vyapar AI is a zero-dependency, Python standard-library algorithmic trading engine, risk governor, and local web terminal engineered specifically for the National Stock Exchange of India (NSE) and Bombay Stock Exchange (BSE).

Originating as an Indian-market adaptation of Jake Schincariol's open-source `day-trader-skill`, the project has undergone a complete architectural, forensic code, and security audit. Over the course of this transformation:
- **12 discrete code review findings (CR-01 through CR-12)** spanning security, concurrency deadlocks, tax modeling, and state corruption were identified, remediated, and verified.
- **76 automated regression unit tests** pass with 100% reliability without relying on live external networks.
- A **multi-target skill suite installer (`install.py`)** was developed to bridge the project seamlessly across Claude Code, Google Antigravity / Gemini, Cursor, and local operating systems.
- The **Web Terminal** was upgraded to an institutional 5-view SPA with TradingView Lightweight Charts overlays, `Ctrl+K` command palette, tabular numerals, glassmorphism, and SSE streaming.

---

## 2. Project Lineage & Upstream Differentiation

| Architectural Dimension | Upstream (`day-trader-skill`) | Vyapar AI v2.0.0 (Indian Market) |
|---|---|---|
| **Market Calibration** | US Equities (NASDAQ, NYSE) | Indian Equities (NSE, BSE) |
| **Dependencies** | Requires `alpaca-py`, `yfinance`, US MCP | **Zero mandatory dependencies** (Python standard library only) |
| **Trading Hours** | 09:30 – 16:00 EST | 09:15 – 15:30 IST (MIS square-off at 15:10 IST) |
| **Pivots & Indicators** | Traditional Daily High/Low | Central Pivot Range (CPR), Camarilla (H4/L4), VWAP, Supertrend |
| **Tax Modeling** | US SEC fees / 0% transaction tax | Indian STT (Finance Act 2026-27), Stamp Duty, Exchange Fee, SEBI Fee, GST (18%) |
| **Market Data** | Yahoo Finance US & Alpaca API | NSE Bhavcopy, Pre-open auction, BSE quote fallback, FII/DII flow |
| **Web Terminal** | Minimal terminal text | 5-View SPA with offline TradingView Lightweight Charts v4.2.0 |
| **Broker Ecosystem** | Alpaca Paper/Live | Paper Simulator, Zerodha Kite Connect, Angel One SmartAPI, Finvasia Shoonya |

---

## 3. Technology Stack & Zero-Dependency Invariant

Vyapar AI strictly adheres to the principle of **zero mandatory external dependencies** on the backend:
- **Runtime**: Python 3.10+ (tested on Python 3.14.7).
- **HTTP Engine**: `http.server.ThreadingHTTPServer` (concurrent request handling).
- **Network Client**: `urllib.request` with `http.cookiejar.CookieJar` session priming.
- **Database Engine**: `sqlite3` with Write-Ahead Logging (`PRAGMA journal_mode=WAL;`).
- **Concurrency**: `threading.RLock`, `threading.Event`, and bounded thread pools.
- **Data Serialization**: `json` with atomic temporary file swapping (`atomic_write_json`).
- **Frontend**: Native HTML5, modern CSS3 (tokens, glassmorphism, scroll-driven animations), vanilla JavaScript (ES6+), and offline vendored TradingView Lightweight Charts v4.2.0.

---

## 4. Indian Market Microstructure Calibration

The platform enforces hard operational constraints dictated by Indian market regulations:
1. **Timezone Pinning**: All operations execute strictly in Indian Standard Time (`Asia/Kolkata` / UTC+05:30).
2. **Session Phases**:
   - `09:00 - 09:08 IST`: Pre-Open Auction session order matching.
   - `09:08 - 09:15 IST`: Order matching buffer.
   - `09:15 IST`: Regular trading session open.
   - `09:30 IST`: Earliest permitted intraday entry (eliminating initial opening whipsaws).
   - `13:45 IST`: Thursday weekly F&O expiry entry cutoff.
   - `14:45 IST`: End of new intraday entries.
   - `15:10 IST`: Compulsory MIS intraday position square-off.
   - `15:30 IST`: NSE/BSE closing bell.
3. **Tick Grid Rules**: Equities trade on ₹0.05 tick sizes; ETFs trade on ₹0.01 tick sizes.

---

## 5. Security & Risk Audit (CR-01 & CR-02)

### CR-01: Risk Decision Audit Masking
In `skills/trader-risk/check.py`, `log_risk_decision` previously masked file persistence failures using `except Exception: pass`. This broke the fail-closed invariant. The function was refactored to remove the silent catch, report write errors to `sys.stderr`, and tag every risk verdict with a deterministic SHA-256 order fingerprint.

### CR-02: Secret Hygiene & Git Purge
Compiled Python bytecode (`__pycache__/*.pyc`) and database binaries were previously tracked in Git. The repository was cleaned with updated `.gitignore` rules, and `resolve_secrets()` in `main.py` was implemented to read secrets exclusively from environment variables (`TELEGRAM_BOT_TOKEN`, `DISCORD_WEBHOOK_URL`) while masking them in console logs.

---

## 6. Concurrency & State Persistence (CR-03, CR-06, CR-07)

### CR-03: Atomic File Persistence
To prevent corrupt JSON state files if a crash occurred during file writes, `skills/common.py` was equipped with `atomic_write_json()`. The function writes to a hidden temporary file in the destination folder, flushes and syncs to disk (`os.fsync`), and atomically renames via `os.replace` under `STATE_LOCK`.

### CR-06: SQLite WAL Mode Concurrency
Under concurrent web requests and backtests, SQLite previously threw `database is locked`. All SQLite connections in `history.py`, `journal.py`, and `data_layer.py` were hardened with:
```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;
```

### CR-07: In-Flight Request Deduplication
In `skills/data_layer.py`, waiting threads unblocked before reading the worker thread's response, causing race conditions. The synchronization was restructured so all waiting threads safely consume the worker's output before releasing in-flight locks.

---

## 7. Statutory Taxation Engine & Finance Act 2026-27 (CR-05)

Indian securities transaction costs represent a significant hurdle for high-frequency day traders. `skills/trader-budget/tax_calculator.py` was updated to incorporate the **Finance Act 2026-27** statutory amendments:
- **Equity Intraday (MIS)**: STT 0.025% on sell turnover.
- **F&O Futures**: STT raised from 0.02% to **0.05%** on sell turnover.
- **F&O Options**: STT raised from 0.10% to **0.15%** on sell premium turnover.
- **Statutory Rounding**: Implemented `round_rupee` using `decimal.ROUND_HALF_UP` to round STT to the nearest whole rupee, matching Zerodha and NSE clearing corporation settlement sheets.

---

## 8. Cash Reconciliation & Accounting Hardening (CR-04 & CR-10)

### CR-04: Phantom Cash Credit Elimination
In `web_server.py`, trade exits previously credited `margin_returned + gross_pnl` to portfolio cash, effectively returning statutory charges to the user balance and causing phantom cash inflation. This was corrected to credit `margin_returned + net_pnl`.

### CR-10: Short Position Panic Square-Off
In `dashboard.py`, `emergency_flatten_all()` previously treated all open positions as long, crediting market value to cash. It was refactored to handle short (`SELL`) positions by covering the short at market price, returning locked margin, and crediting/debiting realized net P&L.

---

## 9. Upstream & Network Resiliency (CR-08 & CR-09)

### CR-08: Percentage Move Calibration
Percentage move alert triggers were updated in `alerts.py` to calculate price changes relative to `previous_close` rather than intraday open, correctly detecting overnight gaps and early morning momentum.

### CR-09: NSE Cookie Jar Session Opener
Direct requests to NSE endpoints frequently resulted in HTTP 403 Forbidden. `create_nse_session_opener()` in `skills/common.py` initializes a `CookieJar` and performs a pre-flight visit to `https://www.nseindia.com/` to acquire session cookies before executing API calls.

---

## 10. Web Terminal & UI/UX Modernization

The web interface (`skills/trader-broker/web/`) was upgraded into a production-grade single-page application:
- **5-View SPA Architecture**: Hash routing support for `#/cockpit`, `#/scanner`, `#/intel`, `#/timemachine`, and `#/journal`.
- **Lightweight Charts Overlays**: Entry line (solid saffron), stop-loss line (dashed red), and target line (dashed green) rendered dynamically on top of candlestick series.
- **8-Stage Pipeline Stepper**: Visual stage-by-stage progression in the cockpit ribbon.
- **Command Palette (`Ctrl+K`)**: Instant search and navigation across symbols, strategies, and views.
- **REST & SSE Endpoints**: `/api/v1/bootstrap` with ETag caching and `/api/v1/stream` Server-Sent Events.
- **Styling Upgrades**: `font-variant-numeric: tabular-nums;`, glassmorphic top header, price tick flash animations, and CSS scroll-driven progress bars.

---

## 11. Multi-Target Skill Suite Installer (`install.py`)

To eliminate manual configuration friction, `install.py` provides unified multi-platform setup:
```bash
python install.py --target all --verify
```
Supports:
- **Claude Code**: Installs 20 skills to `.claude/skills/`.
- **Google Antigravity / Gemini**: Registers 9 skills in `.agent/skills/`.
- **Cursor**: Generates `.cursorrules` with project safety invariants.
- **Local Workspace**: Generates `vyapar.cmd` and `vyapar.sh` launchers.

---

## 12. Verification & Test Suite Performance

The comprehensive regression suite in `tests/test_indian_market.py` was expanded to 76 tests covering:
- Statutory tax calculations and rounding.
- SQLite WAL mode and concurrent reads/writes.
- Atomic state file persistence.
- Pre-trade risk gates, profit locks, and consecutive loss killswitches.
- Autotrader thread start/stop lifecycle.
- Web server REST endpoints and failover switches.

**Verification Result**:
```text
Ran 76 tests in 14.121s
OK (0 failures, 0 errors)
```

---

## 13. SEBI Regulatory Compliance & Disclaimers

Vyapar AI is engineered strictly for **educational, quantitative research, and paper-trading simulation purposes**:
- **SEBI RA Regulation**: The software does not provide personalized investment advice, guaranteed returns, or SEBI-registered advisory services.
- **Fail-Closed Execution**: The system cannot execute live orders without explicit human configuration and multi-step broker authorization.
- **Performance Reporting**: All metrics in the trade journal are calculated strictly from the user's historical paper ledger; the software never fabricates win rates or profit claims.

---

## 14. Known Limitations

1. **Options Execution**: F&O options strategies (9:20 Straddle, Strangle, Iron Condor) are classified as Analysis-Only and blocked from automated execution until Phase 1 roadmap completion.
2. **Polling Frequency**: Quotes are polled at 5-second intervals via HTTP; sub-second high-frequency scalping requires WebSocket tick streaming (Phase 2 roadmap).
3. **NSE Bot Mitigation**: During periods of extreme exchange website maintenance, direct NSE Bhavcopy downloads may experience transient delays.

---

## 15. Conclusion & Operational Sign-Off

The Vyapar AI codebase has successfully transitioned from an unhardened fork into a robust, institutional-grade Indian equities algorithmic toolkit. With zero external dependencies, atomic state guarantees, fail-closed pre-trade gates, and full AI agent compatibility, the platform is ready for production paper-trading operations.

