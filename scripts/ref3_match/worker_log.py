"""Per-worker log file: evidence that survives a dead stderr pump.

Bench finding (peersim, 2026-08-13): each role worker's pumped [tw]/[pw] stream
can die after the first inbound wire turn, leaving the match log blind for the
rest of the series — exactly what made the live najamjad forensics hard. The
worker therefore tees everything it prints into its OWN file as well; the pump
remains the live view, the file is the record.
"""

from __future__ import annotations

import contextlib
import sys
from datetime import datetime

from ref3_match.runtime_cfg import REPO_ROOT


class _Tee:
    """Write-through to several streams; one failing sink never silences the rest."""

    def __init__(self, *streams) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for stream in self._streams:
            try:
                stream.write(data)
                stream.flush()
            except Exception:
                pass
        return len(data)

    def flush(self) -> None:
        for stream in self._streams:
            with contextlib.suppress(Exception):
                stream.flush()

    def isatty(self) -> bool:  # uvicorn's formatter probes this for color detection
        return False

    def fileno(self) -> int:
        return self._streams[0].fileno()

    @property
    def encoding(self) -> str:
        return getattr(self._streams[0], "encoding", "utf-8")


def install_worker_log(role: str) -> str:
    """Tee this worker's PRINT stream (sys.stdout) into stderr + its own file.

    Only sys.stdout is wrapped: our own [match]/[wire<-] prints are the evidence
    that must survive; sys.stderr stays the real stream so uvicorn's logging
    machinery (which probes stream attributes at startup) is untouched.
    """
    out_dir = REPO_ROOT / "reports" / "ref3_matches"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"worker_{role}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    handle = open(path, "a", encoding="utf-8", errors="replace")  # noqa: SIM115 (lifetime = process)
    sys.stdout = _Tee(sys.__stderr__, handle)
    return str(path)
