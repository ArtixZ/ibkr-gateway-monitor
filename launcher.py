"""Start / stop IB Gateway via IBC.

Usage:
    python launcher.py start   # start Gateway
    python launcher.py stop    # stop Gateway
    python launcher.py status  # check if running
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("launcher")

IBC_PATH = Path(os.getenv("IBC_PATH", "~/opt/ibc")).expanduser()
GW_PATH = Path(os.getenv("IB_GATEWAY_PATH", "~/Applications/IB Gateway 10.44")).expanduser()
TRADING_MODE = os.getenv("IBKR_TRADING_MODE", "paper")
API_PORT = int(os.getenv("IBKR_PORT", "4002"))
USERNAME = os.getenv("IBKR_USERNAME", "")
PASSWORD = os.getenv("IBKR_PASSWORD", "")
CONFIG_DIR = Path(__file__).parent
LOG_DIR = CONFIG_DIR / "logs"


def _detect_gw_version() -> str:
    for part in GW_PATH.name.replace("-", " ").replace("_", " ").split():
        try:
            int(part.split(".")[0])
            return part
        except ValueError:
            continue
    return ""


def _write_runtime_config() -> Path:
    template = CONFIG_DIR / "config.ini.template"
    content = template.read_text()
    content = content.replace("IbLoginId=", f"IbLoginId={USERNAME}", 1)
    content = content.replace("IbPassword=", f"IbPassword={PASSWORD}", 1)
    content = content.replace("TradingMode=paper", f"TradingMode={TRADING_MODE}", 1)
    content = content.replace("OverrideTwsApiPort=4002", f"OverrideTwsApiPort={API_PORT}", 1)

    config_path = CONFIG_DIR / "config.ini"
    config_path.write_text(content)
    config_path.chmod(0o600)
    return config_path


def find_gateway_pids() -> list[int]:
    pids: set[int] = set()
    for pattern in ["ibgateway", "IB Gateway", "IBGateway"]:
        try:
            result = subprocess.run(
                ["pgrep", "-fi", pattern],
                capture_output=True, text=True, timeout=5)
            for line in result.stdout.strip().splitlines():
                if line.strip().isdigit():
                    pids.add(int(line.strip()))
        except Exception:
            pass
    pids.discard(os.getpid())
    return sorted(pids)


def stop_gateway() -> None:
    pids = find_gateway_pids()
    if not pids:
        logger.info("No Gateway processes running")
        return
    logger.info("Stopping Gateway PIDs: %s", pids)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(5)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def start_gateway() -> bool:
    if not USERNAME or not PASSWORD:
        logger.error("IBKR_USERNAME and IBKR_PASSWORD must be set in .env")
        return False

    config_path = _write_runtime_config()

    script = IBC_PATH / "scripts" / "ibcstart.sh"
    if not script.exists():
        logger.error("IBC start script not found: %s", script)
        return False

    version = _detect_gw_version()
    if not version:
        logger.error("Could not detect Gateway version from: %s", GW_PATH)
        return False

    LOG_DIR.mkdir(exist_ok=True)

    # Gateway is a Java Swing GUI — needs macOS GUI context to render the
    # login dialog.  Write a launch script and run it via Terminal.app.
    launch_script = CONFIG_DIR / "launch.sh"
    launch_script.write_text(
        f'#!/bin/bash\n'
        f'"{script}" {version} --gateway'
        f' "--ibc-path={IBC_PATH}"'
        f' "--ibc-ini={config_path}"'
        f' "--tws-path={GW_PATH.parent}"'
        f' --mode={TRADING_MODE}\n'
    )
    launch_script.chmod(0o755)

    logger.info("Launching Gateway v%s via Terminal.app", version)

    try:
        subprocess.run(
            ["osascript", "-e",
             f'tell app "Terminal" to do script "{launch_script}"'],
            check=True, capture_output=True, timeout=10,
        )
        return True
    except Exception:
        logger.exception("Failed to launch Gateway")
        return False


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
    )

    parser = argparse.ArgumentParser(description="IB Gateway launcher (via IBC)")
    parser.add_argument("action", choices=["start", "stop", "status"])
    args = parser.parse_args()

    if args.action == "status":
        pids = find_gateway_pids()
        print(f"Gateway running: PIDs {pids}" if pids else "Gateway not running")
        sys.exit(0 if pids else 1)

    if args.action == "stop":
        stop_gateway()

    if args.action == "start":
        stop_gateway()
        if start_gateway():
            logger.info("Gateway launch initiated")
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
