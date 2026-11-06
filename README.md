<div align="center">
  <img src="docs/vyapar_ai_logo.png" alt="Vyapar AI - Smarter Trades for Bharat" width="620" style="border-radius: 12px; margin-bottom: 12px;"/>

  # Vyapar AI — Smarter Trades for Bharat
  ### Institutional Algorithmic Day Trading, Execution & Quantitative Research Suite (NSE / BSE)

  [![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Dependencies: Zero](https://img.shields.io/badge/Dependencies-Zero%20(Standard%20Library)-brightgreen.svg)]()
  [![Market: NSE / BSE](https://img.shields.io/badge/Exchanges-NSE%20%7C%20BSE-orange.svg)]()
  [![Brokers: Multi-Broker](https://img.shields.io/badge/Brokers-Paper%20%7C%20Zerodha%20%7C%20Angel%20%7C%20Shoonya-blueviolet.svg)]()
  [![AI Providers: Universal](https://img.shields.io/badge/AI%20Support-Claude%20%7C%20Gemini%20%7C%20OpenAI%20%7C%20Cursor%20%7C%20DeepSeek-cyan.svg)]()
</div>

**Vyapar AI** is an institutional-grade algorithmic day trading, autonomous execution, and quantitative research platform engineered specifically for the **National Stock Exchange of India (NSE)** and **Bombay Stock Exchange (BSE)**.

Built with **100% Python Standard Library** (zero mandatory `pip` dependencies), local offline **TradingView Lightweight Charts v4.2.0**, institutional pre-trade risk gates, statutory SEBI charges calculation, multi-broker failover routing, and an open skill architecture compatible with **all AI models and agent frameworks**.

---

## Table of Contents
1. [Key Features](#key-features)
2. [Indian Market Microstructure Architecture](#indian-market-microstructure-architecture)
3. [Installation & Quick Start](#installation--quick-start)
4. [Institutional Documentation Package](#institutional-documentation-package)
5. [Clean Subfolder Structure](#clean-subfolder-structure)
6. [Complete Library of 20 Indian Intraday Strategies](#complete-library-of-20-indian-intraday-strategies)
7. [The AIC-20 Confluence Ensemble Model](#the-aic-20-confluence-ensemble-model)
8. [Autonomous AutoTrader Engine](#autonomous-autotrader-engine)
9. [Institutional Risk Gates & Safeguards](#institutional-risk-gates--safeguards)
10. [Statutory SEBI Taxes & Net P&L Engine](#statutory-sebi-taxes--net-pl-engine)
11. [Supported Broker Providers](#supported-broker-providers)
12. [Universal AI Agent Support (All AI Providers)](#universal-ai-agent-support-all-ai-providers)
13. [Interactive Web Dashboard & REST API](#interactive-web-dashboard--rest-api)
14. [Automated Unit Verification](#automated-unit-verification)
15. [Compliance & Disclaimer](#compliance--disclaimer)

---

## Key Features

- **Zero Mandatory Dependencies**: Runs entirely on Python's built-in libraries (`sqlite3`, `json`, `urllib`, `datetime`, `threading`, `math`, `hashlib`). No fragile pip packages required.
- **Universal Multi-Target Installer**: Automated setup (`python install.py --target all --verify`) configuring Claude Code, Google Antigravity / Gemini, Cursor, and local CLI wrappers.
- **Universal AI Interoperability**: Every trading package contains a standard `SKILL.md` compliant with Anthropic Claude (Claude Code, Desktop MCP), OpenAI (GPT-4o, Agents SDK), Google Gemini / Antigravity, Cursor / Windsurf, and local LLMs (Ollama, DeepSeek-R1).
- **20 Verified Indian Intraday Strategies**: Complete implementation spanning Opening Range Breakouts (ORB), CPR/Camarilla, VWAP, Supertrend, 9/20 EMA cross, RSI Divergence, 9:20 Straddle, Expiry Buying, and FII/DII flow.
- **AIC-20 Confluence Engine**: Evaluates all 20 strategies simultaneously per 5-minute bar and normalizes them into a composite 0–100 institutional conviction score.
- **Autonomous AutoTrader**: Universal stock scanner across Nifty 50 and liquid F&O constituents with setup qualification, automated ₹1,000 risk-capped position sizing, 1.5x ATR trailing stops, and 15:10 IST square-off.
- **Institutional Pre-Trade Risk Gates**: Enforces C1 sizing rejection, C3 server validation, C4 pre-trade gate, C5 mid-day risk locking, High-Water Mark Daily Profit Lock, 2-consecutive losses killswitch, macro event blackouts (RBI MPC & Union Budget), Thursday weekly expiry cutoff, and India VIX filters.
- **Finance Act 2026-27 Tax Engine**: Statutory Indian transaction costs with revised STT (Futures 0.05%, Options 0.15%), nearest-rupee rounding, Stamp Duty, NSE turnover fees, SEBI turnover charges, GST (18%), and slippage.
- **Institutional SQLite Trade Journal**: Persistent `trades` and `risk_state` schemas in WAL mode storing trade history, Win Rate, Profit Factor, Expectancy, and System Quality Number (SQN).
- **Offline TradingView Lightweight Charts**: Vendored local v4.2.0 charting library with automatic BSE symbol mapping fallback, CPR/Camarilla overlays, intraday VWAP lines, and setup price lines (`ENTRY`, `STOP`, `TARGET`).
- **Command Palette & Keyboard Control**: Instant navigation via `Ctrl + K`, 5-view SPA hash routing (`#/cockpit`, `#/scanner`, `#/intel`, `#/timemachine`, `#/journal`), and tabular numerals (`font-variant-numeric: tabular-nums;`).
- **Multi-Broker Failover**: Default zero-risk Paper Trading simulator alongside API payload generators and instant failover switches for **Zerodha Kite Connect**, **Angel One SmartAPI**, and **Shoonya (Finvasia)**.
- **Mobile Push Notifications**: Real-time trade fills, stop hits, profit targets, 09:15 opening bell, and 15:10 square-off reminders dispatched via **Telegram Bot** and **Discord Webhooks**.

---

## Institutional Documentation Package

Comprehensive institutional engineering documentation is available in the [`docs/`](docs/) directory:

| Document | Description |
|---|---|
| [**`docs/PROJECT_REPORT.md`**](docs/PROJECT_REPORT.md) | 15-Section Comprehensive Project Audit, Architecture & Transformation Report |
| [**`docs/ARCHITECTURE.md`**](docs/ARCHITECTURE.md) | System Design Manual with 4 Mermaid Architecture & State Diagrams |
| [**`docs/CODE_REVIEW.md`**](docs/CODE_REVIEW.md) | Forensic Code Review Ledger documenting CR-01 through CR-12 Remediations |
| [**`docs/SETUP_GUIDE.md`**](docs/SETUP_GUIDE.md) | Developer & Operator Setup Manual for Windows, macOS, and Linux |
| [**`docs/CHANGELOG.md`**](docs/CHANGELOG.md) | Semantic Release History (v1.0.0 to v2.0.0 Institutional Upgrade) |
| [**`docs/ROADMAP.md`**](docs/ROADMAP.md) | 4-Phase Future Engineering Roadmap (F&O, WebSockets, ML, HSM) |

---

## Indian Market Microstructure Architecture

The platform is strictly calibrated to the real-world operational rules of Indian exchanges:
- **Timezone**: All clocks, candles, and schedules are pinned to **Indian Standard Time (IST / UTC+05:30)**.
- **Session Hours**:
  - `09:00 - 09:08 IST`: Pre-Open Auction session order matching & gap discovery.
  - `09:15 IST`: Official NSE/BSE opening bell.
  - `09:15 - 09:30 IST`: Opening Range calculation window (ORB).
  - `09:30 IST`: First valid intraday trade entries allowed (avoids first-15-minute fakeouts).
  - `13:45 IST`: Thursday Weekly F&O Expiry Shield cutoff (no new entries permitted).
  - `14:45 IST`: Standard daily entry cutoff (no new entries permitted).
  - `15:10 IST`: Mandatory broker auto-square-off threshold for MIS intraday positions.
  - `15:30 IST`: Official market close and EOD Bhavcopy reconciliation.
- **Bar Count**: Exactly 75 five-minute bars per regular trading session (375 trading minutes).
- **Tick Size**: Mandatory NSE 0.05 INR price rounding on all stops, limits, and targets.
- **SEBI Peak Margin**: Maximum 5× intraday leverage on equities under SEBI peak margin rules.

---

## Installation & Quick Start

### 1. Prerequisites
- **Python 3.10 or higher** installed on Windows, macOS, or Linux.
- Git (optional, for cloning).

### 2. Setup
```bash
# Clone the repository (or extract the zip)
git clone https://github.com/your-username/trading.git
cd trading
```

### 3. Verify System Health
Run the comprehensive automated unit test suite:
```bash
python main.py test
# Or directly via unittest:
python -m unittest tests/test_indian_market.py
```
*All 72 institutional unit and contract tests run and pass in ~5.2s using only Python's standard library.*

### 4. Launch Unified Master Console
```bash
python main.py
```
This opens the interactive terminal orchestrator:
```
============================================================
           VYAPAR AI - SMARTER TRADES FOR BHARAT            
============================================================
 Capital: Rs 100,000 | Risk/Trade: Rs 1,000 | Broker: PAPER
 Watchlist: RELIANCE.NS, TCS.NS, INFY.NS, JIOFIN.NS, HDFC.NS
------------------------------------------------------------
 [1] View Portfolio & Market Clock Status
 [2] Calculate CPR & Camarilla Pivot Setups (Watchlist)
 [3] Run Morning Pre-Open Auction Scan (09:08 AM)
 [4] Run 15-Minute ORB & VWAP Breakout Scan (09:35 AM)
 [5] Multi-Week Swing & Fibonacci Analysis (RSI Divergence)
 [6] View Terminal Dashboard
 [7] Emergency PANIC Square-Off (Market Exit All)
 [8] View Trade Performance Journal
 [9] Run Automated Unit Tests (Verification)
 [10] Test Push Notifications (Telegram / Discord)
 [11] Configure Telegram / Discord Push Alerts
 [12] 🌐 Launch Interactive Web Dashboard (Browser UI)
 [13] 📊 All 20 Intraday Strategies Library & Signals
 [0] Exit
------------------------------------------------------------
```

### 5. Launch Interactive Browser Dashboard
To open the live visual dashboard with TradingView charts, AIC-20 gauge, watchlist pills, and paper trading tickets:
```bash
python main.py ui
# Or start directly:
python skills/trader-broker/web_server.py --port 8765
```
Open **`http://127.0.0.1:8765`** in any modern web browser.

### 6. (Optional) Configure Windows Task Scheduler
To automate market-hour triggers at 09:08 AM (Pre-Open), 09:35 AM (ORB Scan), and 15:10 PM (MIS Squareoff):
```powershell
powershell -ExecutionPolicy Bypass -File automation/schedule_tasks.ps1
```

---

## Clean Subfolder Structure

```
trading/
├── skills/                      # 11 Modular Trading Skill Packages (AI Agent Compatible)
│   ├── trader-alerts/           # Market clock, live quote tracking, Telegram/Discord notifications
│   ├── trader-analyst/          # 52-week ranges, moving averages, multi-week swing & Fibonacci
│   ├── trader-broker/           # Order routing, web UI, failover router, SQLite trade journal
│   │   ├── web/                 # Web interface assets
│   │   │   ├── static/          # Vendored local TradingView lightweight-charts v4.2.0
│   │   │   └── index.html       # Institutional Dashboard UI (DOM/Canvas, IBM Plex fonts)
│   │   ├── autotrader.py        # Autonomous trading engine & universal stock screener
│   │   ├── dashboard.py         # Terminal dashboard & panic flatten button
│   │   ├── failover.py          # Zerodha/AngelOne/Shoonya failover routing engine
│   │   ├── journal.py           # Trade journal, SQLite persistence & SEBI tax calculator
│   │   ├── ticket.py            # Order ticket generator & paper trading simulator
│   │   └── web_server.py        # REST API & live HTTP/WebSocket backend server
│   ├── trader-budget/           # Half-Kelly position sizing, cash buffers, statutory charges
│   ├── trader-entry/            # 5m candle confirmation, intraday VWAP filter, chart snapshots
│   ├── trader-exit/             # 0.05 INR tick rounding, ATR trailing stops, Net R:R math
│   ├── trader-insider/          # SEBI PIT & SAST insider transaction disclosures tracker
│   ├── trader-news/             # Breaking Indian financial RSS news & FII/DII cash flow tracker
│   ├── trader-risk/             # Universal pre-trade gate, daily profit lock, macro blackouts
│   ├── trader-scanner/          # 20 intraday strategies, AIC-20 confluence, CPR/Camarilla, pre-open
│   └── trader-timemachine/      # 75-bar session simulator, SQLite bar cache, Monte Carlo paths
├── trader/                      # Runtime Data, Configurations & SQLite Databases
│   ├── charts/                  # Rendered entry/exit PNG chart snapshots
│   ├── data/                    # history.db (5m candles) & journal.db (closed trades ledger)
│   ├── state/                   # risk.json, broker.json, breadth.json, news.json
│   ├── config.json              # Primary system configuration & watchlist
│   ├── events.json              # RBI MPC policy & corporate results blackout calendar
│   ├── portfolio.json           # Live holdings ledger & cash balance
│   └── watchlist.json           # Active watchlist & sector maps
├── docs/                        # Architecture & Blueprint Documentation
│   └── CLAUDE_DASHBOARD_BLUEPRINT.md
├── tests/                       # Verification Suite
│   └── test_indian_market.py    # 23-point automated unit test suite
├── automation/                  # Windows Task Scheduler automation scripts
│   └── schedule_tasks.ps1
├── main.py                      # Unified CLI orchestrator & interactive console
└── README.md                    # Platform documentation & user manual
```

---

## Complete Library of 20 Indian Intraday Strategies

The platform implements all 20 of the most widely traded intraday strategies across NSE and BSE, categorized by execution style:

```
+----------------------------------------------------------------------------------------------------+
|                                    ALL 20 INTRADAY STRATEGIES                                      |
+--------------------------+--------------------------+--------------------------+-------------------+
| 🚀 BREAKOUT / MOMENTUM   | 📈 TREND-FOLLOWING       | 🔄 REVERSAL / REVERSION  | ⚡ OPTIONS & FLOW |
| 1. 15m ORB Breakout      | 5. VWAP Pullback         | 9. RSI Divergence        | 13. Expiry Buying |
| 2. PDH/PDL Breakout      | 6. 9/20 EMA Cross        | 10. Bollinger Squeeze    | 14. Hedged Selling|
| 3. Gap-and-Go / Fill     | 7. Supertrend (10, 3)    | 11. CPR & Camarilla      | 15. 9:20 Straddle |
| 4. Volume Consolidation  | 8. 20 EMA + RSI Retest   | 12. Bank Nifty Scalping  | 16. OI / Max Pain |
|                          |                          |                          | 17. News / Events |
|                          |                          |                          | 18. Sector Trend  |
|                          |                          |                          | 19. FII/DII Flows |
|                          |                          |                          | 20. AIC-20 Gauge  |
+--------------------------+--------------------------+--------------------------+-------------------+
```

### Breakout & Momentum
1. **15-Minute Opening Range Breakout (ORB)**: Marks the 09:15–09:30 IST high and low; enters on a confirmed 5m bar close beyond the range with volume confirmation and a hard stop at the midpoint or opposite extreme.
2. **Previous Day High / Low (PDH/PDL) Breakout**: Uses yesterday's high/low as primary trigger thresholds when confirmed with volume > 1.5× the 20-period moving average.
3. **Gap-and-Go / Gap-Fill**: Analyzes 09:08 AM pre-open auction gaps (>1–2%). If the opening 15m candle holds above the gap, enters in direction of gap; if it breaches the opening low within 30 minutes, fades the gap for a fill.
4. **Volume Breakout & Narrow Range (NR7 / Inside Bar)**: Identifies consolidation days with the narrowest range of the last 7 sessions (NR7) or inside bars; enters on expansion accompanied by 2–3× average volume.

### Trend-Following
5. **Intraday VWAP Strategy**: Buys pullbacks to the Volume-Weighted Average Price in uptrends and shorts bounces to VWAP in downtrends. VWAP acts as a primary institutional regime filter.
6. **9/20 EMA Moving Average Crossover**: Uses 9 EMA crossing 20 EMA on 5-minute charts for high-momentum trends, utilizing the 20 EMA as a dynamic trailing stop.
7. **Supertrend (10, 3)**: Fast trend-following system with entries triggered upon directional trend line flips; highly popular on Bank Nifty and liquid F&O stocks.
8. **Pullback to 20 EMA with RSI**: Enters when price retests the 20 EMA while RSI(14) remains in bullish territory (>40 for long, <60 for short).

### Reversal & Mean-Reversion
9. **RSI Divergence & Overbought/Oversold**: Identifies momentum exhaustion when RSI(14) > 70 or < 30 displays divergence against price at key horizontal support or resistance.
10. **Bollinger Band Squeeze & Snap-Back**: Fades candle closes outside the 20, 2 Bollinger Bands during sideways market regimes; trades volatility expansion when the bandwidth contracts.
11. **Central Pivot Range (CPR) & Camarilla Pivots**: Classifies trading days as Narrow CPR (trending breakout probability > 70%) vs Wide CPR (sideways / range-bound day). Uses Camarilla H3/L3 as mean-reversion boundaries and H4/L4 as breakout triggers.
12. **Bank Nifty Scalping**: Fast-execution system targeting 0.15%–0.30% moves on 1–3 minute charts with tight stops and strict slippage controls.

### Options-Specific (Index Intraday)
13. **Expiry-Day Option Buying**: Targets ATM/near-OTM Nifty and Bank Nifty weekly options on post-10:30 AM breakouts to capitalize on rapid delta moves and gamma spikes.
14. **Option Selling with Hedge (Iron Condor / Strangle)**: Sells OTM call and put legs on low-VIX sideways days with defined-risk protective wings, mandatory square-off by 15:00 IST.
15. **9:20 AM Rule-Based Straddle ("920 Straddle")**: Sells ATM straddle at 09:20 IST with a strict 25% stop-loss per leg and automatic square-off by 15:10 IST.
16. **Open Interest (OI) & Max Pain Analysis**: Identifies intraday support and resistance strikes based on real-time call/put OI accumulation and shift in max pain levels.

### Macro, Event & Flow-Based
17. **Corporate Results & News Trading**: Trades post-announcement volatility for quarterly financial earnings released under SEBI LODR disclosures.
18. **Sector Momentum & Rotation**: Identifies the top-moving sector index (Nifty Bank, Nifty IT, Nifty Auto, Nifty Metal) and trades the relative strength leader.
19. **FII / DII Institutional Flows & Global Bias**: Synthesizes overnight GIFT Nifty, US markets, and domestic institutional net cash flows to establish pre-market directional bias.
20. **AIC-20 Confluence Ensemble Model**: Custom quantitative ensemble uniting all above strategies into an institutional multi-factor gauge.

---

## The AIC-20 Confluence Ensemble Model

Rather than relying on a single indicator, the **AIC-20 Confluence Model** evaluates all 20 strategies simultaneously on incoming 5-minute candles:
- Each strategy returns a directional signal (`BUY`, `SELL`, `NEUTRAL`) and conviction weight.
- Signals are aggregated into a composite score from **0 to 100**:
  - `Score >= 75`: **STRONG BUY** (Green) — High probability trend alignment.
  - `60 <= Score < 75`: **BUY** (Emerald) — Favorable entry setup.
  - `40 < Score < 60`: **NEUTRAL** (Gray) — Choppy / sideways market. No trade allowed.
  - `25 < Score <= 40`: **SELL / SHORT** (Amber) — Weakness / breakdown setup.
  - `Score <= 25`: **STRONG SHORT** (Crimson) — High conviction short breakdown.

The score is rendered in real-time on the web dashboard via an institutional SVG radial gauge and cockpit safety readout.

---

## Autonomous AutoTrader Engine

The AutoTrader (`skills/trader-broker/autotrader.py`) is an autonomous background engine designed for hands-free or semi-automated execution:

1. **Universal Stock Screener**: Continuously monitors the Nifty 50 and active watchlist for Narrow CPR setups and opening volatility.
2. **Setup Qualification**: Requires both 15m ORB range break and price confirmation relative to VWAP (`Price > VWAP` for longs; `Price < VWAP` for shorts).
3. **Dynamic Position Sizing**: Computes whole-share order size so that the maximum risk is strictly capped at **₹1,000** (or your configured `max_loss_per_trade_inr`).
4. **Active Trade Management**:
   - Computes ATR(14) for dynamic volatility-based trailing stop updates (1.5× ATR).
   - Enforces a minimum 1.5R or 2.0R take-profit target.
   - Monitors market clock and forces square-off at **15:10 IST**.
5. **Thread-Safe Architecture**: Runs in a non-blocking daemon thread with full start/stop controls via both CLI and the web dashboard REST API.

---

## Institutional Risk Gates & Safeguards

The platform implements a multi-layer risk hierarchy ensuring capital preservation under all market conditions:

```
[ Incoming Order Proposal ]
             │
             ▼
[ Check 1: Symbol & Tick Validation ] ──► (BSE/NSE symbol format, 0.05 tick rounding)
             │
             ▼
[ Check 2: C1 & C3 Sizing Rejection ] ──► (Per-share risk > ₹1,000 cap? REJECT)
             │
             ▼
[ Check 3: C4 Universal Pre-Trade Gate ]
  ├─ Event Blackout Guard ──────────────► (RBI MPC / Union Budget active? BLOCK)
  ├─ Corporate Action Blackout ─────────► (Earnings results day? BLOCK symbol)
  ├─ Thursday Weekly Expiry Shield ─────► (Time > 13:45 IST on Thursday? BLOCK)
  ├─ India VIX Regime Filter ───────────► (VIX < 11.5 or VIX > 24.0? BLOCK)
  ├─ Correlated Sector Cap ─────────────► (Already traded sector today? BLOCK)
  ├─ Daily Loss Limit Killswitch ───────► (Cumulative risk > ₹3,000? BLOCK)
  ├─ Consecutive Losses Killswitch ─────► (2 consecutive losses today? BLOCK)
  └─ High-Water Mark Profit Lock ───────► (Daily profit floor breached? LOCK CAPITAL)
             │
             ▼
[ Check 4: C5 Mid-Day Parameter Guard ] ─► (Risk limits loosened during 09:00-15:30? REJECT)
             │
             ▼
[ Safe Order Execution / Paper Ticket ]
```

- **Daily Profit High-Water Mark Lock**: If your intraday profit hits ₹2,500, a floor is established at ₹1,500 (60% lock). If profit pulls back to the floor, trading is locked for the remainder of the session. A green day is never allowed to become a red day.
- **Consecutive Losses Killswitch**: Two consecutive losing trades instantly triggers an account freeze to prevent emotional revenge trading.
- **Macro Event Blackouts**: Automatically reads `trader/events.json` to freeze entries 15 minutes before and 30 minutes after major economic announcements (e.g., RBI Interest Rate decisions).
- **One-Key Panic Flatten**: Instantly liquidates all active positions at market price with a single command (`python main.py panic` or web dashboard button).

---

## Statutory SEBI Taxes & Net P&L Engine

Unlike standard international trading software, **Vyapar AI** features a built-in Indian tax engine (`skills/trader-budget/tax_calculator.py` and `skills/trader-broker/journal.py`) that calculates true net take-home returns:

| Charge | Statutory Rate | Applied On |
| :--- | :--- | :--- |
| **Securities Transaction Tax (STT)** | 0.025% | Sell-side turnover (Equities intraday) |
| **Stamp Duty** | 0.003% (₹300 per crore) | Buy-side turnover |
| **Exchange Turnover Charges** | 0.00297% | Total turnover (Buy + Sell) |
| **SEBI Turnover Fee** | 0.0001% (₹10 per crore) | Total turnover |
| **Goods & Services Tax (GST)** | 18.0% | Brokerage + Exchange fees + SEBI charges |
| **Discount Brokerage** | ₹20 per executed order | Fixed rate per order (₹40 round-trip) |
| **Slippage Buffer** | 0.02% | Turnover estimate for market impact |

### Performance Metrics Computed in SQLite Journal
- **Win Rate (%)**: Winning trades / Total closed trades.
- **Profit Factor**: Gross Profits / Gross Losses.
- **Expectancy (₹)**: Average net rupee outcome per executed trade.
- **System Quality Number (SQN)**: Van Tharp's SQN metric assessing system edge.
- **Maximum Drawdown**: Peak-to-trough equity decline in rupees.

---

## Supported Broker Providers

The suite is engineered with a modular broker adapter interface:

```
                              [ Order Dispatcher ]
                                       │
            ┌──────────────────┬───────┴──────────┬──────────────────┐
            ▼                  ▼                  ▼                  ▼
     [ Paper Trading ]     [ Zerodha ]       [ Angel One ]       [ Shoonya ]
       (Built-in Sim)    (KiteConnect API)   (SmartAPI JSON)   (NorenRestApi)
```

1. **Paper Trading (Default)**:
   - Zero financial risk. Simulates executions with accurate slippage, cash balances, and statutory taxes.
   - All positions tracked in `trader/portfolio.json`.
2. **Zerodha Kite Connect**:
   - Generates copy-ready or automated Python KiteConnect v3 order tickets (`variety=kite.VARIETY_REGULAR`, `product=kite.PRODUCT_MIS`, `order_type=kite.ORDER_TYPE_LIMIT`).
3. **Angel One SmartAPI**:
   - Generates SmartConnect JSON payloads with pre-mapped instrument tokens and TOTP authentication.
4. **Shoonya by Finvasia**:
   - Generates NorenRestApi payloads for zero-brokerage intraday execution.
5. **Instant Broker Failover (`skills/trader-broker/failover.py`)**:
   - Switch active broker routing instantly if your primary broker experiences downtime or API latency:
   ```bash
   python skills/trader-broker/failover.py switch --to angel
   python skills/trader-broker/failover.py switch --to zerodha
   python skills/trader-broker/failover.py switch --to paper
   ```

---

## Universal AI Agent Support (All AI Providers)

Every package inside `skills/` is packaged as an **open AI skill** containing a standardized `SKILL.md` specification with YAML frontmatter, capabilities, and command-line execution interfaces. This enables any AI assistant, agent platform, or local LLM to inspect, understand, and invoke trading tools autonomously.

### 1. Anthropic Claude (Claude Code & Claude Desktop)
- **Claude Code CLI**: Simply run `claude` inside the `trading/` directory. Claude automatically discovers all 11 skills, reads `SKILL.md` documentation, and runs analysis or scans when prompted.
- **Claude Desktop MCP Server**: Add the suite to your `claude_desktop_config.json`:
  ```json
  {
    "mcpServers": {
      "indian-trader": {
        "command": "python",
        "args": ["-m", "skills.trader-broker.web_server", "--no-browser"]
      }
    }
  }
  ```

### 2. OpenAI (ChatGPT, GPT-4o, Agents SDK)
Export skills as OpenAI function tools using the standard JSON schema:
```json
{
  "type": "function",
  "function": {
    "name": "scan_orb",
    "description": "Run 15-minute Opening Range Breakout scanner on Indian stocks",
    "parameters": {
      "type": "object",
      "properties": {
        "symbols": { "type": "array", "items": { "type": "string" }, "description": "NSE tickers (e.g. ['RELIANCE.NS'])" }
      }
    }
  }
}
```

### 3. Google Gemini & Antigravity
Native integration with Antigravity and Gemini CLI (`agy`). When operating in Antigravity or prompting Gemini 1.5 Pro / 2.0 Flash, skills are surfaced automatically and executed via standard terminal tool calls.

### 4. Cursor / Windsurf / GitHub Copilot
Add this rule to your `.cursorrules` or workspace prompt:
```markdown
You have access to the Indian Day Trader Suite in ./skills.
- Use `python skills/trader-scanner/cpr.py <symbols>` for CPR & Camarilla pivot analysis.
- Use `python skills/trader-scanner/scan.py orb` for opening range breakout signals.
- Use `python skills/trader-risk/check.py` to validate any proposed orders before execution.
```

### 5. Local & Open-Source LLMs (Ollama, DeepSeek-R1, vLLM)
Local models can interact directly with the platform via:
1. Standard CLI subcommands (`python main.py <command>`).
2. The REST API (`http://127.0.0.1:8765/api/...`) with standard JSON responses.

---

## Interactive Multi-Page Dashboard & REST API

The platform provides an institutional browser-based Command Center powered by vanilla HTML/CSS/JavaScript and local TradingView charts, structured as an 8-page hash-routed Single Page Application (zero external JS frameworks or npm build steps required):

### 8 Dedicated Pages (`#/hash` routing)
1. **`#/trade` (Trading Cockpit)**: Live TradingView Lightweight Chart v4.2.0 with CPR/Camarilla overlays and VWAP, AIC-20 radial conviction gauge, order execution ticket, active positions, timeline ribbon, and autopilot console.
2. **`#/scanner` (Real-Time Scrip Scanner)**: Filterable matrix of 15m ORB breakout candidates and pre-open gap leaders with CPR width, delivery %, AIC-20 score, setup tags, and "Send to Trade" one-click action.
3. **`#/strategies` (20 Strategies Matrix)**: Complete matrix of all 20 intraday strategies showing live signal states (BUY/SELL/NEUTRAL), empirical win rates and trade counts from the SQLite journal (no hardcoded estimates), AIC-20 6-pillar breakdown, and explicit analysis-only badges.
4. **`#/journal` (Trade Journal & Net P&L)**: SQLite trade ledger net of all statutory charges (STT, GST, stamp duty, SEBI turnover, brokerage), interactive cumulative equity curve, drawdown shading, monthly calendar P&L heatmap, and sortable trade table with CSV export.
5. **`#/risk` (Institutional Risk Radar)**: 5 real-time radial gauges (daily loss limit used, profit-lock state, consecutive-loss killswitch counter, sector exposure, and India VIX band) paired with an audit log of every PASS/BLOCK decision and its statutory justification.
6. **`#/backtest` (Walk-Forward & Monte Carlo Engine)**: 15m ORB walk-forward engine and Monte Carlo simulation with in-sample vs out-of-sample equity curves, outcome distribution, and sample size warning banner ($N < 200$).
7. **`#/news` (Market Intelligence & FII/DII)**: NSE market news feed, institutional FII/DII net flows chart (cash segment in ₹ Cr), insider filings ($\ge$ ₹10 Lakhs), and upcoming corporate/macro event calendar.
8. **`#/settings` (Broker Routing & System Safeguards)**: Broker failover heartbeat, watchlist scrip manager, risk parameter controls, webhook test dispatchers, and a modal safeguard requiring typed confirmation (`"I UNDERSTAND LIVE RISKS"`) to prevent accidental live execution.

### Core REST API Endpoints
All endpoints return JSON and are accessible at `http://127.0.0.1:8765`:

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/status` | `GET` | Live market clock (IST), portfolio cash, active holdings, and configuration |
| `/api/quotes?symbols=...` | `GET` | Real-time NSE/BSE quote snapshots (5s TTL cache) |
| `/api/candles?symbol=...&interval=5m` | `GET` | High-fidelity OHLCV bars with VWAP and CPR overlays |
| `/api/strategies/list` | `GET` | Complete library of all 20 intraday strategies |
| `/api/strategies/evaluate?symbol=...` | `GET` | Real-time multi-strategy evaluation & AIC-20 score |
| `/api/strategies/matrix?symbol=...` | `GET` | Live signal state and journal win rates for all 20 strategies |
| `/api/scanner/candidates` | `GET` | Pre-open gap and 15m ORB screening candidates |
| `/api/risk/radar` | `GET` | 5 visual risk gauges and timestamped pre-trade decision audit log |
| `/api/backtest/run?symbol=...` | `GET` | Walk-forward backtest and Monte Carlo simulation metrics |
| `/api/news/feed` | `GET` | Curated NSE market news items |
| `/api/news/fiidii` | `GET` | Institutional FII & DII net cash investment flows |
| `/api/news/insider` | `GET` | SEBI insider trading disclosures ($\ge$ ₹10 Lakhs) |
| `/api/failover/status` | `GET` | Broker heartbeat and primary/secondary routing status |
| `/api/failover/switch` | `POST` | Switch broker routing (requires typed confirmation for live) |
| `/api/trade/place` | `POST` | Paper trade execution with C1/C3/C4 risk validations |
| `/api/trade/exit` | `POST` | Position square-off with SQLite trade journal logging |
| `/api/panic` | `POST` | Emergency liquidation of all active positions |
| `/api/analytics/summary` | `GET` | Win rate, profit factor, SQN, and charges summary |

---

## Automated Unit Verification

The test suite in [`tests/test_indian_market.py`](tests/test_indian_market.py) provides comprehensive regression testing without external dependencies:

```bash
python -m unittest tests/test_indian_market.py
```

### Coverage Highlights (72 Comprehensive Tests)
- **Timezone & Session Calendar**: Bidirectional UTC/IST mapping, 75 five-minute bars per session, boundary time testing (09:14, 09:15, 14:45, 15:10, 15:30), weekend/holiday skipping.
- **API Contracts & UI Shapes**: Shape, empty, and error contract tests for all 18 REST endpoints without live network dependency.
- **Pre-Trade Risk Gates & Safeguards**: Fail-closed gate validation, side-aware risk calculation (longs & shorts), daily loss limit, consecutive loss killswitch, high-water mark profit lock, VIX bounds, and macro blackout days.
- **Position Sizing Property Tests**: 50 randomized iterations proving orders never breach risk caps, capital limits, or tick size constraints.
- **Resilient Data Layer**: Exponential backoff, in-flight request deduplication, HTTP 429 rate limit cooldowns, and timeout fallbacks.
- **Broker Payloads & Order Execution**: Zerodha, Angel One, and Shoonya payload generation, broker-side protective stops, and failover validation.
- **Autopilot Engine**: Daily session rollover, 15:10 IST square-off with actual exit price P&L, thread-safe start/stop, and Windows console UTF-8 safety.

---

## Compliance & Disclaimer

> [!WARNING]
> **Regulatory Disclaimer**: This software is built for educational, quantitative research, and paper-trading simulation purposes. Algorithmic trading and derivative instruments (F&O) in Indian equities involve substantial financial risk. In accordance with SEBI regulations, always test strategies thoroughly in paper-trading mode before deploying real capital. The authors and contributors assume no liability for financial losses incurred through live broker execution.
