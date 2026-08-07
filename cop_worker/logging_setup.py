"""Dual-sink logging: terminal (stderr) + timestamped file under logs/."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


def setup_dual_logging(prefix: str = "agent", log_dir: str | Path = "logs") -> Path:
    """Configure root logger to write to stderr AND a timestamped file.

    Call once at process startup before any other logging. Returns the log file path.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{prefix}_{ts}.log"

    fmt = logging.Formatter("[%(asctime)s] [%(name)s] %(levelname)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove any handlers added by a previous basicConfig call
    root.handlers.clear()

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Suppress noisy HTTP libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logging.getLogger(__name__).info("Logging to %s", log_file)
    return log_file
