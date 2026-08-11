"""Match logging: timestamped tee, inbound-wire metadata logging, peer scent diagnostic."""

from __future__ import annotations

import sys
from pathlib import Path

from ref3_match.runtime_cfg import REPO_ROOT


class _TimestampedTee:
    """Mirror a stream to a log file, stamping wall-clock time at each line start.

    Installed over stdout+stderr for a real match so every line — ours, uvicorn's,
    tracebacks — lands in one timestamped file. Deadline disputes (the signed 30s
    response budget, their 180s turn budget) are evidence questions; an unstamped
    console scrollback answers none of them.
    """

    def __init__(self, stream, sink) -> None:
        self._stream = stream
        self._sink = sink
        self._at_line_start = True

    def write(self, text: str) -> int:
        n = self._stream.write(text)
        from datetime import datetime

        for piece in text.splitlines(keepends=True):
            if self._at_line_start and piece.strip():
                self._sink.write(datetime.now().strftime("%H:%M:%S.%f")[:-3] + " ")
            self._sink.write(piece)
            self._at_line_start = piece.endswith("\n")
        self._sink.flush()
        return n

    def flush(self) -> None:
        self._stream.flush()
        self._sink.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _wire_session_class():
    """A ReferenceV3Session that logs INBOUND wire metadata — names/fields, never bodies.

    WARNINGS §2c: a team that logs only its own view cannot log an ABSENCE, and the one
    fact that matters in a stall ("what did you actually receive from us?") becomes
    structurally invisible. Metadata only: keys, step numbers, senders, commit prefixes,
    lock hashes. No smell grids, no hint text, and never a nonce of ours.
    """
    from cop_worker.protocol.reference_v3 import ReferenceV3Session

    class WireLoggingSession(ReferenceV3Session):
        def receive_negotiation(self, message: dict) -> None:
            m = message if isinstance(message, dict) else {}
            print(
                f"[wire<-] negotiate keys={sorted(m)} group={m.get('group_id')!r} "
                f"role={m.get('role')!r} sub_game={m.get('sub_game_number')!r} "
                f"uid={str(m.get('game_uid'))[:13]!r} "
                f"scent={str(m.get('scent_model_sha256'))[:8]} "
                f"wire={str(m.get('wire_shape_sha256'))[:8]}"
            )
            super().receive_negotiation(message)

        def receive_turn(self, message: dict) -> list[dict]:
            m = message if isinstance(message, dict) else {}
            print(
                f"[wire<-] turn step={m.get('step')} sender={m.get('sender')!r} "
                f"commit={str(m.get('commit'))[:8]} ts={str(m.get('timestamp'))[:23]!r} "
                f"cells={len(m.get('smell_grid') or {})} "
                f"barrier={m.get('barrier_placed')} claim={m.get('capture_claim')} "
                f"answer={(m.get('claim_response') or {}).get('caught')} "
                f"win={(m.get('win_claim') or {}).get('type')}"
            )
            return super().receive_turn(message)

        def receive_audit(self, payload: dict) -> None:
            p = payload if isinstance(payload, dict) else {}
            print(
                f"[wire<-] audit sender={p.get('sender')!r} "
                f"records={len(p.get('records') or [])} claim={p.get('result_claim')!r}"
            )
            super().receive_audit(payload)

        def receive_control(self, message: dict) -> None:
            m = message if isinstance(message, dict) else {}
            print(
                f"[wire<-] control kind={m.get('kind')!r} sender={m.get('sender')!r} "
                f"sub_game={m.get('sub_game_number')!r} status={m.get('status')!r}"
            )
            super().receive_control(message)

    return WireLoggingSession


def _install_match_log(opponent: str) -> Path:
    """Tee stdout+stderr into a timestamped per-match log file."""
    out_dir = REPO_ROOT / "reports" / "ref3_matches"
    out_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    path = out_dir / f"match_{opponent}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    sink = open(path, "a", encoding="utf-8")
    sys.stdout = _TimestampedTee(sys.stdout, sink)
    sys.stderr = _TimestampedTee(sys.stderr, sink)
    print(f"[match] logging to {path}")
    return path


_PEER_SCENT_SEEN: dict[int, str] = {}


def _log_peer_scent_model(
    sub_game: int, step: int, smell_grid: dict, ours: str = "multiplicative_book_v1"
) -> None:
    """Print the peer's scent model the first time a frame is decisive, per sub-game.

    Diagnostic only. Early frames are the informative ones: both registered models decay, so
    a late accumulated frame holds intermediate values that belong to neither and classifies
    as ``inconclusive`` rather than guessing.
    """
    if _PEER_SCENT_SEEN.get(sub_game) is not None:
        return
    from cop_worker.protocol.scent_fingerprint import fingerprint

    result = fingerprint(smell_grid)
    model = result["model"]
    if model in ("inconclusive", "empty"):
        return
    _PEER_SCENT_SEEN[sub_game] = model
    if model == ours:
        print(f"[scent] sg{sub_game} step{step}: peer transmits {model} — MATCHES ours")
    else:
        print(
            f"[scent] sg{sub_game} step{step}: *** PEER SCENT MODEL MISMATCH *** "
            f"peer={model} ours={ours} "
            f"(peer cells={result['cells']} max={result['max']} "
            f"distinct={result['distinct']}) — our policy is reading a field at the wrong "
            f"scale; raise this with the opponent before a counted series"
        )
