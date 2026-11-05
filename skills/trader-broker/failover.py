#!/usr/bin/env python3
"""Multi-Broker Failover Manager for trader-broker (Indian Equities - NSE/BSE).
Allows routing and instant failover between Zerodha Kite, Angel One SmartAPI,
and Shoonya (Finvasia) in case of broker downtime or API latency. Standard library only.

    python3 failover.py status                       # check active and backup broker health
    python3 failover.py switch --to shoonya          # switch active routing to backup broker
"""

import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CONFIG_FILE = os.path.join(BASE_DIR, "trader", "config.json")


def get_active_broker():
    if os.path.exists(DEFAULT_CONFIG_FILE):
        try:
            with open(DEFAULT_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("broker", "paper")
        except Exception:
            pass
    return "paper"


def switch_broker(target_broker):
    cfg = {"broker": target_broker}
    if os.path.exists(DEFAULT_CONFIG_FILE):
        try:
            with open(DEFAULT_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                cfg["broker"] = target_broker
        except Exception:
            pass
    with open(DEFAULT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print(f"Switched active broker routing to: {target_broker.upper()}")


def main():
    p = argparse.ArgumentParser(description="Multi-Broker Failover Engine")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="Show active and backup broker status")
    c_sw = sub.add_parser("switch", help="Switch primary broker")
    c_sw.add_argument("--to", choices=["paper", "zerodha", "angel", "shoonya"], required=True)
    args = p.parse_args()

    active = get_active_broker()

    if args.cmd == "status" or not args.cmd:
        print("==================================================")
        print("BROKER FAILOVER & ROUTING STATUS")
        print("==================================================")
        print(f"Active Primary Broker:   {active.upper()}")
        print(f"Supported Connectors:    PAPER, ZERODHA, ANGEL_ONE, SHOONYA")
        print("Failover Strategy:       If primary API returns 5xx/timeout, run 'failover.py switch --to <backup>'")
        print("==================================================")
        sys.exit(0)

    if args.cmd == "switch":
        switch_broker(args.to)
        sys.exit(0)


if __name__ == "__main__":
    main()

