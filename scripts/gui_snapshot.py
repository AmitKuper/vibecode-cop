"""Screenshot every GUI surface for visual review.

    uv run python scripts/gui_snapshot.py                 # all views
    uv run python scripts/gui_snapshot.py hub play        # a subset

Writes PNGs to reports/gui_review/ (gitignored run scratch). Requires the
dashboard on :8780 (starts nothing itself - fail loud, not magic). Handles
Edge's asynchronous file write by polling for a stable file size.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = "http://127.0.0.1:8780"
OUT = Path(__file__).resolve().parents[1] / "reports" / "gui_review"

#: name -> (url, window WxH). One entry per distinct visual state worth reviewing.
VIEWS = {
    "hub_status": (f"{BASE}/#status", "1280,800"),
    "hub_history": (f"{BASE}/#history", "1280,950"),
    "hub_replay_tab": (f"{BASE}/#replay", "1280,950"),
    "hub_settings": (f"{BASE}/#settings", "1280,800"),
    "replay_step0": (f"{BASE}/replay?log=log_nis-yar1-vs-vibecode_g02.json", "1150,1000"),
    "replay_midgame": (f"{BASE}/replay?log=log_nis-yar1-vs-vibecode_g02.json&i=20", "1150,1000"),
    "replay_empty": (f"{BASE}/replay", "1150,700"),
    "play_setup": (f"{BASE}/play", "1150,900"),
    "live_cop": ("http://127.0.0.1:8781/", "1150,850"),
    "live_thief": ("http://127.0.0.1:8782/", "1150,850"),
}


def shoot(name: str, url: str, size: str) -> bool:
    target = OUT / f"{name}.png"
    target.unlink(missing_ok=True)
    subprocess.run(
        [
            EDGE,
            "--headless",
            "--disable-gpu",
            f"--window-size={size}",
            "--virtual-time-budget=6000",
            f"--screenshot={target}",
            url,
        ],
        capture_output=True,
        timeout=60,
    )
    last = -1
    for _ in range(20):  # Edge flushes the PNG asynchronously
        time.sleep(0.5)
        if target.exists():
            now = target.stat().st_size
            if now == last and now > 0:
                return True
            last = now
    return target.exists() and target.stat().st_size > 0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = sys.argv[1:] or list(VIEWS)
    ok = fail = 0
    for name in wanted:
        matches = [v for v in VIEWS if v == name or v.startswith(name)]
        for view in matches or [name]:
            if view not in VIEWS:
                print(f"SKIP  unknown view {view!r}")
                continue
            url, size = VIEWS[view]
            if shoot(view, url, size):
                print(f"OK    {view}.png")
                ok += 1
            else:
                print(f"FAIL  {view} ({url}) - server down or page broke")
                fail += 1
    print(f"\n{ok} captured, {fail} failed -> {OUT}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
