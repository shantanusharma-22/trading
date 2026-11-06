# Vyapar AI — Developer & Operator Setup Manual

**Release**: v2.0.0  
**Target Architecture**: Zero-Dependency Python 3.10+ (Standard Library)  
**Supported Platforms**: Windows (PowerShell / CMD), macOS (zsh / bash), Linux (bash)  

---

## 1. Prerequisites

Vyapar AI requires **zero pip packages**. You only need Python 3.10 or higher installed on your system.

```bash
# Verify Python version
python --version   # Output should be Python 3.10.x or higher
```

Core built-in libraries utilized:
- `sqlite3`: Concurrency-hardened local bar cache and trade journal (WAL mode).
- `urllib.request`: Resilient market data HTTP client with cookie jar session priming.
- `json`: Atomic configuration, portfolio, and state persistence.
- `http.server`: Built-in multithreaded web server (`ThreadingHTTPServer`).
- `datetime`: Microsecond-precision Indian Standard Time (IST / Asia/Kolkata) clock.
- `threading`: Background auto-trader scanner and in-flight request deduplication locks.
- `math` & `hashlib`: Algorithmic indicators, statistical simulations, and SHA-256 fingerprints.

---

## 2. Multi-Target Skill Suite Installation (`install.py`)

Vyapar AI includes a dedicated multi-target installer that configures workspace files, AI agent skills, and launcher shortcuts.

### Option A: Complete Multi-Platform Installation (Recommended)
```bash
python install.py --target all --verify
```
This automatically:
1. Configures local workspace state directories (`trader/data`, `trader/state`, `trader/data/bhavcopy`).
2. Generates `vyapar.cmd` (Windows) and `vyapar.sh` (Unix/macOS) launcher wrappers.
3. Copies `trader/portfolio.example.json` to `trader/portfolio.json`.
4. Installs 20 skills into `.claude/skills/` for Claude Code.
5. Verifies 9 registered skills in `.agent/skills/` for Google Antigravity / Gemini.
6. Configures `.cursorrules` with institutional safety and microstructure rules for Cursor.
7. Executes the automated regression test suite (`tests/test_indian_market.py`) to verify the installation.

### Option B: Local Workspace Only
```bash
python install.py --target local --verify
```

### Option C: Specific Agent Target
```bash
python install.py --target claude        # For Anthropic Claude Code
python install.py --target antigravity   # For Google Antigravity / Gemini
python install.py --target cursor        # For Cursor AI Editor
```

---

## 3. Configuration & Secrets Management

Configuration is stored in `trader/config.json`. 

### Safe Credentials Handling
In compliance with Project Rule 5, never store plaintext API keys or bot tokens in `trader/config.json`. Configure them as environment variables instead:

```bash
# Windows (PowerShell)
$env:TELEGRAM_BOT_TOKEN = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
$env:TELEGRAM_CHAT_ID = "987654321"
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."

# Linux / macOS (Bash / Zsh)
export TELEGRAM_BOT_TOKEN="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
export TELEGRAM_CHAT_ID="987654321"
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

### Risk Boundaries Configuration (`trader/config.json`)
```json
{
  "broker": "paper",
  "budget": 100000.0,
  "max_order_inr": 50000.0,
  "min_order_inr": 1000.0,
  "max_loss_per_trade_inr": 1000.0,
  "max_daily_loss_inr": 3000.0,
  "max_trades_per_day": 3,
  "max_consecutive_losses": 2,
  "profit_lock_trigger_inr": 2500.0,
  "profit_lock_floor_inr": 1500.0,
  "watchlist": [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "TATAMOTORS.NS"
  ]
}
```

---

## 4. Running Vyapar AI

### Master CLI Console
```bash
# Via launcher wrapper
vyapar           # On Windows
./vyapar.sh      # On Unix/macOS

# Or directly via Python
python main.py
```

### Command-Line Subcommands
```bash
# Check live portfolio, budget, and market clock
python main.py status

# Calculate CPR & Camarilla pivot levels for watchlist
python main.py pivots

# Check morning pre-open auction (09:08 AM IST)
python main.py preopen

# Run 15-minute Opening Range Breakout scanner
python main.py scan

# Launch interactive Web Dashboard (127.0.0.1:8765)
python main.py ui

# Emergency PANIC square-off (market exit all positions to 100% cash)
python main.py panic

# View Trade Performance Journal & SQN analytics
python main.py journal

# Run regression test suite
python main.py test
```

---

## 5. Web Terminal Navigation & Hotkeys

The Web Dashboard runs on `http://127.0.0.1:8765` featuring TradingView Lightweight Charts, live order execution, and real-time risk gauges.

### Keyboard Shortcuts
- `Ctrl + K`: Open Institutional Command Palette (Search symbols, switch views, trigger actions).
- `Alt + 1`: Trading Cockpit (`#/cockpit`)
- `Alt + 2`: 15m ORB & Gap Scanner (`#/scanner`)
- `Alt + 3`: Strategies Matrix (`#/strategies`)
- `Alt + 4`: Trade Journal & SQN Analytics (`#/journal`)
- `Alt + 5`: Risk Radar & Decisions Audit Log (`#/risk`)
- `Alt + 6`: TimeMachine Backtest Engine (`#/timemachine`)
- `Alt + 7`: Institutional News & FII Flows (`#/intel`)
- `Alt + 8`: Broker & System Settings (`#/settings`)
- `Ctrl + B`: Toggle collapsible desktop sidebar
- `Shift + P`: Immediate Panic Flatten Modal
- `Escape`: Close active modal or command palette

---

## 6. Verification & Smoke Testing

To ensure all systems are operating cleanly, execute the automated verification test suite:

```bash
python -m unittest tests/test_indian_market.py
```
Expected output:
```text
Ran 76 tests in ~5-15s
OK
```
