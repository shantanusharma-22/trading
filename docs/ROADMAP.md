# Vyapar AI — Strategic Engineering Roadmap

**Version**: 2.0.0  
**Planning Horizon**: 2026 – 2027  

---

## Phase 1: Derivatives & Options Risk Analytics (Q1 2027)

Currently, strategies 13–16 (9:20 Short Straddle, Long Strangle, Iron Condor, Expiry Day Gamma Scalping) operate in **Analysis-Only Mode** and are rejected by the equity execution gate.

- **Objective**: Introduce institutional-grade risk models for Indian National Stock Exchange (NSE) equity derivatives.
- **Key Milestones**:
  1. Real-time implied volatility (IV) surface calibration using standard-library Black-Scholes formulas.
  2. Portfolio-level Greeks monitoring (Delta, Gamma, Vega, Theta) with hard delta-neutral limits.
  3. Pre-expiry margin surge calculators complying with SEBI peak margin and physical delivery margin escalation rules.
  4. Options paper-execution simulator supporting multi-leg orders and synthetic spreads under `STATE_LOCK`.

---

## Phase 2: Ultra-Low Latency WebSocket Tick Feeds (Q2 2027)

Currently, market quotes are polled via HTTP endpoints with in-flight deduplication and bounded TTL caching.

- **Objective**: Add optional, persistent WebSocket streaming adapters for Indian brokerage feeds without adding mandatory pip dependencies.
- **Key Milestones**:
  1. Pure standard-library WebSocket client implementation (RFC 6455) for Zerodha Kite Connect WebSocket (`wss://ws.kite.trade`) and Angel One SmartAPI SmartWebSocket.
  2. High-performance ring buffer for sub-millisecond tick ingestion and on-the-fly 5-minute candle aggregation.
  3. Automatic connection failover to HTTP polling if WebSocket connectivity degrades.

---

## Phase 3: Machine Learning & NLP Sentiment Intelligence (Q3 2027)

Currently, news and corporate filings are parsed using RSS feeds, keyword matching, and regex scoring.

- **Objective**: Integrate quantitative natural language processing for Indian corporate disclosures and macroeconomic releases.
- **Key Milestones**:
  1. Offline, lightweight ONNX runtime integration for transformer-based sentiment scoring on BSE/NSE corporate announcements.
  2. Automated RBI MPC monetary policy statement diffing to quantify hawkish/dovish shifts.
  3. Real-time FII/DII block deal classification detecting institutional accumulation vs distribution.

---

## Phase 4: Hardware HSM & Multi-Signature Risk Governance (Q4 2027)

- **Objective**: Enterprise-grade cryptographic security for multi-user or proprietary trading desk deployments.
- **Key Milestones**:
  1. Hardware Security Module (HSM) / FIDO2 token integration for order signing.
  2. Multi-signature consensus requiring two independent risk managers to authorize live broker switching.
  3. Immutable cryptographic audit log replication to off-site append-only storage.
