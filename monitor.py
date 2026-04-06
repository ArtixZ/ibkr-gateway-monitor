"""IBKR Gateway health monitor with automatic restart.

Probes the Gateway API port and restarts via IBC when failures are detected.

Usage:
    python monitor.py          # run monitor loop
    python monitor.py --check  # single health check (exit 0=healthy, 1=down)
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

import launcher

load_dotenv()

CHECK_INTERVAL = 10
FAILURE_THRESHOLD = 3
STARTUP_TIMEOUT = 60
MAX_RESTARTS = 10
COOLDOWN_BASE = 60
COOLDOWN_CAP = 600
HEALTHY_RESET_AFTER = 300

LOG_DIR = Path(__file__).parent / "logs"
HOST = os.getenv("IBKR_HOST", "127.0.0.1")
PORT = int(os.getenv("IBKR_PORT", "4002"))

logger = logging.getLogger("monitor")


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    fmt = "%(asctime)s | %(levelname)-8s | %(message)s"
    fh = TimedRotatingFileHandler(
        LOG_DIR / "monitor.log", when="midnight", backupCount=14, encoding="utf-8")
    fh.setFormatter(logging.Formatter(fmt))
    logging.basicConfig(level=logging.INFO, format=fmt,
                        handlers=[logging.StreamHandler(sys.stdout), fh])


def check_health() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=5):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


class Monitor:
    def __init__(self) -> None:
        self._failures = 0
        self._restarts = 0
        self._last_restart = 0.0
        self._last_healthy = time.time()
        self._running = True

    def _restart(self) -> bool:
        now = time.time()
        cooldown = min(COOLDOWN_BASE * (2 ** min(self._restarts, 4)), COOLDOWN_CAP)
        if self._last_restart and now - self._last_restart < cooldown:
            logger.info("Cooldown: %.0fs remaining", cooldown - (now - self._last_restart))
            return False
        if self._restarts >= MAX_RESTARTS:
            logger.critical("Exhausted %d restart attempts — manual intervention required", MAX_RESTARTS)
            return False

        self._restarts += 1
        self._last_restart = now
        logger.warning("== RESTARTING GATEWAY (%d/%d) ==", self._restarts, MAX_RESTARTS)

        launcher.stop_gateway()
        if not launcher.start_gateway():
            return False

        logger.info("Waiting up to %ds for Gateway...", STARTUP_TIMEOUT)
        for elapsed in range(0, STARTUP_TIMEOUT, 3):
            time.sleep(3)
            if check_health():
                logger.info("Gateway UP after ~%ds", elapsed + 3)
                self._failures = 0
                self._last_healthy = time.time()
                return True

        logger.error("Gateway did not start within %ds", STARTUP_TIMEOUT)
        return False

    def run(self) -> None:
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "_running", False))
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "_running", False))

        logger.info("=" * 50)
        logger.info("IBKR GATEWAY MONITOR — %s:%d", HOST, PORT)
        logger.info("Check every %ds, restart after %d failures", CHECK_INTERVAL, FAILURE_THRESHOLD)
        logger.info("=" * 50)

        while self._running:
            try:
                if check_health():
                    if self._failures > 0:
                        logger.info("Gateway RECOVERED after %d failed checks", self._failures)
                    self._failures = 0
                    self._last_healthy = time.time()
                    if self._restarts and time.time() - self._last_restart > HEALTHY_RESET_AFTER:
                        self._restarts = 0
                else:
                    self._failures += 1
                    logger.warning("Health check FAILED (%d/%d)", self._failures, FAILURE_THRESHOLD)
                    if self._failures >= FAILURE_THRESHOLD:
                        self._restart()
            except Exception:
                logger.exception("Error in monitor loop")

            time.sleep(CHECK_INTERVAL)

        logger.info("Monitor stopped")


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="IBKR Gateway health monitor")
    parser.add_argument("--check", action="store_true", help="Single health check")
    args = parser.parse_args()

    if args.check:
        ok = check_health()
        logger.info("%s:%d — %s", HOST, PORT, "HEALTHY" if ok else "DOWN")
        sys.exit(0 if ok else 1)

    Monitor().run()


if __name__ == "__main__":
    main()
