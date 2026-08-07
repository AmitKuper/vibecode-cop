"""Test game_uid derivation against conformance vectors."""

import hashlib
import json
from pathlib import Path


def load_vector(filename):
    """Load a conformance vector JSON file."""
    path = Path(__file__).parent.parent.parent / "conformance" / "vectors" / filename
    return json.loads(path.read_text())


def test_game_uid_derivation_matches_vectors():
    """game_uid derivation must match conformance vectors exactly."""
    cases = load_vector("game_uid_derivation.json")["cases"]
    for case in cases:
        group_ids = sorted(case["group_ids"])
        data = "".join(group_ids) + case["game_id"]
        result = hashlib.sha256(data.encode()).hexdigest()
        assert result == case["expected_uid"], f"game_uid mismatch for case {case.get('id', '?')}"
