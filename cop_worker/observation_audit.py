"""Observation audit: detect hidden opponent coordinate leaks."""

from __future__ import annotations


def audit_observation_for_leaks(
    obs: dict,
    own_role: str,
    own_position: tuple,
    opponent_true_position: tuple,
) -> list[str]:
    """Return list of leak paths if hidden opponent coordinate is found in obs.

    Args:
        obs: The observation dict passed to RL / strategy.
        own_role: "cop" or "thief" — the role of the agent receiving obs.
        own_position: The agent's own true position (not a leak).
        opponent_true_position: The opponent's true position (must NOT appear in obs).

    Returns:
        List of strings describing leak paths; empty list means clean.
    """
    leaks = []

    # Check grid_state sub-dict for explicit position keys
    if "grid_state" in obs:
        gs = obs["grid_state"]
        opp_key = "cop_position" if own_role == "thief" else "thief_position"
        if opp_key in gs:
            leaks.append(f"grid_state.{opp_key} exposes hidden coordinate")

    return leaks
