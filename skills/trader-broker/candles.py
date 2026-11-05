#!/usr/bin/env python3
"""Redirect shim for candles module."""
import os
import sys

_skills_scanner = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trader-scanner")
if _skills_scanner not in sys.path:
    sys.path.insert(0, _skills_scanner)

from candles import *

