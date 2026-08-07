"""Worker lifecycle management — start, stop, ping cop/thief workers."""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path  # noqa: F401 — kept for caller convenience imports

logger = logging.getLogger(__name__)

PING_TIMEOUT = 5.0
STARTUP_WAIT = 30.0
PING_INTERVAL = 1.0


class WorkerStartupError(Exception):
    """Raised when a worker fails to start within the timeout."""


class WorkerLifecycle:
    """Manages cop_worker and thief_worker subprocess lifecycle.

    Responsible for starting, pinging, and stopping worker processes.
    Workers are started on-demand if not already running.
    """

    def __init__(
        self,
        cop_url: str = "http://localhost:8001",
        thief_url: str = "http://localhost:8002",
        cop_cmd: list[str] | None = None,
        thief_cmd: list[str] | None = None,
    ) -> None:
        """Initialise lifecycle manager with worker URLs and optional start commands."""
        self._cop_url = cop_url
        self._thief_url = thief_url
        self._cop_cmd = cop_cmd or ["python", "-m", "cop_worker", "--port", "8001"]
        self._thief_cmd = thief_cmd or ["python", "-m", "thief_worker", "--port", "8002"]
        self._cop_proc: subprocess.Popen | None = None
        self._thief_proc: subprocess.Popen | None = None

    def is_alive(self, role: str) -> bool:
        """Check if the given worker is responding.

        Args:
            role: 'cop' or 'thief'.

        Returns:
            True if the worker responds to a ping.
        """
        url = self._cop_url if role == "cop" else self._thief_url
        try:
            import urllib.request

            urllib.request.urlopen(f"{url}/health", timeout=PING_TIMEOUT)
            return True
        except Exception:
            return False

    def ensure_ready(self, timeout: float = STARTUP_WAIT) -> None:
        """Ensure both workers are alive, starting them if needed.

        Args:
            timeout: Max seconds to wait for workers to become ready.

        Raises:
            WorkerStartupError: If any worker fails to start within timeout.
        """
        for role in ("cop", "thief"):
            if not self.is_alive(role):
                self._start_worker(role)
                self._wait_for_worker(role, timeout)

    def stop_all(self) -> None:
        """Stop both worker processes if they were started by this manager."""
        for proc, name in ((self._cop_proc, "cop"), (self._thief_proc, "thief")):
            if proc is not None:
                proc.terminate()
                logger.info("%s worker stopped", name)

    def _start_worker(self, role: str) -> None:
        """Launch the worker subprocess for the given role."""
        cmd = self._cop_cmd if role == "cop" else self._thief_cmd
        logger.info("Starting %s worker: %s", role, " ".join(cmd))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if role == "cop":
            self._cop_proc = proc
        else:
            self._thief_proc = proc

    def _wait_for_worker(self, role: str, timeout: float) -> None:
        """Poll the worker until it responds or timeout expires."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_alive(role):
                return
            time.sleep(PING_INTERVAL)
        raise WorkerStartupError(f"{role} worker did not start within {timeout}s")
