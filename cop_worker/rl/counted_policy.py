"""Checksum-verified counted inference for supported RL architectures.

Public facade: the Dueling-DDQN network/adapter/loader implementation lives in
``cop_worker.rl.dueling_policy`` and is re-exported here unchanged; the manifest
dispatch (``load_counted_policy``) and the serving observation-mode guard stay in
this module so tests that patch attributes on it keep landing.
"""

from __future__ import annotations

from pathlib import Path

SUPPORTED_GRID_SIZE = 7


class CountedPolicyLoadError(RuntimeError):
    """Raised when a manifest-selected counted policy cannot be loaded safely."""


from cop_worker.rl.dueling_policy import (  # noqa: E402  (error class must exist first)
    DuelingDoubleQNetwork,
    DuelingDoubleQRolePolicy,
    _load_dueling_policy,
)

__all__ = [
    "SUPPORTED_GRID_SIZE",
    "CountedPolicyLoadError",
    "DuelingDoubleQNetwork",
    "DuelingDoubleQRolePolicy",
    "_guard_serving_obs_mode",
    "_load_dueling_policy",
    "load_counted_policy",
]


def _guard_serving_obs_mode(entry, role: str) -> None:
    """Refuse to serve a policy whose SERVING observation a stray env flag would alter.

    Two switches change what the net reads at inference time (not merely in training):
    ``COPTHIEF_DECODED_SCENT`` (the decoder inverts the scent channels inside
    ``local_obs_to_tensor``) and ``COPTHIEF_SCENT_MODEL`` (which physics our emission
    and the training fields ran). A live value that contradicts what the manifest
    records for the artifact means the net reads inputs it never trained on — the
    exact silent-regression shape this project has shipped before. Manifests written
    before the switches existed read as book-model / decoder-off.
    """
    from cop_worker.rl.obs_mode import decoded_scent_enabled, scent_model

    recorded = dict(getattr(entry, "obs_mode", None) or {})
    want_decoded = bool(recorded.get("decoded_scent", False))
    # decoded_scent is manifest-driven per policy (the wrapper self-enables when the
    # entry records decoded_scent=true), so a process-wide env flag is never needed to
    # serve — and the only DANGEROUS combination is the env forcing the decoder onto
    # an artifact that never trained on it.
    if decoded_scent_enabled() and not want_decoded:
        raise CountedPolicyLoadError(
            f"COPTHIEF_DECODED_SCENT=1 but the {role} manifest entry records "
            f"decoded_scent=False — a stray env flag would silently change the serving "
            f"observation; unset it (decoded artifacts self-enable from the manifest)"
        )
    want_model = recorded.get("scent_model", "multiplicative_book_v1")
    if scent_model() != want_model:
        raise CountedPolicyLoadError(
            f"COPTHIEF_SCENT_MODEL resolves to {scent_model()!r} but the {role} manifest "
            f"entry records scent_model={want_model!r} — the net would read a field it "
            f"never trained on; align the locked model and the promoted artifact"
        )


def load_counted_policy(manifest_path: str | Path, role: str):
    """Load the manifest-selected recurrent or dueling-DDQN counted policy."""
    from cop_worker.rl.model_schema import load_manifest

    manifest_path = Path(manifest_path)
    entries = load_manifest(str(manifest_path))
    if role not in entries:
        raise CountedPolicyLoadError(f"manifest has no {role!r} policy")
    entry = entries[role]
    compatible, reason = entry.is_compatible(role, SUPPORTED_GRID_SIZE)
    if not compatible:
        raise CountedPolicyLoadError(reason)
    _guard_serving_obs_mode(entry, role)
    if entry.algorithm == "RecurrentA2C-GRU":
        from cop_worker.rl.recurrent_policy import load_recurrent_policy

        policy = load_recurrent_policy(manifest_path, role)
    elif entry.algorithm == "DuelingDoubleDQN":
        policy = _load_dueling_policy(manifest_path, entry, role)
    else:
        policy = None
    if policy is not None:
        from cop_worker.rl.live_belief import LiveBeliefPolicy, wants_live_belief

        if wants_live_belief(entry):
            # Manifest-gated: only artifacts trained on the live filter get it.
            policy = LiveBeliefPolicy(policy, role)
        return policy
    raise CountedPolicyLoadError(f"unsupported counted algorithm {entry.algorithm!r}")
