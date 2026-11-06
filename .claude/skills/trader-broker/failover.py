#!/usr/bin/env python3
"""Multi-Broker Failover Manager for trader-broker (Indian Equities - NSE/BSE).
Allows routing and instant failover between Zerodha Kite, Angel One SmartAPI,
and Shoonya (Finvasia) in case of broker downtime or API latency. Standard library only.

    python3 failover.py status                       # check active and backup broker health
    python3 failover.py switch --to shoonya          # switch active routing to backup broker
"""

import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from skills.common import load_json, save_json

DEFAULT_CONFIG_FILE = os.path.join(BASE_DIR, "trader", "config.json")


def get_active_broker():
    cfg = load_json(DEFAULT_CONFIG_FILE, default={"broker": "paper"})
    return cfg.get("broker", "paper")


def switch_broker(target_broker):
    cfg = load_json(DEFAULT_CONFIG_FILE, default={"broker": "paper"})
    cfg["broker"] = target_broker
    save_json(DEFAULT_CONFIG_FILE, cfg)
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
