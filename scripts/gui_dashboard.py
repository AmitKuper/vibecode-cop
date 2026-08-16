"""Run the persistent GUI dashboard (history + replays + live panels).

    uv run python scripts/gui_dashboard.py            # http://127.0.0.1:8780
    uv run python scripts/gui_dashboard.py --port N

Keep it running in its own terminal, or detached:
    powershell Start-Process -WindowStyle Hidden uv -ArgumentList \
        'run','python','scripts/gui_dashboard.py'

It only reads artifacts and the live GUIs' public views; it can never affect a
match, so it is safe to leave up permanently.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    import uvicorn

    from cop_worker.gui.dashboard import app

    print(f"dashboard on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
