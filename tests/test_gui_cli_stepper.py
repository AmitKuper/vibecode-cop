"""The CLI replay stepper's actual loop (n / p / j / q) against a synthetic log.

Split from test_gui_routes_and_stepping.py (150-line rule).
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cop_worker.protocol.reference_v3.hashing import reference_commit  # noqa: E402


def _write_synthetic_log(tmp_path: Path) -> Path:
    records = []
    for step in (1, 2, 3):
        payload = {
            "step": step,
            "role": "thief",
            "sub_game": 1,
            "position": [3, 3],
            "move": "N",
            "intent": "truth",
        }
        nonce = f"nonce{step:02d}"
        records.append(
            {"payload": payload, "nonce": nonce, "commit": reference_commit(payload, nonce)}
        )
    log = tmp_path / "log_synthetic_g01.json"
    log.write_text(json.dumps({"records": records, "opponent_records": []}), encoding="utf-8")
    return log


def test_cli_stepper_moves_next_prev_jump(tmp_path, monkeypatch):
    from replay_stepper import interactive

    log = _write_synthetic_log(tmp_path)
    keys = iter(["n", "n", "p", "j 1", "q"])
    monkeypatch.setattr("builtins.input", lambda *_: next(keys))
    out = io.StringIO()
    with redirect_stdout(out):
        code = interactive(str(log))
    text = out.getvalue()
    # forward, forward, back, jump: every position was rendered
    for pos in ("timeline 1/3", "timeline 2/3", "timeline 3/3"):
        assert pos in text, pos
    assert text.count("timeline 2/3") >= 2, "prev must re-render position 2"
    assert "final verdict: Verified OK" in text
    assert code == 0


def test_cli_stepper_clamps_at_both_ends(tmp_path, monkeypatch):
    from replay_stepper import interactive

    log = _write_synthetic_log(tmp_path)
    keys = iter(["p", "n", "n", "n", "q"])  # p at start, n past the end
    monkeypatch.setattr("builtins.input", lambda *_: next(keys))
    out = io.StringIO()
    with redirect_stdout(out):
        interactive(str(log))
    text = out.getvalue()
    assert "timeline 0/3" not in text, "prev at the start must clamp, not underflow"
    assert "timeline 4/3" not in text, "next at the end must clamp, not overflow"
