#!/usr/bin/env python3
"""Reference-v3 match orchestrator with the REAL trained RL policy (never random).

Drives our side of a reference-v3 series against a peer: negotiate per sub-game,
thief-first sealed turns, mutual audit. Moves come from the trained RecurrentA2C-GRU
policy (load_counted_policy + select_action) — NOT random. Scent transmitted on the
wire is the byte-exact field of the LOCKED model (book or chebyshev).

Validation entry point:
    cd vibecode-cop
    python scripts/live_match_ref3.py --self-test          # vs local sparring peer
    python scripts/live_match_ref3.py --self-test --role thief

Real match:
    python scripts/live_match_ref3.py --match --config <opponent-profile>

This file is the single entry point and public FACADE: the SDK spawns it by
filename and tests import through it. The implementation lives in the
``ref3_match`` package (one concern per module, ≤150 lines each):

    runtime_cfg     paths, deltas, applied runtime.toml (_t), _git_head
    mover(_mixin)   RLMover — trained policy + board state (scent, barriers, rules)
    wire            [x,y] <-> [row,col] conversion, caught=true corroboration
    match_log       timestamped tee, inbound-wire logging, peer scent diagnostic
    net             port checks, inbox polling, NoGameHappenedError, endpoint await
    subgame_*       handshake -> turn loop (call-site pins live there) -> settlement
    servers/series  our endpoints, gateway caller, index-hold series loop
    selftest        the sparring-peer harness
    artifacts_io    league artifact emission; report_guard: settlement guard + email
    cli(_config)    argument parsing, profile resolution, dispatch
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_REPO_ROOT), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ref3_match.artifacts_io import _save_opponent_profile, _write_result
from ref3_match.cli import main
from ref3_match.match_log import (
    _install_match_log,
    _log_peer_scent_model,
    _TimestampedTee,
    _wire_session_class,
)
from ref3_match.mover import RLMover
from ref3_match.net import (
    NoGameHappenedError,
    _await_endpoint,
    _check_port,
    _latest_turn,
    _poll_agreement,
    _poll_deque,
    _poll_turn,
    _wait_port,
)
from ref3_match.report_guard import _emit_artifacts
from ref3_match.runtime_cfg import (
    _PLACE_DELTAS,
    KIT_ROOT,
    REPO_ROOT,
    _git_head,
    _t,
    apply_runtime_config,
)
from ref3_match.selftest import _self_test
from ref3_match.series import _play_match
from ref3_match.servers import _dial_and_play, _gateway_caller, _start_servers
from ref3_match.subgame import _play_subgame
from ref3_match.subgame_moves import (
    _absorb_inbound_caught,
    _compose_and_send_turn,
    _prep_claim_answer,
    _send_done_control,
)
from ref3_match.subgame_settle import _refine_disputed_trail, _settle
from ref3_match.subgame_setup import _handshake
from ref3_match.subgame_turns import _run_turns
from ref3_match.wire import _corroborate_caught, _from_wire_cell, _to_wire_cell

__all__ = [
    "KIT_ROOT",
    "NoGameHappenedError",
    "REPO_ROOT",
    "RLMover",
    "_PLACE_DELTAS",
    "_TimestampedTee",
    "_absorb_inbound_caught",
    "_await_endpoint",
    "_check_port",
    "_compose_and_send_turn",
    "_corroborate_caught",
    "_dial_and_play",
    "_emit_artifacts",
    "_from_wire_cell",
    "_gateway_caller",
    "_git_head",
    "_handshake",
    "_install_match_log",
    "_latest_turn",
    "_log_peer_scent_model",
    "_play_match",
    "_play_subgame",
    "_poll_agreement",
    "_poll_deque",
    "_poll_turn",
    "_prep_claim_answer",
    "_refine_disputed_trail",
    "_run_turns",
    "_send_done_control",
    "_save_opponent_profile",
    "_self_test",
    "_settle",
    "_start_servers",
    "_t",
    "_to_wire_cell",
    "_wait_port",
    "_wire_session_class",
    "_write_result",
    "apply_runtime_config",
    "main",
]

if __name__ == "__main__":
    sys.exit(main())
