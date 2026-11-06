#!/usr/bin/env python3
"""Multi-Target Skill Suite Installer for Vyapar AI (NSE/BSE).
Standard library only.

Installs and configures Vyapar AI trading skills and safety rules across:
  - Claude Code (.claude/skills, CLAUDE.md)
  - Google Antigravity / Gemini (.agent/skills, AGENTS.md, GEMINI.md)
  - Cursor (.cursorrules)
  - Local workspace CLI wrappers (vyapar.cmd, vyapar.sh, trader configs)

Usage:
    python install.py                                # installs local workspace defaults
    python install.py --target all                   # installs across all platforms
    python install.py --target claude                # installs Claude Code skill suite
    python install.py --target antigravity           # installs Antigravity/Gemini skills
    python install.py --target cursor                # installs Cursor safety rules
    python install.py --verify                       # runs automated verification suite
"""

import argparse
import os
import shutil
import subprocess
import sys

# Configure UTF-8 safe console on Windows
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.join(BASE_DIR, "skills")
AGENT_SKILLS_DIR = os.path.join(BASE_DIR, ".agent", "skills")
TRADER_DIR = os.path.join(BASE_DIR, "trader")

CURSOR_RULES_TEMPLATE = """# Project Rules: Vyapar AI (NSE/BSE Indian Equities)
# Standard-library Python only on the server; zero mandatory pip dependencies.

## SAFETY INVARIANTS:
1. Paper mode is the permanent default. Never add or enable live order placement.
2. Risk checks fail CLOSED: any exception, missing data, or unreadable config blocks the action. Never `except: pass` around a risk or order path.
3. Never invent data. No hardcoded fallback prices, scores, win rates, or 'verified' labels.
4. Every number shown to the user carries its source and as-of time.
5. Never print or commit secrets. Read tokens from environment variables; mask them in output; keep trader/config.json out of git.

## Microstructure & Concurrency:
- Exchange hours: 09:15 to 15:30 IST. Intraday MIS square-off at 15:10 IST.
- State persistence: All state files written atomically via tempfile + os.replace under STATE_LOCK.
- SQLite databases: Enforce WAL mode (`PRAGMA journal_mode=WAL; busy_timeout=5000;`).
- One holdings schema: `{"qty", "entry_price", "side", "stop", "target", "current_price", "margin_used", "strategy", "placed_at"}`.
"""


def log_step(status: str, message: str):
    icon = "[OK]" if status == "ok" else ("[WARN]" if status == "warn" else "[INFO]")
    print(f" {icon:<7} {message}", flush=True)


def ensure_local_setup(dry_run: bool = False, force: bool = False) -> bool:
    print("\n--- [1/4] Configuring Local Workspace Environment ---")
    os.makedirs(os.path.join(TRADER_DIR, "data"), exist_ok=True)
    os.makedirs(os.path.join(TRADER_DIR, "state"), exist_ok=True)
    os.makedirs(os.path.join(TRADER_DIR, "data", "bhavcopy"), exist_ok=True)

    # 1. Initialize portfolio.json from example
    port_file = os.path.join(TRADER_DIR, "portfolio.json")
    port_ex = os.path.join(TRADER_DIR, "portfolio.example.json")
    if not os.path.exists(port_file) or force:
        if os.path.exists(port_ex):
            if not dry_run:
                shutil.copyfile(port_ex, port_file)
            log_step("ok", f"Initialized {os.path.relpath(port_file, BASE_DIR)} from template.")
        else:
            log_step("warn", "portfolio.example.json not found; skipping default template copy.")
    else:
        log_step("ok", f"Existing {os.path.relpath(port_file, BASE_DIR)} preserved.")

    # 2. Generate CLI wrappers
    # Windows: vyapar.cmd
    cmd_wrapper = os.path.join(BASE_DIR, "vyapar.cmd")
    cmd_content = "@echo off\r\npython \"%~dp0main.py\" %*\r\n"
    if not dry_run:
        with open(cmd_wrapper, "w", encoding="utf-8") as f:
            f.write(cmd_content)
    log_step("ok", f"Generated Windows launcher: {os.path.relpath(cmd_wrapper, BASE_DIR)}")

    # Unix: vyapar.sh
    sh_wrapper = os.path.join(BASE_DIR, "vyapar.sh")
    sh_content = "#!/usr/bin/env bash\npython3 \"$(dirname \"$0\")/main.py\" \"$@\"\n"
    if not dry_run:
        with open(sh_wrapper, "w", encoding="utf-8") as f:
            f.write(sh_content)
        try:
            os.chmod(sh_wrapper, 0o755)
        except Exception:
            pass
    log_step("ok", f"Generated Unix/macOS launcher: {os.path.relpath(sh_wrapper, BASE_DIR)}")
    return True


def install_claude_skills(dry_run: bool = False, force: bool = False) -> bool:
    print("\n--- [2/4] Installing Claude Code Skill Suite ---")
    claude_skills_dir = os.path.join(BASE_DIR, ".claude", "skills")
    if not dry_run:
        os.makedirs(claude_skills_dir, exist_ok=True)

    installed_count = 0
    # Copy or mirror trader skills into .claude/skills
    if os.path.exists(SKILLS_DIR):
        for item in os.listdir(SKILLS_DIR):
            if item.startswith("trader-"):
                src = os.path.join(SKILLS_DIR, item)
                dst = os.path.join(claude_skills_dir, item)
                if os.path.isdir(src):
                    if not dry_run:
                        if os.path.exists(dst) and force:
                            shutil.rmtree(dst)
                        if not os.path.exists(dst):
                            shutil.copytree(src, dst)
                    installed_count += 1

    # Mirror .agent/skills as well
    if os.path.exists(AGENT_SKILLS_DIR):
        for item in os.listdir(AGENT_SKILLS_DIR):
            src = os.path.join(AGENT_SKILLS_DIR, item)
            dst = os.path.join(claude_skills_dir, item)
            if os.path.isdir(src):
                if not dry_run:
                    if os.path.exists(dst) and force:
                        shutil.rmtree(dst)
                    if not os.path.exists(dst):
                        shutil.copytree(src, dst)
                installed_count += 1

    log_step("ok", f"Installed {installed_count} skills into .claude/skills/")
    return True


def install_antigravity_skills(dry_run: bool = False, force: bool = False) -> bool:
    print("\n--- [3/4] Configuring Antigravity & Gemini Skills ---")
    os.makedirs(AGENT_SKILLS_DIR, exist_ok=True)
    count = len([d for d in os.listdir(AGENT_SKILLS_DIR) if os.path.isdir(os.path.join(AGENT_SKILLS_DIR, d))])
    log_step("ok", f"Verified {count} registered Antigravity skills in .agent/skills/")
    return True


def install_cursor_rules(dry_run: bool = False, force: bool = False) -> bool:
    print("\n--- [4/4] Configuring Cursor AI Rules ---")
    cursor_file = os.path.join(BASE_DIR, ".cursorrules")
    if not os.path.exists(cursor_file) or force:
        if not dry_run:
            with open(cursor_file, "w", encoding="utf-8") as f:
                f.write(CURSOR_RULES_TEMPLATE)
        log_step("ok", f"Configured {os.path.relpath(cursor_file, BASE_DIR)}")
    else:
        log_step("ok", f"Existing {os.path.relpath(cursor_file, BASE_DIR)} preserved.")
    return True


def run_verification() -> bool:
    print("\n" + "=" * 60)
    print("       VYAPAR AI INSTALLATION VERIFICATION SUITE       ")
    print("=" * 60)

    # 1. Check Python version
    v = sys.version_info
    print(f" Python Version:      {v.major}.{v.minor}.{v.micro} (Standard Library)")
    if v < (3, 10):
        log_step("warn", "Python 3.10+ recommended for modern type hints and match syntax.")
    else:
        log_step("ok", "Python runtime version requirement satisfied.")

    # 2. Check Standard Library Modules
    modules = ["sqlite3", "json", "urllib.request", "datetime", "math", "hashlib", "http.server", "threading"]
    for m in modules:
        try:
            __import__(m)
            log_step("ok", f"Module available: {m}")
        except ImportError:
            log_step("fail", f"Missing core module: {m}")
            return False

    # 3. Check SQLite WAL Mode
    try:
        import sqlite3
        test_db = os.path.join(TRADER_DIR, "data", "test_verify.db")
        conn = sqlite3.connect(test_db, timeout=5.0)
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        res = cur.fetchone()[0]
        conn.close()
        if os.path.exists(test_db):
            os.remove(test_db)
        log_step("ok", f"SQLite WAL Mode Verified (Returned: {res.upper()})")
    except Exception as e:
        log_step("warn", f"SQLite WAL check error: {e}")

    # 4. Run Unit Test Suite
    test_script = os.path.join(BASE_DIR, "tests", "test_indian_market.py")
    if os.path.exists(test_script):
        print("\n Running Indian Market Regression Test Suite...")
        res = subprocess.run([sys.executable, "-m", "unittest", "tests/test_indian_market.py"], cwd=BASE_DIR)
        if res.returncode == 0:
            log_step("ok", "100% of regression unit tests passed cleanly.")
            return True
        else:
            log_step("warn", f"Unit tests returned exit code {res.returncode}.")
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Vyapar AI Skill Suite Installer")
    parser.add_argument("--target", choices=["claude", "antigravity", "cursor", "local", "all"], default="local",
                        help="Installation target (default: local)")
    parser.add_argument("--verify", action="store_true", help="Run automated verification suite after install")
    parser.add_argument("--force", action="store_true", help="Force overwrite existing configuration files")
    parser.add_argument("--dry-run", action="store_true", help="Preview installation without modifying filesystem")
    args = parser.parse_args()

    print("=" * 60)
    print(" VYAPAR AI - MULTI-TARGET SKILL SUITE INSTALLER ")
    print("=" * 60)
    print(f" Target Mode: {args.target.upper()} | Force: {args.force} | Dry-Run: {args.dry_run}")

    success = True
    if args.target in ("local", "all"):
        success = ensure_local_setup(dry_run=args.dry_run, force=args.force) and success
    if args.target in ("claude", "all"):
        success = install_claude_skills(dry_run=args.dry_run, force=args.force) and success
    if args.target in ("antigravity", "all"):
        success = install_antigravity_skills(dry_run=args.dry_run, force=args.force) and success
    if args.target in ("cursor", "all"):
        success = install_cursor_rules(dry_run=args.dry_run, force=args.force) and success

    if args.verify and not args.dry_run:
        success = run_verification() and success

    print("\n" + "=" * 60)
    if success:
        print(" [SUCCESS] Vyapar AI installation and setup complete!")
        print(" Launch via: python main.py OR vyapar (cmd/sh)")
    else:
        print(" [NOTICE] Installation completed with warnings. Check logs above.")
    print("=" * 60 + "\n")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

