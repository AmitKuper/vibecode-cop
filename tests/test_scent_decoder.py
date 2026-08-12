"""The wire-scent inverse must be exact, or the sighted policies are built on sand.

These tests pin the one claim everything else rests on: the negotiated
``multiplicative_book_v1`` accumulation is invertible, so the opponent's cell can be
recovered from the clamped field the peer transmits. They deliberately reproduce the wire law
from ``RulesEngine`` rather than calling the decoder's own helpers, so a change to either
side breaks the test instead of cancelling out.
"""

from __future__ import annotations

import os
import random

import numpy as np
import pytest

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rules_engine import RulesEngine
from cop_worker.scent_decoder import EmitterDecoder
from tests.helpers_scent_decoder import GRID, _wire_step


def test_kernel_ring_at_dist_sq_8_can_never_saturate() -> None:
    """The property that makes the clamp invertible even on a fully saturated board."""
    kernel = RulesEngine._SCENT_KERNEL
    assert kernel[8] == pytest.approx(0.04)
    # Worst case: the cell was already at the clamp ceiling last step.
    assert 0.9 * 0.9 + kernel[8] < 0.9


def test_decoder_recovers_emitter_exactly_over_full_games() -> None:
    rng = random.Random(20260809)
    steps = exact = 0
    for _ in range(25):
        field = np.zeros((GRID, GRID))
        decoder = EmitterDecoder(GRID)
        pos = (rng.randrange(GRID), rng.randrange(GRID))
        for _turn in range(35):
            dx, dy = rng.choice([(0, 1), (0, -1), (1, 0), (-1, 0), (0, 0)])
            pos = (
                min(GRID - 1, max(0, pos[0] + dx)),
                min(GRID - 1, max(0, pos[1] + dy)),
            )
            field = _wire_step(field, pos)
            assert decoder.decode_argmax(field.tolist()) == pos
            steps += 1
            exact += 1
    assert exact == steps


def test_decoder_survives_peer_side_rounding() -> None:
    """``rounding_decimals`` is ``null`` in our profile but a peer may still round to 4."""
    field = np.zeros((GRID, GRID))
    decoder = EmitterDecoder(GRID)
    pos = (2, 3)
    for _turn in range(12):
        field = _wire_step(field, pos)
        rounded = [[round(v, 4) for v in row] for row in field.tolist()]
        assert decoder.decode_argmax(rounded) == pos
        pos = (min(GRID - 1, pos[0] + 1), pos[1])


def test_unknown_field_degrades_to_uniform_not_to_a_confident_guess() -> None:
    """A peer whose arithmetic differs from ours must yield 'no information'."""
    decoder = EmitterDecoder(GRID)
    # Values no book emission can produce from a zero field.
    bogus = [[0.137] * GRID for _ in range(GRID)]
    posterior = decoder.decode(bogus)
    assert posterior == pytest.approx(np.full((GRID, GRID), 1.0 / (GRID * GRID)))
    assert decoder.decode_argmax(bogus) is None


def test_empty_first_frame_is_uniform() -> None:
    decoder = EmitterDecoder(GRID)
    assert decoder.decode_argmax([[0.0] * GRID for _ in range(GRID)]) is None


def test_reset_prevents_cross_episode_leakage() -> None:
    """The decoder differences consecutive frames, so stale state corrupts a new game."""
    field = np.zeros((GRID, GRID))
    decoder = EmitterDecoder(GRID)
    for _ in range(10):
        field = _wire_step(field, (6, 6))
    decoder.decode(field.tolist())

    decoder.reset()
    fresh = _wire_step(np.zeros((GRID, GRID)), (0, 0))
    assert decoder.decode_argmax(fresh.tolist()) == (0, 0)


def test_tensor_layout_is_unchanged_and_channel_carries_the_posterior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decoding must not resize the observation: old checkpoints stay loadable."""
    import importlib

    import cop_worker.rl.local_obs_adapter as adapter
    import cop_worker.rl.obs_mode as obs_mode

    monkeypatch.setitem(os.environ, "COPTHIEF_DECODED_SCENT", "1")
    importlib.reload(obs_mode)
    importlib.reload(adapter)
    try:
        # Prime the decoder with the real accumulation sequence: it differences consecutive
        # frames, so replaying one frame repeatedly is an inconsistent history (and correctly
        # decodes to "no information").
        decoder = EmitterDecoder(GRID)
        field = np.zeros((GRID, GRID))
        for _ in range(8):
            field = _wire_step(field, (4, 1))
            decoder.decode(field.tolist())
        # The 9th frame is left undecoded: local_obs_to_tensor consumes it below.
        field = _wire_step(field, (4, 1))
        obs = LocalObservation(
            own_position=(0, 0),
            own_barriers_remaining=14,
            known_barriers=[],
            opponent_scent=field.tolist(),
            last_hint="",
            step=9,
            gamelet=1,
            grid_size=GRID,
        )
        vector = adapter.local_obs_to_tensor(obs, BeliefState.uniform(GRID, step=9), decoder)
        assert vector.shape == (adapter.obs_tensor_shape(GRID),) == (201,)
        scent_channel = vector[2 * GRID * GRID : 3 * GRID * GRID]
        assert int(scent_channel.argmax()) == 1 * GRID + 4  # (x=4, y=1)
        assert int((scent_channel > 1e-9).sum()) == 1
        # Belief channel mirrors the posterior instead of the frozen uniform prior.
        belief_channel = vector[3 * GRID * GRID : 4 * GRID * GRID]
        assert int(belief_channel.argmax()) == 1 * GRID + 4
    finally:
        monkeypatch.delitem(os.environ, "COPTHIEF_DECODED_SCENT", raising=False)
        importlib.reload(obs_mode)
        importlib.reload(adapter)


def test_decoding_is_off_by_default() -> None:
    """No env var => byte-identical behaviour to before this feature existed."""
    from cop_worker.rl.obs_mode import decoded_scent_enabled

    assert os.environ.get("COPTHIEF_DECODED_SCENT", "") != "1"
    assert decoded_scent_enabled() is False
