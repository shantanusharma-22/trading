# Vyapar AI — Semantic Release History & Changelog

All notable changes to the Vyapar AI platform are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] - 2026-11-06

### Major Architectural Upgrade & Indian Market Institutional Release

#### 🛡️ Security & Risk Invariants Hardening
- **CR-01 Remediation**: Eliminated bare `except Exception: pass` masking in `skills/trader-risk/check.py` (`log_risk_decision`). Pre-trade risk decisions now log failures to `sys.stderr` and record immutable SHA-256 fingerprints in `trader/state/decisions.json`.
- **CR-02 Remediation**: Purged Python bytecode (`__pycache__/*.pyc`) and runtime databases from Git index. Masked sensitive bot tokens in CLI console output and prioritized environment variables (`TELEGRAM_BOT_TOKEN`, `DISCORD_WEBHOOK_URL`).
- **CR-12 Remediation**: Restricted CORS on `127.0.0.1:8765` from wildcard `*` to localhost origins. Introduced `SESSION_CSRF_TOKEN` generation and validated `X-CSRF-Token` headers on all state-mutating POST endpoints.

#### ⚡ Concurrency & State Persistence
- **CR-03 Remediation**: Implemented `atomic_write_json(target_path, payload)` in `skills/common.py` using `tempfile.NamedTemporaryFile` + `os.fsync` + `os.replace` under a re-entrant `STATE_LOCK`.
- **CR-06 Remediation**: Configured Write-Ahead Logging (WAL) mode (`PRAGMA journal_mode=WAL; busy_timeout=5000; synchronous=NORMAL;`) across `trader/data/history.db` and `trader/data/journal.db` to prevent `database is locked` operational deadlocks.
- **CR-07 Remediation**: Resolved thread race condition in `skills/data_layer.py` in-flight request deduplication so waiting threads safely consume worker results.

#### 💰 Statutory Tax & Accounting Accuracy
- **CR-04 Remediation**: Fixed phantom cash inflation in `/api/trade/exit`. Trade square-offs now credit locked margin + realized *net* P&L (not gross P&L) and pass net P&L to `record_closed_trade()`.
- **CR-05 Remediation**: Upgraded `skills/trader-budget/tax_calculator.py` with Finance Act 2026-27 STT rate changes (Futures sell 0.05%, Options sell 0.15%) and implemented statutory nearest-rupee rounding (`round_rupee` via `ROUND_HALF_UP`).
- **CR-10 Remediation**: Hardened `emergency_flatten_all()` in `dashboard.py` to differentiate between long (`BUY`) and short (`SELL`) positions, returning locked margin plus short PnL instead of phantom gross turnover.

#### 🌐 Web Terminal & UI/UX Modernization
- **5-View SPA Router**: Added first-class support for `#/cockpit`, `#/scanner`, `#/intel`, `#/timemachine`, and `#/journal` hash routing.
- **Command Palette**: Added `Ctrl+K` Institutional Command Palette with search, navigation shortcuts, and panic flatten triggers.
- **Lightweight Charts Overlays**: Added dynamic `ENTRY`, `STOP`, and `TARGET` price lines directly on the candlestick chart canvas alongside CPR and Camarilla overlays.
- **8-Stage Pipeline Stepper**: Integrated visual pipeline stepper (`Scanner -> News -> Entry -> Exit -> TimeMachine -> Budget -> Risk -> Broker`) in the trading cockpit.
- **REST & SSE Endpoints**: Implemented `/api/v1/bootstrap` with ETag caching and `/api/v1/stream` Server-Sent Events (SSE) for real-time dashboard updates.
- **Modern Styling**: Applied `font-variant-numeric: tabular-nums;`, glassmorphic top header blur, price tick flash animations, and CSS scroll-driven progress bars.

#### 📦 Multi-Target Skill Suite Installer
- Created `install.py` supporting `--target {claude,antigravity,cursor,local,all}` and `--verify`.
- Added `install` subcommand and interactive menu option `[14]` in `main.py`.
- Generated executable launch wrappers `vyapar.cmd` (Windows) and `vyapar.sh` (Unix/macOS).

---

## [1.0.0] - 2026-11-05
- Initial adaptation of `day-trader-skill` for Indian Equities (NSE/BSE).
- Introduction of 20 Indian Intraday Strategies and AIC-20 Confluence Model.
- CPR & Camarilla engine (`cpr.py`), Bhavcopy delivery scanner (`bhavcopy.py`), and pre-open scanner (`preopen.py`).
- Basic local web dashboard with vendored TradingView Lightweight Charts v4.2.0.
