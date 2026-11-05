# The Day Trader Skill Suite (Indian Equities - NSE/BSE)

Institutional-grade algorithmic day-trading suite engineered specifically for the **National Stock Exchange of India (NSE)** and **Bombay Stock Exchange (BSE)**.

Free, open, standard-library Python (zero mandatory `pip` dependencies). Built around real-world Indian market microstructure, statutory taxes (STT, GST, Stamp Duty), and Indian discount brokers (Zerodha, Angel One, Shoonya).

---

## Clean Subfolder Project Structure

```
trading/
├── skills/                      # 11 Modular Trading Skill Packages
│   ├── trader-alerts/           # Price alerts, market clock, Telegram/Discord notifications
│   ├── trader-analyst/          # Fundamentals, 52w range, multi-week swing & Fibonacci
│   ├── trader-broker/           # Order routing, web UI, failover, SQLite trade journal
│   │   ├── web/                 # Interactive Canvas/DOM Dashboard & TradingView lightweight-charts
│   │   ├── autotrader.py        # Autonomous execution engine & order ticket loop
│   │   ├── dashboard.py         # Terminal dashboard & panic flatten
│   │   ├── failover.py          # Zerodha/AngelOne/Shoonya failover router
│   │   ├── journal.py           # Trade performance journal & SEBI tax calculator
│   │   ├── ticket.py            # Order ticket generator & paper trading
│   │   └── web_server.py        # REST API & live WebSocket/HTTP server
│   ├── trader-budget/           # Half-Kelly sizing, cash buffers, statutory charges
│   ├── trader-entry/            # 5m candle confirmation, intraday VWAP filter, chart snapshots
│   ├── trader-exit/             # 0.05 INR tick rounding, ATR trailing stops, Net R:R
│   ├── trader-insider/          # SEBI PIT & SAST insider trading tracking
│   ├── trader-news/             # Breaking Indian news RSS & FII/DII net flows
│   ├── trader-risk/             # Pre-trade gate, daily profit lock, macro blackouts, India VIX
│   ├── trader-scanner/          # 20 intraday strategies, AIC-20 confluence, CPR/Camarilla, pre-open
│   └── trader-timemachine/      # 75-bar session simulator, SQLite bar cache, Monte Carlo
├── trader/                      # Runtime Data, Configurations & SQLite Databases
│   ├── charts/                  # Rendered entry/exit snapshot PNGs
│   ├── data/                    # history.db (5m candles) & journal.db (closed trades)
│   ├── state/                   # risk.json, broker.json, breadth.json
│   ├── config.json              # Primary system configuration & watchlist
│   ├── events.json              # RBI MPC policy & corporate results blackout calendar
│   ├── portfolio.json           # Live holdings ledger & cash balance
│   └── watchlist.json           # Active watchlist & sector maps
├── docs/                        # Architecture & Planning Documentation
│   └── CLAUDE_DASHBOARD_BLUEPRINT.md
├── tests/                       # Verification Suite
│   └── test_indian_market.py    # Automated test cases
├── automation/                  # Windows Task Scheduler automation scripts
│   └── schedule_tasks.ps1
├── main.py                      # Unified CLI orchestrator & interactive console
└── README.md
```

---

## The Complete Skill Suite & Tooling

| Directory / Tool | Role | Features & Indian Market Specifics |
| :--- | :--- | :--- |
| **`skills/trader-scanner/`** | **Chart Scanner** | • **`scan.py`**: Nifty 100, F&O constituents, and Index ETFs (`NIFTYBEES.NS`, `BANKBEES.NS`). 15-minute ORB (09:15–09:30 IST) + 5d-ATR Gap Exhaustion filter.<br>• **`cpr.py`**: Central Pivot Range (CPR) & Camarilla levels (H4, H3, L3, L4). Classifies days as Narrow CPR (trending breakout probability) vs Wide CPR (sideways).<br>• **`breadth.py`**: Real-time Nifty 50 Advance-Decline (A/D) market breadth barometer.<br>• **`preopen.py`**: Scrapes 09:00–09:08 AM IST pre-open order matching to detect gap leaders before open.<br>• **`strategies.py`**: Complete library of 20 Indian intraday strategies + AIC-20 Confluence Gauge.<br>• **`bhavcopy.py`**: Downloads official daily NSE Bhavcopy to identify high-delivery accumulation (>60%). |
| **`skills/trader-entry/`** | **Entry Timer** | • **`entry.py`**: Real-time 5m candle confirmation with **Intraday VWAP filter** (ensures price > VWAP) and volume expansion checks.<br>• **`chart.py`**: Generates visual PNG chart snapshots with Opening Range box, VWAP line, entry point, and stop/target lines. |
| **`skills/trader-exit/`** | **Exit Planner** | • **`exit.py`**: Computes stop-loss with 0.05 INR tick rounding, fixed 1R/2R targets, and **ATR Trailing Stops**. Calculates true Net R:R after deducting all Indian taxes and brokerage. |
| **`skills/trader-timemachine/`**| **Time Machine** | • **`timemachine.py`**: 75-bar Indian session modeling (375 mins / 5m = 75 bars). Runs 10,000 Monte Carlo bootstrap paths for win probability.<br>• **`history.py`**: Local SQLite database cache (`history.db`) for 5m bars.<br>• **`backtest.py`**: Historical walk-forward backtester for 15m ORB strategy across 60 days. |
| **`skills/trader-budget/`** | **Budget Manager** | • **`size.py`**: Sizes positions to whole shares and rupee loss caps. Features **Drawdown Protection (Half-Kelly)** scaling.<br>• **`tax_calculator.py`**: Calculates STT (0.025%), Stamp Duty, NSE Exchange charges, SEBI turnover fees, GST (18%), discount brokerage (Rs 20/order), and execution slippage. |
| **`skills/trader-risk/`** | **Risk Manager** | • **`check.py`**: Hard gatekeeper enforcing: rupee loss limits, **Daily Profit High-Water Mark Lock** (locks profits if day was green), **Macro Blackouts** (`events.json` for RBI MPC announcements & Union Budget), **India VIX filter** (^INDIAVIX: 11.5–24.0), **Thursday Weekly Expiry cutoff** (13:45 IST), **Consecutive Losses Killswitch**, and **Correlated Sector Caps**. |
| **`skills/trader-broker/`** | **Order Executor** | • **`web_server.py`**: Interactive browser dashboard matching the institutional design blueprint with TradingView Lightweight Charts v4.2.0.<br>• **`dashboard.py`**: Live Terminal Command Center with active positions, live equity, time to 15:10 square-off, and **One-Key Panic Flatten (`--flatten-all`)**.<br>• **`ticket.py`**: Paper trading simulator with local portfolio ledger (`portfolio.json`) + generates copy-ready API payloads for **Zerodha Kite**, **Angel One SmartAPI**, and **Shoonya**.<br>• **`journal.py`**: Automated SQLite EOD Trade Performance Journal (`trades` table, Win rate, turnover, SQN, Net P&L).<br>• **`failover.py`**: Instant broker failover routing switch between active and backup broker APIs. |
| **`skills/trader-alerts/`** | **Price Alerts** | • **`alerts.py`**: Tracks live NSE prices, stop/target triggers, 09:15 opening bell, and the **15:10 IST broker auto-squareoff reminder**. Dispatches instant push notifications via **Telegram Bot** and **Discord Webhook**. |
| **`skills/trader-news/`** | **News & Flows** | • **`news.py`**: Real-time breaking news from Yahoo Finance India & Google News India RSS feeds.<br>• **`fiidii.py`**: Daily NSE Foreign & Domestic Institutional net cash flow tracker. |
| **`skills/trader-analyst/`** | **Financials Analyst**| • **`facts.py`**: Evaluates 52-week ranges, moving averages (20d, 50d, 200d SMA), and quarterly operating margins under SEBI LODR disclosures.<br>• **`swing.py`**: Multi-week swing and Fibonacci retracement scanner with RSI divergence. |
| **`skills/trader-insider/`** | **Insider Tracker** | • **`insider.py`**: Tracks high-value promoter, director, and insider filings (Rs 10 Lakhs+) under SEBI (Prohibition of Insider Trading) regulations. |
| **`automation/`** | **Scheduler** | • **`schedule_tasks.ps1`**: Automated Windows Task Scheduler configuration for Indian market bells (09:08 AM, 09:35 AM, 03:10 PM). |

---

## Typical Workflow

```
preopen (09:08) & cpr.py ➔ breadth.py ➔ scanner (09:35) ➔ entry (+VWAP) ➔ exit (+Trailing Stop)
➔ timemachine (10k paths) ➔ budget (+Taxes & Slippage) ➔ risk (VIX, Macro, Profit Lock) ➔ broker
web_server.py: Live interactive browser GUI + AIC-20 Confluence Gauge + TV Charts
dashboard.py: Live terminal monitoring + emergency panic flatten (--flatten-all)
alerts: stop, target, Telegram push, flat by 15:10 IST
EOD (15:30): journal.py & fiidii.py
```

---

## Automated Verification

Run the comprehensive unit test suite:
```bash
python tests/test_indian_market.py
```
*(Tests cover IST timezones, 75 session bars, NSE holidays, tax & slippage engines, VWAP, CPR & Camarilla math, trailing stops, VIX filters, consecutive loss killswitch, high-water mark profit locks, macro blackouts, sector risk caps, Thursday expiry cutoff, and SQLite caching).*
