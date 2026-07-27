"""Tests that commitment payloads include all required fields including gamelet."""

import hashlib
import json

import pytest

from agent.mcp.crypto import create_commitment, verify_commitment


class TestCommitmentPayloadFields:
    def test_create_commitment_includes_gamelet(self):
        h_commit, nonce = create_commitment(
            game_id="g001",
            step=1,
            role="cop",
            state_hash="abc",
            move="N",
            hint="Moving north",
            intent="truth",
            gamelet=3,
        )
        assert len(h_commit) == 64

    def test_verify_commitment_requires_matching_gamelet(self):
        h_commit, nonce = create_commitment(
            game_id="g001", step=1, role="cop",
            state_hash="abc", move="N", hint="hint", intent="truth", gamelet=2,
        )
        # Same gamelet verifies OK
        assert verify_commitment(
            h_commit=h_commit, game_id="g001", step=1, role="cop",
            state_hash="abc", move="N", hint="hint", intent="truth",
            nonce=nonce, gamelet=2,
        )

    def test_wrong_gamelet_fails_verification(self):
        h_commit, nonce = create_commitment(
            game_id="g001", step=1, role="cop",
            state_hash="abc", move="N", hint="hint", intent="truth", gamelet=1,
        )
        # Different gamelet must NOT verify
        assert not verify_commitment(
            h_commit=h_commit, game_id="g001", step=1, role="cop",
            state_hash="abc", move="N", hint="hint", intent="truth",
            nonce=nonce, gamelet=2,
        )

    def test_default_gamelet_is_1(self):
        h1, n1 = create_commitment(
            game_id="g001", step=1, role="cop",
            state_hash="abc", move="N", hint="hint", intent="truth",
        )
        h2, n2 = create_commitment(
            game_id="g001", step=1, role="cop",
            state_hash="abc", move="N", hint="hint", intent="truth", gamelet=1,
        )
        # Both default to gamelet=1; commits will differ only because of different nonces
        # But verify should work cross-format:
        assert verify_commitment(
            h_commit=h1, game_id="g001", step=1, role="cop",
            state_hash="abc", move="N", hint="hint", intent="truth",
            nonce=n1, gamelet=1,
        )

    def test_all_required_fields_present_in_payload(self):
        """Verify that the commitment hash changes when gamelet changes (field is included)."""
        h1, n = create_commitment(
            game_id="g001", step=1, role="cop",
            state_hash="abc", move="N", hint="hint", intent="truth", gamelet=1,
        )
        # Reconstruct what gamelet=2 would hash to (using same nonce is impossible,
        # but we can check that h1 doesn't verify with gamelet=2)
        assert not verify_commitment(
            h_commit=h1, game_id="g001", step=1, role="cop",
            state_hash="abc", move="N", hint="hint", intent="truth",
            nonce=n, gamelet=2,
        )
