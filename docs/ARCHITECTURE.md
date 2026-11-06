# Vyapar AI — Institutional Architecture & System Design Manual

**Version**: 2.0.0  
**Market Calibration**: National Stock Exchange of India (NSE) & Bombay Stock Exchange (BSE)  
**Engineering Invariant**: Python 3 Standard Library only (Zero mandatory pip dependencies)  
**Operating Mode**: Permanent Paper Trading Simulator default  

---

## 1. System Context & Indian Market Microstructure

Vyapar AI is an algorithmic trading, risk gating, and quantitative execution pipeline engineered for the microstructure of the Indian equity market.

```mermaid
graph TD
    subgraph MarketFeeds["Exchange & Market Data Feeds"]
        NSE["NSE India Archive / Pre-Open"]
        YF["Yahoo Finance (^INDIAVIX / Bars)"]
        BSE["BSE Corporate / Price Grid"]
    end

    subgraph DataLayer["Resilient Data & Concurrency Layer"]
        DL["data_layer.py<br/>(In-Flight Deduplication, TTL Cache, Exponential Backoff)"]
        CookieJar["common.py create_nse_session_opener()<br/>(Cookie-Primed Urllib Opener)"]
        StateLock["STATE_LOCK & atomic_write_json()<br/>(Tempfile + os.replace)"]
    end

    subgraph CorePipeline["8-Stage Algorithmic Pipeline"]
        S1["1. trader-scanner<br/>(ORB 15m, Bhavcopy, CPR, Breadth)"]
        S2["2. trader-news & insider<br/>(FII/DII Cash Flow, SEBI PIT)"]
        S3["3. trader-entry<br/>(AIC-20 Confluence Ensemble)"]
        S4["4. trader-exit<br/>(1.5x ATR Trailing, Target, 15:10 IST Flat)"]
        S5["5. trader-timemachine<br/>(10,000-Bar Bootstrap Monte Carlo)"]
        S6["6. trader-budget<br/>(Volatility Sizing, Post-April 2026 Tax Engine)"]
        S7["7. trader-risk<br/>(Fail-Closed Pre-Trade Risk Gate)"]
        S8["8. trader-broker<br/>(Ticket Generator & Paper Execution Engine)"]
    end

    subgraph Storage["Persistent Storage (WAL Mode SQLite)"]
        HistDB[("history.db<br/>5m Bar Cache")]
        JournDB[("journal.db<br/>Trade Ledger & SQN")]
        StateFiles[("JSON State<br/>portfolio.json, broker.json, risk.json")]
    end

    subgraph Presentation["User & Agent Interfaces"]
        CLI["main.py / vyapar CLI"]
        WebUI["127.0.0.1:8765 Web Terminal<br/>(TradingView Lightweight Charts v4.2.0)"]
        Push["Telegram & Discord Push Notifications"]
        Agents["AI Agents (Claude Code, Antigravity, Cursor)"]
    end

    MarketFeeds --> DataLayer
    DataLayer --> CorePipeline
    S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7 --> S8
    S5 <--> HistDB
    S8 <--> JournDB
    S7 & S8 <--> StateFiles
    CorePipeline --> Presentation
```

---

## 2. 8-Stage Algorithmic Execution Pipeline

The 8-stage pipeline executes sequentially. If any stage encounters missing data, unreadable configuration, or risk boundary violations, the ticket fails **CLOSED** and execution is blocked.

```mermaid
flowchart TD
    Start(["Market Session Start (09:15 IST)"]) --> Step1["1. Scanner: Scan Nifty 50 & Liquid Equities"]
    Step1 --> Step2["2. News/Intel: Check FII/DII Net Flow & SEBI PIT Insider Filings"]
    Step2 --> Step3{"3. Entry: AIC-20 Confluence Score >= 80?"}
    
    Step3 -- No --> RejectScore["Reject Setup (Score < 80)"]
    Step3 -- Yes --> Step4["4. Exit Plan: Calculate Dynamic Stop, Target, and 15:10 IST Square-Off"]
    
    Step4 --> Step5["5. TimeMachine: Run Bootstrap Monte Carlo Simulation"]
    Step5 --> Step6["6. Budget: Position Sizing (Max ₹1,000 Risk) & Statutory Tax Deduction"]
    Step6 --> Step7{"7. Risk Gate: Pre-Trade Hard Invariants Check"}
    
    Step7 -- Fail --> RejectRisk["BLOCK Trade (Log Fingerprint to decisions.json)"]
    Step7 -- Pass --> Step8["8. Broker: Format Ticket & Record to Paper Portfolio"]
    
    RejectScore --> EndState(["Standby / Next Bar"])
    RejectRisk --> EndState
    Step8 --> ActivePosition["Active Position Monitored (1.5x ATR Trailing Stop)"]
    ActivePosition --> ExitCheck{"Target, Stop, or 15:10 IST Reached?"}
    ExitCheck -- Yes --> SquareOff["Square Off: Return Locked Margin + Realized Net PnL"]
    SquareOff --> RecordJournal["Record Completed Trade into journal.db (WAL Mode)"]
    RecordJournal --> EndState
```

---

## 3. Web Terminal & Concurrency Architecture

The web dashboard runs on Python's built-in `ThreadingHTTPServer` bound strictly to `127.0.0.1`. All state file writes are atomic and synchronized across threads under `STATE_LOCK`.

```mermaid
graph LR
    subgraph Browser["Client Browser (127.0.0.1:8765)"]
        SPA["5-View SPA Router<br/>(#/cockpit, #/scanner, #/intel, #/timemachine, #/journal)"]
        TVChart["TradingView Lightweight Charts v4.2.0<br/>(Overlays: CPR, Camarilla, Entry, Stop, Target)"]
        CmdPalette["Ctrl+K Command Palette Modal"]
        SSEClient["SSE Stream Consumer (/api/v1/stream)"]
    end

    subgraph HTTPServer["ThreadingHTTPServer (web_server.py)"]
        Router["HTTP Request Dispatcher"]
        CSRF["CSRF & Localhost Origin Guard"]
        ETagEngine["ETag Caching Engine (/api/v1/bootstrap)"]
        SSEEngine["SSE Broadcaster (Clock, VIX, AutoTrader)"]
    end

    subgraph StateManagement["Concurrency & State Synchronization"]
        Lock["common.py STATE_LOCK (threading.RLock)"]
        Atomic["atomic_write_json()<br/>(Tempfile + os.replace)"]
        WAL["SQLite WAL Mode<br/>(journal_mode=WAL, busy_timeout=5000)"]
    end

    SPA --> Router
    CmdPalette --> Router
    SSEClient <--> SSEEngine
    Router --> CSRF
    CSRF --> ETagEngine
    Router --> Lock
    Lock --> Atomic
    Lock --> WAL
```

---

## 4. Multi-Broker Failover State Machine

Vyapar AI maintains permanent Paper Trading as the fail-safe default. Live broker switching requires deliberate multi-stage cryptographic and interactive confirmation.

```mermaid
stateDiagram-v2
    [*] --> PAPER: System Initialization Default

    state PAPER {
        [*] --> SimulatedExecution
        SimulatedExecution --> RealizedPnL: Deduct Statutory Indian Taxes
        RealizedPnL --> ReconcileCash: Return Margin + Net PnL
    }

    PAPER --> ZERODHA: User Switches to Zerodha Kite Connect
    PAPER --> ANGEL_ONE: User Switches to Angel One SmartAPI
    PAPER --> SHOONYA: User Switches to Finvasia Shoonya

    state ZERODHA {
        FormatKitePayload --> GenerateAPISnippet
    }

    state ANGEL_ONE {
        ResolveToken --> FormatSmartAPIPayload
    }

    state SHOONYA {
        FormatShoonyaPayload --> AddProtectiveSL
    }

    ZERODHA --> PAPER: API Error / Token Expiry / Failover Switch
    ANGEL_ONE --> PAPER: 401 Unauthorized / Failover Switch
    SHOONYA --> PAPER: Network Disconnect / Failover Switch
```

---

## 5. Microstructure Calibrations & Compliance Invariants

1. **Exchange Clock & Expiries**:
   - `09:00 - 09:08 IST`: Pre-Open Auction session order collection.
   - `09:15 IST`: NSE opening bell.
   - `09:30 IST`: Earliest allowed intraday entry.
   - `13:45 IST`: Thursday weekly F&O expiry entry cutoff.
   - `14:45 IST`: Daily intraday entry freeze.
   - `15:10 IST`: Compulsory MIS square-off.
   - `15:30 IST`: NSE closing bell.
2. **Indian Statutory Taxation (Finance Act 2026-27)**:
   - **Equity Intraday**: STT 0.025% on sell turnover; Brokerage min(₹20, 0.03%); Stamp Duty 0.003% on buy; Exchange turnover fee 0.00297%; SEBI fee 0.0001%; GST 18% on (Brokerage + Exchange + SEBI).
   - **F&O Futures**: STT 0.05% on sell turnover (Finance Act 2026-27).
   - **F&O Options**: STT 0.15% on sell premium (Finance Act 2026-27).
   - **Statutory Rounding**: All Securities Transaction Tax rounded to the nearest whole rupee (`ROUND_HALF_UP`).
