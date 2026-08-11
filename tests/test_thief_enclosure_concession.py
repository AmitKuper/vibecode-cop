"""The thief must SAY the endings only it can see (rules 46/47), or the game forks.

imreeyal §3.14 / kit WARNINGS §5c: a barrier on the thief's cell, or a thief with no
orthogonal escape, is a capture visible ONLY to the thief. A thief that plays on claims a
survival the cop's audit scores as a capture — two honest teams, contradictory reports,
rule 35 zeroes both. These tests pin (a) the detection logic, (b) that the serving loop
actually tracks peer barriers and sends the concession — the call sites, not just the
methods (the episode-reset lesson).
"""

from __future__ import annotations

import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _mover(role: str, pos: list[int], barriers: list[list[int]], grid: int = 7):
    """RLMover without loading a trained policy (unit-test the logic, not the net)."""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from live_match_ref3 import RLMover

    m = RLMover.__new__(RLMover)
    m.role = role
    m.grid = grid
    m.pos = list(pos)
    m.barriers = [list(b) for b in barriers]
    return m


class TestSelfCaptureCheck:
    def test_rule46_barrier_on_our_cell(self) -> None:
        assert _mover("thief", [3, 3], [[3, 3]]).self_capture_check() == "rule46"

    def test_rule47_corner_enclosure(self) -> None:
        # Corner (0,0): N/W are off-board, E/S barriered — STAY does not rescue.
        assert _mover("thief", [0, 0], [[1, 0], [0, 1]]).self_capture_check() == "rule47"

    def test_rule47_full_enclosure_mid_board(self) -> None:
        m = _mover("thief", [3, 3], [[3, 2], [3, 4], [2, 3], [4, 3]])
        assert m.self_capture_check() == "rule47"

    def test_one_open_neighbour_is_no_capture(self) -> None:
        assert _mover("thief", [3, 3], [[3, 2], [3, 4], [2, 3]]).self_capture_check() is None

    def test_cop_role_never_self_captures(self) -> None:
        assert _mover("police", [3, 3], [[3, 3]]).self_capture_check() is None


class TestObservePeerBarrier:
    def test_thief_tracks_cop_barrier(self) -> None:
        m = _mover("thief", [3, 3], [])
        m.observe_peer_barrier([2, 3])
        assert m.barriers == [[2, 3]]

    def test_duplicates_and_out_of_board_and_junk_ignored(self) -> None:
        m = _mover("thief", [3, 3], [[2, 3]])
        m.observe_peer_barrier([2, 3])
        m.observe_peer_barrier([9, 9])
        m.observe_peer_barrier(None)
        m.observe_peer_barrier("2,3")
        assert m.barriers == [[2, 3]]

    def test_cop_role_ignores_peer_barrier_field(self) -> None:
        # A thief-sent barrier is not a legal turn of either role (kit refuses it);
        # our cop's list holds OUR placements only and must not absorb one.
        m = _mover("police", [3, 3], [])
        m.observe_peer_barrier([2, 3])
        assert m.barriers == []


class TestServingLoopCallSites:
    """The methods above are worthless if the match loop never calls them."""

    def _subgame_source(self) -> str:
        import sys

        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import live_match_ref3

        # The turn loop (barrier tracking, self-check, concession, audit submission)
        # lives in _run_turns since the ref3_match decomposition; the facade re-exports
        # it precisely for this pin.
        return inspect.getsource(live_match_ref3._run_turns)

    def test_loop_tracks_peer_barriers_and_self_checks(self) -> None:
        src = self._subgame_source()
        assert "observe_peer_barrier" in src
        assert "self_capture_check" in src

    def test_concession_is_a_real_turn_before_the_audit(self) -> None:
        src = self._subgame_source()
        concession_at = src.index("self_capture_check")
        audit_at = src.index("send_audit")
        assert concession_at < audit_at
        # The concession turn carries caught=true and an ADVANCING field (a real STAY
        # turn, never an empty grid — kit dogfood finding 4).
        window = src[concession_at : concession_at + 1600]
        assert '"caught": True' in window
        assert "our_smell_grid()" in window
        assert '"move": "STAY"' in window
